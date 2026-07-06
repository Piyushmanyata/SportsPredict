"""Lambda engine (spec §5.2 / §5.2.1).

Fit total goals T from the O/U 2.5 anchor, split T into team rates so the
Poisson score grid reproduces the devigged 1X2, then read every goal-flavoured
market off closed forms. Dixon-Coles / overdispersion is a small documented
tilt (cap +/-3 combined), applied by the caller — never silently.
"""

from __future__ import annotations

import math

GRID_MAX = 12  # goals per team in the exact score grid (P(>12) ~ 0 at these T)


def pois_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def pois_cdf(k: int, lam: float) -> float:
    return sum(pois_pmf(i, lam) for i in range(k + 1))


def pois_sf(k: int, lam: float) -> float:
    """P(N >= k)."""
    return 1.0 - pois_cdf(k - 1, lam)


def t_from_over25(p_over: float) -> float:
    """Solve P(Poisson(T) >= 3) = p_over for T by bisection.

    p_over is 0-1 (pass 0.51, not 51). Spec grid: 0.51 -> T ~ 2.7.
    """
    lo, hi = 0.2, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if pois_sf(3, mid) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def one_x_two(lam_a: float, lam_b: float) -> tuple[float, float, float]:
    """(P(A win), P(draw), P(B win)) from the independent-Poisson score grid."""
    pa = [pois_pmf(i, lam_a) for i in range(GRID_MAX + 1)]
    pb = [pois_pmf(j, lam_b) for j in range(GRID_MAX + 1)]
    win = draw = loss = 0.0
    for i in range(GRID_MAX + 1):
        for j in range(GRID_MAX + 1):
            p = pa[i] * pb[j]
            if i > j:
                win += p
            elif i == j:
                draw += p
            else:
                loss += p
    return win, draw, loss


def fit_split(t: float, p_home_win: float) -> tuple[float, float]:
    """Find (lam_a, lam_b) with lam_a + lam_b = t reproducing the devigged
    home-win probability (0-1) on the Poisson grid. Bisection on lam_a."""
    lo, hi = 0.05, t - 0.05
    for _ in range(60):
        mid = (lo + hi) / 2.0
        w, _, _ = one_x_two(mid, t - mid)
        if w < p_home_win:
            lo = mid
        else:
            hi = mid
    lam_a = (lo + hi) / 2.0
    return lam_a, t - lam_a


# --- §5.2 closed forms (all return 0-1) ---

def p_scores(lam: float) -> float:
    return 1.0 - math.exp(-lam)


def p_scores_2h(lam: float) -> float:
    return 1.0 - math.exp(-0.55 * lam)


def p_scores_1h(lam: float) -> float:
    return 1.0 - math.exp(-0.45 * lam)


def p_btts(lam_a: float, lam_b: float) -> float:
    return (1.0 - math.exp(-lam_a)) * (1.0 - math.exp(-lam_b))


def p_1_1(lam_a: float, lam_b: float) -> float:
    return lam_a * lam_b * math.exp(-(lam_a + lam_b))


def p_clean_sheet_a(lam_b: float) -> float:
    return math.exp(-lam_b)


def p_btts_and_3plus(lam_a: float, lam_b: float) -> float:
    """BTTS AND 3+ total goals = BTTS - P(1-1). Never multiply marginals (§5.2).
    L6: read this off the grid at the anchor-implied T, never freestyle below."""
    return p_btts(lam_a, lam_b) - p_1_1(lam_a, lam_b)


def p_total_goals_geq(k: int, t: float) -> float:
    """P(total goals >= k), archetype #2 ('3 or more' -> k=3)."""
    return pois_sf(k, t)


def p_2h_goals_geq(k: int, t: float) -> float:
    """P(2H goals >= k) with 2H share 0.55 of T (archetype #7 variant)."""
    return pois_sf(k, 0.55 * t)


def dixon_coles_tilt(base_p: int, kind: str, strength: int = 2,
                     cap: int = 3) -> tuple[int, str]:
    """Documented DC/overdispersion tilt (§5.2/§5.2.1). One adjustment, not two.

    kind: 'draw_flavored' (+), 'btts_over' (-), 'blowout_over' (+ in clear
    mismatches only). Returns (tilted integer p, log line). strength 1-3.
    """
    s = max(1, min(cap, strength))
    delta = {"draw_flavored": s, "btts_over": -min(2, s), "blowout_over": s}[kind]
    return base_p + delta, f"overdispersion-tilt {delta:+d} ({kind})"
