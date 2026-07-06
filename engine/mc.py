"""L8 batched Monte Carlo over lambda uncertainty (spec §5.11).

If >4 of a match's ~10 markets load on the same latent axis, integrate over
lambda ~ Normal(lam_hat, sigma^2) — sigma from observable sharp-source spread,
or the documented placeholder sigma = 0.15 * lam_hat. Batch every flagged
match of the session into ONE call. The MC-integrated value IS the honest
E[p]: submit it directly, not as a hedge.

Uses numpy when available; otherwise a pure-Python fallback (slower, same
semantics) so the engine still runs on a bare interpreter.
"""

from __future__ import annotations

import math

try:
    import numpy as np
except ImportError:      # pure-python fallback
    np = None

import random

from engine.constants import MC_DEFAULT_SIGMA_FRAC

SUPPORTED = ("btts3plus", "p_2h_2plus", "clean_sheet_a", "clean_sheet_b",
             "scores_2h_a", "scores_2h_b", "scores_a", "scores_b",
             "total_3plus", "total_2less", "btts", "ht_tied")


def default_sigma(lam_hat: float) -> float:
    """Documented placeholder when no sharp-source spread is observable."""
    return MC_DEFAULT_SIGMA_FRAC * lam_hat


def _market_values(la: float, lb: float, key: str) -> float:
    t = la + lb
    if key == "btts3plus":
        return (1 - math.exp(-la)) * (1 - math.exp(-lb)) - la * lb * math.exp(-t)
    if key == "btts":
        return (1 - math.exp(-la)) * (1 - math.exp(-lb))
    if key == "p_2h_2plus":
        l2 = 0.55 * t
        return 1 - math.exp(-l2) * (1 + l2)
    if key == "clean_sheet_a":
        return math.exp(-lb)
    if key == "clean_sheet_b":
        return math.exp(-la)
    if key == "scores_a":
        return 1 - math.exp(-la)
    if key == "scores_b":
        return 1 - math.exp(-lb)
    if key == "scores_2h_a":
        return 1 - math.exp(-0.55 * la)
    if key == "scores_2h_b":
        return 1 - math.exp(-0.55 * lb)
    if key == "total_3plus":
        return 1 - math.exp(-t) * (1 + t + t * t / 2)
    if key == "total_2less":
        return math.exp(-t) * (1 + t + t * t / 2)
    if key == "ht_tied":
        ha, hb = 0.45 * la, 0.45 * lb
        # series I0 — lambdas here are small enough
        x = 2 * math.sqrt(ha * hb)
        total, term, k = 1.0, 1.0, 0
        while term > total * 1e-12:
            k += 1
            term *= (x / 2) ** 2 / (k * k)
            total += term
        return math.exp(-(ha + hb)) * total
    raise KeyError(f"unsupported market key: {key}")


def batch_mc(matches: list[dict], n_draws: int = 2000, seed: int = 42) -> dict:
    """matches: [{"name", "lam_a", "sigma_a", "lam_b", "sigma_b",
                  "markets": [keys from SUPPORTED]}].
    Returns {name: {market_key: mc_probability (0-1)}}.
    """
    out: dict[str, dict[str, float]] = {}
    if np is not None:
        rng = np.random.default_rng(seed)
        for m in matches:
            la = np.clip(rng.normal(m["lam_a"], m["sigma_a"], n_draws), 0.05, None)
            lb = np.clip(rng.normal(m["lam_b"], m["sigma_b"], n_draws), 0.05, None)
            res = {}
            for key in m["markets"]:
                vals = [_market_values(a, b, key) for a, b in zip(la, lb)]
                res[key] = float(sum(vals) / len(vals))
            out[m["name"]] = res
        return out
    rnd = random.Random(seed)
    for m in matches:
        draws = [(max(0.05, rnd.gauss(m["lam_a"], m["sigma_a"])),
                  max(0.05, rnd.gauss(m["lam_b"], m["sigma_b"])))
                 for _ in range(n_draws)]
        out[m["name"]] = {
            key: sum(_market_values(a, b, key) for a, b in draws) / n_draws
            for key in m["markets"]
        }
    return out


def fallback_widen(p: int, source_spread_pts: float) -> tuple[int, str]:
    """If a flagged match missed the batch: widen toward 50 by at most
    min(3, spread/2) pts — logged as 'lambda-uncertainty adjustment (Jensen
    correction)', never as safety shade."""
    w = min(3, round(source_spread_pts / 2))
    adj = p + w if p < 50 else p - w
    return adj, f"lambda-uncertainty adjustment (Jensen correction) {adj - p:+d}"
