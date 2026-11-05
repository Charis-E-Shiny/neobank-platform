"""Request and response models for the HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CURRENCY = r"^[A-Z]{3}$"


class AccountCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    owner_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(pattern=CURRENCY, examples=["USD", "INR"])


class AccountOut(BaseModel):
    id: str
    owner_name: str
    currency: str
    balance_minor: int


class DepositIn(BaseModel):
    reference: str = Field(min_length=1, max_length=128, description="Idempotency key")
    amount_minor: int = Field(gt=0, description="Amount in minor units (e.g. cents)")


class TransferIn(BaseModel):
    reference: str = Field(min_length=1, max_length=128, description="Idempotency key")
    from_account_id: str = Field(min_length=1, max_length=64)
    to_account_id: str = Field(min_length=1, max_length=64)
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=CURRENCY)
    description: str = Field(default="", max_length=300)


class JournalOut(BaseModel):
    journal_id: int
    reference: str
    currency: str
    description: str
    created_at: datetime


class StatementLine(BaseModel):
    reference: str
    description: str
    created_at: datetime
    amount_minor: int
    currency: str


class AuthorizationIn(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=CURRENCY)
    merchant: str = Field(min_length=1, max_length=120)
    mcc: str = Field(pattern=r"^\d{4}$", description="ISO 18245 merchant category code")
    channel: Literal["pos", "online", "atm"]
    device_id: str | None = Field(default=None, max_length=64)
    occurred_at: datetime | None = Field(default=None, description="Defaults to server time, UTC")


class FraudOut(BaseModel):
    transaction_id: int
    outcome: Literal["APPROVE", "REVIEW", "DECLINE"]
    score: float
    model_version: str
    reasons: list[str]


class CreditApplicationIn(BaseModel):
    applicant_id: str = Field(min_length=1, max_length=64, description="Your internal applicant reference")
    annual_income_minor: int = Field(gt=0)
    monthly_debt_minor: int = Field(ge=0)
    revolving_utilization: float = Field(ge=0, le=1)
    delinquencies_24m: int = Field(ge=0, le=50)
    credit_history_years: float = Field(ge=0, le=80)
    recent_inquiries_6m: int = Field(ge=0, le=50)
    requested_minor: int = Field(gt=0)


class CreditOut(BaseModel):
    outcome: Literal["APPROVE", "REFER", "DECLINE"]
    probability_of_default: float
    approved_amount_minor: int
    reasons: list[str]
    model_version: str


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    subject_id: str
    outcome: str
    score: float
    model_version: str
    reasons: list[str]
    created_at: datetime


class AccountRiskOut(BaseModel):
    account_id: str
    score: float
    reasons: list[str]
    features: dict[str, int]


class BankLineIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    date: date
    amount_minor: int
    description: str = Field(max_length=300)


class ReconciliationIn(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    bank_lines: list[BankLineIn] = Field(max_length=5000)


class MatchOut(BaseModel):
    bank_id: str
    reference: str
    score: float


class ReconciliationOut(BaseModel):
    matched: list[MatchOut]
    unmatched_bank_ids: list[str]
    unmatched_ledger_references: list[str]


class IntegrityOut(BaseModel):
    balanced: bool
    unbalanced_journal_ids: list[int]
