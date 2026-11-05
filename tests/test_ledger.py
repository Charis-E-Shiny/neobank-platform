import pytest

from neobank import ledger
from neobank.errors import ConflictError, CurrencyMismatchError, InsufficientFundsError, LedgerError


@pytest.fixture
def session(database):
    s = database.session()
    yield s
    s.close()


def _accounts(session):
    ledger.create_account(session, account_id="alice", owner_name="Alice", currency="USD")
    ledger.create_account(session, account_id="bob", owner_name="Bob", currency="USD")


def test_deposit_then_transfer_moves_balance(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=10_000)
    ledger.transfer(
        session,
        reference="tx-1",
        from_account_id="alice",
        to_account_id="bob",
        amount_minor=2_500,
        currency="USD",
    )
    assert ledger.balance_minor(session, "alice") == 7_500
    assert ledger.balance_minor(session, "bob") == 2_500


def test_replaying_same_reference_is_idempotent(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=10_000)
    first = ledger.transfer(
        session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=500, currency="USD"
    )
    second = ledger.transfer(
        session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=500, currency="USD"
    )
    assert first.id == second.id
    assert ledger.balance_minor(session, "alice") == 9_500


def test_reusing_reference_for_different_payload_conflicts(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=10_000)
    ledger.transfer(
        session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=500, currency="USD"
    )
    with pytest.raises(ConflictError):
        ledger.transfer(
            session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=900, currency="USD"
        )


def test_customer_cannot_overdraw(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=1_000)
    with pytest.raises(InsufficientFundsError):
        ledger.transfer(
            session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=1_001, currency="USD"
        )
    assert ledger.balance_minor(session, "alice") == 1_000


def test_currency_mismatch_is_rejected(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=1_000)
    with pytest.raises(CurrencyMismatchError):
        ledger.transfer(
            session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=100, currency="INR"
        )


@pytest.mark.parametrize("amount", [0, -5])
def test_non_positive_amounts_are_rejected(session, amount):
    _accounts(session)
    with pytest.raises(LedgerError):
        ledger.transfer(
            session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=amount, currency="USD"
        )


def test_reserved_system_prefix_cannot_be_used_for_customers(session):
    with pytest.raises(LedgerError):
        ledger.create_account(session, account_id="SYS-CASH-USD", owner_name="Mallory", currency="USD")


def test_every_journal_balances_to_zero(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=5_000)
    ledger.transfer(
        session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=700, currency="USD"
    )
    assert ledger.unbalanced_journal_ids(session) == []


def test_statement_lists_most_recent_first(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=5_000)
    ledger.transfer(
        session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=700, currency="USD"
    )
    lines = ledger.statement(session, "alice")
    assert [line["reference"] for line in lines] == ["tx-1", "dep-1"]
    assert lines[0]["amount_minor"] == -700


def test_transfer_records_skip_deposits(session):
    _accounts(session)
    ledger.deposit(session, reference="dep-1", account_id="alice", amount_minor=5_000)
    ledger.transfer(
        session, reference="tx-1", from_account_id="alice", to_account_id="bob", amount_minor=700, currency="USD"
    )
    records = ledger.transfer_records(session)
    assert len(records) == 1
    assert (records[0].sender_id, records[0].receiver_id, records[0].amount_minor) == ("alice", "bob", 700)
