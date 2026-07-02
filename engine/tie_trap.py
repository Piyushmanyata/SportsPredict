"""Tie-trap engine: strict "Team A more X than Team B" markets (spec section 5.4).

For two independent Poisson(m) counts with EQUAL means m, the exact tie
mass is exp(-2m) * I0(2m) (a standard identity for the difference of two
i.i.d. Poisson variables evaluated at 0). The crowd tends to price these
strict comparisons near a tie-blind 50, which is the richest well in the
whole market taxonomy.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from besselfn import i0  # noqa: E402

STAT_MEANS = {
    "fouls": 11,
    "ft_corners": 4.5,
    "2h_corners": 2.4,
    "ht_corners": 2.1,
    "2h_sot": 2.0,
    "cards": 1.8,
    "offsides": 1.5,
}


def tie_probability(m):
    """Exact tie mass for two independent Poisson(m) counts with equal means."""
    return math.exp(-2 * m) * i0(2 * m)


def p_a_more_even(m):
    """P(A more) in an even matchup: the non-tie mass split evenly."""
    return (1.0 - tie_probability(m)) / 2.0


def skewed_split(m, favored):
    """Non-tie mass split per the spec's documented strength skew (60/40 default).

    This is a judgement-call band, not an exact formula: the spec observes
    favored-side outcomes roughly 44-52% and weak-side roughly 27-36% once
    combined with typical tie mass -- sanity-check any call against those
    bands rather than treating this split as exact.
    """
    non_tie = 1.0 - tie_probability(m)
    conditional_share = 0.60 if favored else 0.40
    return non_tie * conditional_share


if __name__ == "__main__":
    rows = [
        ("fouls", 8.56, 45.72),
        ("ft_corners", 13.50, 43.25),
        ("2h_corners", 18.76, 40.62),
        ("ht_corners", 20.16, 39.92),
        ("2h_sot", 20.70, 39.65),
        ("cards", 21.93, 39.03),
        ("offsides", 24.30, 37.85),
    ]
    for stat, expected_tie_pct, expected_a_more_pct in rows:
        m = STAT_MEANS[stat]
        tie = tie_probability(m) * 100
        a_more = p_a_more_even(m) * 100
        assert abs(tie - expected_tie_pct) < 0.5, (stat, tie, expected_tie_pct)
        assert abs(a_more - expected_a_more_pct) < 0.5, (stat, a_more, expected_a_more_pct)
        print(f"{stat:12s} tie={tie:.2f}% a_more={a_more:.2f}% OK")

    assert skewed_split(11, favored=True) > skewed_split(11, favored=False)
    print("check (favored > weak skew) OK")

    print("tie_trap.py: all checks passed")
