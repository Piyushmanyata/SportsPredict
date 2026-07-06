"""§5.2 lambda engine: derive everything from two anchored numbers (T, split).

Dixon-Coles + overdispersion tilt (§5.2 / §5.2.1, hardened v8): raw Poisson
slightly underprices draws/low scores in tight internationals, and slightly
underprices the fat 4+ tail in mismatches. Both are capped, documented,
input-side tilts -- never a free-form override of the anchor (§5.10).
"""
import math

from .poisson import poisson_pmf, poisson_cdf, poisson_sf, poisson_greater_prob

TOTALS_GRID = [
    # P(Over2.5), T, P(<=2 goals), P(0-0), P(2H>=2 goals)
    (0.32, 2.0, 0.68, 0.14, 0.30),
    (0.38, 2.2, 0.62, 0.11, 0.34),
    (0.46, 2.5, 0.54, 0.08, 0.40),
    (0.51, 2.7, 0.49, 0.07, 0.44),
    (0.58, 3.0, 0.42, 0.05, 0.49),
    (0.64, 3.3, 0.36, 0.04, 0.54),
]

REFERENCE_SPLITS = {
    # label -> (lam_a, lam_b) at T ~= 2.7, and the 1X2 they reproduce (~%)
    "even": (1.35, 1.35, {"home": 37, "draw": 26, "away": 37}),
    "moderate_favorite": (1.65, 1.05, {"home": 48, "draw": 25, "away": 27}),
    "strong_favorite": (2.0, 0.75, {"home": 60, "draw": 16, "away": 24}),
}

BTTS_GRID = {
    # split label -> (BTTS, P(1-1), BTTS ^ 3+)
    "even_1.35_1.35": (0.55, 0.12, 0.43),
    "moderate_fav_1.65_1.05": (0.52, 0.12, 0.41),
    "strong_2.0_0.75": (0.46, 0.10, 0.36),
    "heavy_2.4_0.55": (0.38, 0.07, 0.32),
}

DC_TILT_CAP = 3       # capped +/-3, per §5.2.1
OVERDISPERSION_TILT_CAP = 3  # merged with DC tilt, do not double count


def interpolate_T(p_over25):
    """Linear interpolation of T from the O/U 2.5 totals grid (§5.2)."""
    grid = TOTALS_GRID
    if p_over25 <= grid[0][0]:
        return grid[0][1]
    if p_over25 >= grid[-1][0]:
        return grid[-1][1]
    for (p0, t0, *_), (p1, t1, *_) in zip(grid, grid[1:]):
        if p0 <= p_over25 <= p1:
            frac = (p_over25 - p0) / (p1 - p0)
            return t0 + frac * (t1 - t0)
    return grid[-1][1]


def p_over(threshold_goals, T):
    """P(total goals > threshold_goals) via exact Poisson(T)."""
    return poisson_sf(threshold_goals, T)


def p_at_most(k, T):
    return poisson_cdf(k, T)


def p_00(T):
    return poisson_pmf(0, T)


def p_scores(lam):
    return 1 - math.exp(-lam)


def p_scores_2h(lam):
    return 1 - math.exp(-0.55 * lam)


def p_scores_1h(lam):
    return 1 - math.exp(-0.45 * lam)


def p_btts(lam_a, lam_b):
    return (1 - math.exp(-lam_a)) * (1 - math.exp(-lam_b))


def p_11(lam_a, lam_b):
    T = lam_a + lam_b
    return lam_a * lam_b * math.exp(-T)


def p_btts_and_3plus(lam_a, lam_b):
    """Never multiply marginals (correlated) -- P(BTTS) - P(1-1)."""
    return p_btts(lam_a, lam_b) - p_11(lam_a, lam_b)


def p_clean_sheet(lam_opponent):
    return math.exp(-lam_opponent)


def poisson_1x2(lam_a, lam_b, max_goals=15):
    """Exact home/draw/away from independent Poisson(lam_a), Poisson(lam_b)."""
    p_draw = sum(poisson_pmf(i, lam_a) * poisson_pmf(i, lam_b) for i in range(max_goals + 1))
    p_home = poisson_greater_prob(lam_a, lam_b, max_goals)
    p_away = poisson_greater_prob(lam_b, lam_a, max_goals)
    return {"home": p_home, "draw": p_draw, "away": p_away}


def solve_split(T, target_home, target_away, steps=2000):
    """Grid-search lam_home in (0, T) so poisson_1x2 reproduces the devigged
    1X2 as closely as possible -- 'calibrate the split to reproduce the
    devigged 1X2, not the labels' (§5.2).
    """
    best = None
    for i in range(1, steps):
        lam_home = T * i / steps
        lam_away = T - lam_home
        result = poisson_1x2(lam_home, lam_away)
        err = (result["home"] - target_home) ** 2 + (result["away"] - target_away) ** 2
        if best is None or err < best[0]:
            best = (err, lam_home, lam_away, result)
    _, lam_home, lam_away, result = best
    return {"lam_home": lam_home, "lam_away": lam_away, "implied_1x2": result}


def apply_capped_tilt(base_p, tilt_pts, cap=DC_TILT_CAP):
    """Apply a Dixon-Coles / overdispersion tilt, capped at +/-cap points.
    tilt_pts is signed, in probability points (e.g. +2 means +0.02).
    """
    tilt = max(-cap, min(cap, tilt_pts))
    return max(0.0, min(1.0, base_p + tilt / 100.0))
