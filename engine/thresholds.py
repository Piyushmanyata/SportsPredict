"""Threshold & state tables — exact Poisson / Bessel (spec §5.5).

Covers archetype #7 threshold counts, #9 HT-tied, #10 HT both-teams-SOT.
"""

from __future__ import annotations

import math

from engine.constants import HT_SOT_SHARE, HT_TIED_CEILING, SECOND_HALF_CARD_SHARE
from engine.goals import pois_sf
from engine.tietrap import bessel_i0


def p_geq(k: int, lam: float) -> float:
    """P(count >= k) for Poisson(lam): corners, SOT, offsides, cards, ..."""
    return pois_sf(k, lam)


def p_cards_4plus(match_cards_lam: float) -> float:
    return pois_sf(4, match_cards_lam)


def p_cards_2h_2plus(match_cards_lam: float) -> float:
    """2H card share ~ 0.62 of the match total."""
    return pois_sf(2, SECOND_HALF_CARD_SHARE * match_cards_lam)


def p_ht_tied(lam_a: float, lam_b: float) -> float:
    """'At halftime, will the match be tied?' (includes 0-0).

    Pass FULL-TIME team lambdas; HT share 0.45 is applied here.
    P = e^(-(la+lb)) * I0(2*sqrt(la*lb)) on the HT rates.
    Standing rule L9: do not exceed 47 unless anchor-implied T < 2.2.
    """
    la, lb = 0.45 * lam_a, 0.45 * lam_b
    x = 2.0 * math.sqrt(la * lb)
    if x < 25.0:
        return math.exp(-(la + lb)) * bessel_i0(x)
    return math.exp(-(la + lb) + x) * (1 + 1 / (8 * x)) / math.sqrt(2 * math.pi * x)


def ht_tied_capped(lam_a: float, lam_b: float) -> int:
    """Integer HT-tied p with the L9 ceiling applied (T >= 2.2 case)."""
    p = round(100 * p_ht_tied(lam_a, lam_b))
    if lam_a + lam_b >= 2.2:
        p = min(p, HT_TIED_CEILING)
    return p


def p_ht_both_sot(sot_lam_a: float, sot_lam_b: float) -> float:
    """'At halftime, both teams >= 1 SOT' — product of HT-SOT Poissons.

    Pass FULL-TIME team SOT lambdas; HT share 0.45 applied here.
    """
    pa = 1.0 - math.exp(-HT_SOT_SHARE * sot_lam_a)
    pb = 1.0 - math.exp(-HT_SOT_SHARE * sot_lam_b)
    return pa * pb
