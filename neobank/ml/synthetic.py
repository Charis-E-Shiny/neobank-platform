"""Synthetic data generators.

These exist so the project runs end to end without private data. The generative
assumptions are documented in docs/MODEL_CARDS.md. Models trained on this data demonstrate
the pipeline. They are not calibrated for any real portfolio.
"""

from __future__ import annotations

import numpy as np

from ..features import CREDIT_FEATURES, FRAUD_FEATURES, CreditApplicant, FraudContext, credit_vector, fraud_vector


def _sample_fraud_context(rng: np.random.Generator, fraud: bool) -> FraudContext:
    amount = int(rng.lognormal(8.6 if fraud else 6.0, 1.0)) + 1
    mean_30d = float(rng.lognormal(6.0, 0.6))
    if fraud:
        hour = int(rng.integers(0, 6)) if rng.random() < 0.5 else int(rng.integers(0, 24))
        channel = str(rng.choice(["online", "atm", "pos"], p=[0.7, 0.2, 0.1]))
        new_device = rng.random() < 0.6
        txns_last_hour = int(rng.poisson(4))
        high_risk = rng.random() < 0.25
        extra_spend = float(rng.lognormal(7.5, 0.5))
    else:
        hour = int(rng.integers(0, 24))
        channel = str(rng.choice(["online", "atm", "pos"], p=[0.3, 0.05, 0.65]))
        new_device = rng.random() < 0.05
        txns_last_hour = int(rng.poisson(0.3))
        high_risk = rng.random() < 0.01
        extra_spend = 0.0
    spend_24h = int(amount * rng.uniform(1, 4) + extra_spend)
    return FraudContext(
        amount_minor=amount,
        hour_utc=hour,
        channel=channel,
        new_device=bool(new_device),
        txns_last_hour=txns_last_hour,
        spend_last_24h_minor=spend_24h,
        mean_30d_minor=mean_30d,
        high_risk_mcc=bool(high_risk),
    )


def fraud_dataset(n: int, seed: int, fraud_rate: float = 0.02) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    labels = (rng.random(n) < fraud_rate).astype(int)
    X = np.empty((n, len(FRAUD_FEATURES)))
    for i, label in enumerate(labels):
        X[i] = fraud_vector(_sample_fraud_context(rng, bool(label)))
    return X, labels


def credit_dataset(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Defaults follow a logistic model over the same features the scorecard sees."""
    rng = np.random.default_rng(seed)
    X = np.empty((n, len(CREDIT_FEATURES)))
    y = np.empty(n, dtype=int)
    for i in range(n):
        income = int(rng.lognormal(13.0, 0.6))
        applicant = CreditApplicant(
            annual_income_minor=income,
            monthly_debt_minor=int(income / 12 * rng.uniform(0, 0.6)),
            revolving_utilization=float(rng.beta(2, 5)),
            delinquencies_24m=int(rng.poisson(0.3)),
            credit_history_years=float(rng.uniform(0, 25)),
            recent_inquiries_6m=int(rng.poisson(1.0)),
        )
        x = credit_vector(applicant)
        X[i] = x
        logit = -3.0 + 1.5 * x[1] + 2.0 * x[2] + 0.6 * x[3] - 0.06 * x[4] + 0.25 * x[5] - 0.3 * (x[0] - 13.0)
        p_default = 1.0 / (1.0 + np.exp(-logit))
        y[i] = int(rng.random() < p_default)
    return X, y
