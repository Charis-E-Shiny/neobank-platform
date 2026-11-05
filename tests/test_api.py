from dataclasses import replace

from fastapi.testclient import TestClient

from neobank.api import create_app


def _create(client, account_id, currency="USD"):
    response = client.post(
        "/v1/accounts", json={"id": account_id, "owner_name": account_id.title(), "currency": currency}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_end_to_end_payment_flow(client):
    _create(client, "alice")
    _create(client, "bob")

    deposit = client.post("/v1/accounts/alice/deposits", json={"reference": "dep-1", "amount_minor": 10_000})
    assert deposit.status_code == 201

    transfer = client.post(
        "/v1/transfers",
        json={
            "reference": "tx-1",
            "from_account_id": "alice",
            "to_account_id": "bob",
            "amount_minor": 2_500,
            "currency": "USD",
            "description": "Rent share",
        },
    )
    assert transfer.status_code == 201, transfer.text

    assert client.get("/v1/accounts/bob").json()["balance_minor"] == 2_500
    statement = client.get("/v1/accounts/alice/statement").json()
    assert [line["reference"] for line in statement] == ["tx-1", "dep-1"]
    assert client.get("/v1/ledger/integrity").json() == {"balanced": True, "unbalanced_journal_ids": []}


def test_error_mapping(client):
    _create(client, "alice")
    _create(client, "bob")

    assert client.get("/v1/accounts/ghost").status_code == 404
    assert client.post("/v1/accounts", json={"id": "alice", "owner_name": "x", "currency": "USD"}).status_code == 409

    overdraft = client.post(
        "/v1/transfers",
        json={"reference": "tx-x", "from_account_id": "alice", "to_account_id": "bob", "amount_minor": 1, "currency": "USD"},
    )
    assert overdraft.status_code == 422
    assert overdraft.json()["error"] == "InsufficientFundsError"


def test_invalid_payloads_are_rejected(client):
    assert client.post("/v1/accounts", json={"id": "bad id!", "owner_name": "x", "currency": "usd"}).status_code == 422
    assert client.post("/v1/accounts/alice/deposits", json={"reference": "r", "amount_minor": 0}).status_code == 422


def test_fraud_and_credit_endpoints_write_audit_log(client):
    _create(client, "card-9")
    fraud = client.post(
        "/v1/fraud/authorizations",
        json={
            "account_id": "card-9",
            "amount_minor": 1_500,
            "currency": "USD",
            "merchant": "Bakery",
            "mcc": "5462",
            "channel": "pos",
            "device_id": "dev-1",
            "occurred_at": "2026-11-05T12:00:00+00:00",
        },
    )
    assert fraud.status_code == 200, fraud.text
    assert fraud.json()["outcome"] == "APPROVE"

    credit = client.post(
        "/v1/credit/applications",
        json={
            "applicant_id": "app-42",
            "annual_income_minor": 9_000_000,
            "monthly_debt_minor": 40_000,
            "revolving_utilization": 0.1,
            "delinquencies_24m": 0,
            "credit_history_years": 12,
            "recent_inquiries_6m": 0,
            "requested_minor": 1_000_000,
        },
    )
    assert credit.status_code == 200, credit.text
    assert credit.json()["outcome"] == "APPROVE"

    fraud_log = client.get("/v1/decisions", params={"kind": "fraud"}).json()
    credit_log = client.get("/v1/decisions", params={"kind": "credit"}).json()
    assert len(fraud_log) == 1 and fraud_log[0]["subject_id"] == "card-9"
    assert len(credit_log) == 1 and credit_log[0]["subject_id"] == "app-42"


def test_reconciliation_endpoint(client):
    _create(client, "alice")
    _create(client, "shop")
    client.post("/v1/accounts/alice/deposits", json={"reference": "dep-1", "amount_minor": 10_000})
    client.post(
        "/v1/transfers",
        json={
            "reference": "pay-1",
            "from_account_id": "alice",
            "to_account_id": "shop",
            "amount_minor": 450,
            "currency": "USD",
            "description": "Coffee shop",
        },
    )
    response = client.post(
        "/v1/reconciliation",
        json={
            "account_id": "alice",
            "bank_lines": [
                {"id": "stmt-1", "date": "2026-11-05", "amount_minor": -450, "description": "COFFEE SHOP 221"},
                {"id": "stmt-2", "date": "2026-11-05", "amount_minor": -99, "description": "Unrelated"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [m["bank_id"] for m in body["matched"]] == ["stmt-1"]
    assert body["unmatched_bank_ids"] == ["stmt-2"]


def test_api_key_is_enforced_when_configured(settings):
    secured = TestClient(create_app(replace(settings, api_key="s3cret")))
    assert secured.get("/health").status_code == 200  # health stays open for uptime checks
    assert secured.get("/v1/accounts/x").status_code == 401
    assert secured.get("/v1/accounts/x", headers={"X-API-Key": "wrong"}).status_code == 401
    assert secured.get("/v1/accounts/x", headers={"X-API-Key": "s3cret"}).status_code == 404
