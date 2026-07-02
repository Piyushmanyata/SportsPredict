"""Anchor extraction / devig (spec section 5.1).

Converts bookmaker decimal odds (which embed a bookmaker margin, the
"overround") into fair, devigged probabilities. Two methods:

- multiplicative: normalize implied probabilities so they sum to 1.
- power: solve for k such that sum(p_i ** k) == 1, then p_i ** k is the
  fair probability. Mandatory when overround is large AND there's a
  strong favorite, because the additive +1/-1 heuristic breaks down near
  the 0/1 boundary (it can push a probability outside [0, 1]).
"""

import math

SOURCE_TRUST_ORDER = (
    "Betfair Exchange",
    "Pinnacle",
    "consensus aggregators (Oddschecker/OddsPortal/Oddspedia)",
    "single soft book",
)
PREDICTION_MARKET_SOURCES = ("Polymarket", "Kalshi", "Smarkets", "Metaculus")
FRESHNESS_MAX_AGE_HOURS = 24
FRESHNESS_NEAR_KICKOFF_HOURS = 2
SOURCE_DISPUTE_THRESHOLD_PTS = 5


def implied_prob(decimal_odds):
    """Implied probability from decimal odds: 1 / odds."""
    return 1.0 / decimal_odds


def devig_multiplicative(implied):
    """Normalize implied probabilities so they sum to exactly 1."""
    total = sum(implied)
    return [p / total for p in implied]


def _power_sum(implied, k):
    return sum(p ** k for p in implied) - 1.0


def devig_power(implied, lo=0.05, hi=10.0, tol=1e-12, max_iter=200):
    """Solve sum(p_i**k) == 1 via bisection on k, return [p_i**k]."""
    if len(implied) == 1:
        return [1.0]
    f_lo = _power_sum(implied, lo)
    f_hi = _power_sum(implied, hi)
    # f is monotonically decreasing in k for probabilities in (0, 1).
    if f_lo < 0:
        # Even the smallest k undershoots (e.g. implied sum already <= 1);
        # fall back to multiplicative rather than extrapolate blindly.
        return devig_multiplicative(implied)
    if f_hi > 0:
        hi *= 2
        f_hi = _power_sum(implied, hi)

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = _power_sum(implied, mid)
        if abs(f_mid) < tol:
            break
        if f_mid > 0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2.0
    return [p ** k for p in implied]


def should_use_power_devig(implied, overround_threshold=0.05, favorite_threshold=0.65):
    """True when overround and favorite price are both large enough to require power devig."""
    overround = sum(implied) - 1.0
    favorite_implied = max(implied)
    return overround > overround_threshold and favorite_implied > favorite_threshold


def devig(implied):
    """Auto-select power vs multiplicative devig per the spec's mandatory rule."""
    overround = sum(implied) - 1.0
    if should_use_power_devig(implied):
        probs = devig_power(implied)
        method = "power"
    else:
        probs = devig_multiplicative(implied)
        method = "multiplicative"
    return {"probs": probs, "method": method, "overround": overround}


if __name__ == "__main__":
    # 1. No overround -> multiplicative, unchanged.
    r = devig([0.5, 0.5])
    assert r["method"] == "multiplicative"
    assert abs(sum(r["probs"]) - 1.0) < 1e-9
    assert abs(r["probs"][0] - 0.5) < 1e-9 and abs(r["probs"][1] - 0.5) < 1e-9
    print("check 1 (no overround, multiplicative) OK")

    # 2. Large overround + strong favorite -> power devig.
    implied = [0.75, 0.32]
    assert should_use_power_devig(implied) is True
    r = devig(implied)
    assert r["method"] == "power"
    assert abs(sum(r["probs"]) - 1.0) < 1e-6
    assert r["probs"][0] < 0.75
    assert r["probs"][0] > r["probs"][1]
    print("check 2 (power devig triggered, favorite deflated) OK")

    # 3. Favorite not extreme enough -> multiplicative.
    implied = [0.5, 0.3, 0.25]
    assert should_use_power_devig(implied) is False
    r = devig(implied)
    assert r["method"] == "multiplicative"
    assert abs(sum(r["probs"]) - 1.0) < 1e-9
    assert r["probs"][0] > r["probs"][1] > r["probs"][2]
    print("check 3 (3-way, multiplicative, ordering preserved) OK")

    # 4. Single-outcome edge case.
    assert devig_power([0.9]) == [1.0]
    print("check 4 (single-outcome guard) OK")

    print("devig.py: all checks passed")
