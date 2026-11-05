from datetime import date, datetime, timedelta

import numpy as np

from neobank.aml import CTR_THRESHOLD_MINOR, triage
from neobank.ledger import TransferRecord
from neobank.monitoring import approval_rate_by_group, drift_status, psi
from neobank.reconciliation import BankLine, LedgerLine, reconcile

T0 = datetime(2026, 11, 1, 9, 0)


def _t(sender, receiver, amount, hours=0):
    return TransferRecord(sender_id=sender, receiver_id=receiver, amount_minor=amount, at=T0 + timedelta(hours=hours))


def test_structuring_pattern_is_flagged():
    just_below = int(CTR_THRESHOLD_MINOR * 0.95)
    records = [_t("smurf", f"mule-{i}", just_below, hours=i) for i in range(3)]
    result = triage(records)
    top = result[0]
    assert top.account_id == "smurf"
    assert top.features["structuring_hits"] == 3
    assert any("reporting threshold" in r for r in top.reasons)


def test_passthrough_is_flagged_within_window():
    records = [_t("source", "hub", 500_000, hours=0), _t("hub", "sink", 480_000, hours=10)]
    result = {r.account_id: r for r in triage(records)}
    assert result["hub"].features["passthrough_hits"] == 1


def test_passthrough_outside_window_is_not_flagged():
    records = [_t("source", "hub", 500_000, hours=0), _t("hub", "sink", 480_000, hours=100)]
    # The hub has no flags at all, so it is absent from the ranking entirely.
    assert "hub" not in {r.account_id for r in triage(records)}


def test_ordinary_account_is_not_flagged():
    records = [_t("alice", "bob", 2_000, hours=0), _t("bob", "carol", 15_000, hours=100)]
    assert triage(records) == []


def test_psi_is_near_zero_for_identical_samples():
    sample = np.random.default_rng(0).normal(size=5000)
    assert psi(sample, sample) < 0.01
    assert drift_status(psi(sample, sample)) == "stable"


def test_psi_detects_a_shift():
    rng = np.random.default_rng(0)
    baseline = rng.normal(0, 1, 5000)
    shifted = rng.normal(1.5, 1, 5000)
    value = psi(baseline, shifted)
    assert value > 0.25
    assert drift_status(value) == "drift"


def test_approval_rates_by_group():
    rates = approval_rate_by_group([("a", True), ("a", False), ("b", True), ("b", True)])
    assert rates == {"a": 0.5, "b": 1.0}


def test_reconciliation_matches_on_amount_date_and_description():
    bank = [
        BankLine(id="b1", date=date(2026, 11, 3), amount_minor=-4_500, description="UPI SWIGGY ORDER 7781"),
        BankLine(id="b2", date=date(2026, 11, 4), amount_minor=-999, description="NETFLIX.COM"),
        BankLine(id="b3", date=date(2026, 11, 4), amount_minor=-1_200, description="Unknown merchant"),
    ]
    ledger_lines = [
        LedgerLine(reference="l1", date=date(2026, 11, 3), amount_minor=-4_500, description="Swiggy food order"),
        LedgerLine(reference="l2", date=date(2026, 11, 4), amount_minor=-999, description="Netflix subscription"),
        LedgerLine(reference="l3", date=date(2026, 11, 9), amount_minor=-300, description="Coffee"),
    ]
    result = reconcile(bank, ledger_lines)
    matched = {m.bank_id: m.reference for m in result.matched}
    assert matched == {"b1": "l1", "b2": "l2"}
    assert result.unmatched_bank == ["b3"]
    assert result.unmatched_ledger == ["l3"]


def test_reconciliation_is_one_to_one():
    bank = [
        BankLine(id="b1", date=date(2026, 11, 3), amount_minor=-500, description="Cafe"),
        BankLine(id="b2", date=date(2026, 11, 3), amount_minor=-500, description="Cafe"),
    ]
    ledger_lines = [LedgerLine(reference="l1", date=date(2026, 11, 3), amount_minor=-500, description="Cafe")]
    result = reconcile(bank, ledger_lines)
    assert len(result.matched) == 1
    assert len(result.unmatched_bank) == 1
