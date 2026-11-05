"""Real-time card authorization: features from history, model score, hard rules, audit log."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .errors import CurrencyMismatchError
from .features import FRAUD_FEATURES, FraudContext, fraud_vector
from .ledger import get_account
from .ml.registry import ModelRegistry
from .models import CardTransaction, DecisionLog

VELOCITY_HARD_LIMIT = 20  # attempts in the trailing hour
SINGLE_TXN_HARD_LIMIT_MINOR = 5_000_000  # policy cap. Tune per product and jurisdiction.
HIGH_RISK_MCC = frozenset({"4829", "6051", "7995"})  # wire transfers, quasi-cash, gambling

APPROVE, REVIEW, DECLINE = "APPROVE", "REVIEW", "DECLINE"


@dataclass(frozen=True)
class FraudResult:
    transaction_id: int
    outcome: str
    score: float
    model_version: str
    reasons: tuple[str, ...]


def _count_and_sum(session: Session, account_id: str, since: datetime, before: datetime) -> tuple[int, int]:
    count, total = session.execute(
        select(func.count(CardTransaction.id), func.coalesce(func.sum(CardTransaction.amount_minor), 0)).where(
            CardTransaction.account_id == account_id,
            CardTransaction.occurred_at >= since,
            CardTransaction.occurred_at < before,
        )
    ).one()
    return int(count), int(total)


def _mean_amount_30d(session: Session, account_id: str, at: datetime) -> float:
    avg = session.scalar(
        select(func.avg(CardTransaction.amount_minor)).where(
            CardTransaction.account_id == account_id,
            CardTransaction.occurred_at >= at - timedelta(days=30),
            CardTransaction.occurred_at < at,
        )
    )
    return float(avg) if avg is not None else 0.0


def _device_seen_before(session: Session, account_id: str, device_id: str | None, at: datetime) -> bool:
    if not device_id:
        return False
    count = session.scalar(
        select(func.count(CardTransaction.id)).where(
            CardTransaction.account_id == account_id,
            CardTransaction.device_id == device_id,
            CardTransaction.occurred_at < at,
        )
    )
    return bool(count)


def _risk_reasons(ctx: FraudContext) -> list[str]:
    reasons = []
    if ctx.new_device:
        reasons.append("Device has not been seen on this account before")
    if 0 <= ctx.hour_utc <= 5:
        reasons.append("Transaction during unusual hours (00:00-05:59 UTC)")
    if ctx.channel == "online":
        reasons.append("Card-not-present (online) transaction")
    if ctx.mean_30d_minor > 0 and ctx.amount_minor / ctx.mean_30d_minor >= 3:
        reasons.append("Amount is at least 3x the 30-day average")
    if ctx.txns_last_hour >= 5:
        reasons.append("Elevated attempt velocity in the last hour")
    if ctx.high_risk_mcc:
        reasons.append("High-risk merchant category")
    return reasons


def score_authorization(
    session: Session,
    registry: ModelRegistry,
    settings: Settings,
    *,
    account_id: str,
    amount_minor: int,
    currency: str,
    merchant: str,
    mcc: str,
    channel: str,
    device_id: str | None = None,
    occurred_at: datetime | None = None,
) -> FraudResult:
    at = occurred_at or utcnow()
    account = get_account(session, account_id)
    if account.currency != currency:
        raise CurrencyMismatchError(f"account {account_id} holds {account.currency}, not {currency}")

    txns_last_hour, _ = _count_and_sum(session, account_id, at - timedelta(hours=1), at)
    _, prior_spend_24h = _count_and_sum(session, account_id, at - timedelta(hours=24), at)
    ctx = FraudContext(
        amount_minor=amount_minor,
        hour_utc=at.hour,
        channel=channel,
        new_device=not _device_seen_before(session, account_id, device_id, at),
        txns_last_hour=txns_last_hour,
        # Includes the current amount. The training data defines the feature the same way.
        spend_last_24h_minor=prior_spend_24h + amount_minor,
        mean_30d_minor=_mean_amount_30d(session, account_id, at),
        high_risk_mcc=mcc in HIGH_RISK_MCC,
    )
    features = fraud_vector(ctx)
    model = registry.get("fraud")
    score = float(model.model.predict_proba([features])[0][1])

    hard_reasons: list[str] = []
    if txns_last_hour >= VELOCITY_HARD_LIMIT:
        hard_reasons.append(f"More than {VELOCITY_HARD_LIMIT} attempts in the last hour")
    if amount_minor > SINGLE_TXN_HARD_LIMIT_MINOR:
        hard_reasons.append("Amount exceeds the single-transaction policy limit")

    if hard_reasons:
        outcome = DECLINE
    elif score >= settings.fraud_decline_threshold:
        outcome = DECLINE
    elif score >= settings.fraud_review_threshold:
        outcome = REVIEW
    else:
        outcome = APPROVE

    reasons = hard_reasons + _risk_reasons(ctx) if outcome != APPROVE else []

    txn = CardTransaction(
        account_id=account_id,
        amount_minor=amount_minor,
        currency=currency,
        merchant=merchant[:120],
        mcc=mcc,
        channel=channel,
        device_id=device_id,
        decision=outcome,
        fraud_score=score,
        occurred_at=at,
    )
    session.add(txn)
    session.flush()
    session.add(
        DecisionLog(
            kind="fraud",
            subject_id=account_id,
            model_version=model.version,
            outcome=outcome,
            score=score,
            inputs={"transaction_id": txn.id, "features": dict(zip(FRAUD_FEATURES, features))},
            reasons=reasons,
        )
    )
    session.commit()
    return FraudResult(
        transaction_id=txn.id,
        outcome=outcome,
        score=score,
        model_version=model.version,
        reasons=tuple(reasons),
    )
