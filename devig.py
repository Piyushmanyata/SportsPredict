"""
Odds devigging utilities — §5.1 of spec.
Power devig mandatory when overround >5% AND favourite >65%.
Source trust: Betfair Exchange > Pinnacle > aggregators > soft book.
"""
from scipy.optimize import root_scalar


def implied(decimal_odds: float) -> float:
    """1/decimal → raw implied probability."""
    return 1.0 / decimal_odds


def multiplicative_devig_2way(odds_yes: float, odds_no: float):
    """Standard 2-way multiplicative devig. Returns (p_yes, p_no)."""
    i_yes = implied(odds_yes)
    i_no  = implied(odds_no)
    total = i_yes + i_no
    return i_yes / total, i_no / total


def multiplicative_devig_3way(odds_a: float, odds_draw: float, odds_b: float):
    """3-way multiplicative devig (1X2). Returns (p_a, p_draw, p_b)."""
    ia, id_, ib = implied(odds_a), implied(odds_draw), implied(odds_b)
    total = ia + id_ + ib
    return ia / total, id_ / total, ib / total


def power_devig(implied_probs: list) -> list:
    """
    Power devig: solve k s.t. Σ p_i^k = 1.
    Mandatory when overround >5% AND favourite >65% (§5.1).
    Falls back to multiplicative if solver fails.
    """
    def f(k):
        return sum(p**k for p in implied_probs) - 1.0
    try:
        result = root_scalar(f, bracket=[0.5, 2.0])
        k = result.root
        devd = [p**k for p in implied_probs]
        total = sum(devd)
        return [p / total for p in devd]
    except Exception:
        total = sum(implied_probs)
        return [p / total for p in implied_probs]


def devig_1x2(odds_a: float, odds_draw: float, odds_b: float, force_power: bool = False):
    """
    Devig a 1X2 market. Auto-selects power vs multiplicative per §5.1.
    Returns (p_a, p_draw, p_b) as floats summing to ~1.
    """
    ia, id_, ib = implied(odds_a), implied(odds_draw), implied(odds_b)
    overround = ia + id_ + ib - 1.0
    fav_implied = max(ia, id_, ib)
    if force_power or (overround > 0.05 and fav_implied > 0.65):
        result = power_devig([ia, id_, ib])
        return tuple(result)
    return multiplicative_devig_3way(odds_a, odds_draw, odds_b)


def devig_2way(odds_yes: float, odds_no: float, force_power: bool = False):
    """
    Devig a 2-way market (e.g. BTTS, O/U). Returns (p_yes, p_no).
    """
    iy, in_ = implied(odds_yes), implied(odds_no)
    overround = iy + in_ - 1.0
    fav_implied = max(iy, in_)
    if force_power or (overround > 0.05 and fav_implied > 0.65):
        result = power_devig([iy, in_])
        return tuple(result)
    return multiplicative_devig_2way(odds_yes, odds_no)


def blend_anchor_engine(anchor_p: float, engine_p: float,
                        anchored: bool = True) -> float:
    """
    Blend devigged anchor with engine estimate (§5.0).
    ANCHORED: 60-70% anchor / 30-40% fundamentals.
    MODELED:  ~50% fundamentals.
    """
    if anchored:
        return 0.65 * anchor_p + 0.35 * engine_p
    return 0.50 * anchor_p + 0.50 * engine_p


def parse_eu_odds(odds_str: str) -> float:
    """Parse European decimal odds from string, e.g. '2.10' → 2.10."""
    return float(odds_str.strip())


def lambda_from_1x2_ou(p_a_win: float, p_draw: float, p_b_win: float,
                        p_over25: float) -> tuple:
    """
    Derive (λ_A, λ_B) from devigged 1X2 + O/U 2.5 (§5.2).
    Uses the O/U to fix T, then adjusts split to match 1X2 within ±2 pts.
    Returns (lam_a, lam_b, T).
    """
    from engine import ou25_to_T, p_over25 as _p_over, _poisson_pmf
    T = ou25_to_T(p_over25)
    # Grid search for split ratio r = lam_a / T such that P(A win) matches
    best_r, best_err = 0.5, 1e9
    for r_int in range(20, 81):
        r = r_int / 100.0
        la = r * T
        lb = T - la
        # Compute P(A wins) via Poisson grid
        p_win = 0.0
        for ga in range(9):
            for gb in range(9):
                if ga > gb:
                    p_win += _poisson_pmf(la, ga) * _poisson_pmf(lb, gb)
        err = abs(p_win - p_a_win)
        if err < best_err:
            best_err, best_r = err, r
    lam_a = best_r * T
    lam_b = T - lam_a
    return lam_a, lam_b, T
