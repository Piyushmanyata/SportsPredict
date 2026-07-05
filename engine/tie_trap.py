"""§5.4 — Tie-trap engine for strict "Team A more X than Team B" markets.

P(A more) = (1 − P(tie)) × P(A more | no tie). Exact tie mass for two
independent Poisson(m_a), Poisson(m_b): e^-(m_a+m_b) · I₀(2√(m_a·m_b))
(equal means reduce to the spec's e^(−2m)·I₀(2m)).

Never hand 50 to a strict comparison. A deep-block underdog often out-FOULS
a possession favourite — fouls skew can invert relative to quality.
L3 status: CONFIRMED (n=32 @118).
"""

from __future__ import annotations

import math

from .constants import STAT_MEANS
from .poisson import pois_pmf


def _bessel_i0(x: float) -> float:
    """Modified Bessel I₀ via its power series (converges for our range)."""
    term, total, k = 1.0, 1.0, 0
    x2 = (x / 2.0) ** 2
    while term > 1e-15 * total:
        k += 1
        term *= x2 / (k * k)
        total += term
    return total


def tie_mass(m_a: float, m_b: float | None = None) -> float:
    """Exact P(A == B) for independent Poissons. One arg = equal means."""
    if m_b is None:
        m_b = m_a
    return math.exp(-(m_a + m_b)) * _bessel_i0(2.0 * math.sqrt(m_a * m_b))


def p_strict_more(m_a: float, m_b: float) -> float:
    """Exact P(A > B) for independent Poisson(m_a), Poisson(m_b) by grid sum."""
    n = max(30, int(3 * max(m_a, m_b)) + 15)
    pa = [pois_pmf(i, m_a) for i in range(n + 1)]
    pb = [pois_pmf(i, m_b) for i in range(n + 1)]
    cdf_b = []
    acc = 0.0
    for j in range(n + 1):
        cdf_b.append(acc)      # P(B < j) BEFORE adding pb[j]
        acc += pb[j]
    return sum(pa[i] * cdf_b[i] for i in range(1, n + 1))


def p_strict_more_by_stat(stat: str, skew_a: float = 1.0) -> float:
    """Convenience: strict comparison off the §5.4 canonical per-team means.

    stat: key of STAT_MEANS ('fouls', 'corners_ft', 'corners_2h', 'corners_ht',
          'sot_2h', 'cards', 'offsides').
    skew_a: multiplicative tilt on A's mean vs B's (1.0 = even matchup;
            dominant side ≈ 1.2–1.5 → conditional split ~55–65/45–35).
    """
    m = STAT_MEANS[stat]
    # keep the TOTAL volume at 2m and split it by the skew
    m_a = 2 * m * skew_a / (1 + skew_a)
    m_b = 2 * m - m_a
    return p_strict_more(m_a, m_b)
