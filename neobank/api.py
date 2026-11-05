"""HTTP API. Business rules live in the service modules. This file maps HTTP to them.

Note: this module intentionally does not use `from __future__ import annotations`. FastAPI
resolves endpoint annotations at runtime, and the dependency aliases below are local names.
"""

import secrets
from datetime import timezone
from typing import Annotated, Iterator, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__, aml, credit, fraud, ledger, reconciliation
from .config import Settings
from .db import Database
from .errors import NeobankError
from .features import CreditApplicant
from .ml.registry import ModelRegistry
from .models import DecisionLog
from .schemas import (
    AccountCreate,
    AccountOut,
    AccountRiskOut,
    AuthorizationIn,
    CreditApplicationIn,
    CreditOut,
    DecisionOut,
    DepositIn,
    FraudOut,
    IntegrityOut,
    JournalOut,
    MatchOut,
    ReconciliationIn,
    ReconciliationOut,
    StatementLine,
    TransferIn,
)


def _naive_utc(value):
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _account_out(session: Session, account) -> AccountOut:
    return AccountOut(
        id=account.id,
        owner_name=account.owner_name,
        currency=account.currency,
        balance_minor=ledger.balance_minor(session, account.id),
    )


def _journal_out(entry) -> JournalOut:
    return JournalOut(
        journal_id=entry.id,
        reference=entry.reference,
        currency=entry.currency,
        description=entry.description,
        created_at=entry.created_at,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database_url)
    registry = ModelRegistry(settings.model_dir, allow_synthetic=settings.allow_synthetic_models)

    app = FastAPI(
        title="Neobank Platform API",
        version=__version__,
        description="Ledger, card fraud scoring, credit decisions, AML triage and reconciliation.",
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(NeobankError)
    async def _domain_error(_: Request, exc: NeobankError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    def get_session() -> Iterator[Session]:
        session = database.session()
        try:
            yield session
        finally:
            session.close()

    def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if settings.api_key and not secrets.compare_digest(x_api_key or "", settings.api_key):
            raise HTTPException(status_code=401, detail="missing or invalid X-API-Key header")

    DB = Annotated[Session, Depends(get_session)]
    api = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    # ---- Accounts and ledger -------------------------------------------------

    @api.post("/accounts", status_code=201, response_model=AccountOut, tags=["ledger"])
    def create_account(body: AccountCreate, session: DB) -> AccountOut:
        account = ledger.create_account(
            session, account_id=body.id, owner_name=body.owner_name, currency=body.currency
        )
        return _account_out(session, account)

    @api.get("/accounts/{account_id}", response_model=AccountOut, tags=["ledger"])
    def get_account(account_id: str, session: DB) -> AccountOut:
        return _account_out(session, ledger.get_account(session, account_id))

    @api.post("/accounts/{account_id}/deposits", status_code=201, response_model=JournalOut, tags=["ledger"])
    def deposit(account_id: str, body: DepositIn, session: DB) -> JournalOut:
        entry = ledger.deposit(
            session, reference=body.reference, account_id=account_id, amount_minor=body.amount_minor
        )
        return _journal_out(entry)

    @api.post("/transfers", status_code=201, response_model=JournalOut, tags=["ledger"])
    def transfer(body: TransferIn, session: DB) -> JournalOut:
        entry = ledger.transfer(
            session,
            reference=body.reference,
            from_account_id=body.from_account_id,
            to_account_id=body.to_account_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
            description=body.description,
        )
        return _journal_out(entry)

    @api.get("/accounts/{account_id}/statement", response_model=list[StatementLine], tags=["ledger"])
    def statement(
        account_id: str,
        session: DB,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> list[dict]:
        ledger.get_account(session, account_id)
        return ledger.statement(session, account_id, limit=limit)

    @api.get("/ledger/integrity", response_model=IntegrityOut, tags=["ops"])
    def integrity(session: DB) -> IntegrityOut:
        ids = ledger.unbalanced_journal_ids(session)
        return IntegrityOut(balanced=not ids, unbalanced_journal_ids=ids)

    # ---- Fraud and credit ----------------------------------------------------

    @api.post("/fraud/authorizations", response_model=FraudOut, tags=["fraud"])
    def authorize(body: AuthorizationIn, session: DB) -> FraudOut:
        result = fraud.score_authorization(
            session,
            registry,
            settings,
            account_id=body.account_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
            merchant=body.merchant,
            mcc=body.mcc,
            channel=body.channel,
            device_id=body.device_id,
            occurred_at=_naive_utc(body.occurred_at),
        )
        return FraudOut(
            transaction_id=result.transaction_id,
            outcome=result.outcome,
            score=result.score,
            model_version=result.model_version,
            reasons=list(result.reasons),
        )

    @api.post("/credit/applications", response_model=CreditOut, tags=["credit"])
    def apply_for_credit(body: CreditApplicationIn, session: DB) -> CreditOut:
        applicant = CreditApplicant(
            annual_income_minor=body.annual_income_minor,
            monthly_debt_minor=body.monthly_debt_minor,
            revolving_utilization=body.revolving_utilization,
            delinquencies_24m=body.delinquencies_24m,
            credit_history_years=body.credit_history_years,
            recent_inquiries_6m=body.recent_inquiries_6m,
        )
        result = credit.assess_application(
            session,
            registry,
            settings,
            applicant_id=body.applicant_id,
            applicant=applicant,
            requested_minor=body.requested_minor,
        )
        return CreditOut(
            outcome=result.outcome,
            probability_of_default=result.probability_of_default,
            approved_amount_minor=result.approved_amount_minor,
            reasons=list(result.reasons),
            model_version=result.model_version,
        )

    # ---- Audit, AML and reconciliation --------------------------------------

    @api.get("/decisions", response_model=list[DecisionOut], tags=["audit"])
    def decisions(
        session: DB,
        kind: Literal["fraud", "credit"] | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> list[DecisionLog]:
        query = select(DecisionLog).order_by(DecisionLog.id.desc()).limit(limit)
        if kind:
            query = query.where(DecisionLog.kind == kind)
        return list(session.scalars(query))

    @api.post("/aml/triage", response_model=list[AccountRiskOut], tags=["aml"])
    def triage(
        session: DB,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
    ) -> list[AccountRiskOut]:
        risks = aml.triage(ledger.transfer_records(session), limit=limit)
        return [
            AccountRiskOut(account_id=r.account_id, score=r.score, reasons=r.reasons, features=r.features)
            for r in risks
        ]

    @api.post("/reconciliation", response_model=ReconciliationOut, tags=["reconciliation"])
    def reconcile(body: ReconciliationIn, session: DB) -> ReconciliationOut:
        ledger.get_account(session, body.account_id)
        bank = [
            reconciliation.BankLine(
                id=line.id, date=line.date, amount_minor=line.amount_minor, description=line.description
            )
            for line in body.bank_lines
        ]
        ledger_lines = [
            reconciliation.LedgerLine(
                reference=row["reference"],
                date=row["created_at"].date(),
                amount_minor=row["amount_minor"],
                description=row["description"],
            )
            for row in ledger.statement(session, body.account_id, limit=500)
        ]
        result = reconciliation.reconcile(bank, ledger_lines)
        return ReconciliationOut(
            matched=[MatchOut(bank_id=m.bank_id, reference=m.reference, score=m.score) for m in result.matched],
            unmatched_bank_ids=result.unmatched_bank,
            unmatched_ledger_references=result.unmatched_ledger,
        )

    app.include_router(api)
    app.state.database = database
    app.state.registry = registry
    return app
