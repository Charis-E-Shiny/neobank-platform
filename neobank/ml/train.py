"""Train and persist model artifacts.

Usage:
    python -m neobank.ml.train --model-dir models

Each artifact is a joblib bundle with the fitted model, a version string, and holdout metrics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..features import CREDIT_FEATURES, FRAUD_FEATURES
from .synthetic import credit_dataset, fraud_dataset

FRAUD_VERSION = "fraud-hgb-isotonic/2026.11.1"
CREDIT_VERSION = "credit-logreg/2026.11.1"


def train_fraud(seed: int = 7) -> dict[str, Any]:
    X, y = fraud_dataset(n=60_000, seed=seed)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=seed)
    base = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=31, random_state=seed)
    # Isotonic calibration so a score of 0.30 means roughly a 30% chance of fraud.
    model = CalibratedClassifierCV(base, method="isotonic", cv=3)
    model.fit(X_tr, y_tr)
    p = model.predict_proba(X_te)[:, 1]
    return {
        "model": model,
        "version": FRAUD_VERSION,
        "metrics": {
            "holdout_pr_auc": float(average_precision_score(y_te, p)),
            "holdout_roc_auc": float(roc_auc_score(y_te, p)),
            "holdout_brier": float(brier_score_loss(y_te, p)),
            "train_fraud_rate": float(y.mean()),
            "features": list(FRAUD_FEATURES),
            "data": "synthetic",
        },
    }


def train_credit(seed: int = 11) -> dict[str, Any]:
    X, y = credit_dataset(n=40_000, seed=seed)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=seed)
    # Logistic regression is the standard scorecard form: additive, auditable, and easy to
    # turn into reason codes (see neobank/credit.py).
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    model.fit(X_tr, y_tr)
    p = model.predict_proba(X_te)[:, 1]
    return {
        "model": model,
        "version": CREDIT_VERSION,
        "metrics": {
            "holdout_roc_auc": float(roc_auc_score(y_te, p)),
            "holdout_brier": float(brier_score_loss(y_te, p)),
            "train_default_rate": float(y.mean()),
            "features": list(CREDIT_FEATURES),
            "data": "synthetic",
        },
    }


TRAINERS: dict[str, Callable[..., dict[str, Any]]] = {
    "fraud": train_fraud,
    "credit": train_credit,
}


def train_all(model_dir: Path) -> dict[str, dict[str, Any]]:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, Any]] = {}
    for name, trainer in TRAINERS.items():
        bundle = trainer()
        joblib.dump(bundle, model_dir / f"{name}.joblib")
        summary[name] = {"version": bundle["version"], **bundle["metrics"]}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Neobank model artifacts.")
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    args = parser.parse_args()
    print(json.dumps(train_all(args.model_dir), indent=2))


if __name__ == "__main__":
    main()
