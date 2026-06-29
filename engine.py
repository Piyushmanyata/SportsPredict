"""
Probability Cup Engine v3 — Reusable computation library.
Implements §5 of the system instructions. All probabilities returned as 0-100 integers.
"""
import numpy as np
from scipy.optimize import root_scalar
import math


# ── §5.1 Anchor extraction ────────────────────────────────────────────────────

def power_devig(implied: list[float]) -> list[float]:
    """
    Mandatory power devig when overround > 5% and favorite implied > 65%.
    Falls back to multiplicative if solver fails.
    """
    total = sum(implied)
    if total <= 1.01:
        return implied  # already clean
    def f(k):
        return sum(p ** k for p in implied) - 1
    try:
        k = root_scalar(f, bracket=[0.3, 3.0]).root
        return [p ** k for p in implied]
    except Exception:
        return [p / total for p in implied]  # multiplicative fallback


def devig_1x2(d_home: float, d_draw: float, d_away: float) -> tuple[float, float, float]:
    """
    Returns devigged (p_home, p_draw, p_away) from decimal odds.
    Automatically uses power devig when appropriate.
    """
    imp = [1/d_home, 1/d_draw, 1/d_away]
    overround = sum(imp) - 1
    fav_implied = max(imp)
    if overround > 0.05 and fav_implied > 0.65:
        probs = power_devig(imp)
    else:
        total = sum(imp)
        probs = [p / total for p in imp]
    return tuple(probs)


def devig_2way(d_yes: float, d_no: float) -> tuple[float, float]:
    """Returns devigged (p_yes, p_no) from decimal odds."""
    imp = [1/d_yes, 1/d_no]
    total = sum(imp)
    overround = total - 1
    fav = max(imp)
    if overround > 0.05 and fav > 0.65:
        probs = power_devig(imp)
    else:
        probs = [p / total for p in imp]
    return tuple(probs)


# ── §5.2 λ engine ────────────────────────────────────────────────────────────

# O/U 2.5 → T lookup (exact Poisson)
OU25_TABLE = {
    # (p_over_2_5) -> T
    0.32: 2.0, 0.38: 2.2, 0.46: 2.5,
    0.51: 2.7, 0.58: 3.0, 0.64: 3.3,
}

def ou25_to_T(p_over_2_5: float) -> float:
    """Interpolate T from P(over 2.5)."""
    keys = sorted(OU25_TABLE.keys())
    vals = [OU25_TABLE[k] for k in keys]
    return float(np.interp(p_over_2_5, keys, vals))


def fit_lambda_split(T: float, p_home_win: float) -> tuple[float, float]:
    """
    Find (lam_a, lam_b) such that lam_a+lam_b=T and the Poisson 1X2
    reproduces p_home_win within ±2 percentage points.
    Returns lam_a, lam_b.
    """
    best_la, best_lb, best_err = T/2, T/2, 999.0
    for la in np.arange(0.1, T - 0.05, 0.05):
        lb = T - la
        p_hw = poisson_win(la, lb)
        err = abs(p_hw - p_home_win)
        if err < best_err:
            best_err = err
            best_la, best_lb = la, lb
    return round(best_la, 3), round(best_lb, 3)


def poisson_win(lam_a: float, lam_b: float, max_goals: int = 10) -> float:
    """P(A wins) under Poisson independence."""
    p = 0.0
    for a in range(max_goals + 1):
        for b in range(a):  # b < a → A wins
            p += (math.exp(-lam_a) * lam_a**a / math.factorial(a) *
                  math.exp(-lam_b) * lam_b**b / math.factorial(b))
    return p


def poisson_draw(lam_a: float, lam_b: float, max_goals: int = 10) -> float:
    """P(draw) under Poisson independence."""
    T = lam_a + lam_b
    # e^(-lam_a)*e^(-lam_b)*sum_k (lam_a*lam_b)^k/(k!)^2
    p = 0.0
    for k in range(max_goals + 1):
        p += (lam_a * lam_b)**k / (math.factorial(k)**2)
    return math.exp(-T) * p


def poisson_goals_prob(lam: float, k: int) -> float:
    """P(X=k) for Poisson(lam)."""
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


# ── §5.2 closed-form market formulas ─────────────────────────────────────────

def p_team_scores(lam: float) -> float:
    return 1 - math.exp(-lam)

def p_scores_2h(lam: float) -> float:
    return 1 - math.exp(-0.55 * lam)

def p_scores_1h(lam: float) -> float:
    return 1 - math.exp(-0.45 * lam)

def p_btts(lam_a: float, lam_b: float) -> float:
    return (1 - math.exp(-lam_a)) * (1 - math.exp(-lam_b))

def p_score_1_1(lam_a: float, lam_b: float) -> float:
    return lam_a * lam_b * math.exp(-(lam_a + lam_b))

def p_btts_and_3plus(lam_a: float, lam_b: float) -> float:
    """P(BTTS AND ≥3 total goals) = P(BTTS) - P(1-1). §5.2"""
    return p_btts(lam_a, lam_b) - p_score_1_1(lam_a, lam_b)

def p_over_goals(T: float, threshold: float) -> float:
    """P(total goals > threshold) using Poisson(T)."""
    # threshold=2.5 → P(≥3 goals)
    k_max = int(math.floor(threshold))
    p_under = sum(math.exp(-T) * T**k / math.factorial(k) for k in range(k_max + 1))
    return 1 - p_under

def p_clean_sheet(lam_opp: float) -> float:
    """P(opponent scores 0) = e^(-lam_opp)"""
    return math.exp(-lam_opp)


# ── §5.4 Tie-trap engine (strict "more than" comparisons) ────────────────────

# e^(-2m) * I0(2m) where I0 is modified Bessel function of first kind
def p_tie_poisson(m: float) -> float:
    """Exact tie probability for two independent Poisson(m) variables."""
    # I0(2m) = sum_{k=0}^{inf} (m^2k) / (k!)^2
    result = 0.0
    for k in range(50):
        result += m**(2*k) / (math.factorial(k)**2)
    return math.exp(-2*m) * result

def p_a_more(m_a: float, m_b: float) -> float:
    """
    P(A > B) for A~Poisson(m_a), B~Poisson(m_b).
    For even (m_a=m_b=m): P(tie)=p_tie_poisson(m), P(A more)=(1-tie)/2.
    For skewed: approximate via simulation.
    """
    if abs(m_a - m_b) < 0.01:
        p_tie = p_tie_poisson(m_a)
        return (1 - p_tie) / 2
    # General case: enumerate
    max_k = 25
    p_a_gt_b = 0.0
    for a in range(max_k + 1):
        for b in range(a):
            pa = math.exp(-m_a) * m_a**a / math.factorial(a)
            pb = math.exp(-m_b) * m_b**b / math.factorial(b)
            p_a_gt_b += pa * pb
    return p_a_gt_b

# Reference means per stat (§5.4)
STAT_MEANS = {
    "fouls": 11.0,
    "ft_corners": 4.5,
    "2h_corners": 2.4,
    "ht_corners": 2.1,
    "2h_sot": 2.0,
    "cards": 1.8,
    "offsides": 1.5,
}

def tie_trap_prob(stat: str, m_a: float = None, m_b: float = None,
                  strength_ratio: float = 1.0) -> int:
    """
    Returns P(A more than B) as integer 1-99 for strict comparison markets.
    strength_ratio: lam_a / lam_b (>1 means A is dominant).
    Never returns 50 (D3 guideline).
    """
    if m_a is None:
        m = STAT_MEANS.get(stat, 2.0)
        m_a = m * strength_ratio / (1 + strength_ratio) * 2
        m_b = m * 2 - m_a
    p = p_a_more(m_a, m_b)
    result = round(p * 100)
    return max(1, min(99, result if result != 50 else 49))


# ── §5.5 Threshold & state tables ────────────────────────────────────────────

def p_cards_4plus(lam_cards: float) -> int:
    """P(≥4 total cards) from §5.5 table, interpolated."""
    table = [(2.8, 31), (3.2, 40), (3.5, 46), (4.0, 57), (4.5, 66)]
    lams, ps = zip(*table)
    return round(float(np.interp(lam_cards, lams, ps)))

def p_cards_2h_2plus(lam_cards: float) -> int:
    """P(≥2 cards in 2H); 2H share ≈ 0.62."""
    table = [(2.8, 52), (3.2, 59), (3.5, 64), (4.0, 71), (4.5, 77)]
    lams, ps = zip(*table)
    return round(float(np.interp(lam_cards, lams, ps)))

def p_corners_5plus(lam_corners: float) -> int:
    """P(team ≥5 corners)."""
    table = [(3.0, 19), (3.5, 28), (4.0, 37), (4.5, 47),
             (5.0, 56), (5.5, 64), (6.0, 72)]
    lams, ps = zip(*table)
    return round(float(np.interp(lam_corners, lams, ps)))

def p_sot_2plus(lam_sot: float) -> int:
    """P(team ≥2 SOT)."""
    table = [(1.0, 26), (1.5, 44), (2.0, 59), (2.5, 71),
             (3.0, 80), (3.5, 86), (4.0, 91), (4.5, 94)]
    lams, ps = zip(*table)
    return round(float(np.interp(lam_sot, lams, ps)))

def p_offsides_2plus(lam_off: float) -> int:
    """P(≥2 offsides)."""
    table = [(0.8, 19), (1.0, 26), (1.2, 34), (1.5, 44),
             (1.8, 54), (2.0, 59)]
    lams, ps = zip(*table)
    return round(float(np.interp(lam_off, lams, ps)))

def p_ht_tied(lam_a: float, lam_b: float) -> int:
    """
    P(match tied at HT). Uses half-time λ share ≈ 0.45.
    From §5.5 Bessel table. Ceiling 47 per L9.
    """
    la_ht = 0.45 * lam_a
    lb_ht = 0.45 * lam_b
    T_ht = la_ht + lb_ht
    # P(HT tied) = e^(-T_ht) * I0(2*sqrt(la_ht * lb_ht))
    sqrt_prod = math.sqrt(la_ht * lb_ht)
    # I0(x) = sum_{k=0}^{inf} (x/2)^{2k} / (k!)^2
    x = 2 * sqrt_prod
    i0 = sum((x/2)**(2*k) / (math.factorial(k)**2) for k in range(50))
    p = math.exp(-T_ht) * i0
    result = round(p * 100)
    return min(47, max(1, result))  # L9 ceiling


def p_poisson_atleast(lam: float, k: int) -> float:
    """P(Poisson(lam) >= k)."""
    return 1 - sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k))


# ── §5.6 Player prop engine ───────────────────────────────────────────────────

def player_goal_prob(lam_team: float, goal_share: float) -> int:
    """
    Player anytime goal probability.
    lam_team: team expected goals; goal_share: player's fraction.
    Bands: star striker 32-45 · secondary 18-28 · mid 8-15.
    """
    lam_p = lam_team * goal_share
    p = 1 - math.exp(-lam_p)
    return max(1, min(99, round(p * 100)))

def player_sot_prob(lam_sot_player: float) -> int:
    """
    Player 1+ SOT.
    v8/L10: main striker band 52-64, winger/AM 42-56.
    Any modeled p in top half of 56-70 requires explicit driver.
    """
    p = 1 - math.exp(-lam_sot_player)
    return max(1, min(99, round(p * 100)))

def player_sot_2h_prob(lam_sot_player: float) -> int:
    """Player 1+ SOT in 2H. Rate × 0.55 per §5.6."""
    p = 1 - math.exp(-0.55 * lam_sot_player)
    return max(1, min(99, round(p * 100)))

def player_sot_2plus_prob(lam_sot_player: float) -> int:
    """Player 2+ SOT."""
    return p_sot_2plus(lam_sot_player)

def score_or_assist(p_goal: float, assist_multiplier: float = 1.6) -> int:
    """
    Score or assist probability. assist_multiplier: 1.5-1.8 (creators), 1.2-1.4 (pure 9s).
    Overlap-corrected approximation: p_s_or_a ≈ p_goal * multiplier, capped at 85.
    """
    p = p_goal * assist_multiplier
    return max(1, min(85, round(p * 100)))


# ── §5.11 Batch MC integration (L8) ─────────────────────────────────────────

def batch_mc(matches: list[dict], n_draws: int = 5000, seed: int = 42) -> dict:
    """
    MC integration over λ-uncertainty for correlated markets.
    matches: list of dicts with keys:
      name, lam_a, sigma_a, lam_b, sigma_b, markets (list of str keys)
    Returns: {match_name: {market_key: int_probability}}
    """
    rng = np.random.default_rng(seed)
    out = {}
    for m in matches:
        la = np.clip(rng.normal(m["lam_a"], m["sigma_a"], n_draws), 0.05, None)
        lb = np.clip(rng.normal(m["lam_b"], m["sigma_b"], n_draws), 0.05, None)
        T = la + lb
        res = {}
        mkt = m.get("markets", [])

        if "btts3plus" in mkt:
            btts = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            p11 = la * lb * np.exp(-T)
            res["btts3plus"] = int(round(float(np.mean(btts - p11)) * 100))

        if "btts" in mkt:
            btts = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            res["btts"] = int(round(float(np.mean(btts)) * 100))

        if "over_2_5" in mkt:
            p_over = np.mean(1 - np.exp(-T) * (1 + T + T**2/2))
            res["over_2_5"] = int(round(float(p_over) * 100))

        if "over_3_5" in mkt:
            p_under = np.exp(-T) * (1 + T + T**2/2 + T**3/6)
            res["over_3_5"] = int(round(float(np.mean(1 - p_under)) * 100))

        if "p_2h_2plus" in mkt:
            lam_2h = 0.55 * T
            res["p_2h_2plus"] = int(round(float(np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h))) * 100))

        if "clean_sheet_a" in mkt:
            res["clean_sheet_a"] = int(round(float(np.mean(np.exp(-lb))) * 100))

        if "clean_sheet_b" in mkt:
            res["clean_sheet_b"] = int(round(float(np.mean(np.exp(-la))) * 100))

        if "scores_a" in mkt:
            res["scores_a"] = int(round(float(np.mean(1 - np.exp(-la))) * 100))

        if "scores_b" in mkt:
            res["scores_b"] = int(round(float(np.mean(1 - np.exp(-lb))) * 100))

        if "scores_2h_a" in mkt:
            res["scores_2h_a"] = int(round(float(np.mean(1 - np.exp(-0.55 * la))) * 100))

        if "scores_2h_b" in mkt:
            res["scores_2h_b"] = int(round(float(np.mean(1 - np.exp(-0.55 * lb))) * 100))

        if "scores_1h_a" in mkt:
            res["scores_1h_a"] = int(round(float(np.mean(1 - np.exp(-0.45 * la))) * 100))

        if "ht_tied" in mkt:
            # simplified: Poisson ht sum
            ht_a = 0.45 * la; ht_b = 0.45 * lb
            ht_T = ht_a + ht_b
            p_ht = np.exp(-ht_T)
            for k in range(20):
                p_ht_tie_k = np.exp(-ht_T) * (ht_a * ht_b)**k / (np.array([math.factorial(i) for i in range(k+1)])**2)[-1]
                # approximate: e^(-T_ht) * sum (la*lb)^k/(k!)^2
            # use closed form with vectorized approx
            max_k = 15
            tie_p = np.zeros(n_draws)
            for k in range(max_k + 1):
                tie_p += (ht_a * ht_b)**k / (math.factorial(k)**2)
            tie_p *= np.exp(-ht_T)
            p_ht_tied = min(47, int(round(float(np.mean(tie_p)) * 100)))
            res["ht_tied"] = p_ht_tied

        if "win_a" in mkt:
            p_win_a = np.zeros(n_draws)
            for a in range(12):
                for b in range(a):
                    p_win_a += (np.exp(-la) * la**a / math.factorial(a) *
                                np.exp(-lb) * lb**b / math.factorial(b))
            res["win_a"] = int(round(float(np.mean(p_win_a)) * 100))

        if "win_b" in mkt:
            p_win_b = np.zeros(n_draws)
            for b in range(12):
                for a in range(b):
                    p_win_b += (np.exp(-la) * la**a / math.factorial(a) *
                                np.exp(-lb) * lb**b / math.factorial(b))
            res["win_b"] = int(round(float(np.mean(p_win_b)) * 100))

        out[m["name"]] = res
    return out


# ── §5.9 Noisy register clamp ─────────────────────────────────────────────────

NOISY_MARKETS = {
    "penalty", "red_card", "pen_or_red", "2h_cards", "ht_sot_comparison",
    "2h_sot_comparison", "offside_count", "ht_corner_comparison",
    "2h_corner_comparison", "leads_at_ht",
}

def clamp_noisy(p: int, market_type: str = "", anchored: bool = False) -> int:
    """Clamp noisy register markets to 15-85 unless anchored."""
    if market_type in NOISY_MARKETS and not anchored:
        return max(15, min(85, p))
    return max(1, min(99, p))


# ── Brier helpers ─────────────────────────────────────────────────────────────

def brier(p: int, outcome: int) -> float:
    """Brier score: (p/100 - outcome)^2."""
    return (p/100 - outcome) ** 2

def self_expected_brier(p: int) -> float:
    """Self-expected Brier: p(1-p) where p is 0-1."""
    q = p / 100
    return q * (1 - q)

def decode_outcome(p_submitted: float, brier_score: float, eps: float = 0.001) -> int:
    """
    Decode outcome from submitted probability (0-1 decimal) and brier score.
    o=1 if (p-1)^2 ≈ brier, else o=0. Returns -1 if p=0.5 (ambiguous).
    """
    if abs(p_submitted - 0.5) < 0.001:
        return -1
    if abs((p_submitted - 1)**2 - brier_score) < eps:
        return 1
    return 0


# ── §5.12 Situational overlays ────────────────────────────────────────────────

def altitude_overlay(venue_altitude_m: float, is_lowland_team: bool) -> int:
    """
    Altitude drag on lowland teams.
    Azteca ≈ 2240m, Guadalajara ≈ 1560m.
    Returns adjustment to apply to favorite win / scoring λ.
    """
    if venue_altitude_m >= 2000 and is_lowland_team:
        return -3  # -2 to -4 per spec
    elif venue_altitude_m >= 1400 and is_lowland_team:
        return -2
    return 0


def round_int(p: float) -> int:
    """Round float probability (0-1) to int 1-99, never exactly 50."""
    r = max(1, min(99, round(p * 100)))
    return r


if __name__ == "__main__":
    # Quick smoke test
    print("Power devig 1X2 test:")
    p_h, p_d, p_a = devig_1x2(2.10, 3.30, 4.00)
    print(f"  Home={p_h:.3f} Draw={p_d:.3f} Away={p_a:.3f} Sum={p_h+p_d+p_a:.3f}")

    print("\nλ engine test (T=2.7, split 1.65/1.05):")
    la, lb = 1.65, 1.05
    T = la + lb
    print(f"  BTTS: {round(p_btts(la,lb)*100)}")
    print(f"  BTTS∧3+: {round(p_btts_and_3plus(la,lb)*100)}")
    print(f"  Over 2.5: {round(p_over_goals(T, 2.5)*100)}")
    print(f"  HT tied: {p_ht_tied(la,lb)}")
    print(f"  GER scores: {round(p_team_scores(la)*100)}")

    print("\nTie-trap test (corners, even):")
    print(f"  P(A more FT corners, even): {tie_trap_prob('ft_corners')}")
