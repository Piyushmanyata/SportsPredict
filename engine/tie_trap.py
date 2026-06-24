"""
Tie-trap engine for strict "Team A more X than Team B" markets (§5.4).
P(A more) = (1 - P(tie)) × P(A more | no tie).
Never hand 50 to a strict comparison.
"""

import math
from typing import Optional


# §5.4 Exact tie masses for two independent Poisson(m) via I₀(2m)
# P(tie) = e^(-2m) * I₀(2m)
# Pre-computed reference table — use for sanity checks
TIE_TRAP_TABLE = {
    # stat: (per-team mean m, tie_pct, even-matchup "A more" pct)
    "fouls":      (11.0, 8.6,  46),
    "FT_corners": (4.5,  13.5, 43),
    "2H_corners": (2.4,  18.8, 41),
    "HT_corners": (2.1,  20.2, 40),
    "2H_SOT":     (2.0,  20.7, 40),
    "cards":      (1.8,  21.9, 39),
    "offsides":   (1.5,  24.3, 38),
}


def _bessel_i0(x: float) -> float:
    """Modified Bessel function I₀(x)."""
    result = 0.0
    term = 1.0
    k = 0
    while True:
        result += term
        k += 1
        term *= (x / 2.0) ** 2 / (k * k)
        if term < 1e-14:
            break
    return result


def p_tie_poisson(m: float) -> float:
    """
    P(tie) for two independent Poisson(m) variables.
    = e^(-2m) * I₀(2m)
    """
    if m <= 0:
        return 1.0
    return math.exp(-2 * m) * _bessel_i0(2 * m)


def p_tie_poisson_ab(m_a: float, m_b: float) -> float:
    """
    P(tie) for two independent Poisson(m_a) and Poisson(m_b).
    = e^(-(m_a + m_b)) * I₀(2*sqrt(m_a * m_b))
    """
    x = 2.0 * math.sqrt(m_a * m_b)
    return math.exp(-(m_a + m_b)) * _bessel_i0(x)


def p_strict_more(m_a: float, m_b: float,
                  strength_skew: Optional[float] = None) -> float:
    """
    P(A strictly more than B) for two independent Poisson variables.

    m_a, m_b: per-team mean counts (same stat, e.g. corners, fouls).
    strength_skew: if provided, the conditional P(A more | no tie).
                   If None, computed from m_a vs m_b (favored side
                   gets conditional ~55-65/45-35, roughly).

    Returns probability as a float in [0, 1].
    Guaranteed never to return exactly 0.50 for any strict comparison.
    """
    p_tie = p_tie_poisson_ab(m_a, m_b)

    if strength_skew is not None:
        p_a_given_no_tie = strength_skew
    else:
        # Derive conditional from λ asymmetry
        if m_a + m_b < 1e-9:
            p_a_given_no_tie = 0.5
        else:
            # Approximate: P(A > B | no tie) via normal approximation
            # E[A-B] = m_a - m_b, Var[A-B] = m_a + m_b
            mean_diff = m_a - m_b
            std_diff = math.sqrt(m_a + m_b)
            if std_diff < 1e-9:
                p_a_given_no_tie = 0.5
            else:
                z = mean_diff / std_diff
                p_a_given_no_tie = _norm_cdf(z)

    return (1.0 - p_tie) * p_a_given_no_tie


def _norm_cdf(z: float) -> float:
    """Standard normal CDF via math.erfc."""
    return 0.5 * math.erfc(-z / math.sqrt(2))


def to_int_prob(p: float, lo: int = 1, hi: int = 99) -> int:
    """Convert probability to integer 1-99, clamped."""
    return max(lo, min(hi, int(round(p * 100))))


def price_strict_comparison(stat: str, m_a: Optional[float] = None,
                             m_b: Optional[float] = None,
                             is_dominant_side_a: Optional[bool] = None) -> int:
    """
    Price a strict "Team A more {stat} than Team B" market.
    Returns integer probability 1-99.

    If m_a / m_b are provided, uses exact Poisson calculation.
    Otherwise falls back to the table values.
    """
    if m_a is not None and m_b is not None:
        p = p_strict_more(m_a, m_b)
        return to_int_prob(p)

    # Table-based fallback
    if stat not in TIE_TRAP_TABLE:
        # Unknown stat: default to 40 (conservative, accounts for tie mass)
        return 40

    _, _, even_p = TIE_TRAP_TABLE[stat]

    if is_dominant_side_a is True:
        # Dominant side: conditional split ~55-65 of (1-tie), roughly 44-52 final
        # Use upper end of favored range
        return min(52, even_p + 6)
    elif is_dominant_side_a is False:
        # Weak side: 27-36 range
        return max(27, even_p - 9)
    else:
        return even_p


# Strength skew reference
# Dominant side's conditional split ~55-65/45-35 -> favored ≈ 44-52, weak ≈ 27-36
DOMINANT_CONDITIONAL = 0.60  # P(A more | no tie, A is dominant)
WEAK_CONDITIONAL = 0.40      # P(A more | no tie, A is weak)

# Special note: deep-block underdog often out-fouls possession fav
# Fouls skew can INVERT relative to quality (documented in §5.4)
FOULS_SKEW_NOTE = (
    "A deep-block underdog often out-fouls a possession favourite — "
    "fouls skew can invert relative to quality. Verify before assigning."
)
