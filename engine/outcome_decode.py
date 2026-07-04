"""§9.2 — decode settled outcomes from (p, brier) with no web lookup needed."""


def decode_outcome(p, brier, eps=1e-6):
    """p is the decimal submitted probability. Returns 1, 0, or None if
    undefined (p == 0.5, per D3's 'avoid exactly 50')."""
    if abs(p - 0.5) < eps:
        return None
    if abs((p - 1) ** 2 - brier) < eps:
        return 1
    return 0
