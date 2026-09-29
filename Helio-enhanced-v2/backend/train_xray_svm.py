"""Train the Helio X-ray SVM models.

Expected folder layout (MURA can be arranged into this; any X-ray set works):

    <data>/
        wrist/   normal/*.png   fracture/*.png
        elbow/   normal/*.png   fracture/*.png
        hand/    normal/*.png   fracture/*.png
        ...

Usage:
    python train_xray_svm.py --data ./xray_data [--out app/ml/xray_svm.joblib]

It trains
  * one SVM that recognises the body part,
  * one fracture-vs-normal SVM per body part (plus a global fallback),
holds out 20 % of the images for testing, prints the real accuracy, and stores
those metrics in the model file so the app can show them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from app.agents.imaging_agent import DEFAULT_MODEL_PATH, NORMAL_LABEL, extract_features, load_gray

EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_PER_CLASS = 10


def make_svm(X, y):
    """RBF-SVM with probability output, C/gamma tuned by cross-validation."""
    pipe = make_pipeline(
        StandardScaler(),
        SVC(kernel="rbf", probability=True, class_weight="balanced", random_state=0),
    )
    grid = {"svc__C": [1, 10, 100], "svc__gamma": ["scale", 0.001]}
    folds = max(2, min(3, int(min(np.bincount(np.unique(y, return_inverse=True)[1])))))
    search = GridSearchCV(pipe, grid, cv=folds, n_jobs=-1)
    search.fit(X, y)
    return search.best_estimator_


def load_dataset(root: Path):
    X, part, cond = [], [], []
    for part_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for cond_dir in sorted(p for p in part_dir.iterdir() if p.is_dir()):
            label = NORMAL_LABEL if cond_dir.name.lower() in {"normal", "negative", "healthy"} else "fracture"
            for f in cond_dir.rglob("*"):
                if f.suffix.lower() not in EXTS:
                    continue
                try:
                    gray, _ = load_gray(str(f))
                    X.append(extract_features(gray))
                    part.append(part_dir.name.lower())
                    cond.append(label)
                except Exception as error:
                    print(f"skip {f}: {error}")
    return np.array(X), np.array(part), np.array(cond)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_MODEL_PATH)
    args = ap.parse_args()

    X, part, cond = load_dataset(args.data)
    if len(X) == 0:
        raise SystemExit("No images found. Check the folder layout in the file header.")
    print(f"Loaded {len(X)} images, body parts: {sorted(set(part))}")

    # ---- SVM 1: body part ------------------------------------------------
    Xtr, Xte, ytr, yte = train_test_split(X, part, test_size=0.2, stratify=part, random_state=0)
    part_model = make_svm(Xtr, ytr)
    part_acc = accuracy_score(yte, part_model.predict(Xte))
    print(f"\nBody-part SVM held-out accuracy: {part_acc:.1%}")
    print(classification_report(yte, part_model.predict(Xte), zero_division=0))
    part_model = make_svm(X, part)  # refit on everything for deployment

    # ---- SVM 2: fracture vs normal --------------------------------------
    condition_models, accs = {}, {}
    for p in sorted(set(part)):
        idx = part == p
        Xp, yp = X[idx], cond[idx]
        counts = np.unique(yp, return_counts=True)[1]
        if len(counts) < 2 or counts.min() < MIN_PER_CLASS:
            print(f"[{p}] not enough images per class, using global model")
            continue
        a, b, c, d = train_test_split(Xp, yp, test_size=0.2, stratify=yp, random_state=0)
        accs[p] = accuracy_score(d, make_svm(a, c).predict(b))
        print(f"[{p}] fracture SVM held-out accuracy: {accs[p]:.1%}")
        condition_models[p] = make_svm(Xp, yp)

    Xtr, Xte, ytr, yte = train_test_split(X, cond, test_size=0.2, stratify=cond, random_state=0)
    global_acc = accuracy_score(yte, make_svm(Xtr, ytr).predict(Xte))
    print(f"\nGlobal fracture SVM held-out accuracy: {global_acc:.1%}")
    global_model = make_svm(X, cond)

    bundle = {
        "name": "SVM (RBF) on HOG features",
        "body_part_model": part_model,
        "condition_models": condition_models,
        "condition_model_global": global_model,
        "metrics": {
            "images": int(len(X)),
            "body_part_accuracy": round(float(part_acc), 3),
            "condition_accuracy": round(float(global_acc), 3),
            "condition_accuracy_by_part": {k: round(float(v), 3) for k, v in accs.items()},
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out, compress=3)
    print(f"\nSaved model to {args.out}")


if __name__ == "__main__":
    main()
