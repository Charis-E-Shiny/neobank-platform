"""ORM models. sql/schema.sql is the canonical PostgreSQL DDL and mirrors these tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(String(16), default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (CheckConstraint("kind IN ('customer', 'system')", name="ck_accounts_kind"),)


class JournalEntry(Base):
    """One balanced transaction. `reference` is the client idempotency key."""

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    currency: Mapped[str] = mapped_column(String(3))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    postings: Mapped[list["Posting"]] = relationship(back_populates="journal", cascade="all, delete-orphan")


class Posting(Base):
    """One signed leg of a journal. Positive increases the account balance."""

    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)

    journal: Mapped[JournalEntry] = relationship(back_populates="postings")

    __table_args__ = (CheckConstraint("amount_minor <> 0", name="ck_postings_nonzero"),)


class CardTransaction(Base):
    """Every card authorization attempt, approved or not. Feeds velocity features."""

    __tablename__ = "card_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    merchant: Mapped[str] = mapped_column(String(120))
    mcc: Mapped[str] = mapped_column(String(4))
    channel: Mapped[str] = mapped_column(String(16))
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(16))
    fraud_score: Mapped[float] = mapped_column(Float)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_card_tx_account_time", "account_id", "occurred_at"),
        CheckConstraint("channel IN ('pos', 'online', 'atm')", name="ck_card_tx_channel"),
    )


class DecisionLog(Base):
    """Append-only audit trail. Stores the features and reasons behind every decision."""

    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    reasons: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_decision_kind_time", "kind", "created_at"),)
