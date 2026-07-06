"""§5.11 L8 correlation cap: batched Monte Carlo over lambda uncertainty.

Pure-stdlib re-implementation of the spec's numpy batch_mc (same semantics,
same default sigma=0.15*lam_hat placeholder when no source spread is
available -- log that as such). Batch, don't loop: one call for every
near-horizon match flagged with >4/10 markets on the same latent axis.
"""
import math
import random


def _clip(x, lo):
    return x if x > lo else lo


def batch_mc(matches, n_draws=2000, seed=42):
    """matches: list of dicts, each:
      { "name": str, "lam_a": float, "sigma_a": float,
        "lam_b": float, "sigma_b": float, "markets": [market keys] }
    Returns: {match_name: {market_key: mc_probability}}

    Supported market keys: btts3plus, p_2h_2plus, clean_sheet_a,
    clean_sheet_b, scores_2h_a, scores_2h_b, scores_1h_a, scores_1h_b,
    btts, p_00.
    """
    rng = random.Random(seed)
    out = {}
    for m in matches:
        la_draws = [_clip(rng.gauss(m["lam_a"], m["sigma_a"]), 0.05) for _ in range(n_draws)]
        lb_draws = [_clip(rng.gauss(m["lam_b"], m["sigma_b"]), 0.05) for _ in range(n_draws)]
        res = {}
        markets = m["markets"]

        if "btts3plus" in markets or "btts" in markets or "p_00" in markets:
            btts_vals, p11_vals = [], []
            for la, lb in zip(la_draws, lb_draws):
                btts_vals.append((1 - math.exp(-la)) * (1 - math.exp(-lb)))
                p11_vals.append(la * lb * math.exp(-(la + lb)))
            if "btts3plus" in markets:
                res["btts3plus"] = sum(b - p for b, p in zip(btts_vals, p11_vals)) / n_draws
            if "btts" in markets:
                res["btts"] = sum(btts_vals) / n_draws
        if "p_00" in markets:
            res["p_00"] = sum(math.exp(-(la + lb)) for la, lb in zip(la_draws, lb_draws)) / n_draws
        if "p_2h_2plus" in markets:
            total = 0.0
            for la, lb in zip(la_draws, lb_draws):
                lam_2h = 0.55 * (la + lb)
                total += 1 - math.exp(-lam_2h) * (1 + lam_2h)
            res["p_2h_2plus"] = total / n_draws
        if "clean_sheet_a" in markets:
            res["clean_sheet_a"] = sum(math.exp(-lb) for lb in lb_draws) / n_draws
        if "clean_sheet_b" in markets:
            res["clean_sheet_b"] = sum(math.exp(-la) for la in la_draws) / n_draws
        if "scores_2h_a" in markets:
            res["scores_2h_a"] = sum(1 - math.exp(-0.55 * la) for la in la_draws) / n_draws
        if "scores_2h_b" in markets:
            res["scores_2h_b"] = sum(1 - math.exp(-0.55 * lb) for lb in lb_draws) / n_draws
        if "scores_1h_a" in markets:
            res["scores_1h_a"] = sum(1 - math.exp(-0.45 * la) for la in la_draws) / n_draws
        if "scores_1h_b" in markets:
            res["scores_1h_b"] = sum(1 - math.exp(-0.45 * lb) for lb in lb_draws) / n_draws

        out[m["name"]] = res
    return out


def default_sigma(lam_hat, source_spread=None):
    """sigma from observable spread across sharp sources, else the
    documented 0.15*lam_hat placeholder (log it as such)."""
    if source_spread is not None:
        return source_spread
    return 0.15 * lam_hat
