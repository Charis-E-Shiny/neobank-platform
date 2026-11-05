"""Bank statement to ledger reconciliation.

A bank line matches a ledger line when the amounts are equal, the dates are within a tolerance,
and the descriptions are similar enough. Matching is one-to-one and greedy by score. The
description similarity uses a character-level ratio, which is a dependable baseline for noisy
bank strings like "UPI/SWIGGY*ORDR7781" against a ledger's "Swiggy order".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher


@dataclass(frozen=True)
class BankLine:
    id: str
    date: date
    amount_minor: int
    description: str


@dataclass(frozen=True)
class LedgerLine:
    reference: str
    date: date
    amount_minor: int
    description: str


@dataclass(frozen=True)
class Match:
    bank_id: str
    reference: str
    score: float


@dataclass(frozen=True)
class ReconciliationResult:
    matched: list[Match]
    unmatched_bank: list[str]
    unmatched_ledger: list[str]


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def reconcile(
    bank: list[BankLine],
    ledger: list[LedgerLine],
    *,
    max_days: int = 2,
    min_similarity: float = 0.5,
) -> ReconciliationResult:
    candidates: list[tuple[float, str, str]] = []
    for b in bank:
        for entry in ledger:
            if b.amount_minor != entry.amount_minor:
                continue
            day_gap = abs((b.date - entry.date).days)
            if day_gap > max_days:
                continue
            sim = _similarity(b.description, entry.description)
            if sim < min_similarity:
                continue
            score = 0.7 * sim + 0.3 * (1 - day_gap / (max_days + 1))
            candidates.append((score, b.id, entry.reference))

    candidates.sort(key=lambda c: c[0], reverse=True)
    used_bank: set[str] = set()
    used_ledger: set[str] = set()
    matched: list[Match] = []
    for score, bank_id, reference in candidates:
        if bank_id in used_bank or reference in used_ledger:
            continue
        used_bank.add(bank_id)
        used_ledger.add(reference)
        matched.append(Match(bank_id=bank_id, reference=reference, score=round(score, 4)))

    return ReconciliationResult(
        matched=matched,
        unmatched_bank=[b.id for b in bank if b.id not in used_bank],
        unmatched_ledger=[e.reference for e in ledger if e.reference not in used_ledger],
    )
