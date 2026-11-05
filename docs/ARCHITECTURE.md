# Architecture

## Components

| Component | Tech | Responsibility |
|---|---|---|
| `neobank/` | Python 3.11+, FastAPI, SQLAlchemy 2 | Ledger, fraud scoring, credit decisions, AML triage, reconciliation, monitoring helpers, HTTP API |
| `neobank/ml/` | scikit-learn, NumPy, joblib | Synthetic data, model training, artifact registry |
| `sql/` | PostgreSQL 14+ | Canonical schema, balance trigger, balance view, analytical queries |
| `java-ledger/` | Java 17, Maven, JUnit 5 | Framework-free ledger invariants for JVM payment services |
| `frontend/` | React 18, Vite | Operator console: accounts, payments, authorization scoring, credit, audit log |
| `api/index.py` | Vercel Python runtime | Serverless entry point that exposes the FastAPI `app` |

## Request flow

```
Browser ──HTTPS──► React console ──/v1/*──► FastAPI (Vercel function or container)
                                               │
                    ┌──────────────────────────┼───────────────────────────┐
                    ▼                          ▼                           ▼
             ledger.py                  fraud.py / credit.py          aml.py / reconciliation.py
        (double-entry, idempotent)   (features → model → rules)     (rules on transfer graph)
                    │                          │                           │
                    └──────────────────────────┴───────────────────────────┘
                                               ▼
                                 PostgreSQL (accounts, postings, card_transactions, decision_log)
```

## Key design decisions

**Balances are derived, not stored.** An account's balance is the sum of its postings. A stored
balance column can drift from the history. The derived approach costs an index scan, which is cheap
at this scale. At higher volume, add a materialized balance updated in the same transaction and
keep the postings as the source of truth.

**Every journal balances to zero.** The Python service checks it before writing. In PostgreSQL, a
deferred constraint trigger checks it again at commit (`sql/schema.sql`). The Java module makes an
unbalanced journal impossible to construct.

**Idempotency by reference.** Each journal stores a hash of its request. A replay returns the
original entry. A reused reference with a different payload gets 409 Conflict. A concurrent race on
the unique constraint resolves to the winning entry.

**Concurrency.** Transfers lock both account rows with `SELECT … FOR UPDATE` before checking the
balance, so two concurrent debits cannot both pass the overdraft check.

**Train/serve parity.** Training and serving build features through the same functions in
`neobank/features.py`. A test (`test_risky_pattern_scores_higher_than_routine`) caught a case where
the serving path computed one feature differently from training. Keep that test.

**Decision audit trail.** Every fraud and credit decision writes a `decision_log` row with the model
version, the feature values, the score and the reasons. Any decision can be reconstructed later.

**Explainability.** Fraud reasons come from explicit rules over features (for example, "new device").
Credit reasons come from the scorecard's additive contributions (coefficient × standardized value),
the same mechanism used by traditional scorecard reason codes.

## Scaling notes

- **API:** stateless, so it scales horizontally. On Vercel, each cold start creates a database
  engine and loads models. Keep the model artifacts small, and use a managed PostgreSQL with
  connection pooling (for example, PgBouncer or the provider's pooler) for serverless traffic.
- **Fraud velocity queries** run against `card_transactions (account_id, occurred_at)`. Partition by
  time once the table reaches hundreds of millions of rows.
- **Model serving** is in-process. Move to a dedicated model server (ONNX Runtime or a managed
  endpoint) when models grow or when multiple services need the same model.

## What is intentionally out of scope

- KYC and document verification, transaction categorization, and churn or uplift models
  (listed in the README roadmap).
- Deep learning models. The planned sequence model (GRU over card history) and the graph neural
  network for AML are roadmap items. Each must beat the baselines in this repository on held-out,
  analyst-labelled data before it replaces them.
- Payment network connectivity, card issuing, and money movement with external banks.
