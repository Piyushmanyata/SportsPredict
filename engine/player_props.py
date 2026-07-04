"""§5.6 — player-prop engine (lineup-gated, L7/L10)."""
import math

from .utils import clamp

STRIKER_GOAL_BAND = (32, 45)
SECONDARY_GOAL_BAND = (18, 28)
MID_GOAL_BAND = (8, 15)

# v8/L10: main-striker 1+SOT band corrected 60-72 -> 52-64 (@118 audit).
STRIKER_SOT_BAND = (52, 64)
WINGER_AM_SOT_BAND = (42, 56)

# §5.6 driver gate: any modeled p landing in the top half of 56-70 needs an
# explicit written driver, else regress to the band's lower edge.
DRIVER_GATE_BAND = (56, 70)
DRIVER_GATE_UPPER_HALF_START = 63

SCORE_OR_ASSIST_MULTIPLIER = {"creator": 1.65, "pure9": 1.3}  # midpoints of §5.6 ranges


def anytime_goal_prob(lam_player):
    return 1 - math.exp(-lam_player)


def sot_2h_prob(lam_sot_player):
    return 1 - math.exp(-0.55 * lam_sot_player)


def score_or_assist_prob(goal_prob, role="creator"):
    mult = SCORE_OR_ASSIST_MULTIPLIER[role]
    return clamp(goal_prob * mult, 0, 0.99)


def apply_driver_gate(p_pct, has_written_driver, band_lower_edge):
    """§5.6: no landing in 63-70 without a stated driver (recent per-90 rate,
    expected volume, confirmed starter+minutes) — else regress to the floor."""
    lo, hi = DRIVER_GATE_BAND
    if DRIVER_GATE_UPPER_HALF_START <= p_pct <= hi and not has_written_driver:
        return band_lower_edge
    return p_pct


def rotation_adjust_lambda(lam_player_share, rotation_factor):
    """L7: discount the player's *share of team lambda* under rotation risk,
    not the final output — keeps all derived props coherent with team totals."""
    return lam_player_share * (1 - rotation_factor)
