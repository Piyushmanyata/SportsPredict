"""
L8 Correlation cap — batched Monte Carlo integration over λ uncertainty (§5.11).

When >4 of ~10 markets for a match share a latent axis (same λ misread poisons all),
integrate over λ ~ Normal(λ_hat, σ²) rather than submitting deterministic point estimates.

Canonical worked example: QAT-SUI — four markets on Qatar's attacking λ,
all underpriced 12-35, all YES, 27% of total @79 damage from one match.

Default σ = 0.15 * λ_hat when no source spread data is available (log as placeholder).
"""

import numpy as np
from typing import List, Dict, Optional


MARKET_KEYS = [
    "btts3plus",
    "p_2h_2plus",
    "clean_sheet_a",
    "clean_sheet_b",
    "scores_2h_a",
    "scores_2h_b",
    "scores_ft_a",
    "scores_ft_b",
    "over_2.5",
    "over_3.5",
    "ht_tied",
    "btts",
]


def batch_mc(
    matches: List[Dict],
    n_draws: int = 2000,
    seed: int = 42,
) -> Dict[str, Dict[str, float]]:
    """
    Batch Monte Carlo integration for correlated-axis baskets.

    matches: list of dicts, each:
      {
        "name": str,
        "lam_a": float,   "sigma_a": float,  # σ from source spread; default 0.15*lam_a
        "lam_b": float,   "sigma_b": float,
        "markets": list of market keys to evaluate,  # subset of MARKET_KEYS
        "sigma_source": str,  # "observed_spread" | "default_placeholder" (logged)
      }

    Returns: dict keyed by match name -> {market_key: mc_probability (float 0-1)}
    """
    rng = np.random.default_rng(seed)
    out = {}

    for m in matches:
        lam_a = float(m["lam_a"])
        lam_b = float(m["lam_b"])
        # Use provided σ; default to 0.15 * λ if not specified (log it)
        sigma_a = float(m.get("sigma_a", 0.15 * lam_a))
        sigma_b = float(m.get("sigma_b", 0.15 * lam_b))

        la = np.clip(rng.normal(lam_a, sigma_a, n_draws), 0.05, None)
        lb = np.clip(rng.normal(lam_b, sigma_b, n_draws), 0.05, None)
        T = la + lb

        res = {}
        mkt_set = set(m.get("markets", MARKET_KEYS))

        if "btts3plus" in mkt_set:
            btts = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            p11 = la * lb * np.exp(-T)
            res["btts3plus"] = float(np.mean(btts - p11))

        if "btts" in mkt_set:
            btts = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            res["btts"] = float(np.mean(btts))

        if "p_2h_2plus" in mkt_set:
            lam_2h = 0.55 * T
            res["p_2h_2plus"] = float(np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h)))

        if "clean_sheet_a" in mkt_set:
            res["clean_sheet_a"] = float(np.mean(np.exp(-lb)))

        if "clean_sheet_b" in mkt_set:
            res["clean_sheet_b"] = float(np.mean(np.exp(-la)))

        if "scores_2h_a" in mkt_set:
            res["scores_2h_a"] = float(np.mean(1 - np.exp(-0.55 * la)))

        if "scores_2h_b" in mkt_set:
            res["scores_2h_b"] = float(np.mean(1 - np.exp(-0.55 * lb)))

        if "scores_ft_a" in mkt_set:
            res["scores_ft_a"] = float(np.mean(1 - np.exp(-la)))

        if "scores_ft_b" in mkt_set:
            res["scores_ft_b"] = float(np.mean(1 - np.exp(-lb)))

        if "over_2.5" in mkt_set:
            # P(total > 2.5) = P(total >= 3) = 1 - P(total <= 2)
            p_le2 = np.exp(-T) * (1 + T + T**2 / 2)
            res["over_2.5"] = float(np.mean(1 - p_le2))

        if "over_3.5" in mkt_set:
            # P(total >= 4) = 1 - P(total <= 3)
            p_le3 = np.exp(-T) * (1 + T + T**2 / 2 + T**3 / 6)
            res["over_3.5"] = float(np.mean(1 - p_le3))

        if "ht_tied" in mkt_set:
            # HT λs = 0.45 * FT λs; P(tie) = e^(-(la_ht+lb_ht)) * I₀(2√(la_ht*lb_ht))
            # Approximate I₀ via series (first 15 terms sufficient)
            la_ht = 0.45 * la
            lb_ht = 0.45 * lb
            ht_tie = _vec_ht_tied(la_ht, lb_ht)
            # L9 cap at 0.47 unless T < 2.2 (applied per draw)
            cap = np.where(T < 2.2, 1.0, 0.47)
            res["ht_tied"] = float(np.mean(np.minimum(ht_tie, cap)))

        out[m["name"]] = res

    return out


def _vec_ht_tied(la: np.ndarray, lb: np.ndarray) -> np.ndarray:
    """Vectorised P(HT tie) = e^(-(la+lb)) * I₀(2*sqrt(la*lb))."""
    x = 2.0 * np.sqrt(la * lb)
    # Approximate I₀ via series: I₀(x) = sum_{k=0}^{N} (x/2)^{2k} / (k!)^2
    i0 = np.ones_like(x)
    term = np.ones_like(x)
    for k in range(1, 20):
        term = term * (x / 2) ** 2 / (k * k)
        i0 += term
    return np.exp(-(la + lb)) * i0


def estimate_sigma(source_probs: List[float], lam_hat: float) -> tuple:
    """
    Estimate σ from the observable spread across sharp sources.

    source_probs: list of probability estimates (0-1) from different sharp books.
    lam_hat: point estimate of λ.

    Returns (sigma, source_note).
    """
    if len(source_probs) >= 2:
        spread_pct = (max(source_probs) - min(source_probs)) * 100
        # Rough heuristic: 1pt spread in prob ≈ 0.05 in λ for typical ranges
        sigma = max(0.05, spread_pct * 0.05)
        return sigma, "observed_spread"
    else:
        sigma = 0.15 * lam_hat
        return sigma, "default_placeholder"


def count_correlated_axis(markets: List[dict], threshold: int = 4) -> tuple:
    """
    Count how many markets share a latent axis (same λ sensitivity).
    Returns (count, flag) where flag = True if count > threshold.

    markets: list of {name, axis} dicts where axis is "lam_a" | "lam_b" | "T" | ...
    """
    from collections import Counter
    axes = [m.get("axis", "unknown") for m in markets]
    counts = Counter(axes)
    max_axis = max(counts, key=counts.get)
    max_count = counts[max_axis]
    return max_count, max_count > threshold, max_axis


def should_run_mc(match_markets: List[dict], threshold: int = 4) -> bool:
    """Quick check: does this match need batch MC?"""
    _, flag, _ = count_correlated_axis(match_markets, threshold)
    return flag
