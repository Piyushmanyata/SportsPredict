"""§5.5 — Threshold-count tails and half-time state markets (exact Poisson/Bessel).

Covers archetype #7 ("2+ offsides", "4+ total cards", "2+ cards in 2H",
"5+ corners", "2+ SOT", "2+ total goals in 2H"), #9 (HT tied) and #10
(HT both teams ≥1 SOT).
"""

from __future__ import annotations

import math

from .constants import CARDS_SHARE_2H, SHARE_1H
from .poisson import pois_cdf
from .tie_trap import _bessel_i0

HT_SOT_SHARE = 0.45  # §5.5 — HT share of FT SOT rate


def p_at_least(k: int, lam: float) -> float:
    """P(X ≥ k) for X ~ Poisson(lam). The workhorse for every §5.5 tail."""
    return 1.0 - pois_cdf(k - 1, lam)


def p_cards_4plus(lam_cards: float) -> float:
    return p_at_least(4, lam_cards)


def p_cards_2h_2plus(lam_cards: float) -> float:
    """2H card share ≈ 0.62 of the match cards λ."""
    return p_at_least(2, CARDS_SHARE_2H * lam_cards)


def ht_tied(lam_a: float, lam_b: float, ht_share: float = SHARE_1H) -> float:
    """Archetype #9 — P(tied at HT), includes 0-0.
    Two HT Poissons λa,λb = 0.45 × split → e^-(λa+λb) · I₀(2√(λaλb)).
    Standing rule L9: never exceed 0.47 unless anchor-implied T < 2.2."""
    la, lb = ht_share * lam_a, ht_share * lam_b
    return math.exp(-(la + lb)) * _bessel_i0(2.0 * math.sqrt(la * lb))


def ht_both_teams_sot(sot_lam_a: float, sot_lam_b: float) -> float:
    """Archetype #10 — P(both teams ≥1 SOT at HT). Product of HT-SOT Poissons.
    Args are FULL-TIME team SOT λs; HT share ≈ 0.45 applied here."""
    return ((1.0 - math.exp(-HT_SOT_SHARE * sot_lam_a))
            * (1.0 - math.exp(-HT_SOT_SHARE * sot_lam_b)))
