"""§5.6 player-prop engine (lineup-gated -- L7), with the v8/L10 band fix.

L10 (ACTIVE, n=18 @118): the v7 main-striker 1+SOT band (60-72) ran -16.8pt
hot and is RETIRED. Corrective is input-side only (D2/D11 intact): the band
starts lower, and anything landing in the top half of 56-70 needs a written
driver or regresses to the band floor. This is not an output ceiling.
"""

GOAL_BANDS = {
    "star_striker": (0.32, 0.45),
    "secondary": (0.18, 0.28),
    "mid": (0.08, 0.15),
}

SOT_BANDS = {
    "main_striker": (0.52, 0.64),          # v8/L10 corrected band
    "winger_am": (0.42, 0.56),
}
SOT_BAND_RETIRED_V7 = {"main_striker": (0.60, 0.72)}  # retired, do not use

SCORE_OR_ASSIST_MULTIPLIER = {
    "creator": (1.5, 1.8),
    "pure_nine": (1.2, 1.4),
}

DRIVER_GATE_LOW = 0.56
DRIVER_GATE_HIGH = 0.70
DRIVER_GATE_MIDPOINT = 0.63  # "top half of 56-70"


def driver_gate(p, has_written_driver, band_floor=None):
    """§5.6 driver gate, generalized to any modeled market in 56-70 (not just
    SOT props). If p lands in the top half of 56-70 with no written driver
    (recent per-90 rate, expected volume, confirmed starter+minutes), regress
    to the lower band edge instead of submitting the unsupported number.
    """
    in_top_half = DRIVER_GATE_MIDPOINT <= p <= DRIVER_GATE_HIGH
    if in_top_half and not has_written_driver:
        floor = band_floor if band_floor is not None else DRIVER_GATE_LOW
        return {"allowed_p": floor, "gated": True}
    return {"allowed_p": p, "gated": False}


def score_or_assist(p_goal, player_type="creator"):
    lo, hi = SCORE_OR_ASSIST_MULTIPLIER[player_type]
    return (min(1.0, p_goal * lo), min(1.0, p_goal * hi))


def sot_in_2h(p_sot_ft, share=0.55):
    """'1+ SOT in 2H' derived from the FT SOT prop, not estimated separately."""
    import math
    lam = -math.log(1 - p_sot_ft) if p_sot_ft < 1 else float("inf")
    return 1 - math.exp(-share * lam)


def rotation_adjust_lambda(lam_player_share_of_team, rotation_factor):
    """L7: reduce the player's allocated share of team lambda under rotation
    risk (input-side), then derive ALL downstream player props from that
    adjusted lambda -- never depress the final output probability directly.
    rotation_factor in (0,1], e.g. 0.6 for a confirmed partial-minutes sub risk.
    """
    return lam_player_share_of_team * rotation_factor
