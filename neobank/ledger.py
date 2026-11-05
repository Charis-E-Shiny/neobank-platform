"""Double-entry ledger.

Invariants:
  * Every journal's postings sum to zero (enforced here and by a trigger in sql/schema.sql).
  * Balances are derived from postings, never stored, so they cannot drift from the history.
  * A journal `reference` is an idempotency key. Replaying the same request returns the
    original entry. Reusing a reference for a different request is a conflict.
  * Customer accounts cannot go negative. System clearing accounts can.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from typing import Any, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import utcnow
from .errors import (
    ConflictError,
    CurrencyMismatchError,
    InsufficientFundsError,
    LedgerError,
    NotFoundError,
)
from .models import Account, JournalEntry, Posting

SYSTEM_PREFIX = "SYS-"


class TransferRecord(NamedTuple):
    """A customer-to-customer movement, as seen by downstream analytics."""

    sender_id: str
    receiver_id: str
    amount_minor: int
    at: datetime


def system_account_id(currency: str) -> str:
    return f"{SYSTEM_PREFIX}CASH-{currency}"


def create_account(session: Session, *, account_id: str, owner_name: str, currency: str) -> Account:
    if account_id.startswith(SYSTEM_PREFIX):
        raise LedgerError(f"account ids starting with {SYSTEM_PREFIX!r} are reserved")
    if session.get(Account, account_id) is not None:
        raise ConflictError(f"account {account_id} already exists")
    account = Account(id=account_id, owner_name=owner_name, currency=currency, kind="customer")
    session.add(account)
    session.commit()
    return account


def get_account(session: Session, account_id: str) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"account {account_id} not found")
    return account


def balance_minor(session: Session, account_id: str) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(Posting.amount_minor), 0)).where(Posting.account_id == account_id)
    )
    return int(total)


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _find_replay(session: Session, reference: str, request_hash: str) -> JournalEntry | None:
    entry = session.scalar(select(JournalEntry).where(JournalEntry.reference == reference))
    if entry is None:
        return None
    if entry.request_hash != request_hash:
        raise ConflictError(f"reference {reference!r} was already used for a different request")
    return entry


def _lock_account(session: Session, account_id: str) -> Account:
    # SELECT ... FOR UPDATE on PostgreSQL serializes concurrent debits to the same account.
    # SQLite ignores the clause, which is fine for a single-writer development setup.
    account = session.scalar(select(Account).where(Account.id == account_id).with_for_update())
    if account is None:
        raise NotFoundError(f"account {account_id} not found")
    return account


def _ensure_system_account(session: Session, currency: str) -> Account:
    sid = system_account_id(currency)
    account = session.get(Account, sid)
    if account is None:
        account = Account(id=sid, owner_name="Cash clearing", currency=currency, kind="system")
        session.add(account)
        session.flush()
    return account


def _post(
    session: Session,
    *,
    reference: str,
    description: str,
    currency: str,
    legs: list[tuple[str, int]],
    request_hash: str,
) -> JournalEntry:
    if sum(amount for _, amount in legs) != 0:
        raise LedgerError("journal does not balance")
    entry = JournalEntry(
        reference=reference,
        description=description,
        currency=currency,
        request_hash=request_hash,
        created_at=utcnow(),
    )
    entry.postings = [Posting(account_id=account_id, amount_minor=amount) for account_id, amount in legs]
    session.add(entry)
    return entry


def transfer(
    session: Session,
    *,
    reference: str,
    from_account_id: str,
    to_account_id: str,
    amount_minor: int,
    currency: str,
    description: str = "",
) -> JournalEntry:
    if amount_minor <= 0:
        raise LedgerError("amount must be positive")
    if from_account_id == to_account_id:
        raise LedgerError("source and destination must differ")

    request_hash = _request_hash(
        {
            "from": from_account_id,
            "to": to_account_id,
            "amount": amount_minor,
            "currency": currency,
            "description": description,
        }
    )
    replay = _find_replay(session, reference, request_hash)
    if replay is not None:
        return replay

    source = _lock_account(session, from_account_id)
    destination = _lock_account(session, to_account_id)
    for account in (source, destination):
        if account.currency != currency:
            raise CurrencyMismatchError(f"account {account.id} holds {account.currency}, not {currency}")
    if source.kind == "customer" and balance_minor(session, source.id) < amount_minor:
        raise InsufficientFundsError(f"insufficient funds in {source.id}")

    entry = _post(
        session,
        reference=reference,
        description=description,
        currency=currency,
        legs=[(source.id, -amount_minor), (destination.id, amount_minor)],
        request_hash=request_hash,
    )
    try:
        session.commit()
    except IntegrityError:
        # A concurrent request with the same reference committed first. Return its result.
        session.rollback()
        replay = _find_replay(session, reference, request_hash)
        if replay is None:
            raise
        return replay
    return entry


def deposit(session: Session, *, reference: str, account_id: str, amount_minor: int) -> JournalEntry:
    account = get_account(session, account_id)
    _ensure_system_account(session, account.currency)
    return transfer(
        session,
        reference=reference,
        from_account_id=system_account_id(account.currency),
        to_account_id=account_id,
        amount_minor=amount_minor,
        currency=account.currency,
        description="Deposit",
    )


def statement(session: Session, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            JournalEntry.reference,
            JournalEntry.description,
            JournalEntry.created_at,
            JournalEntry.currency,
            Posting.amount_minor,
        )
        .join(Posting, Posting.journal_id == JournalEntry.id)
        .where(Posting.account_id == account_id)
        .order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "reference": row.reference,
            "description": row.description,
            "created_at": row.created_at,
            "amount_minor": row.amount_minor,
            "currency": row.currency,
        }
        for row in rows
    ]


def unbalanced_journal_ids(session: Session) -> list[int]:
    rows = session.execute(
        select(Posting.journal_id)
        .group_by(Posting.journal_id)
        .having(func.sum(Posting.amount_minor) != 0)
    ).scalars()
    return list(rows)


def transfer_records(session: Session) -> list[TransferRecord]:
    """Customer-to-customer transfers. Deposits and withdrawals involve a system account and are skipped."""
    rows = session.execute(
        select(
            Posting.journal_id,
            Posting.account_id,
            Posting.amount_minor,
            JournalEntry.created_at,
            Account.kind,
        )
        .join(JournalEntry, JournalEntry.id == Posting.journal_id)
        .join(Account, Account.id == Posting.account_id)
    ).all()

    legs_by_journal: dict[int, list] = defaultdict(list)
    for row in rows:
        legs_by_journal[row.journal_id].append(row)

    records: list[TransferRecord] = []
    for legs in legs_by_journal.values():
        if len(legs) != 2:
            continue
        sender = next(leg for leg in legs if leg.amount_minor < 0)
        receiver = next(leg for leg in legs if leg.amount_minor > 0)
        if sender.kind != "customer" or receiver.kind != "customer":
            continue
        records.append(
            TransferRecord(
                sender_id=sender.account_id,
                receiver_id=receiver.account_id,
                amount_minor=-sender.amount_minor,
                at=sender.created_at,
            )
        )
    return records
