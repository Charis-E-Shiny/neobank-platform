# Neobank Platform

A reference fintech platform with a double-entry ledger, card fraud scoring, credit decisioning with
reason codes, AML alert triage, bank reconciliation, and an audit trail for every decision. It runs
end to end with synthetic data, and it's built to be deployed and extended.

- **Python / FastAPI** API with scikit-learn models and a SQLAlchemy data layer
- **PostgreSQL** schema with a database-level double-entry guarantee
- **Java 17** ledger-invariant library for JVM payment services
- **React / Vite** operator console
- **Vercel** deployment for the API and the console

> **Read before use.** This is a reference implementation. Its models are trained on synthetic data
> and are not calibrated for any real portfolio. It is not a licensed financial service. Deploying it
> to handle real money, credit or personal data requires your own security, compliance and
> model-risk review. See [`docs/MODEL_CARDS.md`](docs/MODEL_CARDS.md) and [`SECURITY.md`](SECURITY.md).

---

## What's implemented

| Area | Status | Where |
|---|---|---|
| Double-entry ledger, transfers, deposits, statements, idempotent posting | Implemented, tested | `neobank/ledger.py`, `sql/schema.sql` |
| Overdraft protection and row locking for concurrent debits | Implemented, tested | `neobank/ledger.py` |
| Card fraud scoring (gradient boosting, calibrated) with hard rules | Implemented, tested | `neobank/fraud.py`, `neobank/ml/` |
| Credit scorecard (logistic regression) with reason codes | Implemented, tested | `neobank/credit.py` |
| AML alert triage (rules over the transfer graph) | Implemented, tested | `neobank/aml.py` |
| Bank statement reconciliation (fuzzy description matching) | Implemented, tested | `neobank/reconciliation.py` |
| Audit log of every decision (inputs, score, model version, reasons) | Implemented, tested | `decision_log` table, `GET /v1/decisions` |
| Drift (PSI) and approval-rate-by-group monitoring helpers | Implemented, tested | `neobank/monitoring.py` |
| Java ledger invariants (balanced journals, idempotency, overdraft) | Implemented; the JUnit suite runs in CI | `java-ledger/` |
| Operator console (React) | Implemented | `frontend/` |
| API key authentication, CORS, input validation, typed errors | Implemented | `neobank/api.py` |
| KYC and document verification | Roadmap | — |
| Transaction categorization | Roadmap | — |
| Deep learning: GRU over card history for fraud; graph neural network for AML | Roadmap | Not in this release (see below) |
| Churn and uplift models, experimentation platform | Roadmap | — |

**On deep learning.** This release doesn't include a deep learning model. The API runs on a
serverless function, where a PyTorch runtime is too large to load. The right place for a GRU or
graph neural network is a training pipeline and a separate model server. The plan is to train them
offline, compare them against the baselines in this repository on analyst-labelled data, and promote
them only if they win. The fraud and AML baselines are there so that comparison can be made.

---

## Quick start (local)

Requirements: Python 3.11+, Node 20+, Java 17+ and Maven (for the ledger module), and optionally
PostgreSQL 14+.

```bash
git clone https://github.com/<you>/neobank-platform.git
cd neobank-platform

# 1. API and models
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m neobank.ml.train --model-dir models     # trains both models (~3 s) and prints metrics
uvicorn api.index:app --reload --port 8000        # API at http://localhost:8000/docs

# 2. Tests
pytest

# 3. Console (second terminal)
cd frontend && npm install && npm run dev         # http://localhost:5173 (proxies /v1 to :8000)

# 4. Java ledger (optional)
cd java-ledger && mvn verify
```

Copy `.env.example` to `.env` to change settings. With no configuration, the API uses a SQLite file
in the repository root.

### Running against PostgreSQL

```bash
createdb neobank
psql -1 "postgresql://localhost/neobank" -f sql/schema.sql   # tables, indexes, view, balance trigger
export DATABASE_URL="postgresql+psycopg://localhost/neobank"
uvicorn api.index:app --port 8000
```

`sql/schema.sql` installs a deferred constraint trigger, so PostgreSQL itself rejects any journal
whose postings don't sum to zero, even if an application bug or a manual insert tries to write one.
The integration test runs when `TEST_POSTGRES_URL` is set. CI runs it against a Postgres service.

---

## API examples

All `/v1` routes require `X-API-Key` when `API_KEY` is set. Amounts are integers in minor units
(cents), so `4500` is 45.00.

```bash
KEY=dev-key
H="X-API-Key: $KEY"; J="Content-Type: application/json"; B=http://localhost:8000

# Open accounts and fund one
curl -X POST $B/v1/accounts -H "$H" -H "$J" -d '{"id":"alice","owner_name":"Alice","currency":"USD"}'
curl -X POST $B/v1/accounts -H "$H" -H "$J" -d '{"id":"shop","owner_name":"Corner Shop","currency":"USD"}'
curl -X POST $B/v1/accounts/alice/deposits -H "$H" -H "$J" -d '{"reference":"dep-001","amount_minor":50000}'

# Transfer. Re-sending the same reference returns the original entry, not a second debit.
curl -X POST $B/v1/transfers -H "$H" -H "$J" \
  -d '{"reference":"pay-001","from_account_id":"alice","to_account_id":"shop","amount_minor":4500,"currency":"USD","description":"Coffee"}'

# Score a card authorization
curl -X POST $B/v1/fraud/authorizations -H "$H" -H "$J" \
  -d '{"account_id":"alice","amount_minor":900000,"currency":"USD","merchant":"Casino","mcc":"7995","channel":"online","device_id":"new-device","occurred_at":"2026-11-05T03:00:00Z"}'

# Credit application
curl -X POST $B/v1/credit/applications -H "$H" -H "$J" \
  -d '{"applicant_id":"app-42","annual_income_minor":1200000,"monthly_debt_minor":60000,"revolving_utilization":0.95,"delinquencies_24m":3,"credit_history_years":1,"recent_inquiries_6m":6,"requested_minor":500000}'

# Other endpoints
curl "$B/v1/accounts/alice/statement?limit=20" -H "$H"
curl -X POST "$B/v1/aml/triage?limit=10" -H "$H"
curl "$B/v1/decisions?kind=fraud&limit=50" -H "$H"
curl "$B/v1/ledger/integrity" -H "$H"                 # balanced: true when every journal sums to zero
curl -X POST $B/v1/reconciliation -H "$H" -H "$J" \
  -d '{"account_id":"alice","bank_lines":[{"id":"stmt-1","date":"2026-11-05","amount_minor":-4500,"description":"COFFEE SHOP 221"}]}'
```

Errors use one shape: `{"error": "<ErrorType>", "detail": "<message>"}`. Status codes:
`404` unknown account, `409` conflicting reuse of a reference or a duplicate account, `422` rule
violation (for example, insufficient funds or a currency mismatch), `401` missing or invalid key.

Interactive documentation is served at `/docs`.

---

## Deploying to Vercel

Deploy two Vercel projects from this one repository.

### 1. API project (root of the repository)

- **Framework:** Other. `api/index.py` exposes the FastAPI `app`, and `vercel.json` rewrites every
  path to it.
- **Environment variables:**

  | Variable | Value |
  |---|---|
  | `DATABASE_URL` | A hosted PostgreSQL URL, `postgresql+psycopg://…?sslmode=require`. **Required**: Vercel's filesystem is ephemeral, so SQLite will lose data. |
  | `API_KEY` | A long random string (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
  | `CORS_ORIGINS` | The console's URL, for example `https://neobank-web.vercel.app` |
  | `ALLOW_SYNTHETIC_MODELS` | `true` (default). See the note below. |

- **Apply the schema once** to that database: `psql -1 "$DATABASE_URL" -f sql/schema.sql`.

**Model artifacts on Vercel.** The `models/*.joblib` files are gitignored. On a cold start, the API
trains the two synthetic models into `/tmp`, which takes a few seconds. For a real deployment, train
your own models offline, commit or bundle the artifacts (remove them from `.gitignore`), and set
`ALLOW_SYNTHETIC_MODELS=false` so the API fails loudly rather than serving synthetic models.

**Verify routing on first deploy.** The rewrite in `vercel.json` sends all paths to the Python
function. Confirm `GET https://<your-api>.vercel.app/health` returns `{"status":"ok",…}` before
relying on it. I have not deployed this to Vercel myself. The app runs locally under uvicorn and
passes its tests. Vercel's routing is the part to check.

### 2. Console project (`frontend/`)

- **Root directory:** `frontend`
- **Framework preset:** Vite (build `npm run build`, output `dist`)
- **Environment variable:** `VITE_API_BASE=https://<your-api>.vercel.app`

The console stores the API key in the browser's local storage, so anyone who can use the browser can
use the key. For a shared deployment, put the console behind your identity provider, or use
per-user keys issued by your gateway.

### Java ledger

`java-ledger/` is a library, not a web service. Vercel doesn't run JVM services, so the Java module
is for Spring Boot, Quarkus or other JVM services hosted on Cloud Run, ECS, Fly.io or Render. Publish
it to your Maven repository with `mvn deploy`, or consume it as a source module.

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the components, request flow, design decisions
and scaling notes. [`docs/MODEL_CARDS.md`](docs/MODEL_CARDS.md) covers each model's data, evaluation,
intended use and known risks.

```
neobank-platform/
├── api/index.py              Vercel entry point
├── neobank/
│   ├── api.py                HTTP routes, auth, error mapping
│   ├── ledger.py             double-entry ledger
│   ├── fraud.py              card authorization scoring
│   ├── credit.py             credit decisions and reason codes
│   ├── aml.py                AML alert triage
│   ├── reconciliation.py     statement matching
│   ├── monitoring.py         PSI drift, approval rates by group
│   ├── features.py           feature definitions shared by training and serving
│   ├── models.py, db.py      SQLAlchemy models and engine
│   ├── schemas.py            request and response models
│   ├── config.py             environment settings
│   └── ml/                   synthetic data, training, artifact registry
├── sql/
│   ├── schema.sql            canonical PostgreSQL schema and balance trigger
│   └── queries/analytics.sql monitoring and investigation queries
├── java-ledger/             Maven project: ledger invariants and JUnit tests
├── frontend/                 React console (Vite)
├── tests/                    pytest suite, including the PostgreSQL integration test
└── docs/                     architecture and model cards
```

---

## Testing and CI

- `pytest`: 36 tests in total, covering the ledger rules, fraud and credit decisions, AML rules,
  reconciliation, monitoring, the HTTP API, and the PostgreSQL schema (when `TEST_POSTGRES_URL` is set).
- `npm run build`: checks that the console compiles.
- `mvn verify`: runs the Java ledger tests.

GitHub Actions (`.github/workflows/ci.yml`) runs all three on every push and pull request, and it
starts a PostgreSQL service for the integration test.

---

## Known limitations

- **Synthetic data.** Models are trained on generated data, so their metrics describe the generator,
  not real fraud or credit outcomes. See the model cards before quoting any number.
- **Single shared API key.** Fine for a demo or an internal tool. Replace it with per-client keys or
  an identity provider before exposing the API more widely.
- **No rate limiting or request signing** in the application. Add them at your gateway.
- **Schema management.** Development uses `create_all()`. For production, apply `sql/schema.sql` or
  add Alembic migrations generated from it.
- **Concurrency.** Row locks are used on PostgreSQL. SQLite is a single-writer development store.
- **Idempotency keys are client-supplied.** Clients must generate unguessable references.

---

## Contributing

1. Fork the repository and create a branch.
2. Run `pytest`, `npm run build` and `mvn verify` before opening a pull request.
3. Add a test for any change to a financial rule, a feature definition or a decision threshold.
   Changes to feature definitions must update the model cards and retrain the artifacts.

## License

MIT. See [`LICENSE`](LICENSE). The license includes a notice that this software is a reference
implementation and not a financial service.
