"""
Player prop engine (§5.6) with L7 λ-allocation discipline and L10 band correction.

Key constraints:
- L10 ACTIVE: main-striker 1+SOT band 52-64 (was 60-72, RETIRED).
- Any modeled p in top half of 56-70 requires explicit written driver.
- L7: discount inside team λ allocation, not final output.
- Rotation is the dominant variable; MD3 doubles rotation risk.
"""

import math
from dataclasses import dataclass
from typing import Optional


# §5.6 Player goal share bands
GOAL_BANDS = {
    "star_striker":   (32, 45),   # anytime goal probability range
    "secondary":      (18, 28),
    "midfielder":     ( 8, 15),
}

# §5.6 1+SOT probability bands (v8, L10 ACTIVE input-side correction)
SOT_BANDS = {
    "main_striker":  (52, 64),  # WAS (60, 72) — RETIRED via L10
    "winger_AM":     (42, 56),
}

# Driver gate: landing in top half of 56-70 requires an explicit written driver
SOT_DRIVER_GATE_LO = 56
SOT_DRIVER_GATE_HI = 70
SOT_DRIVER_GATE_MID = 63  # "top half" threshold within 56-70


# Score-or-assist multipliers (§5.6)
SOA_MULTIPLIER = {
    "creator": (1.5, 1.8),   # applying to goal probability
    "pure_9":  (1.2, 1.4),
}


def _poisson_tail_ge1(lam: float) -> float:
    """P(X >= 1) = 1 - e^(-lam)."""
    return 1.0 - math.exp(-lam)


@dataclass
class PlayerPropResult:
    market: str
    probability: float        # raw computed (0-1)
    p_int: int                # integer 1-99
    band_lo: int
    band_hi: int
    driver_gate_triggered: bool
    driver_required: str
    confidence: str           # HIGH / MED / LOW
    notes: str = ""


def anytime_goal(lam_player: float) -> float:
    """P(player scores anytime) = 1 - e^(-lam_player)."""
    return _poisson_tail_ge1(lam_player)


def player_lam(team_lam: float, goal_share: float,
               rotation_factor: float = 1.0) -> float:
    """
    λ_player = team_lam * goal_share * rotation_factor.
    L7: apply rotation factor to the ALLOCATION (input), not the output.
    rotation_factor: e.g. 0.7 for 70% chance of starting full game.
    """
    return team_lam * goal_share * rotation_factor


def sot_lam_from_team(team_sot_lam: float, sot_share: float,
                      rotation_factor: float = 1.0) -> float:
    """Player SOT lambda from team SOT expectation."""
    return team_sot_lam * sot_share * rotation_factor


def p_1plus_sot(lam_sot: float) -> float:
    """P(player 1+ SOT) = 1 - e^(-lam_sot)."""
    return _poisson_tail_ge1(lam_sot)


def p_1plus_sot_2h(lam_sot_ft: float) -> float:
    """P(player 1+ SOT in 2H) ≈ 1 - e^(-0.55 * lam_sot). 2H share ≈ 55% of rate."""
    return 1.0 - math.exp(-0.55 * lam_sot_ft)


def clamp_to_band(p: float, band: tuple) -> float:
    """Clamp probability to the specified band (as 0-1)."""
    lo, hi = band[0] / 100.0, band[1] / 100.0
    return max(lo, min(hi, p))


def _check_driver_gate(p_int: int) -> bool:
    """Returns True if the driver gate is triggered (top half of 56-70 band)."""
    return SOT_DRIVER_GATE_MID <= p_int <= SOT_DRIVER_GATE_HI


def price_sot_prop(
    player_type: str,       # "main_striker" | "winger_AM"
    lam_sot_player: float,  # player's FT SOT lambda
    rotation_factor: float = 1.0,
    driver: Optional[str] = None,
    period: str = "FT",     # "FT" | "2H"
) -> PlayerPropResult:
    """
    Price a 1+ SOT (or 1+ SOT 2H) market with L10 band correction.

    Returns a PlayerPropResult with band-clamped output and gate info.
    """
    lam_adjusted = lam_sot_player * rotation_factor

    if period == "2H":
        raw_p = p_1plus_sot_2h(lam_adjusted)
        market = "1+ SOT 2H"
    else:
        raw_p = p_1plus_sot(lam_adjusted)
        market = "1+ SOT"

    band = SOT_BANDS.get(player_type, (42, 64))
    p_clamped = clamp_to_band(raw_p, band)
    p_int = int(round(p_clamped * 100))

    gate_triggered = _check_driver_gate(p_int)

    if gate_triggered and driver is None:
        # L10: no driver -> regress to lower edge of band
        p_int = band[0]
        p_clamped = band[0] / 100.0
        notes = "L10 driver gate: no driver provided, regressed to band lower edge."
        confidence = "LOW"
    elif gate_triggered:
        notes = f"L10 driver gate satisfied: {driver}"
        confidence = "MED"
    else:
        notes = ""
        confidence = "MED" if rotation_factor < 1.0 else "HIGH"

    return PlayerPropResult(
        market=market,
        probability=p_clamped,
        p_int=p_int,
        band_lo=band[0],
        band_hi=band[1],
        driver_gate_triggered=gate_triggered,
        driver_required="explicit written driver: recent per-90 SOT rate, expected service/shot volume, confirmed starter + heavy minutes" if gate_triggered else "",
        confidence=confidence,
        notes=notes,
    )


def price_goal_prop(
    player_type: str,       # "star_striker" | "secondary" | "midfielder"
    lam_player: float,      # already adjusted for rotation
) -> PlayerPropResult:
    """Price an anytime goal prop."""
    raw_p = anytime_goal(lam_player)
    band = GOAL_BANDS.get(player_type, (8, 45))
    p_clamped = clamp_to_band(raw_p, band)
    p_int = int(round(p_clamped * 100))

    gate_triggered = _check_driver_gate(p_int)

    return PlayerPropResult(
        market="anytime goal",
        probability=p_clamped,
        p_int=p_int,
        band_lo=band[0],
        band_hi=band[1],
        driver_gate_triggered=gate_triggered,
        driver_required="explicit driver required in 56-70 band" if gate_triggered else "",
        confidence="MED",
    )


def price_score_or_assist(
    p_goal: float,
    player_role: str = "creator",
) -> PlayerPropResult:
    """
    Score-or-assist = goal × multiplier, overlap-corrected.
    creator: ×1.5-1.8; pure 9: ×1.2-1.4.
    """
    mult_lo, mult_hi = SOA_MULTIPLIER.get(player_role, (1.3, 1.5))
    mult = (mult_lo + mult_hi) / 2.0
    raw_p = min(0.99, p_goal * mult)
    p_int = int(round(raw_p * 100))
    p_int = max(1, min(99, p_int))

    gate_triggered = _check_driver_gate(p_int)

    return PlayerPropResult(
        market="score or assist",
        probability=raw_p,
        p_int=p_int,
        band_lo=0,
        band_hi=99,
        driver_gate_triggered=gate_triggered,
        driver_required="explicit driver required in 56-70 band" if gate_triggered else "",
        confidence="MED",
        notes=f"multiplier {mult:.2f} ({player_role})",
    )


def player_props(
    team_lam: float,
    team_sot_lam: float,
    goal_share: float,
    sot_share: float,
    player_type: str = "main_striker",
    rotation_factor: float = 1.0,
    sot_driver: Optional[str] = None,
) -> dict:
    """
    Convenience: price all standard player props for one player.
    Returns dict of market_name -> PlayerPropResult.
    """
    lam_g = player_lam(team_lam, goal_share, rotation_factor)
    lam_s = sot_lam_from_team(team_sot_lam, sot_share, rotation_factor)

    goal_res = price_goal_prop(player_type, lam_g)
    sot_res = price_sot_prop(player_type, lam_s, 1.0, sot_driver)  # rotation already in lam_s
    sot_2h_res = price_sot_prop(player_type, lam_s, 1.0, sot_driver, period="2H")
    soa_res = price_score_or_assist(goal_res.probability)

    return {
        "anytime_goal": goal_res,
        "1plus_sot": sot_res,
        "1plus_sot_2h": sot_2h_res,
        "score_or_assist": soa_res,
    }
