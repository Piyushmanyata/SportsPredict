"""§5.5 — threshold & state tables (exact Poisson / Bessel-equivalent)."""
from .utils import poisson_cdf, poisson_pmf

# Reference tables from §5.5, kept for citation/cross-check against the
# exact functions below (p_at_least, p_ht_tied, p_ht_both_sot).
CARDS_TABLE = {  # lam_cards -> (P(>=4 total), P(>=2 in 2H))
    2.8: (31, 52), 3.2: (40, 59), 3.5: (46, 64), 4.0: (57, 71), 4.5: (66, 77),
}
CORNERS_GE5_TABLE = {3.0: 19, 3.5: 28, 4.0: 37, 4.5: 47, 5.0: 56, 5.5: 64, 6.0: 72}
SOT_GE2_TABLE = {1.0: 26, 1.5: 44, 2.0: 59, 2.5: 71, 3.0: 80, 3.5: 86, 4.0: 91, 4.5: 94}
OFFSIDES_GE2_TABLE = {0.8: 19, 1.0: 26, 1.2: 34, 1.5: 44, 1.8: 54, 2.0: 59}

HT_TIED_CEILING = 47  # L9 — do not exceed unless anchor-implied T < 2.2


def p_at_least(k, lam):
    return 1 - poisson_cdf(k - 1, lam)


def p_ht_tied(lamA_ht, lamB_ht, kmax=40):
    """P(HT tied), including 0-0 — Skellam P(diff=0) via direct convolution."""
    return sum(poisson_pmf(k, lamA_ht) * poisson_pmf(k, lamB_ht) for k in range(kmax))


def p_ht_both_sot(lamA_ht_sot, lamB_ht_sot):
    return p_at_least(1, lamA_ht_sot) * p_at_least(1, lamB_ht_sot)


def enforce_ht_tied_ceiling(p, anchor_implied_T, ceiling=HT_TIED_CEILING):
    """L9: don't exceed 47 on HT-tied unless anchor-implied T < 2.2."""
    if anchor_implied_T is not None and anchor_implied_T < 2.2:
        return p
    return min(p, ceiling)
