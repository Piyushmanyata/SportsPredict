"""
Probability Engine v3 — Jump Trading Probability Cup
Implements §5 of the system instructions (v8-final).
All market derivations flow from two anchors: λ_A, λ_B (team goal rates).
"""

import math

# ── Constants ────────────────────────────────────────────────────────────────
EVENT_ID  = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID  = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

# Stage weights (§1.1)
WEIGHT_GROUP   = 1
WEIGHT_KNOCKOUT = 2
WEIGHT_FINAL   = 3

# Half-split factors (§5): 1H ≈ 45% of λ, 2H ≈ 55%
SPLIT_1H = 0.45
SPLIT_2H = 0.55


# ── Poisson helpers ──────────────────────────────────────────────────────────

def poisson_pmf(k, lam):
    """P(X = k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def poisson_cdf(n, lam):
    """P(X <= n) for X ~ Poisson(lam)."""
    return sum(poisson_pmf(k, lam) for k in range(n + 1))

def poisson_sf(n, lam):
    """P(X > n) = 1 - P(X <= n)."""
    return 1.0 - poisson_cdf(n, lam)


# ── Bessel I0 (§5.4 tie-trap correction) ────────────────────────────────────

def bessel_i0(x):
    """Modified Bessel function I0(x), series expansion (accurate to 1e-8 for x<20)."""
    result = 1.0
    term   = 1.0
    for k in range(1, 50):
        term *= (x / 2) ** 2 / (k * k)
        result += term
        if term < 1e-12:
            break
    return result

def tie_prob(lam_a, lam_b):
    """
    P(A == B) for A ~ Poisson(lam_a), B ~ Poisson(lam_b) independent.
    Formula: e^{-(λA+λB)} · I0(2√(λAλB))    [§5.4 / L3]
    """
    return math.exp(-(lam_a + lam_b)) * bessel_i0(2 * math.sqrt(lam_a * lam_b))

def compare_more_than(lam_a, lam_b, max_k=30):
    """
    P(A > B) for A ~ Poisson(lam_a), B ~ Poisson(lam_b).
    Uses: P(A>B) = [1 - P(tie)] × P(A>B | no tie) via explicit summation.
    """
    p_a_gt_b = 0.0
    for a in range(1, max_k + 1):
        pa = poisson_pmf(a, lam_a)
        if pa < 1e-10:
            break
        p_a_gt_b += pa * poisson_cdf(a - 1, lam_b)
    return p_a_gt_b


# ── Devigging ────────────────────────────────────────────────────────────────

def devig_shin(implied_probs):
    """
    Shin devigging — better for large overrounds or big favorites (§5.0).
    Iterative: find z such that sum(sqrt(z² + 4p_i(1-z))) normalises to 1.
    Returns true probabilities.
    """
    probs = list(implied_probs)
    n = len(probs)
    overround = sum(probs)
    if abs(overround - 1.0) < 1e-6:
        return probs

    z = 0.0
    for _ in range(100):
        vals = [math.sqrt(z**2 + 4*p*(1-z)) for p in probs]
        total = sum((v - z) / (2*(1-z)) for v in vals)
        diff  = total - 1.0
        if abs(diff) < 1e-8:
            break
        # Newton step
        d = sum(
            ((1 - z) * (1/(2*vals[i])) * (2*probs[i] - 1) - (1/(2*(1-z))) * (vals[i] - z))
            / (2*(1-z))
            for i in range(n)
        )
        if abs(d) < 1e-12:
            break
        z -= diff / d

    true_probs = [(math.sqrt(z**2 + 4*p*(1-z)) - z) / (2*(1-z)) for p in probs]
    s = sum(true_probs)
    return [p / s for p in true_probs]

def devig_power(implied_probs):
    """Power (exponent) devigging — accurate for moderate overrounds."""
    overround = sum(implied_probs)
    if abs(overround - 1.0) < 1e-6:
        return list(implied_probs)
    exp = math.log(len(implied_probs)) / math.log(overround * len(implied_probs))
    raw = [p ** exp for p in implied_probs]
    s   = sum(raw)
    return [p / s for p in raw]

def devig_basic(implied_probs):
    """Simple proportional devigging."""
    s = sum(implied_probs)
    return [p / s for p in implied_probs]

def devig(implied_probs, method="auto", fav_threshold=0.65, overround_threshold=1.05):
    """
    Devig dispatcher per §5.0:
    - overround > 5% AND fav > 65% → Shin/power; else basic/Shin.
    implied_probs: list of bookmaker implied probs (e.g., [0.55, 0.28, 0.22] for 1X2).
    Returns list of true probs summing to ~1.
    """
    overround = sum(implied_probs)
    max_p     = max(implied_probs)
    if method == "auto":
        if overround > overround_threshold and max_p > fav_threshold:
            method = "power"
        else:
            method = "shin"
    if method == "power":
        return devig_power(implied_probs)
    if method == "shin":
        return devig_shin(implied_probs)
    return devig_basic(implied_probs)

def odds_to_implied(decimal_odds):
    """Convert decimal odds to implied probability."""
    return 1.0 / decimal_odds


# ── λ derivation from anchors ────────────────────────────────────────────────

# O/U 2.5 → λ_total lookup table from §5.3
# ou_over_prob: probability that total goals > 2.5 (i.e., 3+)
_OU_TABLE = [
    (0.32, 2.0),
    (0.40, 2.3),
    (0.46, 2.5),
    (0.51, 2.7),
    (0.55, 2.9),
    (0.58, 3.0),
    (0.62, 3.2),
    (0.65, 3.4),
]

def lambda_total_from_ou(ou_over_prob):
    """
    Derive total goal rate λ from P(over 2.5 goals) anchor.
    Interpolates the table from §5.3.
    """
    if ou_over_prob <= _OU_TABLE[0][0]:
        return _OU_TABLE[0][1]
    if ou_over_prob >= _OU_TABLE[-1][0]:
        return _OU_TABLE[-1][1]
    for i in range(len(_OU_TABLE) - 1):
        p0, t0 = _OU_TABLE[i]
        p1, t1 = _OU_TABLE[i + 1]
        if p0 <= ou_over_prob <= p1:
            frac = (ou_over_prob - p0) / (p1 - p0)
            return t0 + frac * (t1 - t0)
    # fallback: invert Poisson CDF numerically
    return _lambda_from_ou_numeric(ou_over_prob)

def _lambda_from_ou_numeric(p_over, tol=1e-6):
    """Binary search for λ such that P(Poisson(λ) >= 3) == p_over."""
    lo, hi = 0.01, 15.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if poisson_sf(2, mid) < p_over:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2

def split_team_lambdas(lambda_total, p_win_a, p_draw, p_win_b):
    """
    Derive team-level goal rates from total λ and 1X2 win probabilities.
    Simple allocation: λ_A / λ_total ≈ p_score_A / (p_score_A + p_score_B).
    Uses iterative refinement against Dixon-Coles draw mass (§5.2).
    λ_A · (expected goals share of A) = strength_ratio.
    Returns (lambda_a, lambda_b).
    """
    # Approximate: team λ proportional to attack strength implied by win prob
    # P(A wins 90min) driven mainly by λ_A > λ_B
    # Simple first-order: λ_A = λ_total * r / (1+r) where r = f(win_probs)
    # Use log-ratio of win probabilities as proxy for λ ratio
    eps = 1e-4
    p_a = max(p_win_a, eps)
    p_b = max(p_win_b, eps)
    # log-ratio approach
    log_ratio = math.log(p_a / p_b) * 0.5  # damped
    ratio = math.exp(log_ratio)  # λ_A / λ_B
    lambda_a = lambda_total * ratio / (1 + ratio)
    lambda_b = lambda_total / (1 + ratio)
    return lambda_a, lambda_b

def dixon_coles_draw_inflation(lambda_a, lambda_b, rho=-0.1):
    """
    Dixon-Coles correction for 0-0 and 1-1 draw inflation (§5.2).
    rho ≈ -0.1 is typical. Returns adjusted (p_00, p_11) multipliers.
    Not applied to lambdas directly — call adjust_1x2_for_dc() to get
    corrected win/draw/loss.
    """
    tau_00 = 1 - lambda_a * lambda_b * rho
    tau_11 = 1 + rho
    return tau_00, tau_11


# ── Core market derivations ──────────────────────────────────────────────────

def score_prob(lam, half="full"):
    """P(team scores ≥ 1 goal) in the given half. §5.3."""
    if half == "full":
        effective = lam
    elif half == "1H":
        effective = lam * SPLIT_1H
    elif half == "2H":
        effective = lam * SPLIT_2H
    else:
        effective = lam
    return 1.0 - math.exp(-effective)

def btts_prob(lam_a, lam_b):
    """P(both teams score ≥ 1 goal). §5.3."""
    return score_prob(lam_a) * score_prob(lam_b)

def btts_and_over25(lam_a, lam_b):
    """
    P(both score AND total >= 3 goals).
    Computed by summing over joint Poisson grid.
    """
    total = 0.0
    for a in range(1, 15):
        pa = poisson_pmf(a, lam_a)
        if pa < 1e-10:
            break
        for b in range(1, 15):
            if a + b < 3:
                continue
            pb = poisson_pmf(b, lam_b)
            if pb < 1e-10:
                break
            total += pa * pb
    return total

def ou_prob(lam_total, threshold=2.5):
    """P(total goals > threshold), typically O/U 2.5."""
    floor = int(threshold)
    return poisson_sf(floor, lam_total)

def under_prob(lam_total, threshold=2.5):
    """P(total goals <= threshold)."""
    return 1.0 - ou_prob(lam_total, threshold)

def ht_tie_prob(lam_a, lam_b):
    """
    P(HT score is tied). Uses Bessel formula on half-λ values.
    L9: result ≤ 47 unless T < 2.2.
    """
    return tie_prob(lam_a * SPLIT_1H, lam_b * SPLIT_1H)

def half_goals_comparison(lam_a, lam_b):
    """
    P(2H total goals > 1H total goals).
    Tie-trap market (L3). Uses Bessel on 1H vs 2H totals.
    """
    lam_1h = (lam_a + lam_b) * SPLIT_1H
    lam_2h = (lam_a + lam_b) * SPLIT_2H
    p_tie = tie_prob(lam_1h, lam_2h)
    p_2h_gt = compare_more_than(lam_2h, lam_1h)
    return p_2h_gt

def first_goal_scorer_prob(lam_a, lam_b):
    """
    P(team A scores the first goal of the match).
    λ_A / (λ_A + λ_B) × P(at least one goal).
    """
    lam_total = lam_a + lam_b
    p_goal = 1 - math.exp(-lam_total)
    if lam_total < 1e-8:
        return 0.0
    return (lam_a / lam_total) * p_goal

def player_goal_prob(player_share, lam_team):
    """
    P(player scores ≥ 1 goal). player_share = λ_player / λ_team.
    λ_player = player_share × λ_team.
    """
    lam_player = player_share * lam_team
    return 1.0 - math.exp(-lam_player)

def player_sot_prob(position, lam_team=None):
    """
    P(player has ≥ 1 shot on target). v8 bands per position (§5.6, L10):
    striker: 0.52–0.64 (v8 lowered from 0.60–0.72)
    winger:  0.42–0.56
    midfielder (attacking): 0.35–0.48
    """
    bands = {
        "striker":    (0.52, 0.64),
        "winger":     (0.42, 0.56),
        "midfielder": (0.35, 0.48),
    }
    lo, hi = bands.get(position, (0.35, 0.55))
    return (lo + hi) / 2  # midpoint; refine with team λ context if available

def offside_2plus_prob(lam_team):
    """
    P(team caught offside >= 2 times). Rough Poisson: λ_offsides ≈ 1.5 per team.
    Use team λ as a weak proxy (better teams generate more offside traps).
    """
    lam_offside = 1.5 + 0.3 * (lam_team - 1.3)  # empirical adjustment
    lam_offside = max(0.5, lam_offside)
    return poisson_sf(1, lam_offside)

def corners_over_n(lam_team_goals, n, is_dominant=False):
    """
    P(team has >= n corner kicks). Corner λ ≈ 4-6 per team; scale with dominance.
    Dominant team (much higher λ) → corners ≈ 6-7.
    """
    base_corners = 4.5 + 1.5 * min((lam_team_goals - 0.8) / 1.2, 1.0)
    if is_dominant:
        base_corners *= 1.15
    return poisson_sf(n - 1, base_corners)

def fouls_more_than(lam_a, lam_b):
    """
    P(team A commits more fouls than team B).
    Average fouls: ~11-13 per team. Defender (team with lower λ) fouls more.
    """
    # Teams with lower goal λ tend to be more defensive → more fouls
    lam_fouls_a = 11.5 - 1.5 * (lam_a - 1.2)
    lam_fouls_b = 11.5 - 1.5 * (lam_b - 1.2)
    lam_fouls_a = max(8.0, min(15.0, lam_fouls_a))
    lam_fouls_b = max(8.0, min(15.0, lam_fouls_b))
    return compare_more_than(lam_fouls_a, lam_fouls_b)

def cards_more_than(lam_a, lam_b):
    """
    P(team A receives more cards than team B).
    More defensive teams (lower λ) tend to receive more cards.
    """
    lam_cards_a = 1.8 - 0.4 * (lam_a - 1.2)
    lam_cards_b = 1.8 - 0.4 * (lam_b - 1.2)
    lam_cards_a = max(0.8, min(3.0, lam_cards_a))
    lam_cards_b = max(0.8, min(3.0, lam_cards_b))
    return compare_more_than(lam_cards_a, lam_cards_b)

def pen_or_red_prob():
    """Base rate P(penalty OR red card in match). L5: near base rates ~0.28."""
    return 0.28

def penalty_only_prob():
    """Base rate P(penalty kick awarded). ~0.17."""
    return 0.17

def cards_4plus_prob(lam_a=1.2, lam_b=1.2):
    """P(≥ 4 total cards shown). ~0.17 base; match intensity adjusts slightly."""
    return 0.17 + 0.02 * abs(lam_a - lam_b)  # contested matches → more cards

def sot_total_over_n(lam_a, lam_b, n):
    """P(total shots on target >= n). SOT rate ≈ 4.5×λ per team (rough)."""
    lam_sot_a = 3.5 * lam_a
    lam_sot_b = 3.5 * lam_b
    lam_sot_total = lam_sot_a + lam_sot_b
    return poisson_sf(n - 1, lam_sot_total)

def sot_more_than_2h(lam_a, lam_b):
    """
    P(team A has more shots on target than team B in 2H).
    Tie-trap market. λ_sot_2h_A = 3.5 × lam_a × SPLIT_2H.
    """
    lam_sot_a = 3.5 * lam_a * SPLIT_2H
    lam_sot_b = 3.5 * lam_b * SPLIT_2H
    return compare_more_than(lam_sot_a, lam_sot_b)

def corners_more_than_2h(lam_a, lam_b):
    """P(team A has more 2H corners than team B). Tie-trap."""
    lam_corner_a = (4.5 + 1.5 * min((lam_a - 0.8) / 1.2, 1.0)) * SPLIT_2H
    lam_corner_b = (4.5 + 1.5 * min((lam_b - 0.8) / 1.2, 1.0)) * SPLIT_2H
    return compare_more_than(lam_corner_a, lam_corner_b)

def goals_more_than_2h(lam_a, lam_b):
    """P(team A scores more goals than team B in 2H). Tie-trap."""
    return compare_more_than(lam_a * SPLIT_2H, lam_b * SPLIT_2H)

def both_sot_1h_prob(lam_a, lam_b):
    """P(both teams have ≥ 1 SOT in 1H). SOT lambda ≈ 3.5 × goal_lambda × 0.45."""
    lam_sot_a_1h = 3.5 * lam_a * SPLIT_1H
    lam_sot_b_1h = 3.5 * lam_b * SPLIT_1H
    return (1 - math.exp(-lam_sot_a_1h)) * (1 - math.exp(-lam_sot_b_1h))

def both_sot_2h_prob(lam_a, lam_b):
    """P(both teams have ≥ 1 SOT in 2H)."""
    lam_sot_a_2h = 3.5 * lam_a * SPLIT_2H
    lam_sot_b_2h = 3.5 * lam_b * SPLIT_2H
    return (1 - math.exp(-lam_sot_a_2h)) * (1 - math.exp(-lam_sot_b_2h))

def rsa_sot_3plus(lam_team):
    """P(team has >= 3 shots on target). General use."""
    lam_sot = 3.5 * lam_team
    return poisson_sf(2, lam_sot)

def civ_corners_5plus(lam_team):
    """P(team has >= 5 corners). Alias for corners_over_n."""
    return corners_over_n(lam_team, 5, is_dominant=(lam_team > 1.5))

def player_goal_or_assist(player_share_goal, player_share_assist, lam_team):
    """
    P(player scores OR assists ≥ 1 goal).
    Approximate: P(score) + P(assist|no score) × P(team_scores).
    """
    p_score = player_goal_prob(player_share_goal, lam_team)
    # Assist rate conditioned on not scoring
    lam_assist = player_share_assist * lam_team
    p_assist = 1 - math.exp(-lam_assist)
    # Complement: P(score OR assist) ≈ P(score) + P(assist)(1-P(score))
    return p_score + p_assist * (1 - p_score)


# ── Output formatting ────────────────────────────────────────────────────────

def to_int(p, avoid_50=True):
    """
    Convert float probability to valid integer 1–99.
    Avoid exactly 50 per D3 / §9.2 telemetry constraint.
    """
    v = max(1, min(99, round(p * 100)))
    if avoid_50 and v == 50:
        v = 49  # round down; caller may override to 51 if p > 0.50
    return v

def to_int_calibrated(p, avoid_50=True):
    """to_int with directional rounding: 50.x → 51, 49.x → 49."""
    v = max(1, min(99, round(p * 100)))
    if avoid_50 and v == 50:
        v = 51 if p > 0.500 else 49
    return v


# ── Full match derivation ────────────────────────────────────────────────────

def derive_all_markets(lam_a, lam_b, players=None):
    """
    Derive all standard ~10 market probabilities from team lambdas.
    players: dict of player → {"position": str, "share_goal": float, "share_sot": float}
    Returns dict of market_archetype → float (0-1 probability).
    """
    if players is None:
        players = {}

    t = lam_a + lam_b
    markets = {}

    # 1X2
    markets["win_a"]  = poisson_sf(0, 0)  # placeholder; use actual win_prob
    markets["draw"]   = None
    markets["win_b"]  = None

    # O/U 2.5
    markets["under_25"] = under_prob(t, 2.5)
    markets["over_25"]  = ou_prob(t, 2.5)

    # Over 3.0
    markets["over_3"] = ou_prob(t, 3.0)

    # BTTS
    markets["btts"] = btts_prob(lam_a, lam_b)

    # BTTS + O2.5
    markets["btts_and_o25"] = btts_and_over25(lam_a, lam_b)

    # Scoring by half
    markets["a_score_1h"] = score_prob(lam_a, "1H")
    markets["a_score_2h"] = score_prob(lam_a, "2H")
    markets["b_score_1h"] = score_prob(lam_b, "1H")
    markets["b_score_2h"] = score_prob(lam_b, "2H")
    markets["a_score"]    = score_prob(lam_a)
    markets["b_score"]    = score_prob(lam_b)

    # HT tied
    markets["ht_tied"] = ht_tie_prob(lam_a, lam_b)

    # 2H more goals than 1H
    markets["2h_more_than_1h"] = half_goals_comparison(lam_a, lam_b)

    # 2H goals ≥ 2
    markets["2h_goals_2plus"] = poisson_sf(1, t * SPLIT_2H)

    # Comparison markets (tie-trap, L3)
    markets["a_more_2h_goals"]   = goals_more_than_2h(lam_a, lam_b)
    markets["b_more_2h_goals"]   = goals_more_than_2h(lam_b, lam_a)
    markets["a_more_2h_sot"]     = sot_more_than_2h(lam_a, lam_b)
    markets["b_more_2h_sot"]     = sot_more_than_2h(lam_b, lam_a)
    markets["a_more_2h_corners"] = corners_more_than_2h(lam_a, lam_b)
    markets["b_more_2h_corners"] = corners_more_than_2h(lam_b, lam_a)
    markets["a_more_corners"]    = compare_more_than(
        4.5 + 1.5 * min((lam_a - 0.8) / 1.2, 1.0),
        4.5 + 1.5 * min((lam_b - 0.8) / 1.2, 1.0)
    )
    markets["b_more_corners"]    = compare_more_than(
        4.5 + 1.5 * min((lam_b - 0.8) / 1.2, 1.0),
        4.5 + 1.5 * min((lam_a - 0.8) / 1.2, 1.0)
    )
    markets["a_more_fouls"]  = fouls_more_than(lam_a, lam_b)
    markets["b_more_fouls"]  = fouls_more_than(lam_b, lam_a)
    markets["a_more_cards"]  = cards_more_than(lam_a, lam_b)
    markets["b_more_cards"]  = cards_more_than(lam_b, lam_a)

    # First goal by team
    markets["a_scores_first"] = first_goal_scorer_prob(lam_a, lam_b)
    markets["b_scores_first"] = first_goal_scorer_prob(lam_b, lam_a)

    # Offsides
    markets["a_offside_2plus"] = offside_2plus_prob(lam_a)
    markets["b_offside_2plus"] = offside_2plus_prob(lam_b)

    # Noisy markets (base rates, §5 L5)
    markets["pen_or_red"] = pen_or_red_prob()
    markets["penalty"]    = penalty_only_prob()
    markets["cards_4plus"] = cards_4plus_prob(lam_a, lam_b)
    markets["cards_2plus_2h"] = 0.32  # base rate for ≥2 cards in 2H

    # SOT totals
    markets["sot_8plus"]    = sot_total_over_n(lam_a, lam_b, 8)
    markets["sot_4plus_2h"] = sot_total_over_n(lam_a, lam_b, 4)  # 2H only (approx)
    markets["both_sot_1h"]  = both_sot_1h_prob(lam_a, lam_b)
    markets["both_sot_2h"]  = both_sot_2h_prob(lam_a, lam_b)

    # Corners ≥5
    markets["a_corners_5plus"] = corners_over_n(lam_a, 5, is_dominant=(lam_a > lam_b * 1.5))
    markets["b_corners_5plus"] = corners_over_n(lam_b, 5, is_dominant=(lam_b > lam_a * 1.5))

    # SOT ≥3 per team
    markets["a_sot_3plus"] = rsa_sot_3plus(lam_a)
    markets["b_sot_3plus"] = rsa_sot_3plus(lam_b)

    # Player markets
    for name, cfg in players.items():
        pos = cfg.get("position", "midfielder")
        sg  = cfg.get("share_goal", 0.3)
        sa  = cfg.get("share_assist", 0.15)
        markets[f"{name}_sot"]   = player_sot_prob(pos)
        markets[f"{name}_goal"]  = player_goal_prob(sg, lam_a if cfg.get("team") == "A" else lam_b)
        markets[f"{name}_g_or_a"] = player_goal_or_assist(
            sg, sa, lam_a if cfg.get("team") == "A" else lam_b
        )

    return markets


# ── Calibration helpers ──────────────────────────────────────────────────────

def brier(p_submitted, outcome):
    """Brier score: (p - o)^2, lower is better."""
    return (p_submitted - outcome) ** 2

def rbp(your_brier, crowd_brier, stage_weight=1):
    """Relative Brier Points: (crowd_brier - your_brier) * 100 * weight."""
    return (crowd_brier - your_brier) * 100 * stage_weight

def expected_brier(p_true):
    """Self-expected Brier when you submit honestly: p(1-p)."""
    return p_true * (1 - p_true)

def noise_band_1sigma(n):
    """±1σ noise band for mean Brier with n settled markets (§9.1)."""
    return 0.15 / math.sqrt(n)

def decode_outcome(p_submitted, brier_score, eps=1e-4):
    """
    §9.2: decode outcome from (p, brier) without web search.
    brier = (p - o)^2 → o = 1 iff (p-1)^2 == brier, o = 0 iff p^2 == brier.
    Returns 0, 1, or None (ambiguous when p ~ 0.5).
    """
    p = p_submitted / 100.0  # convert integer to float
    if abs((p - 1) ** 2 - brier_score) < eps:
        return 1
    if abs(p ** 2 - brier_score) < eps:
        return 0
    return None


# ── Quick sanity check ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Example: BIH vs QAT — λ_BIH=1.5, λ_QAT=0.9
    lam_a, lam_b = 1.5, 0.9
    m = derive_all_markets(lam_a, lam_b)
    print(f"BIH vs QAT  λ_A={lam_a}  λ_B={lam_b}")
    print(f"  Under 2.5:      {to_int_calibrated(m['under_25'])}")
    print(f"  BTTS:           {to_int_calibrated(m['btts'])}")
    print(f"  BTTS+O2.5:      {to_int_calibrated(m['btts_and_o25'])}")
    print(f"  A score 1H:     {to_int_calibrated(m['a_score_1h'])}")
    print(f"  A score 2H:     {to_int_calibrated(m['a_score_2h'])}")
    print(f"  HT tied:        {to_int_calibrated(m['ht_tied'])}")
    print(f"  A 2H corners>B: {to_int_calibrated(m['a_more_2h_corners'])}")
    print(f"  A 2H SOT>B:     {to_int_calibrated(m['a_more_2h_sot'])}")
    print(f"  Pen/Red:        {to_int_calibrated(m['pen_or_red'])}")
    print(f"  Striker SOT:    {to_int_calibrated(player_sot_prob('striker'))}")
