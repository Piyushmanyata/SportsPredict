"""Anchor extraction / devig (spec §5.1).

Multiplicative devig is the base. Power devig is MANDATORY when overround > 5%
AND the favourite's implied prob > 65% (the additive +1-2 heuristic is banned —
it violates boundaries near 0/1 and breaks coherence). Always cite the method.
"""

from __future__ import annotations


def implied(decimal_odds: list[float]) -> list[float]:
    """Raw implied probabilities 1/odds (sum > 1 by the overround)."""
    return [1.0 / o for o in decimal_odds]


def overround(imp: list[float]) -> float:
    """Book margin: sum(implied) - 1."""
    return sum(imp) - 1.0


def multiplicative(imp: list[float]) -> list[float]:
    """p_i = imp_i / sum(imp). 2-way and 3-way alike."""
    s = sum(imp)
    return [p / s for p in imp]


def power(imp: list[float]) -> list[float]:
    """Solve sum(imp_i ** k) = 1 by bisection, return imp_i ** k.

    Falls back to multiplicative if the solver cannot bracket a root.
    """
    def f(k: float) -> float:
        return sum(p ** k for p in imp) - 1.0

    lo, hi = 0.5, 4.0
    if f(lo) * f(hi) > 0:           # cannot bracket -> fallback
        return multiplicative(imp)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    k = (lo + hi) / 2.0
    return [p ** k for p in imp]


def devig(decimal_odds: list[float]) -> dict:
    """Full §5.1 pipeline from decimal odds.

    Returns {"probs": [...0-1...], "method": "power"|"multiplicative",
             "overround": float}. Power fires iff overround > 5% and the
             favourite's implied > 65%; otherwise multiplicative.
    """
    imp = implied(decimal_odds)
    ovr = overround(imp)
    use_power = ovr > 0.05 and max(imp) > 0.65
    probs = power(imp) if use_power else multiplicative(imp)
    return {"probs": probs, "method": "power" if use_power else "multiplicative",
            "overround": ovr}
