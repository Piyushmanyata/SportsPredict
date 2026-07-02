"""Threshold and state tables: exact Poisson tails and HT Bessel forms (spec section 5.5).

Card/corner/SOT/offside threshold markets ("2+ offsides", "4+ total cards",
...) are plain Poisson tail probabilities. HT-tied and HT-both-SOT markets
use the same Bessel-based tie identity as tie_trap.py, scaled to the
first-half share of the full-time rate.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from besselfn import i0  # noqa: E402

HT_TIED_CEILING = 47


def _poisson_pmf(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _poisson_cdf(lam, k):
    return sum(_poisson_pmf(lam, i) for i in range(k + 1))


def poisson_at_least(lam, k):
    """P(N >= k) for Poisson(lam)."""
    return 1.0 - _poisson_cdf(lam, k - 1)


def cards_ge4_total(lam_cards):
    """P(4+ total match cards)."""
    return poisson_at_least(lam_cards, 4)


def cards_ge2_second_half(lam_cards_total, second_half_share=0.62):
    """P(2+ cards in the second half)."""
    return poisson_at_least(lam_cards_total * second_half_share, 2)


def team_corners_ge5(lam_team_corners):
    """P(a team takes 5+ corners)."""
    return poisson_at_least(lam_team_corners, 5)


def team_sot_ge2(lam_team_sot):
    """P(a team records 2+ shots on target)."""
    return poisson_at_least(lam_team_sot, 2)


def team_offsides_ge2(lam_team_offsides):
    """P(a team is caught offside 2+ times)."""
    return poisson_at_least(lam_team_offsides, 2)


def ht_tied(lam_a_ft, lam_b_ft, ht_share=0.45):
    """P(tied at half-time), using HT-scaled means and the exact Poisson-difference identity."""
    la = ht_share * lam_a_ft
    lb = ht_share * lam_b_ft
    return math.exp(-(la + lb)) * i0(2 * math.sqrt(la * lb))


def ht_both_teams_sot(lam_a_ft_sot, lam_b_ft_sot, ht_share=0.45):
    """P(both teams have 1+ SOT by half-time), independent HT-scaled Poissons."""
    return (1.0 - math.exp(-ht_share * lam_a_ft_sot)) * (1.0 - math.exp(-ht_share * lam_b_ft_sot))


if __name__ == "__main__":
    cards_rows = [(2.8, 31, 52), (3.2, 40, 59), (3.5, 46, 64), (4.0, 57, 71), (4.5, 66, 77)]
    for lam, exp_ge4, exp_2h in cards_rows:
        assert abs(cards_ge4_total(lam) * 100 - exp_ge4) < 1.0, lam
        assert abs(cards_ge2_second_half(lam) * 100 - exp_2h) < 1.0, lam
    print("check 1 (cards) OK")

    corner_rows = [(3.0, 19), (3.5, 28), (4.0, 37), (4.5, 47), (5.0, 56), (5.5, 64), (6.0, 72)]
    for lam, exp in corner_rows:
        assert abs(team_corners_ge5(lam) * 100 - exp) < 1.0, lam
    print("check 2 (corners) OK")

    sot_rows = [(1.0, 26), (1.5, 44), (2.0, 59), (2.5, 71), (3.0, 80), (3.5, 86), (4.0, 91), (4.5, 94)]
    for lam, exp in sot_rows:
        assert abs(team_sot_ge2(lam) * 100 - exp) < 1.0, lam
    print("check 3 (SOT) OK")

    offside_rows = [(0.8, 19), (1.0, 26), (1.2, 34), (1.5, 44), (1.8, 54), (2.0, 59)]
    for lam, exp in offside_rows:
        assert abs(team_offsides_ge2(lam) * 100 - exp) < 1.0, lam
    print("check 4 (offsides) OK")

    ht_tied_rows = [
        (1.1, 1.1, 47), (1.25, 1.25, 44), (1.35, 1.35, 42), (1.5, 1.5, 39),
        (1.65, 1.05, 41), (2.0, 0.75, 38), (2.4, 0.55, 34),
    ]
    for la, lb, exp in ht_tied_rows:
        assert abs(ht_tied(la, lb) * 100 - exp) < 1.5, (la, lb)
    print("check 5 (HT-tied) OK")

    ht_sot_rows = [(4.5, 4.5, 75), (4.0, 3.0, 62), (5.5, 3.0, 68), (6.0, 2.2, 59)]
    for la, lb, exp in ht_sot_rows:
        assert abs(ht_both_teams_sot(la, lb) * 100 - exp) < 1.5, (la, lb)
    print("check 6 (HT-both-SOT) OK")

    print("thresholds.py: all checks passed")
