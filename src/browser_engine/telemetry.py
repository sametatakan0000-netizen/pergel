"""Decision telemetry: lightweight per-rule counters for a live engine.

Counts what the engine decided and which rule fired, so an operator can see
which filters actually matter on a real workload instead of guessing from the
static list. No I/O, no timers — just counters the caller snapshots on demand.
"""


from collections import Counter
from typing import Optional


class RuleStats:
    """Tally decisions by action and by rule id."""

    __slots__ = ("_by_action", "_by_rule")

    def __init__(self) -> None:
        self._by_action: Counter = Counter()
        self._by_rule: Counter = Counter()

    def record(self, action: str, rule_id: Optional[int] = None) -> None:
        self._by_action[action] += 1
        if rule_id is not None:
            self._by_rule[rule_id] += 1

    def totals(self) -> dict:
        return dict(self._by_action)

    def top_rules(self, n: int = 10) -> list:
        return self._by_rule.most_common(n)

    def total_decisions(self) -> int:
        return sum(self._by_action.values())
