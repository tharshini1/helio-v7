"""Helio Imaging Agent - SVM based X-ray reader.

A nurse uploads an X-ray; this agent reads it with two classic machine-learning
models (Support Vector Machines) that run locally. No external API is called.

Pipeline
--------
1. Pre-processing: grayscale -> resize -> contrast equalisation (CLAHE).
2. Features: HOG (edge / bone-contour texture) + a coarse intensity histogram.
3. SVM #1 (body part): *what is in the X-ray* - e.g. wrist, elbow, hand.
4. SVM #2 (condition): *what has happened* - fracture (break) vs normal, using
   the model trained for that body part (falls back to a global model).
5. Confidence: probability from each SVM (Platt scaling); the overall score is
   the product of the two, so it is only high when BOTH stages are sure.

Safety behaviour
----------------
* The agent NEVER invents a result. If no trained model file exists, or the
  image does not look like an X-ray, it returns ``available=False`` /
  low confidence with a clear message so a doctor reads the image manually.
* Output is decision support only; a doctor must review it.
* Confidence comes from SVM probability calibration. It is only as good as the
  training data; the held-out accuracy measured at training time is reported
  alongside it (``model_metrics``).

Train the models with ``python train_xray_svm.py --data <folder>``.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

try:
    import joblib
    from PIL import Image
    from skimage import exposure
    from skimage.feature import hog
    from skimage.transform import resize
except ImportError:  # pragma: no cover
    joblib = None
    Image = None

from app.core.config import settings

DISCLAIMER = (
    "AI-assisted preliminary reading for clinical decision support only. "
    "It is not a diagnosis and must be reviewed by a qualified doctor or radiologist."
)

ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

IMG_SIZE = 128
# Below this the image is not recognised as any trained body part.
MIN_BODY_PART_CONFIDENCE = 0.45
# Label the model uses for an unbroken bone.
NORMAL_LABEL = "normal"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "ml" / "xray_svm.joblib"


def detect_mime(data: bytes) -> str | None:
    """Identify the real image type from magic bytes (never trust the filename)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ----------------------------------------------------------------------
# Feature extraction (shared with train_xray_svm.py so train == inference)
# ----------------------------------------------------------------------
def extract_features(gray: np.ndarray) -> np.ndarray:
    """gray: 2-D float array in [0, 1]. Returns one 1-D feature vector."""
    img = resize(gray, (IMG_SIZE, IMG_SIZE), anti_aliasing=True)
    img = exposure.equalize_adapthist(img, clip_limit=0.02)
    hog_vec = hog(
        img,
        orientations=9,
        pixels_per_cell=(16, 16),
        cells_per_block=(2, 2),
        block_norm="L2-Hys",
    )
    hist, _ = np.histogram(img, bins=16, range=(0.0, 1.0), density=True)
    return np.concatenate([hog_vec, hist]).astype(np.float32)


def load_gray(source) -> tuple[np.ndarray, float]:
    """Load an image (path or bytes) -> (gray float array, colourfulness 0..1)."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    with Image.open(source) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    gray = rgb.mean(axis=2)
    colourfulness = float(np.abs(rgb - gray[..., None]).mean())
    return gray, colourfulness


# ----------------------------------------------------------------------
class ImagingResult(BaseModel):
    """Structured report handed to the doctor."""

    available: bool = Field(default=True, description="False when no AI reading could be produced.")
    body_part: str = Field(default="", description="What the X-ray shows (limb / bone region).")
    body_part_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    condition: str = Field(default="", description="What has happened: FRACTURE or NORMAL.")
    condition_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    problem: str = Field(description="Short phrase, e.g. 'Possible fracture of the wrist'.")
    reason: str = Field(description="How the reading was reached.")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall confidence 0.0-1.0.")
    findings: list[str] = Field(default_factory=list)
    urgency: Literal["ROUTINE", "URGENT", "CRITICAL"] = "ROUTINE"
    image_quality: Literal["GOOD", "LIMITED", "POOR", "NOT_A_MEDICAL_IMAGE"] = "GOOD"
    recommended_action: str = ""
    model: str = ""
    model_metrics: dict = Field(default_factory=dict)
    disclaimer: str = DISCLAIMER


class ImagingAgent:
    """SVM based reader for X-ray images."""

    def __init__(self, model_path: str | Path | None = None):
        self.model_path = Path(model_path or getattr(settings, "XRAY_MODEL_PATH", "") or DEFAULT_MODEL_PATH)
        self.bundle = None
        self.load_error = ""
        self._load()

    def _load(self):
        if joblib is None:
            self.load_error = "scikit-learn / scikit-image / Pillow are not installed on the server"
            return
        if not self.model_path.exists():
            self.load_error = (
                "no trained X-ray SVM model was found "
                f"({self.model_path.name}). Train one with train_xray_svm.py"
            )
            return
        try:
            self.bundle = joblib.load(self.model_path)
        except Exception as error:  # pragma: no cover
            self.load_error = f"the SVM model file could not be loaded ({str(error)[:100]})"

    # ------------------------------------------------------------------
    def analyse(self, image_bytes: bytes, mime_type: str, test_type: str, patient) -> ImagingResult:
        if self.bundle is None:
            return self._unavailable(
                f"AI X-ray analysis is not available: {self.load_error}. "
                "The image is saved; please review it manually."
            )
        try:
            return self._svm_read(image_bytes)
        except Exception as error:
            print(f"[Imaging Agent] analysis failed: {error}")
            return self._unavailable(
                f"AI X-ray analysis failed ({str(error)[:160]}). "
                "The image is saved; please review it manually."
            )

    # ------------------------------------------------------------------
    def _svm_read(self, image_bytes: bytes) -> ImagingResult:
        gray, colourfulness = load_gray(image_bytes)
        model_name = self.bundle.get("name", "SVM (RBF) HOG")
        metrics = self.bundle.get("metrics", {})

        # An X-ray is grayscale. A strongly coloured picture is not one.
        if colourfulness > 0.08 or gray.std() < 0.03:
            return ImagingResult(
                available=True,
                problem="Not an X-ray image",
                reason="The picture is strongly coloured or has almost no contrast, so it does not look like an X-ray.",
                confidence=0.0,
                findings=[],
                image_quality="NOT_A_MEDICAL_IMAGE",
                recommended_action="Upload a clear grayscale X-ray image.",
                model=model_name,
                model_metrics=metrics,
            )

        features = extract_features(gray).reshape(1, -1)

        # --- SVM 1: which body part -------------------------------------
        part_model = self.bundle["body_part_model"]
        part_probs = part_model.predict_proba(features)[0]
        order = np.argsort(part_probs)[::-1]
        part = str(part_model.classes_[order[0]])
        part_conf = float(part_probs[order[0]])
        runner_up = str(part_model.classes_[order[1]]) if len(order) > 1 else None

        if part_conf < MIN_BODY_PART_CONFIDENCE:
            return ImagingResult(
                available=True,
                body_part="unidentified",
                body_part_confidence=round(part_conf, 2),
                problem="Body part could not be identified",
                reason=(
                    f"The body-part SVM was not sure what this X-ray shows "
                    f"(best guess '{part}' at {part_conf:.0%}). It may be a body part "
                    "the model was not trained on, or a poor-quality image."
                ),
                confidence=round(part_conf, 2),
                findings=[],
                image_quality="LIMITED",
                recommended_action="Manual review by a doctor or radiologist.",
                model=model_name,
                model_metrics=metrics,
            )

        # --- SVM 2: what has happened (fracture / normal) ---------------
        cond_models = self.bundle.get("condition_models", {})
        cond_model = cond_models.get(part) or self.bundle.get("condition_model_global")
        if cond_model is None:
            raise RuntimeError("model file has no condition classifier")
        cond_probs = cond_model.predict_proba(features)[0]
        classes = [str(c) for c in cond_model.classes_]
        fracture_labels = [c for c in classes if c != NORMAL_LABEL]
        p_normal = float(cond_probs[classes.index(NORMAL_LABEL)]) if NORMAL_LABEL in classes else 0.0
        p_fracture = float(sum(cond_probs[classes.index(c)] for c in fracture_labels))
        is_fracture = p_fracture >= p_normal
        cond_conf = p_fracture if is_fracture else p_normal
        condition = "FRACTURE" if is_fracture else "NORMAL"

        overall = round(part_conf * cond_conf, 2)
        pretty_part = part.replace("_", " ")

        if is_fracture:
            problem = f"Possible fracture (break) of the {pretty_part}"
            urgency = "URGENT"
            action = (
                f"Doctor to review the {pretty_part} X-ray urgently; consider immobilising "
                "the limb and orthopaedic assessment."
            )
        else:
            problem = f"No fracture detected in the {pretty_part}"
            urgency = "ROUTINE"
            action = (
                "Doctor to confirm the reading. If pain persists, consider a repeat or "
                "additional view."
            )

        findings = [
            f"Body part: {pretty_part} ({part_conf:.0%} confidence)",
            f"Condition: {condition.lower()} ({cond_conf:.0%} confidence)",
        ]
        if runner_up and part_probs[order[1]] >= 0.2:
            findings.append(
                f"Body part could also be '{runner_up.replace('_', ' ')}' ({part_probs[order[1]]:.0%})"
            )
        if overall < 0.6:
            findings.append("Low overall confidence - doctor should read the image directly.")
            action = "Manual review by a doctor or radiologist. " + action

        acc = metrics.get("condition_accuracy")
        reason = (
            f"Two SVM classifiers read the image. Stage 1 recognised a {pretty_part} X-ray "
            f"({part_conf:.0%}); stage 2 judged it {condition.lower()} ({cond_conf:.0%}). "
            "Overall confidence is the product of the two."
        )
        if acc is not None:
            reason += f" On held-out test images the fracture model scored {acc:.0%} accuracy."

        return ImagingResult(
            available=True,
            body_part=part,
            body_part_confidence=round(part_conf, 2),
            condition=condition,
            condition_confidence=round(cond_conf, 2),
            problem=problem,
            reason=reason,
            confidence=overall,
            findings=findings,
            urgency=urgency,
            image_quality="GOOD" if overall >= 0.6 else "LIMITED",
            recommended_action=action,
            model=model_name,
            model_metrics=metrics,
        )

    # ------------------------------------------------------------------
    def _unavailable(self, message: str) -> ImagingResult:
        return ImagingResult(
            available=False,
            problem="AI reading unavailable",
            reason=message,
            confidence=0.0,
            findings=[],
            urgency="ROUTINE",
            image_quality="LIMITED",
            recommended_action="Manual review by a doctor or radiologist.",
            model="",
        )
