"""
Probability engine v3 — implements §5 of the system instructions (v8-final).
All functions return floats in [0,1]. Multiply by 100 and round to int for submission.
"""

import math

# ---------------------------------------------------------------------------
# §5.1  Anchor extraction — power devig
# ---------------------------------------------------------------------------

def power_devig(implied):
    """
    implied: list of implied probs summing to >1 (e.g. [0.55, 0.25, 0.30]).
    Returns fair probs summing to 1.0 via power-k method.
    Fallback to multiplicative if solver fails.
    """
    s = sum(implied)
    if abs(s - 1.0) < 1e-6:
        return list(implied)
    def f(k):
        return sum(p**k for p in implied) - 1.0
    try:
        # Bisection solve for k in [0.5, 2.0]
        lo, hi = 0.5, 2.0
        for _ in range(50):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid   # sum too high → need larger k to shrink probs
            else:
                hi = mid
        return [p**((lo+hi)/2) for p in implied]
    except Exception:
        return [p / s for p in implied]


def devig_2way(dec_yes, dec_no):
    """2-way market: decimal odds → fair probability of YES."""
    imp_yes = 1.0 / dec_yes
    imp_no  = 1.0 / dec_no
    fair = power_devig([imp_yes, imp_no])
    return fair[0]


def devig_3way(dec_home, dec_draw, dec_away):
    """3-way 1X2 → (p_home, p_draw, p_away) fair."""
    return power_devig([1/dec_home, 1/dec_draw, 1/dec_away])


# ---------------------------------------------------------------------------
# §5.2  λ engine
# ---------------------------------------------------------------------------

# O/U 2.5 → total goals T lookup table (interpolated)
_OU25_TABLE = [
    (0.32, 2.0), (0.38, 2.2), (0.46, 2.5),
    (0.51, 2.7), (0.58, 3.0), (0.64, 3.3),
]

def T_from_ou25(p_over_2_5):
    """Convert P(over 2.5 goals) to expected total T via linear interpolation."""
    p = float(p_over_2_5)
    if p <= _OU25_TABLE[0][0]:
        return _OU25_TABLE[0][1]
    if p >= _OU25_TABLE[-1][0]:
        return _OU25_TABLE[-1][1]
    for i in range(len(_OU25_TABLE) - 1):
        p0, t0 = _OU25_TABLE[i]
        p1, t1 = _OU25_TABLE[i+1]
        if p0 <= p <= p1:
            frac = (p - p0) / (p1 - p0)
            return t0 + frac * (t1 - t0)
    return 2.5


def split_from_1x2(p_home, p_draw, T):
    """
    Fit λ_home, λ_away so Poisson(λ_h, λ_a) reproduces p_home/p_draw.
    Uses a grid search: fix T = λh + λa, scan x = λh/T ∈ (0.3, 0.85).
    Returns (λ_home, λ_away).
    """
    best_err = float('inf')
    best_lh = T * 0.5
    for frac in [0.30 + i * (0.55 / 109) for i in range(110)]:
        lh = T * frac
        la = T * (1 - frac)
        ph, pd, _ = poisson_1x2(lh, la)
        err = (ph - p_home)**2 + (pd - p_draw)**2
        if err < best_err:
            best_err = err
            best_lh = lh
    return best_lh, T - best_lh


def poisson_1x2(lam_h, lam_a, max_goals=10):
    """Exact Poisson grid → (p_home_win, p_draw, p_away_win)."""
    ph = pd = pa = 0.0
    for g_h in range(max_goals + 1):
        for g_a in range(max_goals + 1):
            p = (math.exp(-lam_h) * lam_h**g_h / math.factorial(g_h) *
                 math.exp(-lam_a) * lam_a**g_a / math.factorial(g_a))
            if g_h > g_a:
                ph += p
            elif g_h == g_a:
                pd += p
            else:
                pa += p
    return ph, pd, pa


def poisson_pmf(lam, k):
    return math.exp(-lam) * lam**k / math.factorial(k)


def poisson_cdf(lam, k_max):
    """P(X <= k_max) for Poisson(lam)."""
    return sum(poisson_pmf(lam, k) for k in range(k_max + 1))


def p_at_least(lam, k_min):
    """P(X >= k_min) = 1 - P(X <= k_min-1)."""
    if k_min <= 0:
        return 1.0
    return 1.0 - poisson_cdf(lam, k_min - 1)


# ---------------------------------------------------------------------------
# §5.3  Market archetypes
# ---------------------------------------------------------------------------

def arch1_win(p_win):
    """
    Archetype 1: 'Will X win the match?'
    L12 active: apply Dixon-Coles hardening in 40-60 band (input-side via draw inflation).
    p_win here is the devigged win probability (already draw-inflated if done upstream).
    """
    return p_win


def arch2_3plus_goals(T, dixoncoles_adj=0.0):
    """Archetype 2: '3 or more total goals'. P(goals >= 3) = 1 - P(goals <= 2)."""
    raw = p_at_least(T, 3)
    return max(0.01, min(0.99, raw + dixoncoles_adj))


def arch2_2fewer_goals(T, dixoncoles_adj=0.0):
    """Archetype 2: '2 or fewer total goals'."""
    raw = poisson_cdf(T, 2)
    return max(0.01, min(0.99, raw - dixoncoles_adj))


def arch3_btts_3plus(lam_h, lam_a):
    """Archetype 3: 'Both teams score AND 3+ total goals' = P(BTTS) - P(1-1)."""
    btts = (1 - math.exp(-lam_h)) * (1 - math.exp(-lam_a))
    T = lam_h + lam_a
    p11 = lam_h * lam_a * math.exp(-T)
    return max(0.01, btts - p11)


def arch4_score_2h(lam_team):
    """Archetype 4: 'Will X score in the second half?' 2H share = 55%."""
    return 1.0 - math.exp(-0.55 * lam_team)


def arch5_score_at_least1(lam_team):
    """Archetype 5: 'Will X score at least 1 goal?'"""
    return 1.0 - math.exp(-lam_team)


def arch7_sot_geq2(lam_sot_team):
    """P(team >= 2 SOT) using Poisson."""
    return p_at_least(lam_sot_team, 2)


def arch7_corners_geq5(lam_corner_team):
    """P(team >= 5 corners)."""
    return p_at_least(lam_corner_team, 5)


def arch7_corners_geq9_total(lam_h_corners, lam_a_corners):
    """P(total corners >= 9)."""
    T_corners = lam_h_corners + lam_a_corners
    return p_at_least(T_corners, 9)


def arch7_cards_geq4(lam_cards):
    """P(total cards >= 4). §5.5 table."""
    return p_at_least(lam_cards, 4)


def arch7_offside_geq2(lam_offside_team):
    """P(team >= 2 offsides)."""
    return p_at_least(lam_offside_team, 2)


def arch7_sot_2h_geq4_total(lam_h, lam_a):
    """P(total SOT in 2H >= 4): 2H rate = 0.55 * (team SOT rates)."""
    lam_2h = 0.55 * (lam_h + lam_a)
    return p_at_least(lam_2h, 4)


def arch9_ht_tied(lam_h, lam_a):
    """
    Archetype 9: 'At halftime, will the match be tied?'
    HT Poissons: λht_h = 0.45*lam_h, λht_a = 0.45*lam_a.
    P(tied at HT) using Bessel: e^(-(λa+λb)) * I0(2*sqrt(λa*λb)).
    Capped at 47 (L9).
    """
    la = 0.45 * lam_h
    lb = 0.45 * lam_a
    val = math.exp(-(la + lb)) * _bessel_i0(2 * math.sqrt(la * lb))
    return min(val, 0.47)


def arch10_ht_both_sot(lam_h_sot, lam_a_sot):
    """
    Archetype 10: 'At HT, both teams >= 1 SOT'.
    HT SOT share ≈ 0.45.
    P = P(HT_h >= 1) * P(HT_a >= 1).
    """
    ht_h = 0.45 * lam_h_sot
    ht_a = 0.45 * lam_a_sot
    return (1 - math.exp(-ht_h)) * (1 - math.exp(-ht_a))


# ---------------------------------------------------------------------------
# §5.4  Tie-trap engine (strict "more X than Y" comparisons)
# ---------------------------------------------------------------------------

# Bessel I0 for tie mass: e^(-2m) * I0(2m)
def _bessel_i0(x):
    if x <= 3.75:
        t = (x / 3.75)**2
        return 1 + 3.5156229*t + 3.0899424*t**2 + 1.2067492*t**3
    else:
        t = 3.75 / x
        return (math.exp(x) / math.sqrt(x)) * (
            0.39894228 + 0.01328592*t + 0.00225319*t**2 - 0.00157565*t**3)


def tie_prob(m):
    """P(tie) for 'more X than Y' where both ~ Poisson(m): e^(-2m)*I0(2m)."""
    return math.exp(-2*m) * _bessel_i0(2*m)


def tie_trap(m_a, m_b):
    """
    P(A strictly more than B) for independent Poisson(m_a), Poisson(m_b).
    Approximate: P(tie) using geometric mean m = sqrt(m_a * m_b), then
    P(A > B | no tie) from strength ratio.
    """
    m = math.sqrt(m_a * m_b)
    p_tie = tie_prob(m)
    # P(A more | no tie) using ratio
    ratio = m_a / (m_a + m_b) if (m_a + m_b) > 0 else 0.5
    # Map ratio to conditional win probability (0.3→0.55, 0.5→0.5, 0.7→0.65 from spec)
    # Linear interpolation: at 0.5 → 0.5; stronger side gets 55-65 per spec
    strength_edge = (ratio - 0.5) * 0.6  # scales ±0.3 to ±0.18
    p_a_more_given_no_tie = 0.5 + strength_edge
    p_a_more_given_no_tie = max(0.30, min(0.70, p_a_more_given_no_tie))
    return (1 - p_tie) * p_a_more_given_no_tie


# Reference tie-trap values from §5.4 (even matchup m_A=m_B)
TIE_TRAP_TABLE = {
    "fouls":       {"m": 11.0,  "tie": 0.086, "even_p": 0.46},
    "ft_corners":  {"m": 4.5,   "tie": 0.135, "even_p": 0.43},
    "2h_corners":  {"m": 2.4,   "tie": 0.188, "even_p": 0.41},
    "ht_corners":  {"m": 2.1,   "tie": 0.202, "even_p": 0.40},
    "2h_sot":      {"m": 2.0,   "tie": 0.207, "even_p": 0.40},
    "cards":       {"m": 1.8,   "tie": 0.219, "even_p": 0.39},
    "offsides":    {"m": 1.5,   "tie": 0.243, "even_p": 0.38},
}


def tie_trap_lookup(stat_type, m_a, m_b):
    """
    Use the §5.4 table. stat_type is one of TIE_TRAP_TABLE keys.
    m_a, m_b are per-team rates.
    Returns P(A strictly more than B).
    """
    base = TIE_TRAP_TABLE.get(stat_type, {"m": 3.0, "tie": 0.15, "even_p": 0.43})
    even_m = base["m"]
    # Scale: use tie_trap() for actual m_a, m_b
    if abs(m_a - m_b) < 0.01:
        # Even matchup: use table even_p value
        m = m_a
        p_tie = tie_prob(m)
        return (1 - p_tie) * 0.5  # symmetric
    return tie_trap(m_a, m_b)


# ---------------------------------------------------------------------------
# §5.5  Threshold tables (exact Poisson)
# ---------------------------------------------------------------------------

def cards_geq4(lam_cards):
    return p_at_least(lam_cards, 4)

def cards_geq2_2h(lam_cards, frac_2h=0.62):
    return p_at_least(lam_cards * frac_2h, 2)

def sot_team_geq2(lam_sot):
    return p_at_least(lam_sot, 2)

def corners_team_geq5(lam_corners):
    return p_at_least(lam_corners, 5)

def offside_team_geq2(lam_offside):
    return p_at_least(lam_offside, 2)


# ---------------------------------------------------------------------------
# §5.6  Player-prop engine (lineup-gated, L7, L10)
# ---------------------------------------------------------------------------

def player_anytime_goal(lam_team, goal_share):
    """Anytime goal = 1 - exp(-lam_team * goal_share)."""
    return 1.0 - math.exp(-lam_team * goal_share)


def player_1sot(lam_team_sot, sot_share, kind="main_striker"):
    """
    1+ SOT prop. v8 corrected bands (L10 ACTIVE):
    - main striker: 52-64%
    - winger/AM: 42-56%
    Compute from λ_player_SOT = lam_team_sot * sot_share.
    Apply driver gate: p in top half of 56-70 requires explicit driver.
    """
    lam_p = lam_team_sot * sot_share
    raw = 1.0 - math.exp(-lam_p)
    # Clamp to corrected bands
    if kind == "main_striker":
        raw = max(0.52, min(0.64, raw))
    elif kind == "winger":
        raw = max(0.42, min(0.56, raw))
    return raw


def player_1sot_2h(lam_team_sot, sot_share, kind="main_striker"):
    """'1+ SOT in 2H' ≈ FT prop scaled to 0.55 rate."""
    lam_p = lam_team_sot * sot_share * 0.55
    return 1.0 - math.exp(-lam_p)


def player_score_or_assist(lam_team, goal_share, role="creator"):
    """Score-or-assist = goal * multiplier (overlap-corrected)."""
    p_goal = player_anytime_goal(lam_team, goal_share)
    mult = 1.6 if role == "creator" else 1.3
    return min(0.97, p_goal * mult)


# ---------------------------------------------------------------------------
# §5.7  Joint / sequence props
# ---------------------------------------------------------------------------

def joint_a_first_and_b_scores_2h(lam_h, lam_a):
    """P(A scores first AND B scores in 2H)."""
    T = lam_h + lam_a
    p_a_first = (lam_h / T) * (1 - math.exp(-T))
    p_b_2h = 1 - math.exp(-0.55 * lam_a)
    # Small dependence haircut (-1 to -2 pts)
    raw = p_a_first * p_b_2h
    return max(0.01, raw - 0.015)


# ---------------------------------------------------------------------------
# §5.8  Hydration break / timing markets (not in spec §5 explicitly)
# ---------------------------------------------------------------------------

def p_goal_before_break(T, break_minute=30, total=90):
    """P(at least 1 goal scored before break_minute)."""
    lam_before = T * (break_minute / total)
    return 1.0 - math.exp(-lam_before)


def p_offside_before_break(lam_offside_total, break_minute=30, total=90):
    """P(at least 1 offside call before break_minute)."""
    lam_before = lam_offside_total * (break_minute / total)
    return 1.0 - math.exp(-lam_before)


def p_card_after_break(lam_cards, break_minute=75, total=90):
    """P(at least 1 card after second hydration break ~75min)."""
    frac_remaining = (total - break_minute) / total
    lam_remaining = lam_cards * (1 + frac_remaining * 0.15)  # late-game yellow bias
    return 1.0 - math.exp(-lam_remaining * frac_remaining)


# ---------------------------------------------------------------------------
# §5.11  Coherence gates + L8 MC batch
# ---------------------------------------------------------------------------

def coherence_check(p_home, p_draw, p_away, tol=0.02):
    """1X2 triplet must sum to 100 ± 2."""
    s = p_home + p_draw + p_away
    return abs(s - 1.0) <= tol


def batch_mc(matches, n_draws=2000, seed=42):
    """
    MC integration over λ uncertainty for correlated markets (§5.11 L8).
    matches: list of dicts with keys:
      name, lam_a, sigma_a, lam_b, sigma_b, markets (list of keys)
    Returns dict: match_name -> {market_key: mc_probability}
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    out = {}
    for m in matches:
        la = np.clip(rng.normal(m["lam_a"], m["sigma_a"], n_draws), 0.05, None)
        lb = np.clip(rng.normal(m["lam_b"], m["sigma_b"], n_draws), 0.05, None)
        T = la + lb
        res = {}
        mkts = m.get("markets", [])
        if "btts3plus" in mkts:
            btts = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            p11  = la * lb * np.exp(-T)
            res["btts3plus"] = float(np.mean(btts - p11))
        if "p_2h_2plus" in mkts:
            lam_2h = 0.55 * T
            res["p_2h_2plus"] = float(np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h)))
        if "clean_sheet_a" in mkts:
            res["clean_sheet_a"] = float(np.mean(np.exp(-lb)))
        if "scores_2h_a" in mkts:
            res["scores_2h_a"] = float(np.mean(1 - np.exp(-0.55 * la)))
        if "p_3plus_goals" in mkts:
            cdf2 = np.exp(-T) * (1 + T + T**2/2)
            res["p_3plus_goals"] = float(np.mean(1 - cdf2))
        if "p_win_a" in mkts:
            # Monte Carlo for win probability
            wins = 0
            for i in range(len(la)):
                ph, pd, _ = poisson_1x2(la[i], lb[i], max_goals=8)
                wins += ph
            res["p_win_a"] = wins / len(la)
        out[m["name"]] = res
    return out


# ---------------------------------------------------------------------------
# §5.10  Debias policy helper
# ---------------------------------------------------------------------------

def dixoncoles_draw_adj(p_win, p_draw, side="favourite"):
    """
    L12/§5.2 Dixon-Coles draw inflation for 40-60 win band.
    In near-coinflip win markets, add +1-3 to draw, subtract from wins.
    Returns (adj_p_win, adj_p_draw) — input side only.
    """
    if 0.40 <= p_win <= 0.60:
        draw_add = 0.02  # +2 pts to draw in tight markets (L12)
        adj_draw = min(p_draw + draw_add, 0.35)
        adj_win  = p_win - (adj_draw - p_draw)
        return adj_win, adj_draw
    return p_win, p_draw


# ---------------------------------------------------------------------------
# §9.2  Outcome decoding from Brier
# ---------------------------------------------------------------------------

def decode_outcome(p_submitted, brier):
    """
    Decode o ∈ {0,1} from submitted p (as decimal 0-1) and brier score.
    o=1 if (p-1)^2 ≈ brier, else o=0.
    Returns (o, confidence) where confidence = 'high'/'low'.
    """
    eps = 1e-4
    if abs((p_submitted - 1)**2 - brier) < eps:
        return 1, "high"
    if abs(p_submitted**2 - brier) < eps:
        return 0, "high"
    # Use whichever is closer
    err_yes = abs((p_submitted - 1)**2 - brier)
    err_no  = abs(p_submitted**2 - brier)
    if err_yes < err_no:
        return 1, "low"
    return 0, "low"


# ---------------------------------------------------------------------------
# §9.1  Self-expected Brier
# ---------------------------------------------------------------------------

def self_expected_brier(probabilities):
    """Σ p(1-p)/n for a list of submitted probabilities (as decimals 0-1)."""
    if not probabilities:
        return 0.0
    return sum(p * (1-p) for p in probabilities) / len(probabilities)


# ---------------------------------------------------------------------------
# Utility: clamp and format for submission
# ---------------------------------------------------------------------------

def to_int(p, noisy=False, anchored=False):
    """
    Convert float probability [0,1] to int 1-99 for submission.
    Noisy register clamped 15-85 unless anchored.
    Avoid exactly 50 (D3).
    """
    v = round(p * 100)
    if noisy and not anchored:
        v = max(15, min(85, v))
    v = max(1, min(99, v))
    if v == 50:
        v = 51  # avoid exactly 50 per D3
    return v
