"""
Anchor extraction and devigging utilities (§5.1).

Power devig is mandatory when overround > 5% AND favourite implied > 65%.
Otherwise multiplicative is fine.
"""

from scipy.optimize import root_scalar


def multiplicative_devig(implied: list[float]) -> list[float]:
    """Standard multiplicative (proportional) devig: p_i = imp_i / sum(imp)."""
    total = sum(implied)
    return [p / total for p in implied]


def power_devig(implied: list[float]) -> list[float]:
    """
    Power devig: find k s.t. sum(imp_i^k) == 1, return [imp_i^k].
    Falls back to multiplicative if solver fails (§5.1).
    """
    def f(k):
        return sum(p ** k for p in implied) - 1

    try:
        result = root_scalar(f, bracket=[0.5, 2.0], method="brentq")
        k = result.root
        return [p ** k for p in implied]
    except Exception:
        return multiplicative_devig(implied)


def devig_3way(
    odds_home: float,
    odds_draw: float,
    odds_away: float,
    method: str = "auto",
) -> tuple[float, float, float]:
    """
    Devig a 3-way 1X2 market from decimal odds.
    method='auto': use power when overround>5% and max implied>65%, else multiplicative.
    Returns (p_home, p_draw, p_away) each in [0,1].
    """
    imp = [1 / o for o in (odds_home, odds_draw, odds_away)]
    overround = sum(imp) - 1
    max_implied = max(imp)

    if method == "power" or (method == "auto" and overround > 0.05 and max_implied > 0.65):
        dv = power_devig(imp)
    else:
        dv = multiplicative_devig(imp)

    return tuple(dv)


def devig_2way(
    odds_yes: float,
    odds_no: float,
    method: str = "auto",
) -> tuple[float, float]:
    """
    Devig a 2-way market from decimal odds.
    Returns (p_yes, p_no).
    """
    imp = [1 / odds_yes, 1 / odds_no]
    overround = sum(imp) - 1
    max_implied = max(imp)

    if method == "power" or (method == "auto" and overround > 0.05 and max_implied > 0.65):
        dv = power_devig(imp)
    else:
        dv = multiplicative_devig(imp)

    return (dv[0], dv[1])


def blend_anchor_fundamentals(
    anchor: float,
    fundamentals: float,
    anchored: bool = True,
) -> float:
    """
    Blend devigged anchor with fundamentals model (§5.0).
    ANCHORED: 60-70% anchor / 30-40% fundamentals → use 65/35.
    MODELED:  ~50% fundamentals weight.
    """
    if anchored:
        return 0.65 * anchor + 0.35 * fundamentals
    else:
        return 0.50 * anchor + 0.50 * fundamentals
