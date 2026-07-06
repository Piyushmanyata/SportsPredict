"""§5.1 anchor extraction / devig — power devig with pure-stdlib bisection.

Source trust order (cite whichever was actually used):
  Betfair Exchange > Pinnacle > consensus aggregators (Oddschecker/OddsPortal/
  Oddspedia) > single soft book. Prediction markets (Polymarket/Kalshi/
  Smarkets/Metaculus) for advancement/outrights/specials.
Sources differing >5pts post-devig: take the sharpest, note the dispute, drop
confidence one notch. Freshness: odds <=24h; near kickoff prefer <=2h.
"""

SOURCE_TRUST_ORDER = [
    "Betfair Exchange",
    "Pinnacle",
    "consensus aggregator (Oddschecker/OddsPortal/Oddspedia)",
    "single soft book",
]
SOURCE_TRUST_ORDER_SPECIALS = [
    "Polymarket", "Kalshi", "Smarkets", "Metaculus",
]


def implied_prob(decimal_odds):
    return 1.0 / decimal_odds


def multiplicative_devig(implied):
    total = sum(implied)
    return [p / total for p in implied]


def _power_sum(implied, k):
    return sum(p ** k for p in implied) - 1.0


def power_devig(implied, lo=0.3, hi=3.0, tol=1e-10, max_iter=200):
    """Solve for k such that sum(implied_i ** k) == 1, then p_i = implied_i**k.

    Pure bisection (no scipy). f(k) = sum(p_i^k) - 1 is monotone decreasing in
    k for k>0 since each p_i in (0,1), so bisection is safe once the bracket
    straddles the root.
    """
    f_lo, f_hi = _power_sum(implied, lo), _power_sum(implied, hi)
    if f_lo * f_hi > 0:
        # bracket doesn't straddle a root -- fall back to multiplicative
        return multiplicative_devig(implied), None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = _power_sum(implied, mid)
        if abs(f_mid) < tol:
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    k = (lo + hi) / 2.0
    return [p ** k for p in implied], k


def devig(decimal_odds, favorite_implied_threshold=0.65, overround_threshold=0.05):
    """§5.1: multiplicative is the base; ban the additive heuristic; when
    overround > 5% AND favorite implied > 65%, use the power devig instead.
    In the 35-65 band or low overround, multiplicative remains fine.
    """
    implied = [implied_prob(o) for o in decimal_odds]
    overround = sum(implied) - 1.0
    favorite_implied = max(implied) / sum(implied) if sum(implied) else 0.0
    use_power = overround > overround_threshold and favorite_implied > favorite_implied_threshold
    if use_power:
        probs, k = power_devig(implied)
        method = "power"
    else:
        probs, k = multiplicative_devig(implied), None
        method = "multiplicative"
    return {
        "implied": implied,
        "overround": overround,
        "method": method,
        "k": k,
        "probs": probs,
        "probs_pct": [round(p * 100, 1) for p in probs],
    }
