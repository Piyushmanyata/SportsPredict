"""§5.11 L8 — batched Monte Carlo over lambda uncertainty for correlated
baskets (>4 of 10 markets sharing a latent axis). Pure-stdlib port of the
spec's numpy snippet so it runs with no extra install."""
import math
import random


def default_sigma(lam_hat, ratio=0.15):
    """Documented placeholder (§5.11) when no observable source spread exists."""
    return ratio * lam_hat


def batch_mc(matches, n_draws=2000, seed=42):
    """matches: list of dicts, each:
      {"name": str, "lam_a": float, "sigma_a": float,
       "lam_b": float, "sigma_b": float,
       "markets": [subset of "btts3plus", "p_2h_2plus", "clean_sheet_a", "scores_2h_a"]}
    Returns: {match_name: {market_key: mc_probability}}
    """
    rng = random.Random(seed)
    out = {}
    for m in matches:
        la_draws = [max(rng.gauss(m["lam_a"], m["sigma_a"]), 0.05) for _ in range(n_draws)]
        lb_draws = [max(rng.gauss(m["lam_b"], m["sigma_b"]), 0.05) for _ in range(n_draws)]
        res = {}
        markets = m["markets"]
        if "btts3plus" in markets:
            vals = []
            for la, lb in zip(la_draws, lb_draws):
                T = la + lb
                btts = (1 - math.exp(-la)) * (1 - math.exp(-lb))
                p11 = la * lb * math.exp(-T)
                vals.append(btts - p11)
            res["btts3plus"] = sum(vals) / n_draws
        if "p_2h_2plus" in markets:
            vals = []
            for la, lb in zip(la_draws, lb_draws):
                lam_2h = 0.55 * (la + lb)
                vals.append(1 - math.exp(-lam_2h) * (1 + lam_2h))
            res["p_2h_2plus"] = sum(vals) / n_draws
        if "clean_sheet_a" in markets:
            res["clean_sheet_a"] = sum(math.exp(-lb) for lb in lb_draws) / n_draws
        if "scores_2h_a" in markets:
            res["scores_2h_a"] = sum(1 - math.exp(-0.55 * la) for la in la_draws) / n_draws
        out[m["name"]] = res
    return out


def jensen_fallback_widen(observed_source_spread_pts, cap=3):
    """v4 fallback if a flagged match is missed from the batch this session:
    widen by at most min(3, half the observed source spread), logged as a
    'lambda-uncertainty adjustment (Jensen correction)' — never safety shade."""
    return min(cap, observed_source_spread_pts / 2)
