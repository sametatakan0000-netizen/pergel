"""Router pool policy: the flexible cheap-to-sweet core set.

The user's decision (2026-10-25): no rigid "flagship vs subagent" split, no designated
"hard turn backup" tier. Any model in this pool can serve any role via prompt/tool
directing — so we pick from ONE flexible set and let cost decide inside it.

Members chosen on measured flexibility (intelligence + coding percentile mean, low
spread) and measured cost-per-turn on our own live traffic (input-dominated, ~100K
prompt tokens per turn):
  * claude-haiku-5.5   $0.01/turn  fast, cheap default
  * glm-5.3-flash      $0.02/turn  cheapest with 3-axis benchmark evidence
  * mimo-v2.6-pro      $0.05/turn  balanced, has prompt-cache discount
  * claude-sonnet-5.5  $0.27/turn  sweet spot ceiling (no $4-10 tier models)
"""
import os
from typing import Optional, Tuple

# Comma-separated model ids. Empty/unset = no allowlist (all curated models eligible).
DEFAULT_CORE_POOL: Tuple[str, ...] = (
    "anthropic/claude-haiku-5.5",
    "z-ai/glm-5.3-flash",
    "xiaomi/mimo-v2.6-pro",
    "anthropic/claude-sonnet-5.5",
)


def core_pool_ids(env: Optional[str] = None) -> Tuple[str, ...]:
    raw = os.environ.get("ORACLE_CORE_POOL", "") if env is None else env
    if not raw.strip():
        return ()
    return tuple(x.strip() for x in raw.split(",") if x.strip())
