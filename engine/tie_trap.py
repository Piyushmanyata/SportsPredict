"""
Tie-trap engine for strict "Team A more X than Team B" markets (§5.4, L3).

P(A more) = (1 − P(tie)) × P(A more | no tie)

Exact tie mass for two independent Poisson(m): e^(−2m) · I₀(2m)
where I₀ is the modified Bessel function of order 0.
"""

import math
from scipy.special import i0 as bessel_i0


# Per-stat mean m values from the spec table (§5.4)
MEAN_STATS = {
    "fouls":       11.0,   # per team
    "ft_corners":   4.5,
    "2h_corners":   2.4,
    "ht_corners":   2.1,
    "2h_sot":       2.0,
    "cards":        1.8,
    "offsides":     1.5,
}

# Spec reference: even-matchup "A more" probabilities for each stat
_SPEC_EVEN_PROB = {
    "fouls":       0.46,
    "ft_corners":  0.43,
    "2h_corners":  0.41,
    "ht_corners":  0.40,
    "2h_sot":      0.40,
    "cards":       0.39,
    "offsides":    0.38,
}


def tie_prob_poisson(m: float) -> float:
    """
    P(A == B) for A,B ~ Poisson(m): e^(−2m) · I₀(2m).
    """
    return math.exp(-2 * m) * float(bessel_i0(2 * m))


def tie_trap_prob(
    stat: str | None = None,
    m_a: float | None = None,
    m_b: float | None = None,
    m: float | None = None,
    strength_ratio: float = 1.0,
) -> float:
    """
    Compute P(Team A has strictly more <stat> than Team B).

    Parameters
    ----------
    stat : str or None
        One of MEAN_STATS keys. If given and m is None, uses the canonical mean.
    m_a, m_b : float or None
        Per-team expected counts. If only m is given, m_a = m_b = m.
    m : float or None
        Symmetric mean (used when both teams equal). Ignored if m_a and m_b supplied.
    strength_ratio : float
        > 1 means team A is dominant. P(A more | no tie) shifts from 0.5 toward
        the dominant side using the spec's ~55-65% conditional for the stronger side.
        strength_ratio = lam_a / lam_b; clamped to produce conditional in [0.35, 0.65].

    Returns
    -------
    float in [0, 1]
    """
    if m_a is None and m_b is None:
        if m is None and stat is not None:
            m = MEAN_STATS[stat]
        if m is None:
            raise ValueError("Provide stat name, m, or (m_a, m_b).")
        m_a = m_b = m

    # Use symmetric mean for the tie probability (dominant driver)
    m_avg = (m_a + m_b) / 2
    p_tie = tie_prob_poisson(m_avg)

    # Conditional P(A more | no tie): 0.5 at strength_ratio=1; shifts toward 0.65 as ratio → 2+
    # Spec: dominant side conditional ~55–65%, weak side ~35–45%
    ratio = max(0.5, min(2.5, strength_ratio))  # clamp for stability
    # linear interpolation: ratio=1 → 0.50, ratio=2 → 0.62
    cond_a_more = 0.50 + 0.12 * (ratio - 1.0) / 1.0
    cond_a_more = max(0.35, min(0.65, cond_a_more))

    return (1 - p_tie) * cond_a_more


def tie_trap_int(
    stat: str | None = None,
    m: float | None = None,
    m_a: float | None = None,
    m_b: float | None = None,
    strength_ratio: float = 1.0,
) -> int:
    """Return tie_trap_prob as integer 1-99 (never 50 for a strict comparison)."""
    p = tie_trap_prob(stat=stat, m=m, m_a=m_a, m_b=m_b, strength_ratio=strength_ratio)
    raw = round(p * 100)
    # Never hand 50 to a strict comparison (§5.4)
    if raw == 50:
        raw = 49
    return max(1, min(99, raw))


def ht_tied_prob(lam_a: float, lam_b: float) -> float:
    """
    P(HT tied) using Bessel formula for two HT Poisson rates (§5.5).
    lam_a = 0.45 × full-match λ_A, lam_b = 0.45 × λ_B.
    P = e^(−(λa+λb)) · I₀(2√(λa·λb))
    L9: ceiling 47 unless T < 2.2.
    """
    la = 0.45 * lam_a
    lb = 0.45 * lam_b
    p = math.exp(-(la + lb)) * float(bessel_i0(2 * math.sqrt(la * lb)))
    return p


def ht_tied_int(
    lam_a: float,
    lam_b: float,
    T: float | None = None,
    apply_l9_ceiling: bool = True,
) -> int:
    """
    Return HT-tied probability as integer, applying L9 ceiling of 47 unless T < 2.2.
    """
    p = ht_tied_prob(lam_a, lam_b)
    raw = round(p * 100)
    if apply_l9_ceiling and raw > 47:
        _T = T if T is not None else lam_a + lam_b
        if _T >= 2.2:
            raw = 47
    return max(1, min(99, raw))
