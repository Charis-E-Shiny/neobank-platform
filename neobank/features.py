"""Feature definitions shared by training and serving.

Training and serving build feature vectors through these functions only. A single code path
prevents train/serve skew, one of the most common silent failures in production ML.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

FRAUD_FEATURES: tuple[str, ...] = (
    "log_amount",
    "log_ratio_to_30d_mean",
    "txns_last_hour",
    "log_spend_last_24h",
    "new_device",
    "night_time",
    "card_not_present",
    "atm",
    "high_risk_mcc",
)

CREDIT_FEATURES: tuple[str, ...] = (
    "log_income",
    "debt_to_income",
    "revolving_utilization",
    "delinquencies_24m",
    "credit_history_years",
    "recent_inquiries_6m",
)


@dataclass(frozen=True)
class FraudContext:
    amount_minor: int
    hour_utc: int
    channel: str  # "pos" | "online" | "atm"
    new_device: bool
    txns_last_hour: int
    spend_last_24h_minor: int
    mean_30d_minor: float  # 0.0 when the account has no history
    high_risk_mcc: bool


def fraud_vector(ctx: FraudContext) -> list[float]:
    ratio = ctx.amount_minor / ctx.mean_30d_minor if ctx.mean_30d_minor > 0 else 1.0
    return [
        math.log1p(ctx.amount_minor),
        math.log1p(ratio),
        float(ctx.txns_last_hour),
        math.log1p(ctx.spend_last_24h_minor),
        float(ctx.new_device),
        float(0 <= ctx.hour_utc <= 5),
        float(ctx.channel == "online"),
        float(ctx.channel == "atm"),
        float(ctx.high_risk_mcc),
    ]


@dataclass(frozen=True)
class CreditApplicant:
    annual_income_minor: int
    monthly_debt_minor: int
    revolving_utilization: float  # 0..1
    delinquencies_24m: int
    credit_history_years: float
    recent_inquiries_6m: int


def credit_vector(applicant: CreditApplicant) -> list[float]:
    # Deliberately excludes age, gender, marital status, postcode and other protected or
    # proxy attributes. See docs/MODEL_CARDS.md.
    monthly_income = applicant.annual_income_minor / 12
    dti = min(applicant.monthly_debt_minor / monthly_income, 5.0) if monthly_income > 0 else 5.0
    return [
        math.log1p(applicant.annual_income_minor),
        dti,
        min(max(applicant.revolving_utilization, 0.0), 1.0),
        float(applicant.delinquencies_24m),
        float(applicant.credit_history_years),
        float(applicant.recent_inquiries_6m),
    ]
