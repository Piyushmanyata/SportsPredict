"""Coherence gates — run before EVERY batch write (spec §5.11, D3).

Every function returns a list of violation strings; empty list = pass.
Fix or fall back on violation — never skip the market (coverage doctrine).
"""

from __future__ import annotations

from engine.constants import ANCHOR_DEVIATION_GATE, NOISY_CLAMP, P_MAX, P_MIN


def check_bounds(preds: dict[str, int]) -> list[str]:
    """Integers 1-99 only; flag exactly-50 (breaks §9.2 outcome decode)."""
    v = []
    for name, p in preds.items():
        if not isinstance(p, int) or not (P_MIN <= p <= P_MAX):
            v.append(f"{name}: {p!r} not an integer in 1-99 (D3)")
        elif p == 50:
            v.append(f"{name}: exactly 50 — nudge to 49/51 (D3 decode telemetry)")
    return v


def check_1x2(p_win: int, p_draw: int, p_loss: int, tol: int = 2) -> list[str]:
    s = p_win + p_draw + p_loss
    return [] if abs(s - 100) <= tol else [f"1X2 triplet sums to {s} (need 100 +/- {tol})"]


def check_ou_monotone(ladder: dict[str, int]) -> list[str]:
    """ladder: {'2+': p, '3+': p, '4+': p} — P(>=k) must be non-increasing."""
    items = sorted(ladder.items(), key=lambda kv: int(kv[0].rstrip("+")))
    v = []
    for (k1, p1), (k2, p2) in zip(items, items[1:]):
        if p2 > p1:
            v.append(f"O/U ladder not monotone: P({k2})={p2} > P({k1})={p1}")
    return v


def check_complement(p_a: int, p_b: int, label: str, tol: int = 2) -> list[str]:
    """e.g. clean-sheet-A vs opponent-scores must sum to ~100."""
    s = p_a + p_b
    return [] if abs(s - 100) <= tol else [f"{label}: complements sum to {s}"]


def check_joint(p_joint: int, p_m1: int, p_m2: int, label: str) -> list[str]:
    if p_joint > min(p_m1, p_m2):
        return [f"{label}: joint {p_joint} exceeds a marginal ({min(p_m1, p_m2)})"]
    return []


def check_anchor_deviation(p_final: int, p_anchor: int, cause: str | None,
                           label: str) -> list[str]:
    """|final - anchor| > 10 requires a written concrete cause, else regress."""
    if abs(p_final - p_anchor) > ANCHOR_DEVIATION_GATE and not cause:
        return [f"{label}: |{p_final} - anchor {p_anchor}| > "
                f"{ANCHOR_DEVIATION_GATE} with no written cause — regress to anchor"]
    return []


def clamp_noisy(p: int, anchored: bool = False) -> int:
    """§5.9 noisy register: clamp 15-85 unless anchored."""
    if anchored:
        return p
    lo, hi = NOISY_CLAMP
    return max(lo, min(hi, p))
