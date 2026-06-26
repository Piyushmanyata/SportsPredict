"""
Monte Carlo integration for L8 correlation cap (§5.11).

When >4 of ~10 markets share a latent axis (team λ), integrate over
λ uncertainty instead of submitting deterministic point estimates.

The batch_mc() function is the canonical implementation from §5.11.
"""

import numpy as np
from .lambda_engine import poisson_cdf


def batch_mc(
    matches: list[dict],
    n_draws: int = 2000,
    seed: int = 42,
) -> dict[str, dict[str, float]]:
    """
    Batched MC integration across multiple matches (L8, §5.11).

    matches: list of dicts, each:
      {
        "name": str,
        "lam_a": float, "sigma_a": float,
        "lam_b": float, "sigma_b": float,
        "markets": list of market keys to evaluate (see below),
        # optional: lam_sot_a, lam_sot_b, lam_cards
      }

    Supported market keys:
      win_a, win_b, draw,
      btts, btts3plus,
      goals_3plus, goals_2_or_fewer,
      scores_a, scores_b,
      scores_2h_a, scores_2h_b,
      clean_sheet_a, clean_sheet_b,
      p_2h_2plus,
      ht_tied,
      ht_both_sot,
      sot_team_2plus_a, sot_team_2plus_b,

    Returns: dict[match_name → dict[market_key → float probability in 0-1]]
    """
    rng = np.random.default_rng(seed)
    out = {}

    for m in matches:
        la_draws = np.clip(rng.normal(m["lam_a"], m["sigma_a"], n_draws), 0.05, None)
        lb_draws = np.clip(rng.normal(m["lam_b"], m["sigma_b"], n_draws), 0.05, None)
        T_draws  = la_draws + lb_draws
        mkts = set(m.get("markets", []))
        res  = {}

        # ---- Goal markets ----
        if "goals_3plus" in mkts:
            # P(Poisson(T) > 2) = 1 - e^-T(1 + T + T²/2)
            p = 1 - np.exp(-T_draws) * (1 + T_draws + T_draws**2 / 2)
            res["goals_3plus"] = float(np.mean(p))

        if "goals_2_or_fewer" in mkts:
            p = np.exp(-T_draws) * (1 + T_draws + T_draws**2 / 2)
            res["goals_2_or_fewer"] = float(np.mean(p))

        if "btts" in mkts or "btts3plus" in mkts:
            btts_arr = (1 - np.exp(-la_draws)) * (1 - np.exp(-lb_draws))
            if "btts" in mkts:
                res["btts"] = float(np.mean(btts_arr))
            if "btts3plus" in mkts:
                p11 = la_draws * lb_draws * np.exp(-T_draws)
                res["btts3plus"] = float(np.mean(btts_arr - p11))

        if "p_2h_2plus" in mkts:
            lam_2h = 0.55 * T_draws
            res["p_2h_2plus"] = float(np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h)))

        if "clean_sheet_a" in mkts:
            res["clean_sheet_a"] = float(np.mean(np.exp(-lb_draws)))

        if "clean_sheet_b" in mkts:
            res["clean_sheet_b"] = float(np.mean(np.exp(-la_draws)))

        if "scores_a" in mkts:
            res["scores_a"] = float(np.mean(1 - np.exp(-la_draws)))

        if "scores_b" in mkts:
            res["scores_b"] = float(np.mean(1 - np.exp(-lb_draws)))

        if "scores_2h_a" in mkts:
            res["scores_2h_a"] = float(np.mean(1 - np.exp(-0.55 * la_draws)))

        if "scores_2h_b" in mkts:
            res["scores_2h_b"] = float(np.mean(1 - np.exp(-0.55 * lb_draws)))

        # ---- Win markets (requires score grid) ----
        if any(k in mkts for k in ("win_a", "draw", "win_b")):
            max_g = 8
            g = np.arange(max_g + 1)
            # Vectorised 1X2 over draws
            win_a_arr = np.zeros(n_draws)
            draw_arr  = np.zeros(n_draws)
            win_b_arr = np.zeros(n_draws)
            for a in range(max_g + 1):
                for b in range(max_g + 1):
                    # PMF for each draw
                    log_pa = a * np.log(la_draws) - la_draws - _log_factorial(a)
                    log_pb = b * np.log(lb_draws) - lb_draws - _log_factorial(b)
                    joint  = np.exp(log_pa + log_pb)
                    if a > b:
                        win_a_arr += joint
                    elif a == b:
                        draw_arr  += joint
                    else:
                        win_b_arr += joint
            if "win_a" in mkts:
                res["win_a"] = float(np.mean(win_a_arr))
            if "draw" in mkts:
                res["draw"] = float(np.mean(draw_arr))
            if "win_b" in mkts:
                res["win_b"] = float(np.mean(win_b_arr))

        # ---- HT tied ----
        if "ht_tied" in mkts:
            from scipy.special import i0 as bessel_i0
            la_ht = 0.45 * la_draws
            lb_ht = 0.45 * lb_draws
            p = np.exp(-(la_ht + lb_ht)) * bessel_i0(2 * np.sqrt(la_ht * lb_ht))
            raw = float(np.mean(p))
            # L9 ceiling 47 applies on the mean
            if raw > 0.47 and (m["lam_a"] + m["lam_b"]) >= 2.2:
                raw = 0.47
            res["ht_tied"] = raw

        # ---- HT both teams ≥1 SOT ----
        if "ht_both_sot" in mkts:
            lam_sot_a = m.get("lam_sot_a", m["lam_a"] * 3.0)
            lam_sot_b = m.get("lam_sot_b", m["lam_b"] * 3.0)
            la_sot_ht = 0.45 * lam_sot_a
            lb_sot_ht = 0.45 * lam_sot_b
            p = (1 - np.exp(-la_sot_ht)) * (1 - np.exp(-lb_sot_ht))
            res["ht_both_sot"] = float(p)  # deterministic (no λ MC on SOT here)

        if "sot_team_2plus_a" in mkts:
            lam_sot_a = m.get("lam_sot_a", m["lam_a"] * 3.0)
            p = 1 - np.exp(-lam_sot_a) * (1 + lam_sot_a)
            res["sot_team_2plus_a"] = float(p)

        if "sot_team_2plus_b" in mkts:
            lam_sot_b = m.get("lam_sot_b", m["lam_b"] * 3.0)
            p = 1 - np.exp(-lam_sot_b) * (1 + lam_sot_b)
            res["sot_team_2plus_b"] = float(p)

        out[m["name"]] = res

    return out


def mc_single(
    lam_a: float,
    lam_b: float,
    sigma_a: float | None = None,
    sigma_b: float | None = None,
    markets: list[str] | None = None,
    n_draws: int = 2000,
    seed: int = 42,
    **kwargs,
) -> dict[str, float]:
    """Convenience wrapper for a single match."""
    if sigma_a is None:
        sigma_a = 0.15 * lam_a
    if sigma_b is None:
        sigma_b = 0.15 * lam_b
    if markets is None:
        markets = [
            "win_a", "draw", "win_b",
            "goals_3plus", "goals_2_or_fewer",
            "btts", "btts3plus",
            "scores_a", "scores_b",
            "scores_2h_a", "scores_2h_b",
            "p_2h_2plus", "ht_tied",
        ]
    result = batch_mc(
        [{"name": "single", "lam_a": lam_a, "sigma_a": sigma_a,
          "lam_b": lam_b, "sigma_b": sigma_b, "markets": markets, **kwargs}],
        n_draws=n_draws,
        seed=seed,
    )
    return result["single"]


def _log_factorial(n: int) -> float:
    import math
    return math.lgamma(n + 1)


def mc_to_int(mc_result: dict[str, float]) -> dict[str, int]:
    """Convert MC probabilities to 1-99 integers."""
    return {k: max(1, min(99, round(v * 100))) for k, v in mc_result.items()}
