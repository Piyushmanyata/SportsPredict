"""Lambda engine: derive every market from two anchored numbers (spec section 5.2, 5.2.1).

Given the devigged Over 2.5 price, solve for the total-goals Poisson mean T,
then split T into per-team lambdas to reproduce the devigged 1X2. All
downstream markets (BTTS, clean sheets, half splits, ...) are closed forms
of lambda_a, lambda_b, T.
"""

import math

REFERENCE_SPLITS = {
    "even": (1.35, 1.35),
    "moderate_favorite": (1.65, 1.05),
    "strong_favorite": (2.0, 0.75),
    "heavy_favorite": (2.4, 0.55),
}


def poisson_pmf(lam, k):
    """P(N = k) for Poisson(lam)."""
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_cdf(lam, k):
    """P(N <= k) for Poisson(lam)."""
    return sum(poisson_pmf(lam, i) for i in range(k + 1))


def total_goals_from_over25(p_over25, lo=0.3, hi=8.0, iters=80):
    """Solve for T such that 1 - poisson_cdf(T, 2) == p_over25 (P(3+ goals))."""
    target = 1.0 - p_over25
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if poisson_cdf(mid, 2) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def p_zero_zero(T):
    """P(0-0): exp(-lamA)*exp(-lamB) = exp(-T), independent of the A/B split."""
    return math.exp(-T)


def p_2h_at_least_2(T, second_half_share=0.55):
    """P(2+ goals in the second half), using lam_2h = second_half_share * T."""
    lam_2h = second_half_share * T
    return 1.0 - poisson_cdf(lam_2h, 1)


def team_scores(lam):
    """P(team scores >= 1) = 1 - exp(-lam)."""
    return 1.0 - math.exp(-lam)


def team_scores_2h(lam, share=0.55):
    """P(team scores in the second half)."""
    return 1.0 - math.exp(-share * lam)


def team_scores_1h(lam, share=0.45):
    """P(team scores in the first half)."""
    return 1.0 - math.exp(-share * lam)


def btts(lam_a, lam_b):
    """P(both teams score) under independent Poisson."""
    return (1.0 - math.exp(-lam_a)) * (1.0 - math.exp(-lam_b))


def p_1_1(lam_a, lam_b):
    """P(final score is exactly 1-1)."""
    return lam_a * lam_b * math.exp(-(lam_a + lam_b))


def clean_sheet(lam_opponent):
    """P(a team keeps a clean sheet) = P(opponent scores 0) = exp(-lam_opponent)."""
    return math.exp(-lam_opponent)


def btts_and_3plus(lam_a, lam_b):
    """P(BTTS AND 3+ total goals) = P(BTTS) - P(1-1).

    Never compute this by multiplying the two marginals -- BTTS and the
    3+ goals event are correlated (1-1 is BTTS but not 3+), so the exact
    identity is the difference above, not a product.
    """
    return btts(lam_a, lam_b) - p_1_1(lam_a, lam_b)


def win_draw_loss(lam_a, lam_b, max_goals=15):
    """Exact independent-Poisson 1X2 via double summation over the goal grid."""
    win_a = draw = win_b = 0.0
    for a in range(max_goals + 1):
        pa = poisson_pmf(lam_a, a)
        for b in range(max_goals + 1):
            pb = poisson_pmf(lam_b, b)
            p = pa * pb
            if a > b:
                win_a += p
            elif a == b:
                draw += p
            else:
                win_b += p
    return win_a, draw, win_b


def dixon_coles_overdispersion_tilt(probs, favor_draw_low_scores, cap_pts=3.0):
    """Capped tilt combining the Dixon-Coles caveat (5.2) and overdispersion note (5.2.1).

    Nudges draw/clean-sheet/under-flavored keys one way and btts/over-flavored
    keys the other, each moved by at most cap_pts percentage points. The two
    spec effects share one capped budget per v8 -- do not apply this twice.
    """
    cap = cap_pts / 100.0
    sign = 1.0 if favor_draw_low_scores else -1.0
    out = dict(probs)
    for key, p in probs.items():
        lowered = key.lower()
        if any(tag in lowered for tag in ("draw", "clean_sheet", "under")):
            out[key] = min(1.0, max(0.0, p + sign * cap))
        elif any(tag in lowered for tag in ("btts", "over")):
            out[key] = min(1.0, max(0.0, p - sign * cap))
    return out


if __name__ == "__main__":
    # 1. Totals grid (T from Over 2.5, then P(0-0)/P(2H>=2) exact closed forms).
    totals_grid = [
        (0.32, 2.0, 14, 30),
        (0.38, 2.2, 11, 34),
        (0.46, 2.5, 8, 40),
        (0.51, 2.7, 7, 44),
        (0.58, 3.0, 5, 49),
        (0.64, 3.3, 4, 54),
    ]
    for p_over25, T_table, p00_pct, p2h_pct in totals_grid:
        T = total_goals_from_over25(p_over25)
        assert abs(T - T_table) < 0.05, (p_over25, T, T_table)
        assert abs(p_zero_zero(T) - p00_pct / 100.0) < 0.02, (T, p_zero_zero(T), p00_pct)
        assert abs(p_2h_at_least_2(T) - p2h_pct / 100.0) < 0.02, (T, p_2h_at_least_2(T), p2h_pct)
    print("check 1 (totals grid) OK")

    # 2. BTTS / combo grid at the reference splits.
    btts_grid = [
        (1.35, 1.35, 55, 12, 43),
        (1.65, 1.05, 52, 12, 41),
        (2.0, 0.75, 46, 10, 36),
        (2.4, 0.55, 38, 7, 32),
    ]
    for la, lb, btts_pct, p11_pct, combo_pct in btts_grid:
        assert abs(btts(la, lb) - btts_pct / 100.0) < 0.015
        assert abs(p_1_1(la, lb) - p11_pct / 100.0) < 0.015
        assert abs(btts_and_3plus(la, lb) - combo_pct / 100.0) < 0.02
    print("check 2 (BTTS/combo grid) OK")

    # 3. win_draw_loss sanity (exact for the even split; monotone/sums-to-1 elsewhere --
    #    the spec explicitly warns these reference splits are illustrative labels, not an
    #    exact 1X2 mapping, since real markets are not pure independent Poisson).
    wa, d, wb = win_draw_loss(1.35, 1.35)
    assert abs(wa - wb) < 0.005
    assert abs(wa - 0.371) < 0.02 and abs(d - 0.258) < 0.02
    assert win_draw_loss(2.0, 0.75)[0] > win_draw_loss(1.35, 1.35)[0]
    assert abs(sum(win_draw_loss(2.0, 0.75)) - 1.0) < 1e-6
    print("check 3 (win_draw_loss) OK")

    # 4. Dixon-Coles / overdispersion tilt, capped.
    start = {"draw": 0.26, "btts": 0.55}
    tilted = dixon_coles_overdispersion_tilt(start, favor_draw_low_scores=True, cap_pts=3.0)
    assert tilted["draw"] > start["draw"] and tilted["draw"] - start["draw"] <= 0.03 + 1e-9
    assert tilted["btts"] < start["btts"] and start["btts"] - tilted["btts"] <= 0.03 + 1e-9
    print("check 4 (Dixon-Coles/overdispersion tilt) OK")

    print("lambda_engine.py: all checks passed")
