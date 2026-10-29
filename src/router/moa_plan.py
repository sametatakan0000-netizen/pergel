"""Amiral + subagent planning on top of LiveRouter's ordered candidates.

Minimal, deterministic, zero extra inference:
  * **Amiral (orchestrator)** is simply the first entry of ``LiveRouter.plan()`` — the
    existing tolerance-band policy decides it (tier from difficulty, cheapest model inside
    a QUALITY_TOLERANCE band, proven-before-untried).
  * **Subagent candidates (MoA members)** are cheaper models from the same or the next
    cheaper price tier whose adjusted quality sits inside the Amiral's tolerance band, i.e.
    models the policy already treats as "equal enough". Selection is greedy by
    quality-per-dollar (learned reliability included when available) and capped by a budget
    that is never a constant.

Budget is *dynamic* (Mixture-of-Agents ICLR'25 / BAMAS AAAI'26 both report that a fixed
budget is the wrong knob):

    cap = amiral_single_turn_cost * ratio
    ratio = base_tier_ratio * (1 + hardness) * (1 + uncertainty) * (1 - spend_pressure)

  * ``base_tier_ratio`` — how many parallel opinions are worth paying for at this tier.
  * ``hardness``       — learned floor - keyword guess (router already thinks the turn is
                         harder than it looked), so harder turns buy more opinions.
  * ``uncertainty``    — 1 - learned reliability of the bucket: unproven traffic hedges.
  * ``spend_pressure`` — today's recorded spend vs. a soft daily allowance, so the same
                         request type gets leaner as the day's budget is consumed.

An absolute safety ceiling (``ABSOLUTE_TURN_CAP_USD``) is the only fixed number; it exists
to stop runaway loops, not to be the policy.
"""
from typing import Any, Dict, List, Optional

from src.router.live_router import (QUALITY_TOLERANCE, LiveRouter, adjusted_quality,
                                    price_tier)
from src.router.model_registry import VerifiedProfile
from src.router.request_features import OUTPUT_RESERVE_TOKENS, estimate_tokens

# How many parallel opinions each price tier justifies. Cheap tiers are where MoA is
# actually cost-effective (the ICLR'25 MoA budget analysis: many cheap proposers beat one
# expensive model); at the premium tiers a second opinion costs real money per turn.
BASE_TIER_RATIO = {1: 3.0, 2: 2.0, 3: 1.5}
MAX_MEMBERS = 3                     # user-facing ceiling on subagents
ABSOLUTE_TURN_CAP_USD = 0.60        # runaway guard only, not the policy
DAILY_SOFT_ALLOWANCE_USD = 5.0      # spend pressure starts above this
OUTPUT_TOKEN_ESTIMATE = min(OUTPUT_RESERVE_TOKENS, 1500)  # per parallel call


def turn_cost(profile: VerifiedProfile, prompt_tokens: int,
              output_tokens: int = OUTPUT_TOKEN_ESTIMATE) -> float:
    """Billed cost of one call in USD; ``None`` prices never participate (no guesses)."""
    if profile.billed_cost_in is None or profile.billed_cost_out is None:
        return float("inf")
    return (prompt_tokens * profile.billed_cost_in
            + output_tokens * profile.billed_cost_out) / 1_000_000


def budget_ratio(tier: int, hardness: int, reliability: Optional[float],
                 spent_today_usd: float = 0.0,
                 daily_allowance_usd: float = DAILY_SOFT_ALLOWANCE_USD) -> float:
    """Dynamic MoA budget as a multiple of the Amiral's own single-turn cost."""
    base = BASE_TIER_RATIO.get(tier, 1.0)
    hardness_factor = 1.0 + 0.5 * max(0, min(hardness, 2))
    uncertainty = 1.0 if reliability is None else max(0.0, 1.0 - reliability)
    uncertainty_factor = 1.0 + 0.5 * uncertainty
    pressure = 0.0
    if daily_allowance_usd > 0 and spent_today_usd > daily_allowance_usd:
        pressure = min(0.5, (spent_today_usd - daily_allowance_usd) / daily_allowance_usd)
    return max(1.0, base * hardness_factor * uncertainty_factor * (1.0 - pressure))


def _member_key(profile: VerifiedProfile, learned: Dict[str, float]):
    quality = adjusted_quality(profile, learned)
    cost = (profile.billed_cost_in or 0.0) + (profile.billed_cost_out or 0.0)
    return (-(quality / (cost + 1e-9)), profile.model_id)


def plan_moa(router: LiveRouter, payload: Dict[str, Any], session_id: Optional[str] = None,
             now: Optional[float] = None, spent_today_usd: float = 0.0,
             force: bool = False) -> Dict[str, Any]:
    """Return the Amiral plus the MoA decision.

    ``{"amiral": id|None, "tier": int, "moa": {"enabled": bool, "members": [...],
    "cap_usd": float, "amiral_cost_usd": float, "ratio": float, "reason": str}}``
    Decision only — nothing here spends tokens.
    """
    order, bucket, start = router.plan_with_context(payload, session_id, now)
    if not order:
        return {"amiral": None, "tier": start, "moa": {"enabled": False, "members": [],
                                                       "reason": "no candidate"}}
    amiral_id = order[0]
    amiral = router.profiles[amiral_id]
    prompt_tokens = estimate_tokens(payload)
    learned = router.learner.reliability_map(bucket) if bucket else {}
    reliability = learned.get(amiral_id)
    single_cost = turn_cost(amiral, prompt_tokens)
    tier = price_tier(amiral)
    # How much harder the router believes this turn is than the keyword guess said.
    floor = router.learner.start_tier(bucket, start, now=now) if bucket else start
    ratio = budget_ratio(tier, floor - start, reliability, spent_today_usd)
    cap = min(single_cost * ratio, ABSOLUTE_TURN_CAP_USD)

    # MoA is for hard turns (2+): easy turns are answered cheaper by one model.
    if not force and tier < 2:
        return {"amiral": amiral_id, "tier": tier,
                "moa": {"enabled": False, "members": [], "cap_usd": round(cap, 4),
                        "amiral_cost_usd": round(single_cost, 6), "ratio": round(ratio, 2),
                        "reason": "easy turn: single model"}}

    lead_quality = adjusted_quality(amiral, learned)
    eligible: List[VerifiedProfile] = []
    for model_id in order[1:]:
        profile = router.profiles.get(model_id)
        if profile is None or profile.model_id == amiral_id:
            continue
        if price_tier(profile) > tier:           # never pay more than the Amiral
            continue
        if lead_quality - adjusted_quality(profile, learned) > QUALITY_TOLERANCE:
            continue                             # weaker than the band the Amiral leads
        if turn_cost(profile, prompt_tokens) == float("inf"):
            continue
        eligible.append(profile)
    eligible.sort(key=lambda p: _member_key(p, learned))

    members: List[str] = []
    spent = single_cost
    for profile in eligible:
        if len(members) >= MAX_MEMBERS:
            break
        cost = turn_cost(profile, prompt_tokens)
        if spent + cost > cap:
            continue
        members.append(profile.model_id)
        spent += cost
    reason = ("members fit the dynamic cap" if members
              else "no eligible member fits the dynamic cap")
    return {"amiral": amiral_id, "tier": tier,
            "moa": {"enabled": bool(members), "members": members,
                    "cap_usd": round(cap, 4), "amiral_cost_usd": round(single_cost, 6),
                    "total_cost_usd": round(spent, 6), "ratio": round(ratio, 2),
                    "reason": reason}}
