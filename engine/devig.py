"""§5.1 — Anchor extraction: multiplicative and power devig, anchor blending.

Power devig is mandatory when overround > 5% AND favourite implied > 65%
(the additive +1–2 heuristic is banned — it violates boundaries near 0/1).
No scipy needed: k is solved by bisection on f(k) = Σ impᵢᵏ − 1, which is
strictly decreasing in k for implied probs in (0,1).
"""

from __future__ import annotations


def implied(decimal_odds: list[float]) -> list[float]:
    return [1.0 / o for o in decimal_odds]


def overround(imps: list[float]) -> float:
    return sum(imps) - 1.0


def devig_multiplicative(imps: list[float]) -> list[float]:
    s = sum(imps)
    return [p / s for p in imps]


def devig_power(imps: list[float], tol: float = 1e-10, max_iter: int = 200) -> list[float]:
    """Solve k with Σ impᵢᵏ = 1, return impᵢᵏ. Falls back to multiplicative
    if the bracket fails (per the spec's helper)."""
    def f(k: float) -> float:
        return sum(p ** k for p in imps) - 1.0

    lo, hi = 0.5, 2.0
    # widen the bracket if needed (heavy overrounds push k above 2)
    for _ in range(20):
        if f(lo) > 0 >= f(hi):
            break
        if f(hi) > 0:
            hi *= 2
        if f(lo) < 0:
            lo /= 2
    else:
        return devig_multiplicative(imps)

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        v = f(mid)
        if abs(v) < tol:
            break
        if v > 0:
            lo = mid
        else:
            hi = mid
    k = 0.5 * (lo + hi)
    return [p ** k for p in imps]


def devig(decimal_odds: list[float]) -> tuple[list[float], str]:
    """Devig a set of decimal odds, auto-selecting the method per §5.1.
    Returns (probabilities, method_used) — always cite the method."""
    imps = implied(decimal_odds)
    ov = overround(imps)
    if ov > 0.05 and max(imps) > 0.65:
        return devig_power(imps), "power"
    return devig_multiplicative(imps), "multiplicative"


def blend_anchor(anchor_p: float, fundamentals_p: float, anchor_weight: float = 0.65) -> float:
    """§5.0 — ANCHORED markets blend 60–70% devigged anchor / 30–40% fundamentals.
    Default 65/35. MODELED markets should use ~50% fundamentals instead."""
    return anchor_weight * anchor_p + (1.0 - anchor_weight) * fundamentals_p
