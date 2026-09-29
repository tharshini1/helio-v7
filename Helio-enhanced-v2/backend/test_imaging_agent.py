"""Plumbing test for the SVM imaging agent.

Uses SYNTHETIC grayscale images (not real X-rays) purely to prove that
training -> saving -> loading -> inference works and that the safety paths
behave. It says nothing about real diagnostic accuracy.
"""
import io
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.agents.imaging_agent import ImagingAgent


def _img(kind, rng):
    a = rng.normal(0.3, 0.05, (160, 160))
    if kind == "wrist":
        a[:, 60:100] += 0.4
    else:
        a[60:100, :] += 0.4
    return a


def _png(a):
    buf = io.BytesIO()
    Image.fromarray((np.clip(a, 0, 1) * 255).astype("uint8")).save(buf, "PNG")
    return buf.getvalue()


def test_pipeline(tmp_path):
    rng = np.random.default_rng(0)
    data = tmp_path / "data"
    for part in ("wrist", "elbow"):
        for cond in ("normal", "fracture"):
            d = data / part / cond
            d.mkdir(parents=True)
            for i in range(24):
                a = _img(part, rng)
                if cond == "fracture":
                    a[70:74, :] = 0.0 if part == "wrist" else a[70:74, :]
                    a[:, 78:82] = 0.0
                (d / f"{i}.png").write_bytes(_png(a))
    out = tmp_path / "m.joblib"
    subprocess.run([sys.executable, "train_xray_svm.py", "--data", str(data), "--out", str(out)], check=True)

    agent = ImagingAgent(model_path=out)
    patient = SimpleNamespace()
    r = agent.analyse(_png(_img("wrist", rng)), "image/png", "X-Ray", patient)
    assert r.available and r.body_part == "wrist"
    assert 0.0 <= r.confidence <= 1.0 and r.condition in {"FRACTURE", "NORMAL"}

    colour = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (100, 100, 3), dtype="uint8")).save(colour, "PNG")
    assert agent.analyse(colour.getvalue(), "image/png", "X-Ray", patient).image_quality == "NOT_A_MEDICAL_IMAGE"


def test_no_model_never_invents(tmp_path):
    r = ImagingAgent(model_path=tmp_path / "missing.joblib").analyse(b"x", "image/png", "X-Ray", SimpleNamespace())
    assert not r.available and r.confidence == 0.0
