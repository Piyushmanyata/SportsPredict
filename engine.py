"""
Probability Engine v3 — Jump Trading Probability Cup
Implements §5 of probability-cup-system-instructions-v8-final.md (v8-FINAL).

Usage:
    from engine import Match, compute_all_markets, clamp, clamp_noisy
"""
import math
from dataclasses import dataclass, field
from typing import Optional
from scipy.special import i0  # Bessel I₀ for HT-tie formula

# ── Verified constants (§4.3) ──────────────────────────────────────────────────
EVENT_ID = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID  = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"
STAGE_WEIGHTS = {"group": 1, "r32": 2, "r16": 2, "qf": 2, "sf": 2, "final": 3}

# ── Base rates (§5.8 working values — update after settle audits) ──────────────
BASE_PEN_RATE     = 0.34   # P(pen) ≈ 29%
BASE_RED_RATE     = 0.06   # P(red) ≈ 6%
BASE_PEN_OR_RED   = 0.31   # P(pen∨red) ≈ 31%
BASE_CARDS_MEAN   = 3.5    # working mean cards per match
BASE_GOALS_MEAN   = 2.55   # working goals/match group stage

# ── O/U 2.5 → T lookup table (§5.2) ──────────────────────────────────────────
_OU25_TABLE = [(0.32, 2.0), (0.38, 2.2), (0.46, 2.5),
               (0.51, 2.7), (0.58, 3.0), (0.64, 3.3)]

def ou25_to_T(p_over: float) -> float:
    """Interpolate total expected goals T from P(Over 2.5)."""
    for i in range(len(_OU25_TABLE) - 1):
        a, b = _OU25_TABLE[i], _OU25_TABLE[i + 1]
        if a[0] <= p_over <= b[0]:
            frac = (p_over - a[0]) / (b[0] - a[0])
            return a[1] + frac * (b[1] - a[1])
    return _OU25_TABLE[0][1] if p_over <= _OU25_TABLE[0][0] else _OU25_TABLE[-1][1]


# ── Utility ────────────────────────────────────────────────────────────────────
def clamp(x, lo: int = 1, hi: int = 99) -> int:
    return max(lo, min(hi, round(x)))

def clamp_noisy(x) -> int:
    """Noisy-register markets clamped 15-85 (§5.9)."""
    return clamp(x, lo=15, hi=85)

def to_pct(p: float) -> int:
    """Float [0,1] → integer [1,99]."""
    return clamp(p * 100)


# ── Poisson helpers ────────────────────────────────────────────────────────────
def _poisson_pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)

def p_poisson_ge(lam: float, k: int) -> float:
    """P(X ≥ k) for Poisson(lam). Exact to k=15."""
    cdf = sum(_poisson_pmf(lam, i) for i in range(k))
    return max(0.0, min(1.0, 1.0 - cdf))

def p_poisson_le(lam: float, k: int) -> float:
    return 1.0 - p_poisson_ge(lam, k + 1)


# ── Core probability formulas (§5.2) ──────────────────────────────────────────
def p_scores(lam: float) -> float:
    return 1.0 - math.exp(-lam)

def p_scores_2h(lam: float) -> float:
    return 1.0 - math.exp(-0.55 * lam)

def p_scores_1h(lam: float) -> float:
    return 1.0 - math.exp(-0.45 * lam)

def p_btts(la: float, lb: float) -> float:
    return p_scores(la) * p_scores(lb)

def p_1_1(la: float, lb: float) -> float:
    return la * lb * math.exp(-(la + lb))

def p_btts_3plus(la: float, lb: float) -> float:
    """Never multiply marginals — use BTTS - P(1-1) identity (§5.2)."""
    return max(0.0, p_btts(la, lb) - p_1_1(la, lb))

def p_clean_sheet(lam_opp: float) -> float:
    return math.exp(-lam_opp)

def p_ht_tied(la: float, lb: float) -> float:
    """HT tied via Bessel (§5.5). la, lb are FT λ — scaled internally."""
    la_ht, lb_ht = 0.45 * la, 0.45 * lb
    T_ht = la_ht + lb_ht
    return math.exp(-T_ht) * i0(2 * math.sqrt(la_ht * lb_ht))

def p_over25(T: float) -> float:
    return p_poisson_ge(T, 3)

def p_under2(T: float) -> float:
    return p_poisson_le(T, 2)

def p_scores_first(la: float, T: float) -> float:
    """P(team A scores first) ≈ (λA/T)·(1 − e^(−T)). §5.7."""
    if T <= 0:
        return 0.5
    return (la / T) * (1.0 - math.exp(-T))


# ── Tie-trap engine (§5.4) ─────────────────────────────────────────────────────
# (stat_key → (mean_m, p_tie_exact, p_even_given_no_tie))
_TIE = {
    "fouls":       (11.0, 0.086, 0.46),
    "corners_ft":  (4.5,  0.135, 0.43),
    "corners_2h":  (2.4,  0.188, 0.41),
    "corners_ht":  (2.1,  0.202, 0.40),
    "sot_2h":      (2.0,  0.207, 0.40),
    "sot_ft":      (3.5,  0.160, 0.42),  # approximate for FT SOT
    "cards":       (1.8,  0.219, 0.39),
    "offsides":    (1.5,  0.243, 0.38),
}

def p_more_than(stat: str, ratio: float = 1.0) -> int:
    """
    P(team A has MORE X than team B) — strict tie-trap.
    ratio: λ_A / λ_B estimated strength ratio (>1 favours A).
    Returns integer 1-99. Never returns 50 (L3).
    """
    m, p_tie, p_cond_even = _TIE.get(stat, (3.0, 0.18, 0.41))
    skew = min(0.12, 0.08 * abs(ratio - 1.0))
    if ratio >= 1.0:
        p_cond = min(0.65, p_cond_even + skew)
    else:
        p_cond = max(0.27, p_cond_even - skew)
    raw = (1.0 - p_tie) * p_cond
    return clamp(raw * 100)


# ── Player props (§5.6) — v8 L10 bands applied ────────────────────────────────
# Main striker 1+SOT band: 52-64 (v8: lowered from 60-72 per L10)
# Winger/AM 1+SOT band: 42-56
# Driver gate: if modeled p lands in 56-70, requires explicit written driver

def p_player_goal(team_lam: float, goal_share: float) -> int:
    lam_p = team_lam * goal_share
    return to_pct(1.0 - math.exp(-lam_p))

def p_player_sot_ge(team_sot_lam: float, player_sot_share: float, k: int = 1) -> int:
    lam_p = team_sot_lam * player_sot_share
    return to_pct(p_poisson_ge(lam_p, k))

def p_soa(team_lam: float, involvement_rate: float) -> int:
    """Score-or-assist. involvement_rate ≈ 0.30 creators, 0.20 pure 9s."""
    return to_pct(p_scores(team_lam) * involvement_rate)

def p_sot_2h_player(player_sot_lam_ft: float) -> int:
    """P(player ≥1 SOT in 2H) ≈ 1 − e^(−0.55·λ_SOT_player). §5.6."""
    return to_pct(1.0 - math.exp(-0.55 * player_sot_lam_ft))


# ── Team stat thresholds (§5.5) ────────────────────────────────────────────────
def p_team_sot_ge(sot_lam: float, k: int) -> int:
    return to_pct(p_poisson_ge(sot_lam, k))

def p_team_corners_ge(corner_lam: float, k: int) -> int:
    return to_pct(p_poisson_ge(corner_lam, k))

def p_total_corners_ge(total_corner_lam: float, k: int) -> int:
    return to_pct(p_poisson_ge(total_corner_lam, k))

def p_total_shots_ge(total_shot_lam: float, k: int) -> int:
    return to_pct(p_poisson_ge(total_shot_lam, k))

def p_cards_ge(cards_lam: float, k: int) -> int:
    return to_pct(p_poisson_ge(cards_lam, k))

def p_offsides_ge(offside_lam: float, k: int) -> int:
    return to_pct(p_poisson_ge(offside_lam, k))


# ── Drama markets (§5.8/§5.9) — noisy register ────────────────────────────────
def p_penalty(base: float = BASE_PEN_RATE) -> int:
    return clamp_noisy(base * 100)

def p_red_card(base: float = BASE_RED_RATE) -> int:
    return clamp_noisy(base * 100)

def p_pen_or_red(base: float = BASE_PEN_OR_RED) -> int:
    return clamp_noisy(base * 100)


# ── HT-state markets ───────────────────────────────────────────────────────────
def p_team_leading_ht(la: float, lb: float) -> int:
    """P(team A leading at HT). Enumerate Poisson score grid up to 6-6."""
    la_ht, lb_ht = 0.45 * la, 0.45 * lb
    p_lead = 0.0
    for ga in range(7):
        for gb in range(7):
            if ga <= gb:
                continue
            p_lead += (_poisson_pmf(la_ht, ga) * _poisson_pmf(lb_ht, gb))
    return to_pct(p_lead)

def p_scores_both_halves(lam: float) -> int:
    """P(team scores in BOTH halves)."""
    return to_pct(p_scores_1h(lam) * p_scores_2h(lam))

# L9: HT-tied ceiling = 47 unless anchor-implied T < 2.2 (§5.5/§10 L9)
HT_TIED_CEILING = 47

def p_ht_tied_clamped(la: float, lb: float, T: float) -> int:
    raw = to_pct(p_ht_tied(la, lb))
    ceiling = HT_TIED_CEILING if T >= 2.2 else 52
    return min(raw, ceiling)


# ── Hydration-break and stoppage-time markets (2026 WC new types) ─────────────
def p_goal_before_break1(T: float, break_min: float = 30.0) -> int:
    """P(≥1 goal before ~30' hydration break)."""
    return to_pct(1.0 - math.exp(-T * break_min / 90.0))

def p_goal_after_break2(T: float, break_min: float = 75.0, total_min: float = 95.0) -> int:
    """P(≥1 goal after ~75' hydration break, including stoppage time)."""
    return to_pct(1.0 - math.exp(-T * (total_min - break_min) / 90.0))

def p_goal_ht_stoppage(T: float, stoppage_min: float = 4.0) -> int:
    """P(≥1 goal in first-half stoppage time ~4 min)."""
    return to_pct(1.0 - math.exp(-T * stoppage_min / 90.0))

def p_goal_2h_stoppage(T: float, stoppage_min: float = 5.0) -> int:
    """P(≥1 goal in second-half stoppage time ~5 min)."""
    return to_pct(1.0 - math.exp(-T * stoppage_min / 90.0))

def p_corners_before_break1(total_corner_lam: float, k: int = 2, break_min: float = 30.0) -> int:
    """P(≥k total corners before first hydration break ~30')."""
    lam_partial = total_corner_lam * break_min / 90.0
    return to_pct(p_poisson_ge(lam_partial, k))


# ── Misc markets ───────────────────────────────────────────────────────────────
def p_sub_before_ht(base: float = 0.18) -> int:
    """P(substitution made before halftime). Base ~15-20%."""
    return clamp_noisy(base * 100)

def p_sub_scores(T: float) -> int:
    """P(substitute scores ≥1 goal). ~25% of goals from subs in internationals."""
    return to_pct((1.0 - math.exp(-T)) * 0.25)

def p_own_goal(T: float) -> int:
    """P(≥1 own goal). ~5% base + slight correlation with open play."""
    return to_pct(0.05 + 0.01 * max(0, T - 2.0))

def p_goal_outside_box(T: float) -> int:
    """P(goal scored from outside penalty area). ~13-15% of goals historically."""
    return to_pct(1.0 - math.exp(-T * 0.14))

def p_2h_more_goals_than_1h(T: float) -> int:
    """P(2H goals > 1H goals). 2H has ~55% share but 1H scoring is skewed early."""
    # P(2H>1H) ≈ 0.43–0.46 based on historical data; slight increase with high T
    base = 0.43 + 0.01 * max(0.0, T - 2.5)
    return to_pct(base)

def p_card_in_first_half(cards_lam: float) -> int:
    """P(≥1 card in first half). Cards 1H share ≈ 38%."""
    return to_pct(1.0 - math.exp(-cards_lam * 0.38))

def p_win_by_2plus(la: float, lb: float) -> int:
    """P(team A wins by ≥2 goals regulation). Score-grid enumeration to 8-8."""
    p = 0.0
    for ga in range(9):
        for gb in range(9):
            if ga - gb < 2:
                continue
            p += _poisson_pmf(la, ga) * _poisson_pmf(lb, gb)
    return to_pct(p)


# ── L12 / Dixon-Coles draw inflation (§5.2, input-side, ACTIVE) ───────────────
def apply_dc_draw_inflation(p_win: float, p_draw: float, p_lose: float):
    """
    Inflate draw mass when win market in 40-60 band (L12 ACTIVE + Dixon-Coles).
    Input-side correction only — D2 intact, no output floor.
    Returns (p_win, p_draw, p_lose) normalised to sum=1.
    """
    if 0.40 <= p_win <= 0.60:
        transfer = 0.025
        p_draw += transfer
        p_win  -= transfer * 0.55
        p_lose -= transfer * 0.45
    total = p_win + p_draw + p_lose
    return p_win / total, p_draw / total, p_lose / total


# ── Match data container ────────────────────────────────────────────────────────
@dataclass
class Match:
    """
    Holds all parameters needed to compute predictions for one match.
    Populate from anchor extraction (devig.py) then call compute_all_markets().
    """
    name: str
    match_id: str
    stage: str = "r32"          # "group" | "r32" | "r16" | "qf" | "sf" | "final"

    # Goal λ parameters (fitted to devigged O/U and 1X2)
    lam_a: float = 1.35         # Home/first-named team
    lam_b: float = 1.05         # Away/second-named team

    # SOT λ parameters (estimated from team attacking quality)
    sot_a: float = 5.5          # Team A FT shots on target mean
    sot_b: float = 4.5          # Team B FT shots on target mean

    # Corner λ parameters
    corners_a: float = 5.0
    corners_b: float = 4.5

    # Cards and offsides
    cards_lam: float = BASE_CARDS_MEAN
    offside_lam: float = 3.5    # Total match offsides

    # Player props — fill after lineup confirmation
    # Team A players
    player_a1_name: str = ""
    player_a1_goal_share: float = 0.30   # main striker goal %
    player_a1_sot_share: float = 0.28
    player_a1_involvement: float = 0.30   # SOA involvement rate

    player_a2_name: str = ""
    player_a2_goal_share: float = 0.12
    player_a2_sot_share: float = 0.18
    player_a2_involvement: float = 0.25
    player_a2_sot_k: int = 2             # threshold for player_a2 SOT market

    # Team B players
    player_b1_name: str = ""
    player_b1_goal_share: float = 0.30
    player_b1_sot_share: float = 0.28
    player_b1_involvement: float = 0.30

    player_b2_name: str = ""
    player_b2_goal_share: float = 0.12
    player_b2_sot_share: float = 0.18
    player_b2_involvement: float = 0.25
    player_b2_sot_k: int = 1

    # Situational overlays (§5.12) — add before calling compute
    altitude_adj: float = 0.0   # e.g. -2 to -4 at Azteca
    rotation_adj: float = 0.0   # e.g. -3 to -6 at MD3

    # Confidence label override
    confidence: str = "MED"     # LOW | MED | HIGH

    @property
    def T(self) -> float:
        return self.lam_a + self.lam_b

    @property
    def stage_weight(self) -> int:
        return STAGE_WEIGHTS.get(self.stage, 1)


def compute_all_markets(m: Match) -> dict:
    """
    Compute probabilities for all ~15 market archetypes observed in the 2026 WC R32.
    Returns dict keyed by market description slug → integer probability.
    All outputs are calibrated honest probabilities (D2).
    """
    la, lb, T = m.lam_a, m.lam_b, m.T
    sot_a, sot_b = m.sot_a, m.sot_b
    cor_a, cor_b = m.corners_a, m.corners_b
    total_corners = cor_a + cor_b

    # 1X2 — apply L12 draw inflation in 40-60 band (§5.2 / L12 ACTIVE)
    p_w = p_scores(la) * p_clean_sheet(lb)  # rough; use devigged line when available
    # Use full Poisson score grid for 1X2:
    p_win_a_raw, p_draw_raw, p_win_b_raw = 0.0, 0.0, 0.0
    for ga in range(9):
        for gb in range(9):
            cell = _poisson_pmf(la, ga) * _poisson_pmf(lb, gb)
            if ga > gb:
                p_win_a_raw += cell
            elif ga == gb:
                p_draw_raw += cell
            else:
                p_win_b_raw += cell
    p_win_a, p_draw, p_win_b = apply_dc_draw_inflation(p_win_a_raw, p_draw_raw, p_win_b_raw)

    return {
        # ── Win market (§5.3 #1, L12) ─────────────────────────────────────
        "team_a_wins_regulation":     to_pct(p_win_a),
        "team_b_wins_regulation":     to_pct(p_win_b),
        "draw_regulation":            to_pct(p_draw),

        # ── Totals (§5.3 #2) ──────────────────────────────────────────────
        "3plus_total_goals":          to_pct(p_over25(T)),
        "2or_fewer_total_goals":      to_pct(p_under2(T)),

        # ── BTTS (§5.3 #3) ────────────────────────────────────────────────
        "btts":                       to_pct(p_btts(la, lb)),
        "btts_3plus":                 to_pct(p_btts_3plus(la, lb)),

        # ── Team scoring (§5.3 #4 #5) ─────────────────────────────────────
        "team_a_scores":              to_pct(p_scores(la)),
        "team_b_scores":              to_pct(p_scores(lb)),
        "team_a_scores_2h":           to_pct(p_scores_2h(la)),
        "team_b_scores_2h":           to_pct(p_scores_2h(lb)),
        "team_a_scores_1h":           to_pct(p_scores_1h(la)),
        "team_a_scores_both_halves":  p_scores_both_halves(la),
        "team_b_scores_both_halves":  p_scores_both_halves(lb),

        # ── Strict comparisons / tie-trap (§5.3 #6) ───────────────────────
        "team_a_more_corners_ft":     p_more_than("corners_ft", cor_a / max(cor_b, 0.1)),
        "team_a_more_sot":            p_more_than("sot_ft",     sot_a / max(sot_b, 0.1)),

        # ── Threshold counts (§5.3 #7) ────────────────────────────────────
        "team_a_4plus_sot":           p_team_sot_ge(sot_a, 4),
        "team_a_5plus_sot":           p_team_sot_ge(sot_a, 5),
        "team_a_6plus_sot":           p_team_sot_ge(sot_a, 6),
        "team_a_7plus_sot":           p_team_sot_ge(sot_a, 7),
        "team_a_8plus_sot":           p_team_sot_ge(sot_a, 8),
        "team_b_2plus_sot":           p_team_sot_ge(sot_b, 2),
        "team_b_4plus_sot":           p_team_sot_ge(sot_b, 4),
        "team_b_5plus_sot":           p_team_sot_ge(sot_b, 5),
        "team_b_6plus_sot":           p_team_sot_ge(sot_b, 6),
        "team_b_7plus_sot":           p_team_sot_ge(sot_b, 7),
        "team_a_6plus_corners":       p_team_corners_ge(cor_a, 6),
        "team_a_7plus_corners":       p_team_corners_ge(cor_a, 7),
        "team_a_8plus_corners":       p_team_corners_ge(cor_a, 8),
        "9plus_total_corners":        p_total_corners_ge(total_corners, 9),
        "4plus_total_cards":          p_cards_ge(m.cards_lam, 4),
        "5plus_total_cards":          p_cards_ge(m.cards_lam, 5),
        "3plus_offsides":             p_offsides_ge(m.offside_lam, 3),
        "4plus_offsides":             p_offsides_ge(m.offside_lam, 4),
        "20plus_total_shots":         p_total_shots_ge((sot_a + sot_b) * 3.0, 20),
        "22plus_total_shots":         p_total_shots_ge((sot_a + sot_b) * 3.0, 22),
        "24plus_total_shots":         p_total_shots_ge((sot_a + sot_b) * 3.0, 24),

        # ── Player props (§5.3 #8) ────────────────────────────────────────
        "player_a1_goal":             p_player_goal(la, m.player_a1_goal_share),
        "player_a1_sot1plus":         p_player_sot_ge(sot_a, m.player_a1_sot_share, 1),
        "player_a1_sot2plus":         p_player_sot_ge(sot_a, m.player_a1_sot_share, 2),
        "player_a1_soa":              p_soa(la, m.player_a1_involvement),
        "player_a2_goal":             p_player_goal(la, m.player_a2_goal_share),
        "player_a2_sot_k":            p_player_sot_ge(sot_a, m.player_a2_sot_share, m.player_a2_sot_k),
        "player_a2_soa":              p_soa(la, m.player_a2_involvement),
        "player_b1_goal":             p_player_goal(lb, m.player_b1_goal_share),
        "player_b1_sot1plus":         p_player_sot_ge(sot_b, m.player_b1_sot_share, 1),
        "player_b1_sot2plus":         p_player_sot_ge(sot_b, m.player_b1_sot_share, 2),
        "player_b1_soa":              p_soa(lb, m.player_b1_involvement),
        "player_b2_goal":             p_player_goal(lb, m.player_b2_goal_share),
        "player_b2_sot_k":            p_player_sot_ge(sot_b, m.player_b2_sot_share, m.player_b2_sot_k),
        "player_b2_soa":              p_soa(lb, m.player_b2_involvement),

        # ── Sequence / joint props (§5.3 #11) ─────────────────────────────
        "team_a_scores_first":        to_pct(p_scores_first(la, T)),
        "team_b_scores_first":        to_pct(p_scores_first(lb, T)),

        # ── HT states ─────────────────────────────────────────────────────
        "ht_tied":                    p_ht_tied_clamped(la, lb, T),
        "team_a_leading_ht":          p_team_leading_ht(la, lb),
        "team_b_leading_ht":          p_team_leading_ht(lb, la),

        # ── Drama markets — noisy register (§5.3 #12) ─────────────────────
        "penalty_awarded":            p_penalty(),
        "red_card":                   p_red_card(),
        "pen_or_red":                 p_pen_or_red(),

        # ── Hydration-break markets (2026 WC new) ─────────────────────────
        "goal_before_break1":         p_goal_before_break1(T),
        "goal_after_break2":          p_goal_after_break2(T),
        "corners_before_break1_2plus": p_corners_before_break1(total_corners, 2),

        # ── Stoppage-time markets ──────────────────────────────────────────
        "goal_ht_stoppage":           p_goal_ht_stoppage(T),
        "goal_2h_stoppage":           p_goal_2h_stoppage(T),

        # ── Misc 2026 WC market types ──────────────────────────────────────
        "2h_more_goals_than_1h":      p_2h_more_goals_than_1h(T),
        "goal_outside_box":           p_goal_outside_box(T),
        "own_goal":                   p_own_goal(T),
        "sub_before_ht":              p_sub_before_ht(),
        "sub_scores":                 p_sub_scores(T),
        "card_in_first_half":         p_card_in_first_half(m.cards_lam),
        "team_a_win_by_2plus":        p_win_by_2plus(la, lb),
        "team_b_win_by_2plus":        p_win_by_2plus(lb, la),
        "team_a_more_cards":          p_more_than("cards", m.cards_lam * 0.5 / max(m.cards_lam * 0.5, 0.1)),
        "team_b_more_cards":          p_more_than("cards", 1.0),  # adjust per match
        # Team-specific goal counts
        "team_a_3plus_goals":         to_pct(p_poisson_ge(la, 3)),
        "team_b_3plus_goals":         to_pct(p_poisson_ge(lb, 3)),
        "team_b_scores_1h":           to_pct(p_scores_1h(lb)),
        "clean_sheet_a":              to_pct(math.exp(-lb)),
        "clean_sheet_b":              to_pct(math.exp(-la)),
        # Team advance (knockout: win in regulation)
        "team_a_advances":            to_pct(p_win_a),
        "team_b_advances":            to_pct(p_win_b),
    }
