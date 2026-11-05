"""AML alert triage: ranks accounts by money-flow red flags so analysts review the riskiest first.

This version uses transparent rules. Each flag maps to a typology investigators already know:
  * structuring: repeated amounts just below the reporting threshold
  * pass-through: funds received and then almost fully forwarded within a short window
  * fan-out: sending to many distinct counterparties

A graph neural network over the account graph is the planned next step. The rules are the
baseline it must beat on analyst-confirmed alerts (see docs/MODEL_CARDS.md).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable

from .ledger import TransferRecord

CTR_THRESHOLD_MINOR = 1_000_000  # reporting threshold, expressed in minor units
STRUCTURING_BAND = (0.90, 1.00)  # share of the threshold, half-open at the top
PASSTHROUGH_WINDOW = timedelta(hours=48)
PASSTHROUGH_MATCH = (0.85, 1.00)  # outflow as a share of the matching inflow
FANOUT_THRESHOLD = 8


@dataclass
class AccountRisk:
    account_id: str
    score: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, int] = field(default_factory=dict)


def triage(transfers: Iterable[TransferRecord], limit: int = 20) -> list[AccountRisk]:
    outgoing: dict[str, list[TransferRecord]] = defaultdict(list)
    incoming: dict[str, list[TransferRecord]] = defaultdict(list)
    for t in transfers:
        outgoing[t.sender_id].append(t)
        incoming[t.receiver_id].append(t)

    lower, upper = STRUCTURING_BAND
    results: list[AccountRisk] = []
    for account_id in set(outgoing) | set(incoming):
        outs = sorted(outgoing[account_id], key=lambda t: t.at)
        ins = sorted(incoming[account_id], key=lambda t: t.at)

        structuring = sum(
            1 for t in outs if CTR_THRESHOLD_MINOR * lower <= t.amount_minor < CTR_THRESHOLD_MINOR * upper
        )
        passthrough = 0
        for inc in ins:
            for out in outs:
                in_window = inc.at <= out.at <= inc.at + PASSTHROUGH_WINDOW
                matched = PASSTHROUGH_MATCH[0] * inc.amount_minor <= out.amount_minor <= PASSTHROUGH_MATCH[1] * inc.amount_minor
                if in_window and matched:
                    passthrough += 1
                    break
        distinct_receivers = len({t.receiver_id for t in outs})
        fanout = int(distinct_receivers >= FANOUT_THRESHOLD)

        raw = 1.0 * structuring + 1.5 * passthrough + 1.0 * fanout
        if raw == 0:
            continue

        reasons = []
        if structuring:
            reasons.append(f"{structuring} outgoing transfer(s) just below the reporting threshold")
        if passthrough:
            reasons.append(f"{passthrough} inflow(s) forwarded almost in full within 48 hours")
        if fanout:
            reasons.append(f"Sent to {distinct_receivers} distinct counterparties")

        results.append(
            AccountRisk(
                account_id=account_id,
                score=round(1 - math.exp(-raw / 3), 4),
                reasons=reasons,
                features={
                    "structuring_hits": structuring,
                    "passthrough_hits": passthrough,
                    "distinct_receivers": distinct_receivers,
                    "outgoing_count": len(outs),
                    "incoming_count": len(ins),
                },
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]
