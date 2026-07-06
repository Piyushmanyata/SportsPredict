"""Player-prop engine, lineup-gated (spec §5.6, lessons L7 + L10).

L7: under rotation risk, discount the player's allocated share of the team
lambda FIRST, then derive every downstream prop from the adjusted rate —
never depress the final output directly.

L10 (ACTIVE): main-striker 1+SOT band is 52-64 (the 60-72 band is retired);
any MODELED p in the top half of 56-70 requires an explicit written driver,
else regress toward the lower band edge.
"""

from __future__ import annotations

import math

from engine.constants import DRIVER_GATE_BAND


def lam_player_goal(team_lam: float, goal_share: float,
                    rotation_factor: float = 1.0) -> float:
    """goal_share = player's share of team goals (0-1). rotation_factor < 1
    applies the L7 lambda-side discount (e.g. 0.7 for a real bench risk)."""
    return team_lam * goal_share * rotation_factor


def p_anytime_goal(lam_p: float) -> float:
    return 1.0 - math.exp(-lam_p)


def p_score_or_assist(p_goal: float, role: str = "creator") -> float:
    """goal x 1.5-1.8 (creators) / x 1.2-1.4 (pure 9s), overlap-corrected —
    midpoints used; cap below 0.97."""
    mult = 1.65 if role == "creator" else 1.3
    return min(0.97, p_goal * mult)


def p_sot_1plus(sot_lam_p: float) -> float:
    """1+ SOT from the player's SOT rate. Sanity-check against the L10 bands:
    main striker 52-64, winger/AM 42-56 (engine STARTING band, not a cap)."""
    return 1.0 - math.exp(-sot_lam_p)


def p_sot_1plus_2h(sot_lam_p: float) -> float:
    """'1+ SOT in 2H' = rate x 0.55 share: 1 - e^(-0.55 lam)."""
    return 1.0 - math.exp(-0.55 * sot_lam_p)


def driver_gate(p: int, has_driver: bool, band_floor: int | None = None) -> tuple[int, str]:
    """L10 driver gate for ALL modeled markets landing in 56-70.

    In the top half of 56-70 without an explicit written driver (per-90 SOT
    rate, expected service, confirmed starter + heavy minutes), regress toward
    the lower band edge (band_floor, default 56).
    """
    lo, hi = DRIVER_GATE_BAND
    top_half = (lo + hi + 1) // 2  # 63
    if lo <= p <= hi and p >= top_half and not has_driver:
        floor = band_floor if band_floor is not None else lo
        regressed = (p + floor) // 2
        return regressed, f"L10 driver gate: {p} -> {regressed} (no written driver)"
    return p, "driver gate: pass"
