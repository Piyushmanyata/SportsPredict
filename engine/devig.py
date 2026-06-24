"""
Anchor extraction and devigging (§5.1).
Power devig is mandatory when overround >5% AND favourite implied >65%.
"""

import math
from typing import List, Optional


def multiplicative_devig(implied: List[float]) -> List[float]:
    """Simple multiplicative devig: p_i = imp_i / sum(imp_i)."""
    total = sum(implied)
    return [p / total for p in implied]


def power_devig(implied: List[float]) -> List[float]:
    """
    Power devig: find k s.t. sum(imp_i^k) = 1, then p_i = imp_i^k.
    Mandatory when overround >5% AND favourite implied >65%.
    Falls back to multiplicative if solver fails.
    """
    # Check if devig is even needed
    total = sum(implied)
    if abs(total - 1.0) < 1e-6:
        return list(implied)

    def f(k):
        return sum(p ** k for p in implied) - 1.0

    # Bracket search for k in [0.5, 2.0]
    lo, hi = 0.5, 2.0
    f_lo, f_hi = f(lo), f(hi)

    if f_lo * f_hi > 0:
        # No root in bracket — fall back
        return multiplicative_devig(implied)

    for _ in range(60):  # bisection
        mid = (lo + hi) / 2.0
        if f(mid) * f_lo <= 0:
            hi = mid
            f_hi = f(mid)
        else:
            lo = mid
            f_lo = f(mid)

    k = (lo + hi) / 2.0
    result = [p ** k for p in implied]
    # Normalise for floating point
    s = sum(result)
    return [p / s for p in result]


def _should_use_power_devig(implied: List[float]) -> bool:
    """Returns True when overround >5% AND favourite implied >65%."""
    total = sum(implied)
    overround = total - 1.0
    max_implied = max(implied)
    return overround > 0.05 and max_implied > 0.65


def devig(implied: List[float]) -> List[float]:
    """Auto-select devig method per §5.1."""
    if _should_use_power_devig(implied):
        return power_devig(implied)
    return multiplicative_devig(implied)


def devig_1x2(dec_home: float, dec_draw: float, dec_away: float) -> dict:
    """
    Devig a 3-way 1X2 market from decimal odds.
    Returns {'home': p, 'draw': p, 'away': p, 'method': str}.
    """
    imp = [1 / dec_home, 1 / dec_draw, 1 / dec_away]
    method = "power" if _should_use_power_devig(imp) else "multiplicative"
    probs = devig(imp)
    return {
        "home": probs[0],
        "draw": probs[1],
        "away": probs[2],
        "method": method,
        "overround": sum(imp) - 1.0,
    }


def devig_ou(dec_over: float, dec_under: float) -> dict:
    """
    Devig a 2-way O/U market.
    Returns {'over': p, 'under': p, 'method': str}.
    """
    imp = [1 / dec_over, 1 / dec_under]
    method = "power" if _should_use_power_devig(imp) else "multiplicative"
    probs = devig(imp)
    return {"over": probs[0], "under": probs[1], "method": method}


def blend_anchor_fundamental(anchor: float, fundamental: float,
                              anchored: bool = True) -> float:
    """
    §5.0 blend: ANCHORED -> 60-70% anchor / 30-40% fundamental.
    MODELED -> ~50% each.
    """
    if anchored:
        return 0.65 * anchor + 0.35 * fundamental
    return 0.50 * anchor + 0.50 * fundamental
