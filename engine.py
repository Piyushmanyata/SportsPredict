"""
Jump Trading Probability Cup — Probability Engine v3 (§5).

All formulas exact per spec. Call via Bash tool with:
    python -c "from engine import *; print(to_int(btts(1.65, 1.05)))"

Requires: numpy, scipy
"""

import math
import numpy as np
from scipy.optimize import root_scalar
from scipy.special import i0 as bessel_i0

from constants import (
    OU25_TO_T, TIE_TRAP_REF, CARDS_TABLE, CORNERS_TABLE,
    SOT_GTE2_TABLE, OFFSIDES_TABLE, NOISY_MARKET_KEYWORDS,
)


# ---------------------------------------------------------------------------
# §5.1  Anchor extraction — devigging
# ---------------------------------------------------------------------------

def power_devig(implied):
    """
    Find k such that sum(p**k for p in implied) == 1.
    Returns fair probabilities. Falls back to multiplicative on solver failure.
    Spec §5.1 — exact code from spec.
    """
    def f(k):
        return sum(p**k for p in implied) - 1
    try:
        k = root_scalar(f, bracket=[0.5, 2.0]).root
        return [p**k for p in implied]
    except Exception:
        total = sum(implied)
        return [p / total for p in implied]


def devig_3way(odds_home, odds_draw, odds_away):
    """
    Devig a 1X2 market from decimal odds.
    Returns (p_home, p_draw, p_away) as 0-1 floats. §5.1
    """
    implied = [1.0 / odds_home, 1.0 / odds_draw, 1.0 / odds_away]
    result = power_devig(implied)
    return tuple(result)


def devig_2way(odds_yes, odds_no):
    """
    Devig a 2-way market.
    Uses power devig when overround >5% and favourite implied >65%; else multiplicative. §5.1
    Returns (p_yes, p_no).
    """
    imp = [1.0 / odds_yes, 1.0 / odds_no]
    total = sum(imp)
    overround_pct = (total - 1) * 100
    if overround_pct > 5 and max(imp) / total > 0.65:
        result = power_devig(imp)
    else:
        result = [p / total for p in imp]
    return (result[0], result[1])


# ---------------------------------------------------------------------------
# §5.2  λ engine — derive everything from two anchored numbers
# ---------------------------------------------------------------------------

def t_from_ou25(p_over_25):
    """Interpolate expected total goals T from devigged P(over 2.5). §5.2 table."""
    table = OU25_TO_T
    if p_over_25 <= table[0][0]:
        return table[0][1]
    if p_over_25 >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        p1, t1 = table[i]
        p2, t2 = table[i + 1]
        if p1 <= p_over_25 <= p2:
            alpha = (p_over_25 - p1) / (p2 - p1)
            return t1 + alpha * (t2 - t1)
    return 2.5


def poisson_pmf(lam, k):
    """P(X = k) for Poisson(lam)."""
    if lam <= 0 or k < 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(min(k, 20))


def poisson_cdf(lam, max_k):
    """P(X <= max_k) for Poisson(lam)."""
    return sum(poisson_pmf(lam, k) for k in range(max_k + 1))


def poisson_1x2(lam_a, lam_b, max_goals=12):
    """Compute P(home_win), P(draw), P(away_win) from independent Poisson. §5.2"""
    p_home = p_draw = p_away = 0.0
    for ga in range(max_goals):
        pa = poisson_pmf(lam_a, ga)
        if pa < 1e-12:
            continue
        for gb in range(max_goals):
            pb = poisson_pmf(lam_b, gb)
            if pb < 1e-12:
                continue
            joint = pa * pb
            if ga > gb:
                p_home += joint
            elif ga == gb:
                p_draw += joint
            else:
                p_away += joint
    return p_home, p_draw, p_away


def find_lambda_split(T, p_home, p_draw, p_away):
    """
    Find (lam_a, lam_b) with lam_a + lam_b = T that reproduces devigged 1X2 within ±2pp.
    Scans in 0.05 steps. §5.2 — calibrate the split to reproduce the 1X2, not labels.
    Returns (lam_a, lam_b).
    """
    best = None
    best_err = float("inf")
    steps = int(T / 0.05)
    for i in range(1, steps):
        lam_a = i * 0.05
        lam_b = T - lam_a
        if lam_b <= 0.05:
            continue
        ph, pd, pa = poisson_1x2(lam_a, lam_b)
        err = abs(ph - p_home) + abs(pd - p_draw) + abs(pa - p_away)
        if err < best_err:
            best_err = err
            best = (round(lam_a, 3), round(lam_b, 3))
    return best


# ---------------------------------------------------------------------------
# §5.2  Core closed-form market formulas
# ---------------------------------------------------------------------------

def team_scores(lam):
    """P(team scores ≥ 1). §5.2"""
    return 1 - math.exp(-lam)


def team_scores_2h(lam):
    """P(team scores in 2H). 2H share ≈ 55%. §5.2"""
    return 1 - math.exp(-0.55 * lam)


def team_scores_1h(lam):
    """P(team scores in 1H). 1H share ≈ 45%. §5.2"""
    return 1 - math.exp(-0.45 * lam)


def clean_sheet(lam_opponent):
    """P(team keeps clean sheet) = e^(−λ_opponent). §5.2"""
    return math.exp(-lam_opponent)


def btts(lam_a, lam_b):
    """P(both teams score). §5.2"""
    return team_scores(lam_a) * team_scores(lam_b)


def p_score_1_1(lam_a, lam_b):
    """P(scoreline exactly 1-1). §5.2"""
    T = lam_a + lam_b
    return lam_a * lam_b * math.exp(-T)


def btts3plus(lam_a, lam_b):
    """P(BTTS AND ≥3 total goals) = P(BTTS) − P(1-1). §5.2 — never multiply marginals."""
    return btts(lam_a, lam_b) - p_score_1_1(lam_a, lam_b)


def p_over_n5(T, n_goals_threshold=2):
    """
    P(total goals > n_goals_threshold) using exact Poisson(T).
    Default: P(over 2.5) = P(≥3 goals).
    """
    return 1 - poisson_cdf(T, n_goals_threshold)


def p_2h_goals_gte(T, n):
    """P(2H goals ≥ n). 2H λ = 0.55 × T. §5.2"""
    return 1 - poisson_cdf(0.55 * T, n - 1)


def dixon_coles_draw_adjustment(lam_a, lam_b, win_band_40_60=False):
    """
    Dixon–Coles caveat (§5.2 hardened v8): raw Poisson underprices draws/low scores.
    Returns +pp adjustment to draw probability (subtract from win probabilities).
    Apply firmly in 40-60 win band (L12 ACTIVE). Cap: +1 to +3.
    """
    T = lam_a + lam_b
    is_defensive = T < 2.5
    in_win_band = win_band_40_60

    if in_win_band and is_defensive:
        return 3
    elif in_win_band:
        return 2
    elif is_defensive:
        return 2
    else:
        return 1


# ---------------------------------------------------------------------------
# §5.4  Tie-trap engine for strict "Team A more X than Team B" markets
# ---------------------------------------------------------------------------

def tie_mass_poisson(m):
    """
    Exact P(tie) when both sides are Poisson(m).
    P(X = Y) = e^(-2m) × I_0(2m). §5.4
    """
    return math.exp(-2 * m) * float(bessel_i0(2 * m))


def tie_trap_prob_general(m_a, m_b, max_k=40):
    """
    P(A > B) for two independent Poisson(m_a), Poisson(m_b) via exact enumeration.
    For even matchups (m_a ≈ m_b), use TIE_TRAP_REF table instead. §5.4
    """
    p_a_more = 0.0
    for ka in range(max_k):
        pa = poisson_pmf(m_a, ka)
        if pa < 1e-12:
            break
        for kb in range(ka):
            pb = poisson_pmf(m_b, kb)
            if pb < 1e-12:
                continue
            p_a_more += pa * pb
    return p_a_more


def tie_trap(m_a, m_b, stat_type=None):
    """
    P(A more X than B) with tie-trap correction.
    stat_type: key in TIE_TRAP_REF for the even-matchup table shortcut. §5.4
    Returns float 0-1. Never hand 50 to a strict comparison (L3 CONFIRMED).
    """
    # Even matchup shortcut from §5.4 reference table
    if stat_type and abs(m_a - m_b) < 0.1 and stat_type in TIE_TRAP_REF:
        return TIE_TRAP_REF[stat_type]["even_more"] / 100.0

    # Strength-skew range: dominant side conditional split ~55-65 → 44-52%; weak 27-36%
    return tie_trap_prob_general(m_a, m_b)


# ---------------------------------------------------------------------------
# §5.5  Threshold & state tables
# ---------------------------------------------------------------------------

def _interpolate(table, value):
    """Linear interpolation from a sorted {key: float} table."""
    keys = sorted(table.keys())
    if value <= keys[0]:
        return table[keys[0]]
    if value >= keys[-1]:
        return table[keys[-1]]
    for i in range(len(keys) - 1):
        k1, k2 = keys[i], keys[i + 1]
        if k1 <= value <= k2:
            alpha = (value - k1) / (k2 - k1)
            return table[k1] + alpha * (table[k2] - table[k1])
    return table[keys[-1]]


def cards_gte4(lam_cards):
    """P(total cards ≥ 4) by match cards λ. §5.5 table."""
    return _interpolate({k: v["gte4"] for k, v in CARDS_TABLE.items()}, lam_cards)


def cards_2h_gte2(lam_cards):
    """P(2H cards ≥ 2) by match cards λ. 2H share ≈ 0.62. §5.5 table."""
    return _interpolate({k: v["gte2_2h"] for k, v in CARDS_TABLE.items()}, lam_cards)


def corners_gte5(lam_corners_team):
    """P(team corners ≥ 5). §5.5 table."""
    return _interpolate(CORNERS_TABLE, lam_corners_team)


def sot_gte2(lam_sot_team):
    """P(team SOT ≥ 2). §5.5 table."""
    return _interpolate(SOT_GTE2_TABLE, lam_sot_team)


def offsides_gte2(lam_offsides_team):
    """P(team offsides ≥ 2). §5.5 table."""
    return _interpolate(OFFSIDES_TABLE, lam_offsides_team)


def ht_tied(lam_a, lam_b):
    """
    P(match tied at HT). HT λ share = 0.45. Bessel formula. §5.5
    L9: ceiling 47 unless T < 2.2.
    """
    la = 0.45 * lam_a
    lb = 0.45 * lam_b
    return math.exp(-(la + lb)) * float(bessel_i0(2 * math.sqrt(la * lb)))


def ht_tied_capped(lam_a, lam_b):
    """ht_tied() with L9 ceiling applied (max 47%). §5.5 / §10 L9"""
    T = lam_a + lam_b
    raw = ht_tied(lam_a, lam_b)
    if T >= 2.2:
        return min(raw, 0.47)
    return raw


def ht_both_sot(lam_sot_a, lam_sot_b):
    """
    P(HT, both teams ≥ 1 SOT). HT SOT share ≈ 0.45. §5.5
    Product of independent HT-SOT Poissons.
    """
    la = 0.45 * lam_sot_a
    lb = 0.45 * lam_sot_b
    return (1 - math.exp(-la)) * (1 - math.exp(-lb))


# ---------------------------------------------------------------------------
# §5.6  Player-prop engine (lineup-gated, L7)
# ---------------------------------------------------------------------------

def player_goal_prob(lam_team, goal_share):
    """P(player scores ≥ 1 goal). lam_player = lam_team × goal_share. §5.6"""
    lam_p = lam_team * goal_share
    return 1 - math.exp(-lam_p)


def player_sot_1plus(lam_player_sot):
    """P(player ≥ 1 SOT). §5.6 — v8 band 52-64 for main strikers (L10 input-side)."""
    return 1 - math.exp(-lam_player_sot)


def player_sot_2h(lam_player_sot):
    """P(player ≥ 1 SOT in 2H). §5.6"""
    return 1 - math.exp(-0.55 * lam_player_sot)


def score_or_assist(goal_prob, role="creator"):
    """
    Score-or-assist probability with overlap correction. §5.6
    role: 'creator' → ×1.5-1.8; 'pure_9' → ×1.2-1.4
    """
    multipliers = {"creator": 1.65, "pure_9": 1.30}
    mult = multipliers.get(role, 1.5)
    return min(goal_prob * mult, 0.95)


def l10_driver_gate(p_modeled, market_type="general"):
    """
    L10 (ACTIVE): top-half 56-70 band requires explicit driver; else regress to lower edge. §5.6
    Returns (p_final, requires_driver).
    """
    if 0.56 <= p_modeled <= 0.70:
        if p_modeled > 0.63:
            return (0.56, True)   # regress to lower edge until driver supplied
    return (p_modeled, False)


# ---------------------------------------------------------------------------
# §5.7  Joint / sequence props
# ---------------------------------------------------------------------------

def joint_a_scores_first_and_b_scores_2h(lam_a, lam_b):
    """
    P(A scores first AND B scores in 2H). §5.7
    Includes −1 to −2 dependence haircut.
    """
    T = lam_a + lam_b
    p_a_first = (lam_a / T) * (1 - math.exp(-T))
    p_b_2h = team_scores_2h(lam_b)
    joint = p_a_first * p_b_2h
    # dependence haircut: joint prop inherits all λ-estimation risk of both marginals
    haircut = 0.97
    return min(joint * haircut, p_a_first, p_b_2h)


# ---------------------------------------------------------------------------
# §5.11  Batch MC — correlation cap (exact from spec, extended)
# ---------------------------------------------------------------------------

def batch_mc(matches, n_draws=2000, seed=42):
    """
    Monte Carlo integration over λ uncertainty for correlated market baskets.
    Fires proactively when >4 of ~10 markets load on the same latent axis. §5.11

    matches: list of dicts:
        {
          "name":    str,
          "lam_a":   float,  "sigma_a": float,
          "lam_b":   float,  "sigma_b": float,
          "markets": list[str],   # keys from the supported set below
        }
    sigma_*: use observable spread across sharp sources; default σ = 0.15 × λ̂ if unknown.

    Supported market keys:
        btts3plus, p_2h_2plus, clean_sheet_a, clean_sheet_b, scores_2h_a, scores_2h_b,
        scores_a, scores_b, btts, p_over_25, ht_tied, p_1h_goals_gte1, p_2h_goals_gte1

    Returns dict: {match_name: {market_key: probability_0_1}}
    """
    rng = np.random.default_rng(seed)
    out = {}

    for m in matches:
        la = np.clip(rng.normal(m["lam_a"], m["sigma_a"], n_draws), 0.05, None)
        lb = np.clip(rng.normal(m["lam_b"], m["sigma_b"], n_draws), 0.05, None)
        T = la + lb
        res = {}

        mkt = m["markets"]

        if "btts3plus" in mkt:
            b = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            p11 = la * lb * np.exp(-T)
            res["btts3plus"] = float(np.mean(b - p11))

        if "p_2h_2plus" in mkt:
            lam_2h = 0.55 * T
            res["p_2h_2plus"] = float(np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h)))

        if "clean_sheet_a" in mkt:
            res["clean_sheet_a"] = float(np.mean(np.exp(-lb)))

        if "clean_sheet_b" in mkt:
            res["clean_sheet_b"] = float(np.mean(np.exp(-la)))

        if "scores_2h_a" in mkt:
            res["scores_2h_a"] = float(np.mean(1 - np.exp(-0.55 * la)))

        if "scores_2h_b" in mkt:
            res["scores_2h_b"] = float(np.mean(1 - np.exp(-0.55 * lb)))

        if "scores_a" in mkt:
            res["scores_a"] = float(np.mean(1 - np.exp(-la)))

        if "scores_b" in mkt:
            res["scores_b"] = float(np.mean(1 - np.exp(-lb)))

        if "btts" in mkt:
            res["btts"] = float(np.mean((1 - np.exp(-la)) * (1 - np.exp(-lb))))

        if "p_over_25" in mkt:
            res["p_over_25"] = float(np.mean(1 - np.exp(-T) * (1 + T + T ** 2 / 2)))

        if "ht_tied" in mkt:
            la_ht = 0.45 * la
            lb_ht = 0.45 * lb
            res["ht_tied"] = float(np.mean(
                np.exp(-(la_ht + lb_ht)) * bessel_i0(2 * np.sqrt(la_ht * lb_ht))
            ))

        if "p_1h_goals_gte1" in mkt:
            lam_1h = 0.45 * T
            res["p_1h_goals_gte1"] = float(np.mean(1 - np.exp(-lam_1h)))

        if "p_2h_goals_gte1" in mkt:
            lam_2h = 0.55 * T
            res["p_2h_goals_gte1"] = float(np.mean(1 - np.exp(-lam_2h)))

        out[m["name"]] = res

    return out


def sigma_default(lam):
    """Default σ when source spread is unknown: σ = 0.15 × λ̂. §5.11"""
    return 0.15 * lam


def l8_check(n_markets_on_axis, total_markets=10):
    """Returns True if L8 batch MC should fire (>4 of ~10 markets on same axis). §5.11"""
    return n_markets_on_axis > 4


# ---------------------------------------------------------------------------
# §5.11  Coherence gates (run before every batch submission)
# ---------------------------------------------------------------------------

def coherence_check(markets):
    """
    Run coherence gates on a dict of {market_key: int_probability_1_99}.
    Returns list of (gate_name, description) for every failure.
    Pass before any batch submission. §5.11
    """
    issues = []

    home_win = markets.get("home_win")
    draw     = markets.get("draw")
    away_win = markets.get("away_win")

    if home_win is not None and draw is not None and away_win is not None:
        total = home_win + draw + away_win
        if not (98 <= total <= 102):
            issues.append(("1x2_sum", f"1X2 sums to {total}; must be 98–102"))

    btts_v   = markets.get("btts")
    scores_a = markets.get("scores_a") or markets.get("home_scores")
    scores_b = markets.get("scores_b") or markets.get("away_scores")
    if btts_v and scores_a and scores_b:
        if btts_v > scores_a:
            issues.append(("btts_vs_scores_a", f"BTTS {btts_v} > P(A scores) {scores_a}"))
        if btts_v > scores_b:
            issues.append(("btts_vs_scores_b", f"BTTS {btts_v} > P(B scores) {scores_b}"))

    btts3 = markets.get("btts3plus")
    if btts3 and btts_v and btts3 > btts_v:
        issues.append(("btts3plus_gt_btts", f"BTTS&3+ {btts3} > BTTS {btts_v}"))

    # Complement: clean_sheet_a vs scores_b
    cs_a = markets.get("clean_sheet_a")
    if cs_a and scores_b:
        expected_cs = 100 - scores_b
        if abs(cs_a - expected_cs) > 3:
            issues.append(("clean_sheet_complement", f"CS_A {cs_a} vs 100−scores_b={expected_cs}"))

    # Deviation from anchor gate
    for key in ("home_win", "away_win", "draw"):
        val = markets.get(key)
        anchor = markets.get(f"{key}_anchor")
        if val is not None and anchor is not None:
            if abs(val - anchor) > 10:
                issues.append(("anchor_deviation_10", f"{key}: |{val} − anchor {anchor}| > 10; needs written cause"))

    return issues


# ---------------------------------------------------------------------------
# §5.12  Situational overlays
# ---------------------------------------------------------------------------

def overlay_total(overlays_list):
    """
    Sum a list of (label, delta) overlay tuples and cap at ±8. §5.12
    Returns (capped_total, list of applied labels).
    """
    total = sum(d for _, d in overlays_list)
    capped = max(-8, min(8, total))
    labels = [label for label, d in overlays_list if d != 0]
    return capped, labels


# ---------------------------------------------------------------------------
# §9  Feedback loop utilities
# ---------------------------------------------------------------------------

def decode_outcome(p_decimal, brier, eps=0.001):
    """
    Decode binary outcome from submitted probability (0-1) and Brier score.
    o=1 iff (p−1)² ≈ brier. §9.2
    Returns 0 or 1.
    """
    if abs((p_decimal - 1) ** 2 - brier) < eps:
        return 1
    return 0


def self_expected_brier(p_list):
    """Σ p(1−p) / n across submitted probabilities (0-1 floats). §9.1"""
    if not p_list:
        return None
    return sum(p * (1 - p) for p in p_list) / len(p_list)


def brier_noise_band(n):
    """Per-market Brier sd of the mean ≈ 0.15/√n. §9.1"""
    return 0.15 / math.sqrt(n) if n > 0 else None


def rbp_market(crowd_brier, your_brier, stage_weight=1):
    """RBP per market = (crowd_brier − your_brier) × 100 × stage_weight. §1.1"""
    return (crowd_brier - your_brier) * 100 * stage_weight


def eb_update(entry, new_hit):
    """
    Empirical Bayes posterior update. §5.8
    k = 7 if n < 30, else 15.
    """
    n = entry["n"]
    k = 7 if n < 30 else 15
    n_new = n + 1
    hits_new = entry["hits"] + int(new_hit)
    posterior = (hits_new + k * entry["prior"]) / (n_new + k)
    return {**entry, "n": n_new, "hits": hits_new, "posterior": posterior}


# ---------------------------------------------------------------------------
# §0.2 / D3  Integer clipping and noisy-market clamping
# ---------------------------------------------------------------------------

def to_int(p_float):
    """Convert 0-1 probability to 1-99 integer. §1.1 / D3"""
    return max(1, min(99, round(p_float * 100)))


def noisy_clamp(p_int, anchored=False):
    """Clamp noisy-register markets to 15-85 unless anchored. §5.9"""
    if anchored:
        return max(1, min(99, int(p_int)))
    return max(15, min(85, int(p_int)))


def is_noisy_market(question_text):
    """Check if a market question falls in the noisy register. §5.9"""
    text = question_text.lower()
    return any(kw in text for kw in NOISY_MARKET_KEYWORDS)


if __name__ == "__main__":
    print("=== Engine v3 self-test ===")
    print(f"power_devig([0.55, 0.50]) = {power_devig([0.55, 0.50])}")
    print(f"t_from_ou25(0.46) = {t_from_ou25(0.46)}")
    T = 2.7
    la, lb = 1.65, 1.05
    print(f"λ=({la},{lb})  btts={to_int(btts(la,lb))}  btts3+={to_int(btts3plus(la,lb))}  ht_tied={to_int(ht_tied_capped(la,lb))}")
    print(f"tie_trap corners_ft even m=4.5: {tie_trap(4.5, 4.5, 'corners_ft'):.3f}")
    mc = batch_mc([{"name":"TEST","lam_a":la,"sigma_a":sigma_default(la),"lam_b":lb,"sigma_b":sigma_default(lb),"markets":["btts3plus","clean_sheet_a","ht_tied"]}])
    print(f"batch_mc TEST: {mc['TEST']}")
    print(f"coherence_check pass: {coherence_check({'home_win':48,'draw':26,'away_win':26,'scores_a':72,'scores_b':58,'btts':50,'btts3plus':38})}")
    issues = coherence_check({"home_win":55,"draw":30,"away_win":20})
    print(f"coherence_check fail: {issues}")
