-- Neobank Platform: canonical PostgreSQL schema (PostgreSQL 14+).
--
-- Apply to production with:  psql -1 "$DATABASE_URL" -f sql/schema.sql
-- (-1 runs the whole file as one transaction.)
-- The SQLAlchemy models in neobank/models.py mirror these tables. Development uses create_all();
-- production should use this file or Alembic migrations generated from it.

CREATE TABLE IF NOT EXISTS accounts (
    id          VARCHAR(64)  PRIMARY KEY,
    owner_name  VARCHAR(200) NOT NULL,
    currency    CHAR(3)      NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    kind        VARCHAR(16)  NOT NULL DEFAULT 'customer' CHECK (kind IN ('customer', 'system')),
    created_at  TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

-- One row per balanced transaction. `reference` is the client idempotency key.
CREATE TABLE IF NOT EXISTS journal_entries (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference     VARCHAR(128) NOT NULL UNIQUE,
    description   VARCHAR(300) NOT NULL DEFAULT '',
    currency      CHAR(3)      NOT NULL,
    request_hash  CHAR(64)     NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

-- Signed legs. Positive amounts increase the account balance.
CREATE TABLE IF NOT EXISTS postings (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    journal_id    BIGINT      NOT NULL REFERENCES journal_entries (id) ON DELETE CASCADE,
    account_id    VARCHAR(64) NOT NULL REFERENCES accounts (id),
    amount_minor  BIGINT      NOT NULL CHECK (amount_minor <> 0)
);
CREATE INDEX IF NOT EXISTS ix_postings_journal ON postings (journal_id);
CREATE INDEX IF NOT EXISTS ix_postings_account ON postings (account_id);

-- Every card authorization attempt, approved or not. Feeds velocity features.
CREATE TABLE IF NOT EXISTS card_transactions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id    VARCHAR(64)  NOT NULL REFERENCES accounts (id),
    amount_minor  BIGINT       NOT NULL CHECK (amount_minor > 0),
    currency      CHAR(3)      NOT NULL,
    merchant      VARCHAR(120) NOT NULL,
    mcc           CHAR(4)      NOT NULL CHECK (mcc ~ '^[0-9]{4}$'),
    channel       VARCHAR(16)  NOT NULL CHECK (channel IN ('pos', 'online', 'atm')),
    device_id     VARCHAR(64),
    decision      VARCHAR(16)  NOT NULL CHECK (decision IN ('APPROVE', 'REVIEW', 'DECLINE')),
    fraud_score   DOUBLE PRECISION NOT NULL CHECK (fraud_score BETWEEN 0 AND 1),
    occurred_at   TIMESTAMP    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_card_tx_account_time ON card_transactions (account_id, occurred_at);

-- Append-only audit trail. Stores model inputs, outputs and reasons for every decision.
CREATE TABLE IF NOT EXISTS decision_log (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind           VARCHAR(16)  NOT NULL CHECK (kind IN ('fraud', 'credit')),
    subject_id     VARCHAR(64)  NOT NULL,
    model_version  VARCHAR(64)  NOT NULL,
    outcome        VARCHAR(16)  NOT NULL,
    score          DOUBLE PRECISION NOT NULL,
    inputs         JSONB        NOT NULL,
    reasons        JSONB        NOT NULL,
    created_at     TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_decision_kind_time ON decision_log (kind, created_at);

-- Balances are derived, never stored. This view is the canonical read path.
CREATE OR REPLACE VIEW account_balances AS
SELECT a.id,
       a.currency,
       COALESCE(SUM(p.amount_minor), 0) AS balance_minor
FROM accounts a
LEFT JOIN postings p ON p.account_id = a.id
GROUP BY a.id, a.currency;

-- Double-entry invariant: every journal must sum to zero. The check is DEFERRED so it runs at
-- COMMIT, after all legs of a journal are inserted in the same transaction.
CREATE OR REPLACE FUNCTION assert_journal_balanced() RETURNS trigger AS $$
BEGIN
    IF (SELECT COALESCE(SUM(amount_minor), 0) FROM postings WHERE journal_id = NEW.journal_id) <> 0 THEN
        -- String concatenation is used here instead of a format placeholder.
        RAISE EXCEPTION USING MESSAGE = 'journal ' || NEW.journal_id || ' does not balance';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS postings_balanced ON postings;
CREATE CONSTRAINT TRIGGER postings_balanced
    AFTER INSERT ON postings
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION assert_journal_balanced();
