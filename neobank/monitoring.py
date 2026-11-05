"""Model and data monitoring helpers.

  * Population Stability Index (PSI) measures how far a live score or feature distribution has
    moved from the training baseline.
  * Approval rates by group support the fair-lending review. This is an outcome check, not a
    substitute for a formal fairness audit (see docs/MODEL_CARDS.md).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np

PSI_STABLE = 0.10
PSI_MONITOR = 0.25
_EPS = 1e-6


def psi(expected: Iterable[float], actual: Iterable[float], bins: int = 10) -> float:
    e = np.asarray(list(expected), dtype=float)
    a = np.asarray(list(actual), dtype=float)
    if e.size == 0 or a.size == 0:
        raise ValueError("PSI needs non-empty expected and actual samples")

    edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0  # constant baseline: nothing to compare against
    edges[0], edges[-1] = -np.inf, np.inf

    e_pct = np.histogram(e, bins=edges)[0] / e.size
    a_pct = np.histogram(a, bins=edges)[0] / a.size
    e_pct = np.clip(e_pct, _EPS, None)
    a_pct = np.clip(a_pct, _EPS, None)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


def drift_status(psi_value: float) -> str:
    if psi_value < PSI_STABLE:
        return "stable"
    if psi_value < PSI_MONITOR:
        return "monitor"
    return "drift"


def approval_rate_by_group(rows: Iterable[tuple[str, bool]]) -> dict[str, float]:
    totals: dict[str, int] = defaultdict(int)
    approved: dict[str, int] = defaultdict(int)
    for group, is_approved in rows:
        totals[group] += 1
        approved[group] += int(is_approved)
    return {group: approved[group] / totals[group] for group in totals}
