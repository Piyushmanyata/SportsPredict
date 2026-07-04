"""Shared math primitives — pure stdlib, no numpy/scipy dependency."""
import math


def poisson_pmf(k, lam):
    if k < 0:
        return 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_cdf(k, lam):
    if k < 0:
        return 0.0
    return sum(poisson_pmf(i, lam) for i in range(k + 1))


def bisect_root(f, lo, hi, tol=1e-9, max_iter=200):
    """Standard bisection. Returns None if f(lo)/f(hi) don't bracket a root
    (callers should fall back to a simpler method — mirrors the spec's own
    try/except-to-multiplicative-devig fallback, §5.1)."""
    f_lo, f_hi = f(lo), f(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def clamp(x, lo, hi):
    return max(lo, min(hi, x))
