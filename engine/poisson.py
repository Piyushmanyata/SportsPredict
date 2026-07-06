"""Pure-stdlib Poisson/Bessel primitives shared by the rest of the engine.

No numpy/scipy dependency on purpose: these modules should run with a bare
`python3` in a fresh session container, no pip install step.
"""
import math


def poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_cdf(k, lam):
    """P(X <= k)."""
    return sum(poisson_pmf(i, lam) for i in range(0, k + 1))


def poisson_sf(k, lam):
    """P(X > k), i.e. P(X >= k+1)."""
    return 1.0 - poisson_cdf(k, lam)


def poisson_at_least(k, lam):
    """P(X >= k)."""
    return poisson_sf(k - 1, lam)


def bessel_i0(x, terms=200):
    """Modified Bessel function of the first kind, order 0, via its series.

    I0(x) = sum_{k=0..inf} (x/2)^(2k) / (k!)^2
    """
    half = x / 2.0
    total = 0.0
    term = 1.0  # k=0 term
    total += term
    for k in range(1, terms):
        term *= (half * half) / (k * k)
        total += term
        if term < 1e-18 * total:
            break
    return total


def poisson_tie_prob(lam_a, lam_b):
    """Exact P(X == Y) for independent X~Poisson(lam_a), Y~Poisson(lam_b).

    = e^-(la+lb) * I0(2*sqrt(la*lb))
    Reduces to the tie-trap table's e^(-2m)*I0(2m) when lam_a == lam_b == m.
    """
    if lam_a < 0 or lam_b < 0:
        raise ValueError("lambdas must be >= 0")
    return math.exp(-(lam_a + lam_b)) * bessel_i0(2 * math.sqrt(lam_a * lam_b))


def poisson_greater_prob(lam_a, lam_b, max_goals=60):
    """Exact P(X > Y) for independent Poisson(lam_a), Poisson(lam_b).

    Direct double sum; max_goals is a tail cutoff (Poisson tail beyond it is
    negligible for the goal/card/corner/SOT counts this engine deals with).
    """
    pmf_a = [poisson_pmf(i, lam_a) for i in range(max_goals + 1)]
    pmf_b = [poisson_pmf(j, lam_b) for j in range(max_goals + 1)]
    cdf_b = []
    running = 0.0
    for j in range(max_goals + 1):
        cdf_b.append(running)  # P(Y <= j-1) i.e. P(Y < j)
        running += pmf_b[j]
    return sum(pmf_a[i] * cdf_b[i] for i in range(max_goals + 1))
