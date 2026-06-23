"""
Jump Trading Probability Cup — Probability engine v3.
Implements all §5 procedures from probability-cup-system-instructions-v8-final.md.

Pure Python (stdlib only) — no numpy/scipy needed.
All output probabilities are 0–100 integers (as required by the platform).
"""

import math
import random
from constants import (
    PLAYER_SOT_BANDS, L10_DRIVER_GATE_LOW, L10_DRIVER_GATE_HIGH,
    SOA_MULTIPLIER_CREATOR, SOA_MULTIPLIER_PURE_9,
    NOISY_REGISTER_CLAMP, DC_DRAW_BUMP, WIN_BAND_DC_RANGE,
)

# ─────────────────────────────────────────────────────────────────────────────
# §5.1  Anchor extraction — power devig
# ─────────────────────────────────────────────────────────────────────────────

def power_devig(implied: list) -> tuple:
    """
    Solve Σ p_i^k = 1 via bisection (no scipy).  Returns (k, fair_probs).
    Use when overround > 5% AND favourite implied > 65% (§5.1 mandatory condition).
    Otherwise multiplicative devig (normalize) is fine.
    """
    lo, hi = 0.5, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if sum(p ** mid for p in implied) > 1.0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2.0
    fair = [p ** k for p in implied]
    return k, fair


def devig_2way(dec_yes: float, dec_no: float) -> float:
    """Multiplicative devig for a 2-way market. Returns P(yes) as 0–1."""
    imp_yes = 1.0 / dec_yes
    imp_no  = 1.0 / dec_no
    return imp_yes / (imp_yes + imp_no)


def devig_3way(dec_home: float, dec_draw: float, dec_away: float) -> tuple:
    """Multiplicative 3-way devig. Returns (p_home, p_draw, p_away) as 0–1."""
    ih, id_, ia = 1.0/dec_home, 1.0/dec_draw, 1.0/dec_away
    total = ih + id_ + ia
    return ih / total, id_ / total, ia / total


# ─────────────────────────────────────────────────────────────────────────────
# §5.2  λ engine — fit T from O/U 2.5, derive team split
# ─────────────────────────────────────────────────────────────────────────────

def ou25_to_T(p_over: float) -> float:
    """
    Invert P(total > 2.5) = 1 − Poisson_CDF(2, T) to recover T.
    Bisection over T ∈ [1.0, 5.0].
    """
    def p_over25(T):
        return 1.0 - math.exp(-T) * (1.0 + T + T * T / 2.0)

    lo, hi = 1.0, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if p_over25(mid) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def fit_split(T: float, p_home_win: float, p_draw: float = None) -> tuple:
    """
    Bisection to find (lam_a, lam_b=T−lam_a) that reproduces the devigged
    home-win probability within ±2 pp.  Returns (lam_a, lam_b).
    """
    def score_grid(la):
        lb = T - la
        if lb <= 0:
            return 0.0
        p_win = 0.0
        for i in range(8):
            pa_i = math.exp(-la) * la**i / math.factorial(i)
            for j in range(i):
                pb_j = math.exp(-lb) * lb**j / math.factorial(j)
                p_win += pa_i * pb_j
        return p_win - p_home_win   # zero when split matches

    lo, hi = 0.05, T - 0.05
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if score_grid(mid) < 0:
            lo = mid
        else:
            hi = mid
    la = (lo + hi) / 2.0
    return la, T - la


# ─────────────────────────────────────────────────────────────────────────────
# §5.2  Closed-form Poisson goal/score probabilities
# ─────────────────────────────────────────────────────────────────────────────

def p_scores_ft(lam: float) -> float:
    return 1.0 - math.exp(-lam)

def p_scores_2h(lam: float) -> float:
    return 1.0 - math.exp(-0.55 * lam)

def p_scores_1h(lam: float) -> float:
    return 1.0 - math.exp(-0.45 * lam)

def p_clean_sheet(lam_opponent: float) -> float:
    return math.exp(-lam_opponent)

def p_btts(lam_a: float, lam_b: float) -> float:
    return (1.0 - math.exp(-lam_a)) * (1.0 - math.exp(-lam_b))

def p_1_1(lam_a: float, lam_b: float) -> float:
    T = lam_a + lam_b
    return lam_a * lam_b * math.exp(-T)

def p_btts_and_3plus(lam_a: float, lam_b: float) -> float:
    """P(BTTS ∧ 3+ goals) = P(BTTS) − P(1-1). NEVER multiply marginals."""
    return p_btts(lam_a, lam_b) - p_1_1(lam_a, lam_b)


def dixon_coles_draw_bump(p_win_int: int, base_bump: int = 2) -> int:
    """
    §5.2/L12 hardened Dixon–Coles draw inflation in the 40–60 win band.
    Returns points to add to draw-flavored outcomes (applied input-side only).
    base_bump ∈ 1–3 (caller decides magnitude, capped at ±8 total overlay).
    """
    lo, hi = WIN_BAND_DC_RANGE
    if lo <= p_win_int <= hi:
        return base_bump
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# §5.4  Tie-trap engine — "Team A more X than Team B"
# ─────────────────────────────────────────────────────────────────────────────

def bessel_i0(x: float) -> float:
    """Modified Bessel I_0(x) via series (accurate to 1e-12 for x<20)."""
    result, term, k = 1.0, 1.0, 1
    while True:
        term *= (x / (2.0 * k)) ** 2
        result += term
        if term < 1e-12:
            break
        k += 1
    return result

def p_poisson_tie(m: float) -> float:
    """
    P(Poisson(m) = Poisson(m)), both teams equal count.
    = e^{-2m} · I₀(2m)
    """
    return math.exp(-2.0 * m) * bessel_i0(2.0 * m)

def tie_trap(m_a: float, m_b: float) -> int:
    """
    P(Team A more) for a strict "more than" comparison market.
    m_a, m_b: per-team Poisson rate for the stat.
    Returns integer 1–99.
    P(A more) = (1 − P(tie)) × P(A more | no tie).
    """
    m_avg = math.sqrt(m_a * m_b) if m_b > 0 else m_a
    p_tie = p_poisson_tie(m_avg)

    # Numerical: iterate Poisson grid up to 20
    p_a_more = 0.0
    for i in range(20):
        pa_i = math.exp(-m_a) * m_a**i / math.factorial(i)
        for j in range(i):
            pb_j = math.exp(-m_b) * m_b**j / math.factorial(j)
            p_a_more += pa_i * pb_j

    non_tie = 1.0 - p_tie
    if non_tie < 0.001:
        return clamp(round(p_a_more * 100))
    p = p_a_more
    return clamp(round(p * 100))


# ─────────────────────────────────────────────────────────────────────────────
# §5.5  Threshold Poisson tail — P(X ≥ n)
# ─────────────────────────────────────────────────────────────────────────────

def poisson_tail(lam: float, n: int) -> float:
    """P(Poisson(lam) ≥ n) = 1 − P(X ≤ n−1)."""
    cdf = sum(
        math.exp(-lam) * lam**k / math.factorial(k)
        for k in range(n)
    )
    return max(0.0, 1.0 - cdf)

def p_team_ge5_corners(lam: float) -> int:
    return clamp(round(poisson_tail(lam, 5) * 100))

def p_team_ge2_sot(lam: float) -> int:
    return clamp(round(poisson_tail(lam, 2) * 100))

def p_ge2_goals_2h(lam_total: float) -> int:
    """P(≥2 goals in 2H) where 2H λ = 0.55 × lam_total."""
    return clamp(round(poisson_tail(0.55 * lam_total, 2) * 100))

def p_ht_tied(lam_a: float, lam_b: float) -> int:
    """
    HT-tied probability via exact Bessel formula (§5.5).
    lam_a, lam_b are FULL-MATCH lambdas; HT share = 0.45.
    Applies L9 ceiling of 47.
    """
    la = 0.45 * lam_a
    lb = 0.45 * lam_b
    T_ht = la + lb
    p = math.exp(-T_ht) * bessel_i0(2.0 * math.sqrt(la * lb))
    return clamp(round(p * 100), 1, 47)   # L9 ceiling

def p_ht_both_sot(lam_sot_a: float, lam_sot_b: float) -> int:
    """P(both teams ≥1 SOT at HT). HT SOT share ≈ 0.45."""
    pa = 1.0 - math.exp(-0.45 * lam_sot_a)
    pb = 1.0 - math.exp(-0.45 * lam_sot_b)
    return clamp(round(pa * pb * 100))

def p_both_sot_2h(lam_sot_a: float, lam_sot_b: float) -> int:
    """P(both teams ≥1 SOT in 2H). 2H SOT share ≈ 0.55."""
    pa = 1.0 - math.exp(-0.55 * lam_sot_a)
    pb = 1.0 - math.exp(-0.55 * lam_sot_b)
    return clamp(round(pa * pb * 100))


# ─────────────────────────────────────────────────────────────────────────────
# §5.6  Player-prop engine (L7 / L10)
# ─────────────────────────────────────────────────────────────────────────────

def player_goal_prob(team_lam: float, goal_share: float) -> int:
    """Anytime goal = 1 − e^(−lam_player)."""
    lam_p = team_lam * goal_share
    return clamp(round(p_scores_ft(lam_p) * 100))

def player_sot_prop(
    team_lam: float,
    sot_share: float,
    role: str = "main_striker",
    has_driver: bool = False,
) -> int:
    """
    Player 1+ SOT probability with L10 band enforcement.
    role: "main_striker" or "winger_am"
    has_driver: True if an explicit written driver is provided
                (required for modeled p in top half of 56-70, §5.6 L10 gate).
    """
    lam_player_sot = team_lam * sot_share
    raw_p = round((1.0 - math.exp(-lam_player_sot)) * 100)

    lo, hi = PLAYER_SOT_BANDS.get(role, (42, 56))
    p = clamp(raw_p, lo, hi)

    # L10 driver gate: if p falls in 63-70 (top half of 56-70) and no driver → regress
    if L10_DRIVER_GATE_LOW <= p <= L10_DRIVER_GATE_HIGH and not has_driver:
        p = L10_DRIVER_GATE_LOW - 1

    return clamp(p)

def player_sot_2h(team_lam: float, sot_share: float) -> int:
    """Player 1+ SOT in 2H ≈ 1 − e^(−0.55·lam_player_sot)."""
    lam_p = team_lam * sot_share
    return clamp(round((1.0 - math.exp(-0.55 * lam_p)) * 100))

def score_or_assist(
    goal_prob_pct: int,
    role: str = "creator",
) -> int:
    """
    Score-or-assist = goal × multiplier, overlap-corrected (§5.6).
    goal_prob_pct: anytime goal probability as integer.
    role: "creator" (×1.5–1.8) or "pure_9" (×1.2–1.4).
    """
    if role == "creator":
        mult = sum(SOA_MULTIPLIER_CREATOR) / 2.0
    else:
        mult = sum(SOA_MULTIPLIER_PURE_9) / 2.0
    return clamp(round(goal_prob_pct * mult))


# ─────────────────────────────────────────────────────────────────────────────
# §5.7  Joint / sequence props
# ─────────────────────────────────────────────────────────────────────────────

def p_scores_first(lam_a: float, T: float) -> float:
    """P(A scores first) ≈ (lam_a / T) × P(at least one goal)."""
    if T < 0.01:
        return 0.0
    return (lam_a / T) * (1.0 - math.exp(-T))

def joint_scores_first_and_b_scores_2h(
    lam_a: float, lam_b: float, dep_haircut: int = 1
) -> int:
    """
    P(A first ∧ B scores 2H). Applies −dep_haircut dependence haircut.
    Never exceeds either marginal.
    """
    T = lam_a + lam_b
    pa_first = p_scores_first(lam_a, T)
    pb_2h    = p_scores_2h(lam_b)
    raw = round(pa_first * pb_2h * 100) - dep_haircut
    p = clamp(raw)
    # Must not exceed either marginal
    return min(p, round(pa_first * 100), round(pb_2h * 100))


# ─────────────────────────────────────────────────────────────────────────────
# §5.9  Noisy register clamp
# ─────────────────────────────────────────────────────────────────────────────

def noisy_clamp(p: int, anchored: bool = False) -> int:
    lo, hi = NOISY_REGISTER_CLAMP
    if anchored:
        return clamp(p)
    return clamp(p, lo, hi)


# ─────────────────────────────────────────────────────────────────────────────
# §5.11  L8 — batched MC over λ uncertainty (pure Python, no numpy)
# ─────────────────────────────────────────────────────────────────────────────

def _gauss_clip(mu: float, sigma: float, rng: random.Random, lo: float = 0.05) -> float:
    """Sample Normal(mu, sigma) clipped below `lo`."""
    while True:
        v = rng.gauss(mu, sigma)
        if v >= lo:
            return v

def batch_mc(matches: list, n_draws: int = 2000, seed: int = 42) -> dict:
    """
    MC integration over λ uncertainty for correlated market baskets (§5.11).

    Each entry in `matches`:
        {
          "name": str,
          "lam_a": float, "sigma_a": float,
          "lam_b": float, "sigma_b": float,
          "markets": list[str]   # keys from the supported set below
        }

    Supported market keys:
        btts3plus, p_2h_2plus, clean_sheet_a, clean_sheet_b,
        scores_2h_a, scores_2h_b, scores_ft_a, scores_ft_b,
        ht_tied, p_over_25, p_le2

    Returns: {match_name: {market_key: int (1–99)}}
    """
    rng = random.Random(seed)
    out = {}

    for m in matches:
        la_mu, la_sigma = m["lam_a"], m["sigma_a"]
        lb_mu, lb_sigma = m["lam_b"], m["sigma_b"]
        mkts = set(m.get("markets", []))

        accum = {k: 0.0 for k in mkts}

        for _ in range(n_draws):
            la = _gauss_clip(la_mu, la_sigma, rng)
            lb = _gauss_clip(lb_mu, lb_sigma, rng)
            T  = la + lb

            if "btts3plus" in mkts:
                btts = (1 - math.exp(-la)) * (1 - math.exp(-lb))
                p11  = la * lb * math.exp(-T)
                accum["btts3plus"] += btts - p11

            if "p_2h_2plus" in mkts:
                lam_2h = 0.55 * T
                accum["p_2h_2plus"] += 1 - math.exp(-lam_2h) * (1 + lam_2h)

            if "clean_sheet_a" in mkts:
                accum["clean_sheet_a"] += math.exp(-lb)

            if "clean_sheet_b" in mkts:
                accum["clean_sheet_b"] += math.exp(-la)

            if "scores_2h_a" in mkts:
                accum["scores_2h_a"] += 1 - math.exp(-0.55 * la)

            if "scores_2h_b" in mkts:
                accum["scores_2h_b"] += 1 - math.exp(-0.55 * lb)

            if "scores_ft_a" in mkts:
                accum["scores_ft_a"] += 1 - math.exp(-la)

            if "scores_ft_b" in mkts:
                accum["scores_ft_b"] += 1 - math.exp(-lb)

            if "ht_tied" in mkts:
                la_ht = 0.45 * la
                lb_ht = 0.45 * lb
                T_ht  = la_ht + lb_ht
                x = 2.0 * math.sqrt(la_ht * lb_ht)
                accum["ht_tied"] += math.exp(-T_ht) * bessel_i0(x)

            if "p_over_25" in mkts:
                accum["p_over_25"] += 1 - math.exp(-T) * (1 + T + T*T/2)

            if "p_le2" in mkts:
                accum["p_le2"] += math.exp(-T) * (1 + T + T*T/2)

        res = {}
        for k in mkts:
            mean_p = accum[k] / n_draws
            val = clamp(round(mean_p * 100))
            if k == "ht_tied":
                val = min(val, 47)   # L9 ceiling
            res[k] = val

        out[m["name"]] = res

    return out


# ─────────────────────────────────────────────────────────────────────────────
# §9.2  Outcome decoding (no web lookups needed)
# ─────────────────────────────────────────────────────────────────────────────

def decode_outcome(p_decimal: float, brier: float, eps: float = 1e-4) -> int:
    """
    Given submitted p (0–1) and Brier score, return outcome 0 or 1.
    o=1 iff (p−1)² ≈ brier, else o=0. Returns −1 if p≈0.5 (undefined).
    """
    if abs(p_decimal - 0.5) < eps:
        return -1
    if abs((p_decimal - 1.0) ** 2 - brier) < eps:
        return 1
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# §1.1  Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def brier_score(p: int, outcome: int) -> float:
    """Brier score. p is integer 1–99; outcome ∈ {0,1}."""
    return (p / 100.0 - outcome) ** 2

def rbp(crowd_brier: float, your_brier: float, stage_weight: int = 1) -> float:
    """Relative Brier Points per market."""
    return (crowd_brier - your_brier) * 100.0 * stage_weight

def self_expected_brier(p: int) -> float:
    """E[Brier] = p(1-p) for a calibrated submitter."""
    q = p / 100.0
    return q * (1.0 - q)


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def clamp(x, lo: int = 1, hi: int = 99) -> int:
    return max(lo, min(hi, int(round(x))))


# ─────────────────────────────────────────────────────────────────────────────
# Quick self-test (run as: python3 engine.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    la, lb = 1.35, 1.35
    print(f"BTTS         = {round(p_btts(la,lb)*100)}  (expect 55)")
    print(f"P(1-1)       = {round(p_1_1(la,lb)*100)}   (expect 12)")
    print(f"BTTS∧3+      = {round(p_btts_and_3plus(la,lb)*100)}  (expect 43)")

    print(f"HT-tied T=2.5 even = {p_ht_tied(1.25, 1.25)}  (expect 44)")
    print(f"Tie-trap fouls even = {tie_trap(11.0, 11.0)}  (expect ~46)")
    print(f"P(≥5 corners, lam=4.5) = {p_team_ge5_corners(4.5)}  (expect 47)")
    print(f"P(≥2 SOT, lam=2.0)     = {p_team_ge2_sot(2.0)}  (expect 59)")

    result = batch_mc([{
        "name": "test",
        "lam_a": 1.35, "sigma_a": 0.20,
        "lam_b": 1.35, "sigma_b": 0.20,
        "markets": ["btts3plus", "p_2h_2plus", "ht_tied"],
    }], n_draws=500, seed=42)
    print(f"MC btts3plus = {result['test']['btts3plus']}  (expect near 43)")
    print(f"MC ht_tied   = {result['test']['ht_tied']}   (expect near 44)")

    k, fair = power_devig([0.52, 0.30, 0.25])
    print(f"Power devig k={k:.3f}  fair=[{','.join(str(round(p*100)) for p in fair)}]  sum={sum(fair):.4f}")

    print(f"ou25_to_T(0.46) = {ou25_to_T(0.46):.2f}  (expect 2.5)")
    print(f"decode(0.7, {(0.7-1)**2:.4f}) = {decode_outcome(0.7, (0.7-1)**2)}")
    print(f"decode(0.7, {(0.7)**2:.4f}) = {decode_outcome(0.7, (0.7)**2)}")

    print(f"player_sot_prop(lam=1.8, share=0.35, role=main_striker, driver=False) = "
          f"{player_sot_prop(1.8, 0.35, 'main_striker', False)}")
    print(f"player_sot_prop(lam=1.8, share=0.35, role=main_striker, driver=True) = "
          f"{player_sot_prop(1.8, 0.35, 'main_striker', True)}")
