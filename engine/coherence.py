"""§5.11 coherence gates + §5.9 noisy-register clamp + D3 submission format.

Run `run_gates()` before EVERY batch write. A failed gate means fix or fall
back — never skip the market (coverage doctrine, §2).
"""

from __future__ import annotations

from .constants import NOISY_REGISTER


def to_submission(p: float) -> int:
    """D3 — integer 1–99; avoid exactly 50 (it breaks §9.2 outcome decoding)."""
    v = int(round(p * 100))
    v = max(1, min(99, v))
    if v == 50:
        v = 51 if p >= 0.50 else 49
    return v


def clamp_noisy(p: float, market_key: str, anchored: bool = False) -> float:
    """§5.9 — noisy-register markets clamp to 15–85 unless anchored."""
    if anchored or market_key not in NOISY_REGISTER:
        return p
    return max(0.15, min(0.85, p))


def run_gates(markets: dict[str, float],
              anchors: dict[str, float] | None = None,
              triplet_keys: tuple[str, str, str] | None = None,
              ou_ladder_keys: list[str] | None = None,
              joint_constraints: list[tuple[str, str, str]] | None = None) -> list[str]:
    """Return a list of human-readable gate violations (empty = pass).

    markets:            {key: probability 0–1} about to be submitted
    anchors:            {key: devigged anchor p} — |final − anchor| > 10 pts
                        requires a written concrete cause, else regress (gate
                        flags it; the written cause lives in the report)
    triplet_keys:       (win_a, draw, win_b) keys — must sum to 100 ± 2 pts
    ou_ladder_keys:     keys of "at least k" probs in ascending k — must be
                        monotone non-increasing
    joint_constraints:  (joint_key, marginal1_key, marginal2_key) — joint must
                        not exceed either marginal
    """
    v: list[str] = []

    for key, p in markets.items():
        if not (0.01 <= p <= 0.99):
            v.append(f"{key}: p={p:.3f} outside [0.01, 0.99] (D3)")

    if triplet_keys:
        s = sum(markets[k] for k in triplet_keys)
        if abs(s - 1.0) > 0.02:
            v.append(f"1X2 triplet sums to {s * 100:.1f}, outside 100 ± 2")

    if ou_ladder_keys:
        vals = [markets[k] for k in ou_ladder_keys]
        for a, b, ka, kb in zip(vals, vals[1:], ou_ladder_keys, ou_ladder_keys[1:]):
            if b > a + 1e-9:
                v.append(f"O/U ladder not monotone: {kb}={b:.2f} > {ka}={a:.2f}")

    if joint_constraints:
        for joint, m1, m2 in joint_constraints:
            if markets[joint] > min(markets[m1], markets[m2]) + 1e-9:
                v.append(f"joint {joint}={markets[joint]:.2f} exceeds a marginal "
                         f"({m1}={markets[m1]:.2f}, {m2}={markets[m2]:.2f})")

    if anchors:
        for key, a in anchors.items():
            if key in markets and abs(markets[key] - a) > 0.10:
                v.append(f"{key}: |final {markets[key]:.2f} − anchor {a:.2f}| > 10 pts "
                         "— needs a written concrete cause, else regress to anchor")

    return v
