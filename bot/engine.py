"""
Probability Engine v3 — §5 (complete formula set).

Modules:
  devig_power()         — power-method devigging
  fit_lambda()          — λ-engine from O/U 2.5 + 1X2
  poisson_prob()        — P(X=k) and tails
  ALL_ARCHETYPES        — dispatch table for 12 market types
  coherence_check()     — §5.11 gates before any batch
  run_mc_correlation()  — L8 batched Monte Carlo (numpy/scipy)
  overlay_scan()        — §5.12 situational overlays
"""

import math
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. DEVIGGING (§5.0 / §5.1)
# ---------------------------------------------------------------------------

def devig_power(raw_odds: List[float]) -> List[float]:
    """
    Power-method devigging.
    raw_odds: list of decimal odds (e.g. [2.10, 3.40, 3.60] for 1X2).
    Returns fair probabilities summing to 1.0.
    """
    implied = [1.0 / o for o in raw_odds]
    overround = sum(implied)
    # For overround > 5% or favourite probability > 65%, use power correction
    if overround > 1.05 or max(implied) / overround > 0.65:
        # Power method: find k such that sum(implied^k) = 1
        k = _find_power_k(implied)
        fair = [i ** k for i in implied]
    else:
        fair = [i / overround for i in implied]
    total = sum(fair)
    return [f / total for f in fair]


def _find_power_k(implied: List[float]) -> float:
    """Binary search for power k: sum(implied_i^k) = 1."""
    lo, hi = 0.5, 3.0
    for _ in range(50):
        mid = (lo + hi) / 2
        s = sum(i ** mid for i in implied)
        if s > 1.0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def devig_percent(raw_probs: List[float]) -> List[float]:
    """Simple percentage-strip devigging (for book-format inputs 0–1)."""
    total = sum(raw_probs)
    return [p / total for p in raw_probs]


# ---------------------------------------------------------------------------
# 2. LAMBDA-ENGINE (§5.1)
# ---------------------------------------------------------------------------

# Reference λ splits from spec §5.1
LAMBDA_SPLITS = [
    # (total_goals, lam_home, lam_away, label)
    (2.70, 1.35, 1.35, "even"),
    (2.70, 1.65, 1.05, "moderate_fav"),
    (2.75, 2.00, 0.75, "strong_fav"),
    (2.95, 2.40, 0.55, "heavy_fav"),
]


def fit_lambda(
    ou25_over_prob: float,         # devigged P(over 2.5 goals) in [0,1]
    home_win_prob: Optional[float] = None,  # devigged from 1X2
    draw_prob: Optional[float] = None,
    away_win_prob: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Fit (λ_home, λ_away) from O/U 2.5 price and optionally 1X2.
    Returns (λ_home, λ_away).

    Step 1: derive total λ_T from P(goals > 2.5) = 1 - Poisson_CDF(2; λ_T).
    Step 2: split λ_T using 1X2 to reproduce home_win_prob within ±2 pts.
    """
    lam_total = _solve_lambda_from_over25(ou25_over_prob)

    if home_win_prob is None or draw_prob is None or away_win_prob is None:
        # Even split as fallback
        return lam_total / 2, lam_total / 2

    # Optimise split to match home_win_prob
    best_split = _optimise_split(lam_total, home_win_prob, draw_prob)
    return best_split


def _solve_lambda_from_over25(p_over: float) -> float:
    """Solve P(Poisson(λ) >= 3) = p_over via bisection."""
    lo, hi = 0.1, 8.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _poisson_cdf(2, mid) < 1 - p_over:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _optimise_split(
    lam_total: float,
    target_home_win: float,
    target_draw: float,
    tolerance: float = 0.02,
) -> Tuple[float, float]:
    """
    Binary-search λ_home ∈ [0, lam_total] to match target_home_win.
    Returns (λ_home, λ_away).
    """
    lo, hi = 0.0, lam_total
    for _ in range(60):
        lh = (lo + hi) / 2
        la = lam_total - lh
        hw = _poisson_match_win(lh, la, "home")
        if hw < target_home_win:
            lo = lh
        else:
            hi = lh
    lh = (lo + hi) / 2
    return lh, lam_total - lh


def _poisson_match_win(lam_h: float, lam_a: float, side: str, max_g: int = 10) -> float:
    """P(home wins) or P(away wins) via double-Poisson grid."""
    p = 0.0
    for h in range(max_g + 1):
        ph = _poisson_pmf(lam_h, h)
        for a in range(max_g + 1):
            pa = _poisson_pmf(lam_a, a)
            if side == "home" and h > a:
                p += ph * pa
            elif side == "away" and a > h:
                p += ph * pa
    return p


def poisson_draw(lam_h: float, lam_a: float, max_g: int = 10) -> float:
    p = 0.0
    for k in range(max_g + 1):
        p += _poisson_pmf(lam_h, k) * _poisson_pmf(lam_a, k)
    return p


# ---------------------------------------------------------------------------
# 3. POISSON PRIMITIVES
# ---------------------------------------------------------------------------

def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_cdf(k_max: int, lam: float) -> float:
    return sum(_poisson_pmf(lam, k) for k in range(k_max + 1))


def poisson_prob_at_least(lam: float, k: int) -> float:
    """P(X >= k)."""
    return 1 - _poisson_cdf(k - 1, lam)


def poisson_prob_exactly(lam: float, k: int) -> float:
    return _poisson_pmf(lam, k)


def poisson_prob_over(lam: float, threshold: float) -> float:
    """P(X > threshold) — handles non-integer thresholds like 2.5."""
    k = int(math.floor(threshold)) + 1
    return poisson_prob_at_least(lam, k)


# ---------------------------------------------------------------------------
# 4. BTTS
# ---------------------------------------------------------------------------

def btts_prob(lam_h: float, lam_a: float) -> float:
    """P(both teams score ≥1)."""
    p_home_scores = 1 - _poisson_pmf(lam_h, 0)
    p_away_scores = 1 - _poisson_pmf(lam_a, 0)
    return p_home_scores * p_away_scores


# ---------------------------------------------------------------------------
# 5. TIE-TRAP ENGINE (§5.4) — strict "more than" markets
# ---------------------------------------------------------------------------

# Pre-computed table §5.4: P(tie) for Poisson(λ) at various λ values
# Approximate via simulation; bot computes directly.
def tie_prob_poisson(lam_a: float, lam_b: float, max_k: int = 30) -> float:
    """P(A == B) for two independent Poisson(λ_A), Poisson(λ_B) counts."""
    p = 0.0
    for k in range(max_k + 1):
        p += _poisson_pmf(lam_a, k) * _poisson_pmf(lam_b, k)
    return p


def strict_more_than(p_a_beats_b: float, lam_a: float, lam_b: float) -> float:
    """
    §5.4: P(A strictly > B) = P(A≥B) - P(tie) / 2 ... but simpler: direct grid.
    p_a_beats_b: computed from double-Poisson grid (A > B).
    """
    return p_a_beats_b  # already excludes ties if computed via grid


def strict_more_grid(lam_a: float, lam_b: float, max_k: int = 30) -> float:
    """P(Poisson(lam_a) > Poisson(lam_b)) via double-Poisson grid."""
    p = 0.0
    for a in range(max_k + 1):
        for b in range(a):
            p += _poisson_pmf(lam_a, a) * _poisson_pmf(lam_b, b)
    return p


# ---------------------------------------------------------------------------
# 6. 12 MARKET ARCHETYPES (§5.3)
# ---------------------------------------------------------------------------

def archetype_win(devigged_prob: float) -> float:
    """#1 Win market — devigged 1X2 probability."""
    return devigged_prob * 100


def archetype_goals_over_under(lam_total: float, threshold: float, direction: str) -> float:
    """#2 Over/Under N goals."""
    if direction == "over":
        p = poisson_prob_over(lam_total, threshold)
    else:
        p = 1 - poisson_prob_over(lam_total, threshold)
    return p * 100


def archetype_btts_and_over(lam_h: float, lam_a: float, goal_threshold: float) -> float:
    """#3 BTTS AND 3+ goals = BTTS − P(1−1) (approximately)."""
    lam_total = lam_h + lam_a
    p_btts = btts_prob(lam_h, lam_a)
    # P(BTTS and > threshold) ≈ P(BTTS) - P(exactly 1-1) for threshold=2
    p_one_one = _poisson_pmf(lam_h, 1) * _poisson_pmf(lam_a, 1)
    if goal_threshold == 2:
        p = p_btts - p_one_one
    else:
        # General: P(home>=1, away>=1, total>threshold)
        p = _btts_and_over_grid(lam_h, lam_a, goal_threshold)
    return max(1, min(99, p * 100))


def _btts_and_over_grid(lam_h: float, lam_a: float, threshold: float, max_k: int = 15) -> float:
    p = 0.0
    for h in range(1, max_k + 1):
        ph = _poisson_pmf(lam_h, h)
        for a in range(1, max_k + 1):
            pa = _poisson_pmf(lam_a, a)
            if h + a > threshold:
                p += ph * pa
    return p


def archetype_team_scores_2h(lam_team: float) -> float:
    """#4 Team X scores in 2H: 1 − e^(−0.55 × λ_X)."""
    lam_2h = 0.55 * lam_team
    p = 1 - math.exp(-lam_2h)
    return p * 100


def archetype_team_scores(lam_team: float) -> float:
    """#5 Team X scores ≥1: 1 − e^(−λ_X)."""
    p = 1 - math.exp(-lam_team)
    return p * 100


def archetype_strict_comparison(lam_a: float, lam_b: float) -> float:
    """#6 A strictly more than B (fouls/corners/SOT) — tie-trap §5.4."""
    return strict_more_grid(lam_a, lam_b) * 100


def archetype_threshold_count(lam: float, threshold: int, direction: str = "over") -> float:
    """#7 Threshold counts (4+ cards, 5+ corners, 2+ SOT) — Poisson tail §5.5."""
    if direction == "over":
        p = poisson_prob_at_least(lam, threshold)
    else:
        p = _poisson_cdf(threshold - 1, lam)
    return p * 100


def archetype_player_prop_goal(
    lam_team: float,
    share_of_team_goals: float,
    is_starting: bool,
    rotation_risk: float = 0.0,
) -> float:
    """
    #8 Player anytime scorer — §5.6 with L7 rotation-gating.
    rotation_risk: 0–1, probability player does NOT start (reduces effective λ).
    """
    effective_share = share_of_team_goals * (1 - rotation_risk)
    lam_player = lam_team * effective_share
    p = 1 - math.exp(-lam_player)
    return p * 100


def archetype_player_prop_sot(
    lam_team_sot: float,
    share_of_team_sot: float,
    rotation_risk: float = 0.0,
) -> float:
    """#8 Player 1+ SOT — corrected band per L10 (band lowered from 60-72 → 52-64)."""
    effective_share = share_of_team_sot * (1 - rotation_risk)
    lam_player_sot = lam_team_sot * effective_share
    p = 1 - math.exp(-lam_player_sot)
    return p * 100


def archetype_ht_tied(lam_h: float, lam_a: float) -> float:
    """#9 HT tied — Bessel table ceiling 47 (§5.3, L9)."""
    # P(HT draw) ≈ P(full-time draw from λ_HT where λ_HT = 0.45 × λ_FT)
    lam_h_ht = 0.45 * lam_h
    lam_a_ht = 0.45 * lam_a
    p = poisson_draw(lam_h_ht, lam_a_ht) * 100
    # L9 ceiling: HT tied ≤ 47 unless total λ < 2.2
    lam_total = lam_h + lam_a
    if lam_total >= 2.2:
        p = min(p, 47)
    return p


def archetype_ht_both_sot(lam_h_sot_ht: float, lam_a_sot_ht: float) -> float:
    """#10 HT both ≥1 SOT — product of HT Poissons."""
    p_h = 1 - math.exp(-lam_h_sot_ht)
    p_a = 1 - math.exp(-lam_a_sot_ht)
    return p_h * p_a * 100


def archetype_joint_sequence(
    p_event_a: float,
    p_event_b: float,
    dependence_haircut: float = 0.05,
) -> float:
    """#11 Joint/sequence (X first AND Y 2H) — product with small dependence haircut."""
    p = (p_event_a / 100) * (p_event_b / 100) * (1 - dependence_haircut)
    return p * 100


def archetype_drama(
    event_type: str,
    base_rate: float,
    eb_n: int = 0,
    eb_k: int = 0,
    k_prior: int = 7,
) -> float:
    """
    #12 Drama (pen, red card) — base rates §5.8 + empirical Bayes + noisy-register clamp.
    base_rate: historical base rate for this event type (0–1).
    eb_n: matches observed, eb_k: events observed.
    k_prior: prior pseudo-count (Laplace smoothing).
    """
    # Empirical Bayes update: posterior = (k_prior × base_rate + eb_k) / (k_prior + eb_n)
    posterior = (k_prior * base_rate + eb_k) / (k_prior + eb_n) if (k_prior + eb_n) > 0 else base_rate
    p = posterior * 100
    # Noisy-register: clamp 15–85 (§5.9, unless anchored by strong data)
    p = max(15, min(85, p))
    return p


# ---------------------------------------------------------------------------
# 7. BASE RATES (§5.8) — fallback when data missing
# ---------------------------------------------------------------------------

BASE_RATES = {
    "penalty":         0.28,   # per match (international avg)
    "red_card":        0.22,
    "clean_sheet":     0.30,
    "btts":            0.52,
    "over_2_5":        0.56,
    "corners_over_9":  0.55,
    "cards_over_4":    0.48,
    "player_goal":     0.18,
    "player_sot":      0.55,
    "ht_draw":         0.31,
}


# ---------------------------------------------------------------------------
# 8. COHERENCE GATES (§5.11)
# ---------------------------------------------------------------------------

class CoherenceError(Exception):
    pass


def coherence_check(markets: List[Dict]) -> List[str]:
    """
    Run all §5.11 coherence checks on a list of market dicts.
    Each dict: {'id': ..., 'question': ..., 'p': int, 'type': str, ...}
    Returns list of violation strings (empty = all clear).
    """
    violations = []
    violations.extend(_check_triplet_sums(markets))
    violations.extend(_check_ladder_monotone(markets))
    violations.extend(_check_complements(markets))
    violations.extend(_check_joints_leq_marginals(markets))
    violations.extend(_check_large_deviations(markets))
    return violations


def _check_triplet_sums(markets: List[Dict]) -> List[str]:
    """1X2 triplet must sum to 100 ± 2."""
    from bot.config import TRIPLET_SUM_TOLERANCE
    violations = []
    # Group by match_id
    triplets = {}
    for m in markets:
        q = m.get("question", "").lower()
        mid = m.get("match_id", "")
        if not mid:
            continue
        if mid not in triplets:
            triplets[mid] = {}
        if "home win" in q or "1x2" in q:
            triplets[mid]["home"] = m["p"]
        elif "draw" in q and "win" not in q.replace("draw", ""):
            triplets[mid]["draw"] = m["p"]
        elif "away win" in q:
            triplets[mid]["away"] = m["p"]

    for mid, t in triplets.items():
        if len(t) == 3:
            total = t["home"] + t["draw"] + t["away"]
            if abs(total - 100) > TRIPLET_SUM_TOLERANCE:
                violations.append(f"1X2 triplet sums to {total} (match {mid[:8]})")
    return violations


def _check_ladder_monotone(markets: List[Dict]) -> List[str]:
    """Over/Under ladder must be monotone: P(O/U N) > P(O/U N+1)."""
    violations = []
    by_match = {}
    for m in markets:
        q = m.get("question", "").lower()
        mid = m.get("match_id", "")
        if "over" in q and "goals" in q and mid:
            by_match.setdefault(mid, []).append((m["p"], q))
    # Check sorted by threshold
    for mid, entries in by_match.items():
        entries.sort(key=lambda x: x[1])  # sort by question string (heuristic)
        for i in range(len(entries) - 1):
            if entries[i][0] < entries[i + 1][0]:
                violations.append(
                    f"O/U ladder non-monotone for match {mid[:8]}: "
                    f"{entries[i][1]}={entries[i][0]} < {entries[i+1][1]}={entries[i+1][0]}"
                )
    return violations


def _check_complements(markets: List[Dict]) -> List[str]:
    """For explicitly paired (over/under, yes/no), p + complement should be 100 ± 2."""
    from bot.config import COMPLEMENT_TOLERANCE
    violations = []
    tagged = {m["id"]: m for m in markets if "id" in m}
    for m in markets:
        comp_id = m.get("complement_id")
        if comp_id and comp_id in tagged:
            comp = tagged[comp_id]
            total = m["p"] + comp["p"]
            if abs(total - 100) > COMPLEMENT_TOLERANCE:
                violations.append(
                    f"Complement mismatch: {m['question'][:40]}={m['p']} + "
                    f"{comp['question'][:40]}={comp['p']} = {total}"
                )
    return violations


def _check_joints_leq_marginals(markets: List[Dict]) -> List[str]:
    """Joint probability must be ≤ min(marginals)."""
    violations = []
    for m in markets:
        marginals = m.get("marginal_probs", [])
        if marginals:
            min_marginal = min(marginals)
            if m["p"] > min_marginal + 2:
                violations.append(
                    f"Joint {m.get('question','')[:40]}={m['p']} > min(marginals)={min_marginal}"
                )
    return violations


def _check_large_deviations(markets: List[Dict]) -> List[str]:
    """If |final − anchor| > 10, require written cause (§5.11)."""
    violations = []
    for m in markets:
        anchor = m.get("anchor_p")
        if anchor is not None and abs(m["p"] - anchor) > 10:
            cause = m.get("deviation_cause", "")
            if not cause:
                violations.append(
                    f"Large deviation: {m.get('question','')[:40]} "
                    f"p={m['p']} vs anchor={anchor}, no cause given"
                )
    return violations


# ---------------------------------------------------------------------------
# 9. L8 MONTE CARLO CORRELATION (§5.11 / L8)
# ---------------------------------------------------------------------------

def run_mc_correlation(
    lam_h_mean: float,
    lam_a_mean: float,
    market_list: List[Dict],
    n_draws: int = 2000,
) -> List[Dict]:
    """
    L8 batched MC: sample λ pairs from uncertainty distribution, compute
    each market probability, return mean estimates.

    market_list: each dict has 'archetype' key and archetype-specific params.
    lam_h_mean / lam_a_mean: point estimates of team lambdas.
    Returns same list with 'p_mc' key added.
    """
    try:
        import numpy as np
    except ImportError:
        return market_list  # fallback: return unchanged

    # λ uncertainty: ±15% (calibrated from match-level Brier variance in §9.5)
    lam_h_std = lam_h_mean * 0.15
    lam_a_std = lam_a_mean * 0.15

    lams_h = np.random.normal(lam_h_mean, lam_h_std, n_draws).clip(0.1, 8.0)
    lams_a = np.random.normal(lam_a_mean, lam_a_std, n_draws).clip(0.1, 8.0)

    results = []
    for m in market_list:
        arch = m.get("archetype", "")
        probs = []
        for lh, la in zip(lams_h, lams_a):
            if arch == "win_home":
                p = _poisson_match_win(lh, la, "home")
            elif arch == "win_away":
                p = _poisson_match_win(lh, la, "away")
            elif arch == "draw":
                p = poisson_draw(lh, la)
            elif arch == "btts":
                p = btts_prob(lh, la)
            elif arch == "over_2_5":
                p = poisson_prob_over(lh + la, 2.5)
            else:
                p = m.get("p", 50) / 100.0
            probs.append(p)

        p_mc = float(np.mean(probs)) * 100
        m_copy = dict(m)
        m_copy["p_mc"] = round(p_mc, 1)
        results.append(m_copy)
    return results


# ---------------------------------------------------------------------------
# 10. §5.12 SITUATIONAL OVERLAYS
# ---------------------------------------------------------------------------

OVERLAY_CAP_PTS = 8  # §5.12 total overlay cap

def overlay_scan(
    p_base: float,
    altitude_m: float = 0,
    is_reigning_champion: bool = False,
    is_lowland_side_vs_altitude: bool = False,
    matchday3_rotation_risk: float = 0.0,
) -> Tuple[float, List[str]]:
    """
    Apply §5.12 situational overlays. Returns (p_adjusted, [overlay_notes]).
    Total cap: ±8 pts (absolute) across all overlays.
    """
    adjustment = 0.0
    notes = []

    # Altitude overlay (Goldman evidence: Azteca 2240m is a drag on lowland sides)
    if altitude_m >= 2000 and is_lowland_side_vs_altitude:
        adj = -3.0
        adjustment += adj
        notes.append(f"altitude {altitude_m}m drag on lowland side: {adj:+.0f}pt")

    # Winner's slump / reigning-champion drag
    if is_reigning_champion:
        adj = -2.0
        adjustment += adj
        notes.append(f"reigning-champion drag: {adj:+.0f}pt")

    # Matchday-3 rotation risk
    if matchday3_rotation_risk > 0.3:
        adj = -(matchday3_rotation_risk * 6)  # up to -6 for heavy rotation
        adjustment += adj
        notes.append(f"MD3 rotation risk {matchday3_rotation_risk:.0%}: {adj:+.1f}pt")

    # Cap total overlay at ±OVERLAY_CAP_PTS
    if abs(adjustment) > OVERLAY_CAP_PTS:
        adjustment = math.copysign(OVERLAY_CAP_PTS, adjustment)
        notes.append(f"overlay capped at ±{OVERLAY_CAP_PTS}pt")

    return p_base + adjustment, notes


# ---------------------------------------------------------------------------
# 11. DIXON-COLES CORRECTION (§5.2)
# ---------------------------------------------------------------------------

def dixon_coles_adjust(
    p_draw: float,
    p_btts: float,
    p_over_2_5: float,
    is_tight_match: bool,
    is_defensive_match: bool,
) -> Tuple[float, float, float]:
    """
    Apply Dixon–Coles corrections and overdispersion tilts (§5.2 / §5.2.1 / L14).
    Returns (p_draw_adj, p_btts_adj, p_over_adj) in [0,100] pct.
    """
    from bot.config import DC_DRAW_BONUS_TIGHT, DC_BTTS_PENALTY_DEF, OD_GOALLESS_ADD, OD_FOURPLUS_ADD

    p_draw_adj   = p_draw
    p_btts_adj   = p_btts
    p_over_adj   = p_over_2_5

    if is_tight_match:
        p_draw_adj += DC_DRAW_BONUS_TIGHT

    if is_defensive_match:
        p_btts_adj  -= DC_BTTS_PENALTY_DEF
        p_over_adj  -= DC_BTTS_PENALTY_DEF  # correlated

    # L14 overdispersion: excess goalless + fat 4+ tail
    p_draw_adj += OD_GOALLESS_ADD   # more clean draws
    p_over_adj += OD_FOURPLUS_ADD   # slightly fatter tail

    return (
        max(1, min(99, p_draw_adj)),
        max(1, min(99, p_btts_adj)),
        max(1, min(99, p_over_adj)),
    )


# ---------------------------------------------------------------------------
# 12. L10 CORRECTION (active band 56–70 runs HOT)
# ---------------------------------------------------------------------------

def l10_l12_corrections(p: float, market_type: str, has_explicit_driver: bool) -> float:
    """
    L10: 56–70 band runs HOT → require explicit driver, or pull toward anchor.
    L12: Win markets (40–60 band) run HOT → firmer Dixon-Coles draw inflation.
    Both are input-side only — do not create output floors/ceilings (D2/D11).
    """
    if market_type == "player_sot" and 56 <= p <= 70:
        # L10 input-side correction: lower band from 60-72 → 52-64
        if not has_explicit_driver:
            # Pull back 3-4 pts toward the lower sub-band
            p = p - 4.0
    if market_type == "win" and 40 <= p <= 60:
        # L12 correction: already handled in Dixon-Coles draw inflation above
        pass  # correction is in dixon_coles_adjust()
    return p
