"""Player-prop engine, lineup-gated per lesson L7 (spec section 5.6, ledger L10 in section 10).

Player lambdas are a share of the team's total attacking rate. Rotation
risk discounts that allocated share (the input), never the final output
probability directly, so every derived prop for that player stays
coherent with the anchored team totals.
"""

import math

GOAL_SHARE_BANDS = {
    "star_striker": (0.32, 0.45),
    "secondary": (0.18, 0.28),
    "mid": (0.08, 0.15),
}

# v8/L10-corrected bands. The old v7 star_striker SOT band (0.60-0.72) is
# RETIRED: at @118 the 56-70 band ran -16.8pt hot (n=18), with striker-SOT
# calls as its core. Do not resurrect the v7 band.
SOT_BANDS_V8 = {
    "star_striker": (0.52, 0.64),
    "winger_am": (0.42, 0.56),
}

_SCORE_OR_ASSIST_MULTIPLIERS = {
    "creator": 1.65,
    "pure_9": 1.3,
}


def anytime_goal_prob(lam_player):
    """P(player scores anytime) = 1 - exp(-lam_player)."""
    return 1.0 - math.exp(-lam_player)


def sot_prob(lam_player_sot):
    """P(player records 1+ SOT) = 1 - exp(-lam_player_sot)."""
    return 1.0 - math.exp(-lam_player_sot)


def sot_2h_prob(lam_player_sot_ft, share=0.55):
    """P(player records 1+ SOT in the second half)."""
    return 1.0 - math.exp(-share * lam_player_sot_ft)


def score_or_assist_prob(goal_prob, role):
    """P(score or assist), scaling goal_prob by a role-dependent multiplier, capped at 0.95."""
    if role not in _SCORE_OR_ASSIST_MULTIPLIERS:
        raise ValueError(f"unknown role: {role!r}, expected one of {list(_SCORE_OR_ASSIST_MULTIPLIERS)}")
    return min(0.95, goal_prob * _SCORE_OR_ASSIST_MULTIPLIERS[role])


def apply_rotation_discount(lam_player, rotation_factor):
    """L7: discount the player's allocated share of team lambda, not the final output."""
    return lam_player * rotation_factor


def requires_l10_driver_gate(p):
    """L10 driver gate: top half of the 56-70 band (0.63-0.70) needs an explicit written driver."""
    return 0.63 <= p <= 0.70


if __name__ == "__main__":
    assert anytime_goal_prob(0.0) == 0.0
    assert abs(sot_prob(0.5) - (1 - math.exp(-0.5))) < 1e-9
    print("check 1 (goal/SOT closed forms) OK")

    assert abs(score_or_assist_prob(0.30, "creator") - 0.495) < 0.01
    assert abs(score_or_assist_prob(0.30, "pure_9") - 0.39) < 0.01
    assert score_or_assist_prob(0.9, "creator") <= 0.95
    try:
        score_or_assist_prob(0.3, "unknown")
        raise SystemExit("expected ValueError")
    except ValueError:
        pass
    print("check 2 (score-or-assist) OK")

    assert abs(apply_rotation_discount(1.0, 0.5) - 0.5) < 1e-9
    assert abs(apply_rotation_discount(1.0, 1.0) - 1.0) < 1e-9
    print("check 3 (rotation discount) OK")

    assert requires_l10_driver_gate(0.65) is True
    assert requires_l10_driver_gate(0.60) is False
    assert requires_l10_driver_gate(0.70) is True
    assert requires_l10_driver_gate(0.71) is False
    assert requires_l10_driver_gate(0.50) is False
    print("check 4 (L10 driver gate) OK")

    assert SOT_BANDS_V8["star_striker"] == (0.52, 0.64)
    print("check 5 (retired v7 band guard) OK")

    print("player_props.py: all checks passed")
