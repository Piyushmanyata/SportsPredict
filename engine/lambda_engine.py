"""§5.2 / §5.2.1 — lambda engine: derive everything from two anchored numbers."""
import math

from .utils import poisson_cdf, poisson_pmf, bisect_root, clamp

# §5.2 reference O/U 2.5 -> T grid, kept for citation/cross-check only —
# fit_T_from_over25() below computes the exact value instead of interpolating.
REFERENCE_OU_TABLE = {
    0.32: 2.0, 0.38: 2.2, 0.46: 2.5, 0.51: 2.7, 0.58: 3.0, 0.64: 3.3,
}

REFERENCE_SPLITS = {
    "even": (1.35, 1.35),
    "moderate_favorite": (1.65, 1.05),
    "strong_favorite": (2.0, 0.75),
}


def fit_T_from_over25(p_over25, lo=0.3, hi=6.0):
    """Exact Poisson solve for T s.t. P(total > 2.5) = p_over25 (sum of two
    independent Poissons is Poisson(T), so the split doesn't matter here)."""
    return bisect_root(lambda T: (1 - poisson_cdf(2, T)) - p_over25, lo, hi)


def _win_draw_away(lamA, lamB, kmax=60):
    pmf_a = [poisson_pmf(k, lamA) for k in range(kmax)]
    pmf_b = [poisson_pmf(k, lamB) for k in range(kmax)]
    cum_b = [0.0]
    for x in pmf_b:
        cum_b.append(cum_b[-1] + x)
    p_draw = sum(a * b for a, b in zip(pmf_a, pmf_b))
    p_home = sum(pmf_a[k] * cum_b[k] for k in range(kmax))  # A > B
    cum_a = [0.0]
    for x in pmf_a:
        cum_a.append(cum_a[-1] + x)
    p_away = sum(pmf_b[k] * cum_a[k] for k in range(kmax))  # B > A
    return p_home, p_draw, p_away


def split_lambdas(T, target_home_win, lo=0.05, hi=None):
    """Find lamA (lamB = T - lamA) reproducing a target devigged home-win
    probability — calibrate the split to the 1X2, never freestyle it."""
    hi = hi if hi is not None else T - 0.05

    def f(lamA):
        ph, _, _ = _win_draw_away(lamA, T - lamA)
        return ph - target_home_win

    lamA = bisect_root(f, lo, hi)
    if lamA is None:
        return None
    return lamA, T - lamA


def win_draw_away(lamA, lamB):
    return _win_draw_away(lamA, lamB)


def p_scores(lam):
    return 1 - math.exp(-lam)


def p_scores_2h(lam):
    return 1 - math.exp(-0.55 * lam)


def p_scores_1h(lam):
    return 1 - math.exp(-0.45 * lam)


def p_btts(lamA, lamB):
    return (1 - math.exp(-lamA)) * (1 - math.exp(-lamB))


def p_11(lamA, lamB):
    T = lamA + lamB
    return lamA * lamB * math.exp(-T)


def p_btts_3plus(lamA, lamB):
    """§5.2 — never multiply marginals; BTTS and 3+ goals are correlated."""
    return p_btts(lamA, lamB) - p_11(lamA, lamB)


def p_clean_sheet(lam_opponent):
    return math.exp(-lam_opponent)


def apply_capped_tilt(base_prob_pct, tilt_pts, cap=3):
    """§5.2 Dixon-Coles + §5.2.1 overdispersion tilt — combined and capped at
    +-3, never double-counted (they're the same mechanism, not two shades)."""
    tilt = clamp(tilt_pts, -cap, cap)
    return clamp(base_prob_pct + tilt, 0, 100)
