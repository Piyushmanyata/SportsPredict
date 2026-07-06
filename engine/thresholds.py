"""§5.5 threshold & state tables -- exact Poisson / Bessel, general-lambda.

The spec's tables are worked examples at specific lambda values; these
functions reproduce them exactly for ANY lambda so a fresh match's actual
anchor-implied rate can be plugged in directly instead of eyeballing the
nearest table row.
"""
from .poisson import poisson_at_least, poisson_tie_prob

CARDS_2H_SHARE = 0.62
CORNER_TEAM_2H_SHARE = None  # not tabulated separately in the spec
SOT_2H_SHARE = 0.55
OFFSIDE_NO_SHARE_TABULATED = None
HT_GOAL_SHARE = 0.45


def p_cards_at_least(k, lam_cards):
    return poisson_at_least(k, lam_cards)


def p_cards_2h_at_least(k, lam_cards_total):
    return poisson_at_least(k, lam_cards_total * CARDS_2H_SHARE)


def p_corners_at_least(k, lam_corners_team):
    return poisson_at_least(k, lam_corners_team)


def p_sot_at_least(k, lam_sot_team):
    return poisson_at_least(k, lam_sot_team)


def p_offsides_at_least(k, lam_offsides_team):
    return poisson_at_least(k, lam_offsides_team)


def ht_tied(lam_a_total, lam_b_total, ht_share=HT_GOAL_SHARE, split=None):
    """P(tied at halftime), including 0-0.

    lam_a_total/lam_b_total are FULL-match team lambdas (or pass split=
    (lam_a_ht, lam_b_ht) directly if already HT-scaled).
    Standing rule (L9): do not exceed 47 unless anchor-implied T < 2.2.
    """
    if split is not None:
        lam_a_ht, lam_b_ht = split
    else:
        lam_a_ht, lam_b_ht = lam_a_total * ht_share, lam_b_total * ht_share
    return poisson_tie_prob(lam_a_ht, lam_b_ht)


def ht_both_sot(lam_a_ft_sot, lam_b_ft_sot, ht_share=0.45):
    """P(both teams have >=1 SOT at halftime)."""
    import math
    lam_a_ht = ht_share * lam_a_ft_sot
    lam_b_ht = ht_share * lam_b_ft_sot
    return (1 - math.exp(-lam_a_ht)) * (1 - math.exp(-lam_b_ht))


# Reference rows from the spec, kept for self_check.py validation only.
CARDS_TABLE = [
    # lam_cards, P(>=4 total), P(>=2 in 2H)
    (2.8, 31, 52), (3.2, 40, 59), (3.5, 46, 64), (4.0, 57, 71), (4.5, 66, 77),
]
CORNERS_GE5_TABLE = {3.0: 19, 3.5: 28, 4.0: 37, 4.5: 47, 5.0: 56, 5.5: 64, 6.0: 72}
SOT_GE2_TABLE = {1.0: 26, 1.5: 44, 2.0: 59, 2.5: 71, 3.0: 80, 3.5: 86, 4.0: 91, 4.5: 94}
OFFSIDES_GE2_TABLE = {0.8: 19, 1.0: 26, 1.2: 34, 1.5: 44, 1.8: 54, 2.0: 59}
HT_TIED_TABLE = [
    # label, T (even split unless noted), HT-tied %
    ("even_T2.2", 2.2, 47), ("even_T2.5", 2.5, 44), ("even_T2.7", 2.7, 42),
    ("even_T3.0", 3.0, 39), ("moderate_favorite", None, 41),
    ("strong_favorite", None, 38), ("heavy_favorite", None, 34),
]
HT_BOTH_SOT_TABLE = {
    (4.5, 4.5): 75, (4.0, 3.0): 62, (5.5, 3.0): 68, (6.0, 2.2): 59,
}
