"""
Batch Monte Carlo integration for correlated market baskets — §5.11 / L8.
Fires when >4 of ~10 markets load on the same latent λ/split axis.
Single numpy call per session (never loop per market).
"""
import numpy as np


def batch_mc(matches: list, n_draws: int = 2000, seed: int = 42) -> dict:
    """
    §5.11 canonical implementation.
    matches: list of dicts, each:
      {
        "name":    str,
        "lam_a":   float,   "sigma_a": float,
        "lam_b":   float,   "sigma_b": float,
        "sot_a":   float,   "sigma_sot_a": float,   # optional
        "sot_b":   float,   "sigma_sot_b": float,   # optional
        "markets": list[str]   # keys from the formula dict below
      }
    Returns: {match_name: {market_key: mc_probability_int}}

    sigma default: 0.15 × λ̂ (documented placeholder per §5.11).
    """
    rng = np.random.default_rng(seed)
    out = {}

    for m in matches:
        la_hat  = m["lam_a"]
        lb_hat  = m["lam_b"]
        sig_a   = m.get("sigma_a", 0.15 * la_hat)
        sig_b   = m.get("sigma_b", 0.15 * lb_hat)
        sot_a_hat = m.get("sot_a", la_hat * 4.0)
        sot_b_hat = m.get("sot_b", lb_hat * 4.0)
        sig_sa  = m.get("sigma_sot_a", 0.15 * sot_a_hat)
        sig_sb  = m.get("sigma_sot_b", 0.15 * sot_b_hat)
        mkts    = set(m.get("markets", []))

        la  = np.clip(rng.normal(la_hat,  sig_a,  n_draws), 0.05, None)
        lb  = np.clip(rng.normal(lb_hat,  sig_b,  n_draws), 0.05, None)
        sa  = np.clip(rng.normal(sot_a_hat, sig_sa, n_draws), 0.5, None)
        sb  = np.clip(rng.normal(sot_b_hat, sig_sb, n_draws), 0.5, None)
        T   = la + lb

        res = {}

        # ── Goal markets ────────────────────────────────────────────────────
        if "btts" in mkts:
            res["btts"] = int(round(np.mean((1-np.exp(-la)) * (1-np.exp(-lb))) * 100))

        if "btts_3plus" in mkts:
            btts = (1-np.exp(-la)) * (1-np.exp(-lb))
            p11  = la * lb * np.exp(-T)
            res["btts_3plus"] = int(round(np.mean(np.maximum(0, btts - p11)) * 100))

        if "3plus_goals" in mkts:
            # P(Poisson(T) ≥ 3) per draw — approximate via 1-CDF(2)
            p_le2 = np.exp(-T) * (1 + T + T**2/2)
            res["3plus_goals"] = int(round(np.mean(1 - p_le2) * 100))

        if "2or_fewer_goals" in mkts:
            p_le2 = np.exp(-T) * (1 + T + T**2/2)
            res["2or_fewer_goals"] = int(round(np.mean(p_le2) * 100))

        if "team_a_scores" in mkts:
            res["team_a_scores"] = int(round(np.mean(1 - np.exp(-la)) * 100))

        if "team_b_scores" in mkts:
            res["team_b_scores"] = int(round(np.mean(1 - np.exp(-lb)) * 100))

        if "team_a_scores_2h" in mkts:
            res["team_a_scores_2h"] = int(round(np.mean(1 - np.exp(-0.55*la)) * 100))

        if "team_b_scores_2h" in mkts:
            res["team_b_scores_2h"] = int(round(np.mean(1 - np.exp(-0.55*lb)) * 100))

        if "2h_goals_2plus" in mkts:
            lam_2h = 0.55 * T
            res["2h_goals_2plus"] = int(round(
                np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h)) * 100))

        if "clean_sheet_a" in mkts:
            res["clean_sheet_a"] = int(round(np.mean(np.exp(-lb)) * 100))

        if "clean_sheet_b" in mkts:
            res["clean_sheet_b"] = int(round(np.mean(np.exp(-la)) * 100))

        if "goal_before_break1" in mkts:
            lam_30 = T * 30.0 / 90.0
            p_le0_30 = np.exp(-lam_30)
            res["goal_before_break1"] = int(round(np.mean(1 - p_le0_30) * 100))

        if "goal_after_break2" in mkts:
            lam_tail = T * 20.0 / 90.0
            res["goal_after_break2"] = int(round(np.mean(1 - np.exp(-lam_tail)) * 100))

        if "goal_ht_stoppage" in mkts:
            lam_st = T * 4.0 / 90.0
            res["goal_ht_stoppage"] = int(round(np.mean(1 - np.exp(-lam_st)) * 100))

        if "goal_2h_stoppage" in mkts:
            lam_st2 = T * 5.0 / 90.0
            res["goal_2h_stoppage"] = int(round(np.mean(1 - np.exp(-lam_st2)) * 100))

        # ── SOT markets ─────────────────────────────────────────────────────
        if "team_a_6plus_sot" in mkts:
            # P(Poisson(sa) ≥ 6) — approximate via survival
            p_le5 = sum(np.exp(-sa) * sa**k / float(__import__('math').factorial(k))
                        for k in range(6))
            res["team_a_6plus_sot"] = int(round(np.mean(1 - p_le5) * 100))

        if "team_a_7plus_sot" in mkts:
            p_le6 = sum(np.exp(-sa) * sa**k / float(__import__('math').factorial(k))
                        for k in range(7))
            res["team_a_7plus_sot"] = int(round(np.mean(1 - p_le6) * 100))

        # ── Scores-first ────────────────────────────────────────────────────
        if "team_a_scores_first" in mkts:
            res["team_a_scores_first"] = int(round(
                np.mean((la / T) * (1 - np.exp(-T))) * 100))

        if "team_b_scores_first" in mkts:
            res["team_b_scores_first"] = int(round(
                np.mean((lb / T) * (1 - np.exp(-T))) * 100))

        # ── Win markets ──────────────────────────────────────────────────────
        # (Approximate: skip full grid in MC — use Skellam distribution proxy)
        # For production use, run full grid MC only when L8 specifically flags it.

        out[m["name"]] = {k: max(1, min(99, v)) for k, v in res.items()}

    return out


def should_run_mc(n_markets_on_axis: int) -> bool:
    """§5.11 gate: run MC when >4 of ~10 markets load on same latent axis."""
    return n_markets_on_axis > 4


def default_sigma(lam: float) -> float:
    """Default σ = 0.15·λ̂ when no cross-source spread available (§5.11)."""
    return 0.15 * lam
