"""Modified Bessel function of the first kind, order 0 (I0).

Pure stdlib implementation (no numpy/scipy) so every engine module stays
zero-setup. Used by tie_trap.py (exact tie mass) and thresholds.py
(HT-tied Bessel table, §5.4/§5.5 of probability-cup-system-instructions-v8-final.md).

Series: I0(x) = sum_{k=0}^inf (x/2)^(2k) / (k!)^2, built via the
iterative ratio term_k = term_{k-1} * (x/2)^2 / k^2 so no intermediate
factorial/power overflows even for the x ~ 20-40 range this engine needs.
"""


def i0(x, tol=1e-15, max_terms=200):
    x = abs(x)
    half_x_sq = (x / 2.0) ** 2
    term = 1.0
    total = 1.0
    k = 0
    while k < max_terms:
        k += 1
        term *= half_x_sq / (k * k)
        total += term
        if term < tol * total:
            break
    return total


if __name__ == "__main__":
    # Reference values (scipy.special.i0), spot-checked to 4-6 sig figs.
    checks = [
        (0.0, 1.0),
        (1.0, 1.2660658),
        (2.0, 2.2795853),
        (5.0, 27.239872),
        (10.0, 2815.7167),
        (22.0, 3.0669299e8),
    ]
    for x, expected in checks:
        got = i0(x)
        rel_err = abs(got - expected) / expected
        assert rel_err < 1e-4, f"i0({x}) = {got}, expected {expected}, rel_err={rel_err}"
        print(f"i0({x}) = {got:.6g}  (expected {expected:.6g})  OK")
    print("besselfn.py: all checks passed")
