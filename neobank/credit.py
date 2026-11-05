"""Credit decisioning: scorecard probability of default, reason codes, and an audit record.

Reason codes come from the scorecard's additive structure. Each feature's contribution to the
default log-odds is its coefficient times its standardized value, measured against the average
applicant. The features that push risk up the most become the reasons.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .features import CREDIT_FEATURES, CreditApplicant, credit_vector
from .ml.registry import ModelRegistry
from .models import DecisionLog

REASON_TEXT: dict[str, str] = {
    "log_income": "Income is low relative to the applicant pool",
    "debt_to_income": "Monthly debt payments are high relative to income",
    "revolving_utilization": "Revolving credit utilization is high",
    "delinquencies_24m": "Recent late payments on file in the last 24 months",
    "credit_history_years": "Short credit history",
    "recent_inquiries_6m": "Multiple recent credit inquiries",
}

APPROVE, REFER, DECLINE = "APPROVE", "REFER", "DECLINE"
MAX_LOAN_SHARE_OF_INCOME = 0.5


@dataclass(frozen=True)
class CreditResult:
    outcome: str
    probability_of_default: float
    approved_amount_minor: int
    reasons: tuple[str, ...]
    model_version: str


def top_reason_codes(pipeline, features: list[float], k: int = 3) -> list[str]:
    scaler, classifier = pipeline.steps[0][1], pipeline.steps[-1][1]
    standardized = scaler.transform([features])[0]
    contributions = classifier.coef_[0] * standardized
    order = np.argsort(-contributions)
    return [REASON_TEXT[CREDIT_FEATURES[i]] for i in order[:k] if contributions[i] > 0]


def assess_application(
    session: Session,
    registry: ModelRegistry,
    settings: Settings,
    *,
    applicant_id: str,
    applicant: CreditApplicant,
    requested_minor: int,
) -> CreditResult:
    features = credit_vector(applicant)
    model = registry.get("credit")
    pd = float(model.model.predict_proba([features])[0][1])

    if pd < settings.credit_approve_below_pd:
        outcome = APPROVE
    elif pd > settings.credit_decline_above_pd:
        outcome = DECLINE
    else:
        outcome = REFER  # human underwriter review

    approved = 0
    reasons: list[str] = []
    if outcome == APPROVE:
        cap = int(applicant.annual_income_minor * MAX_LOAN_SHARE_OF_INCOME)
        approved = min(requested_minor, cap)
    else:
        reasons = top_reason_codes(model.model, features)

    session.add(
        DecisionLog(
            kind="credit",
            subject_id=applicant_id,
            model_version=model.version,
            outcome=outcome,
            score=pd,
            # Only model features are stored, not raw applicant data, to minimize retained PII.
            inputs={"features": dict(zip(CREDIT_FEATURES, features)), "requested_minor": requested_minor},
            reasons=reasons,
            created_at=utcnow(),
        )
    )
    session.commit()
    return CreditResult(
        outcome=outcome,
        probability_of_default=pd,
        approved_amount_minor=approved,
        reasons=tuple(reasons),
        model_version=model.version,
    )
