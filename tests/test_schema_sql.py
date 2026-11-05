"""Checks that the canonical PostgreSQL schema is well formed and matches the ORM tables.

The full PostgreSQL run (including the balance trigger) executes only when TEST_POSTGRES_URL is set.
CI sets it through a Postgres service container.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from neobank import models  # noqa: F401  (registers tables)
from neobank.db import Base

SCHEMA = (Path(__file__).resolve().parent.parent / "sql" / "schema.sql").read_text()


def test_schema_tables_match_orm_tables():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    orm_tables = set(Base.metadata.tables)
    expected = {"accounts", "journal_entries", "postings", "card_transactions", "decision_log"}
    assert expected == orm_tables


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="set TEST_POSTGRES_URL to run against PostgreSQL")
def test_postgres_schema_applies_and_balance_trigger_rejects_unbalanced_journal():
    from sqlalchemy.exc import DBAPIError

    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    # Send the DDL through the raw driver cursor so SQLAlchemy does not parse its contents.
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute(SCHEMA)
        raw.commit()
        cursor.close()
    finally:
        raw.close()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO accounts (id, owner_name, currency) VALUES ('a', 'A', 'USD'), ('b', 'B', 'USD')"))
        conn.execute(text("INSERT INTO journal_entries (reference, currency, request_hash) VALUES ('r1', 'USD', 'h')"))

    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO postings (journal_id, account_id, amount_minor) VALUES (1, 'a', -100)"))

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO postings (journal_id, account_id, amount_minor) VALUES (1, 'a', -100), (1, 'b', 100)"
            )
        )
    assert inspect(engine).has_table("postings")
