"""Tie-trap engine — strict "Team A more X than Team B" (spec §5.4).

P(A more) = (1 - P(tie)) * P(A more | no tie). Exact tie mass for two
independent Poisson(m): e^(-2m) * I0(2m). Never hand 50 to a strict comparison.
"""

from __future__ import annotations

import math

from engine.goals import pois_pmf


def bessel_i0(x: float) -> float:
    """Modified Bessel I0 by series (small x) or asymptotic (large x)."""
    if x < 25.0:
        total, term, k = 1.0, 1.0, 0
        while True:
            k += 1
            term *= (x / 2.0) ** 2 / (k * k)
            total += term
            if term < total * 1e-14:
                return total
    # asymptotic with first-order correction, safe from overflow via the
    # combined form used below only through tie_mass()
    return math.exp(x) / math.sqrt(2 * math.pi * x) * (1 + 1 / (8 * x))


def tie_mass(m: float) -> float:
    """P(A == B) for A,B ~ Poisson(m) iid: e^(-2m) I0(2m)."""
    x = 2.0 * m
    if x < 25.0:
        return math.exp(-x) * bessel_i0(x)
    # e^(-x) * I0(x) computed jointly to avoid overflow
    return (1 + 1 / (8 * x)) / math.sqrt(2 * math.pi * x)


def p_more_even(m: float) -> float:
    """Even matchup: P(A more) = (1 - tie)/2."""
    return (1.0 - tie_mass(m)) / 2.0


def p_more_exact(m_a: float, m_b: float, nmax: int = 60) -> float:
    """Exact P(A > B) for independent Poissons — use when means differ.

    Preferred over the heuristic split when you actually have per-team means.
    """
    pb_cdf, acc = [], 0.0
    for j in range(nmax + 1):
        acc += pois_pmf(j, m_b)
        pb_cdf.append(acc)
    total = 0.0
    for i in range(1, nmax + 1):
        total += pois_pmf(i, m_a) * pb_cdf[i - 1]
    return total


def p_more_skewed(m: float, cond_split: float) -> float:
    """Heuristic §5.4 form: (1 - tie) * cond_split, cond_split in 0.55-0.65
    for the dominant side (favored ~44-52, weak side ~27-36). Remember: a
    deep-block underdog often out-FOULS a possession favourite."""
    return (1.0 - tie_mass(m)) * cond_split
