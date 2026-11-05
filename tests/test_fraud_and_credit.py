from datetime import datetime, timedelta

import pytest

from neobank import ledger
from neobank.config import Settings
from neobank.credit import assess_application
from neobank.features import CreditApplicant
from neobank.fraud import DECLINE, score_authorization
from neobank.ml.registry import ModelRegistry
from neobank.models import DecisionLog

T0 = datetime(2026, 11, 5, 12, 0, 0)


@pytest.fixture
def ctx(database, model_dir):
    session = database.session()
    ledger.create_account(session, account_id="card-1", owner_name="Carol", currency="USD")
    settings = Settings(database_url="sqlite://", model_dir=model_dir, allow_synthetic_models=False)
    registry = ModelRegistry(model_dir, allow_synthetic=False)
    yield session, registry, settings
    session.close()


def _auth(session, registry, settings, **overrides):
    params = dict(
        account_id="card-1",
        amount_minor=2_000,
        currency="USD",
        merchant="Corner Store",
        mcc="5411",
        channel="pos",
        device_id="phone-a",
        occurred_at=T0,
    )
    params.update(overrides)
    return score_authorization(session, registry, settings, **params)


def test_routine_purchase_is_approved(ctx):
    session, registry, settings = ctx
    result = _auth(session, registry, settings)
    assert result.outcome == "APPROVE"
    assert result.reasons == ()


def test_risky_pattern_scores_higher_than_routine(ctx):
    session, registry, settings = ctx
    routine = _auth(session, registry, settings)
    risky = _auth(
        session,
        registry,
        settings,
        amount_minor=900_000,
        mcc="7995",
        channel="online",
        device_id="unknown-device",
        occurred_at=T0.replace(hour=3),
    )
    assert risky.score > routine.score
    assert "Device has not been seen on this account before" in risky.reasons


def test_velocity_limit_declines_and_is_logged(ctx):
    session, registry, settings = ctx
    for minute in range(1, 21):
        _auth(session, registry, settings, occurred_at=T0 + timedelta(minutes=minute))
    result = _auth(session, registry, settings, occurred_at=T0 + timedelta(minutes=25))
    assert result.outcome == DECLINE
    assert any("attempts in the last hour" in reason for reason in result.reasons)
    assert session.query(DecisionLog).filter_by(kind="fraud").count() == 21


def test_currency_mismatch_is_rejected_before_scoring(ctx):
    from neobank.errors import CurrencyMismatchError

    session, registry, settings = ctx
    with pytest.raises(CurrencyMismatchError):
        _auth(session, registry, settings, currency="INR")


def _applicant(**overrides) -> CreditApplicant:
    base = dict(
        annual_income_minor=9_000_000,
        monthly_debt_minor=50_000,
        revolving_utilization=0.05,
        delinquencies_24m=0,
        credit_history_years=15.0,
        recent_inquiries_6m=0,
    )
    base.update(overrides)
    return CreditApplicant(**base)


def test_strong_applicant_is_approved_within_income_cap(ctx):
    session, registry, settings = ctx
    result = assess_application(
        session,
        registry,
        settings,
        applicant_id="app-1",
        applicant=_applicant(),
        requested_minor=10_000_000,
    )
    assert result.outcome == "APPROVE"
    assert result.approved_amount_minor == 4_500_000  # capped at half of annual income


def test_weak_applicant_is_declined_with_reason_codes(ctx):
    session, registry, settings = ctx
    result = assess_application(
        session,
        registry,
        settings,
        applicant_id="app-2",
        applicant=_applicant(
            annual_income_minor=1_200_000,
            monthly_debt_minor=60_000,
            revolving_utilization=0.95,
            delinquencies_24m=3,
            credit_history_years=1.0,
            recent_inquiries_6m=6,
        ),
        requested_minor=500_000,
    )
    assert result.outcome == "DECLINE"
    assert result.approved_amount_minor == 0
    assert result.reasons, "declines must carry reason codes"


def test_default_probability_rises_with_debt_to_income(ctx):
    session, registry, settings = ctx
    low = assess_application(
        session, registry, settings, applicant_id="a", applicant=_applicant(monthly_debt_minor=10_000), requested_minor=1
    )
    high = assess_application(
        session, registry, settings, applicant_id="b", applicant=_applicant(monthly_debt_minor=400_000), requested_minor=1
    )
    assert high.probability_of_default > low.probability_of_default
