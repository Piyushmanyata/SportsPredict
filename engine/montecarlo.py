"""§5.11 L8 — batched Monte Carlo over λ-uncertainty for correlated baskets.

When >4 of a match's ~10 markets load on the same latent axis, model
λ ~ Normal(λ̂, σ²) — σ from observed sharp-source spread, or the documented
default σ = 0.15·λ̂ placeholder — and integrate every correlated market over
the same draws. The MC-integrated value IS the honest E[p]: submit it
directly, never as a hedge. Batch all flagged matches for the session into
ONE call. Canonical worked example: QAT-SUI (§5.11).

Extends the spec's helper with the full market-key set the archetypes need.
"""

from __future__ import annotations

import math

import numpy as np

from .constants import SHARE_1H, SHARE_2H

DEFAULT_SIGMA_FRAC = 0.15  # documented placeholder when no source spread exists
_GRID_MAX = 10


def _win_draw_loss(la: np.ndarray, lb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized P(win/draw/loss | λ draws) off the independent-Poisson grid."""
    ks = np.arange(_GRID_MAX + 1)
    fact = np.array([math.factorial(int(k)) for k in ks], dtype=float)
    pa = np.exp(-la[:, None]) * la[:, None] ** ks / fact   # (n, K)
    pb = np.exp(-lb[:, None]) * lb[:, None] ** ks / fact
    joint = pa[:, :, None] * pb[:, None, :]                # (n, Ka, Kb)
    i, j = np.meshgrid(ks, ks, indexing="ij")
    return (joint[:, i > j].sum(axis=1),
            joint[:, i == j].sum(axis=1),
            joint[:, i < j].sum(axis=1))


def _bessel_i0_vec(x: np.ndarray) -> np.ndarray:
    return np.i0(x)


def batch_mc(matches: list[dict], n_draws: int = 2000, seed: int = 42) -> dict:
    """matches: list of dicts:
      { "name": str,
        "lam_a": float, "lam_b": float,
        "sigma_a": float (optional — default 0.15·λ),
        "sigma_b": float (optional),
        "markets": [keys...] }

    Supported market keys:
      win_a, draw, win_b, total_3plus, total_2orless, btts, btts3plus,
      p_2h_2plus, clean_sheet_a, clean_sheet_b, scores_a, scores_b,
      scores_2h_a, scores_2h_b, ht_tied, zero_zero

    Returns {match_name: {market_key: mc_probability}}.
    """
    rng = np.random.default_rng(seed)
    out: dict[str, dict[str, float]] = {}
    for m in matches:
        sa = m.get("sigma_a", DEFAULT_SIGMA_FRAC * m["lam_a"])
        sb = m.get("sigma_b", DEFAULT_SIGMA_FRAC * m["lam_b"])
        la = np.clip(rng.normal(m["lam_a"], sa, n_draws), 0.05, None)
        lb = np.clip(rng.normal(m["lam_b"], sb, n_draws), 0.05, None)
        T = la + lb
        want = set(m["markets"])
        res: dict[str, float] = {}

        if want & {"win_a", "draw", "win_b"}:
            w, d, l = _win_draw_loss(la, lb)
            if "win_a" in want:
                res["win_a"] = float(w.mean())
            if "draw" in want:
                res["draw"] = float(d.mean())
            if "win_b" in want:
                res["win_b"] = float(l.mean())
        if "total_3plus" in want:
            res["total_3plus"] = float(np.mean(1 - np.exp(-T) * (1 + T + T**2 / 2)))
        if "total_2orless" in want:
            res["total_2orless"] = float(np.mean(np.exp(-T) * (1 + T + T**2 / 2)))
        if "btts" in want:
            res["btts"] = float(np.mean((1 - np.exp(-la)) * (1 - np.exp(-lb))))
        if "btts3plus" in want:
            btts = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            p11 = la * lb * np.exp(-T)
            res["btts3plus"] = float(np.mean(btts - p11))
        if "p_2h_2plus" in want:
            lam_2h = SHARE_2H * T
            res["p_2h_2plus"] = float(np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h)))
        if "clean_sheet_a" in want:
            res["clean_sheet_a"] = float(np.mean(np.exp(-lb)))
        if "clean_sheet_b" in want:
            res["clean_sheet_b"] = float(np.mean(np.exp(-la)))
        if "scores_a" in want:
            res["scores_a"] = float(np.mean(1 - np.exp(-la)))
        if "scores_b" in want:
            res["scores_b"] = float(np.mean(1 - np.exp(-lb)))
        if "scores_2h_a" in want:
            res["scores_2h_a"] = float(np.mean(1 - np.exp(-SHARE_2H * la)))
        if "scores_2h_b" in want:
            res["scores_2h_b"] = float(np.mean(1 - np.exp(-SHARE_2H * lb)))
        if "ht_tied" in want:
            ha, hb = SHARE_1H * la, SHARE_1H * lb
            res["ht_tied"] = float(np.mean(np.exp(-(ha + hb)) * _bessel_i0_vec(2 * np.sqrt(ha * hb))))
        if "zero_zero" in want:
            res["zero_zero"] = float(np.mean(np.exp(-T)))

        out[m["name"]] = res
    return out


def fallback_widen(p: float, source_spread_pts: float) -> tuple[float, float]:
    """§5.11 fallback if a flagged match missed the batch: widen by at most
    min(3, ½ × observed source spread in pts) toward 0.5. Log explicitly as
    'λ-uncertainty adjustment (Jensen correction)' — never as safety shade.
    Returns (adjusted_p, applied_pts)."""
    pts = min(3.0, 0.5 * source_spread_pts) / 100.0
    adj = p + pts if p < 0.5 else p - pts
    return adj, pts * 100
