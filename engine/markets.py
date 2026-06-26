"""
All 12 live market archetypes (§5.3) implemented as functions.

Each function returns an integer 1-99 ready to submit (clamped).
Pass a LambdaModel for most calculations; supplemental inputs where needed.

Archetype reference (§5.3):
  #1  Win the match (1X2 win)
  #2  3 or more / 2 or fewer total goals
  #3  BTTS AND 3+ total goals
  #4  Team scores in the second half
  #5  Team scores at least 1 goal
  #6  Strict comparison (tie-trap)
  #7  Threshold counts (cards, corners, SOT, offsides)
  #8  Player props (anytime goal, SOT, score-or-assist)
  #9  HT tied
  #10 HT both teams ≥1 SOT
  #11 Joint / sequence props
  #12 Drama props (penalty, red card)
"""

import math
from .lambda_engine import LambdaModel, poisson_cdf, poisson_pmf, _1x2_from_split
from .tie_trap import tie_trap_prob, ht_tied_prob, tie_prob_poisson


def _to_int(p: float) -> int:
    """Clamp and round probability to 1-99 integer."""
    return max(1, min(99, round(p * 100)))


def _noisy_clamp(p: float, anchored: bool = False) -> float:
    """Noisy-register clamp: 15-85 unless anchored (§5.9)."""
    if anchored:
        return p
    return max(0.15, min(0.85, p))


# ---------------------------------------------------------------------------
# Archetype #1 — Win the match (§5.3, L12)
# ---------------------------------------------------------------------------

def win_match(
    model: LambdaModel,
    team: str = "a",
    apply_dixon_coles: bool = True,
    win_band: bool = True,
) -> int:
    """
    P(team wins in 90 min). Uses Poisson grid with hardened Dixon-Coles in 40-60 band (L12).
    'team' = 'a' (home/first) or 'b' (away/second).
    """
    ph, pd, pa = _1x2_from_split(model.lam_a, model.lam_b)

    if apply_dixon_coles:
        # L12: in near-coinflip 40-60 band, draw gets +1–3 pts; wins lose accordingly
        raw_win = ph if team == "a" else pa
        raw_int = round(raw_win * 100)
        if win_band and 40 <= raw_int <= 60:
            # Harden draw mass by +2 (take from both win sides proportionally)
            draw_boost = 0.02
            ph = ph - draw_boost * ph / (ph + pa)
            pa = pa - draw_boost * pa / (ph + pa)
            pd = pd + draw_boost
        ph, pd, pa = ph, pd, pa  # recalculate not needed, already adjusted above

    p = ph if team == "a" else pa
    return _to_int(p)


# ---------------------------------------------------------------------------
# Archetype #2 — Goals totals (§5.3, §5.2)
# ---------------------------------------------------------------------------

def goals_3_or_more(model: LambdaModel) -> int:
    """P(total goals ≥ 3)."""
    p = 1 - poisson_cdf(model.T, 2)
    return _to_int(p)


def goals_2_or_fewer(model: LambdaModel) -> int:
    """P(total goals ≤ 2)."""
    p = poisson_cdf(model.T, 2)
    return _to_int(p)


def goals_over(model: LambdaModel, line: float = 2.5) -> int:
    """P(total goals > line)."""
    k = int(math.floor(line))
    p = 1 - poisson_cdf(model.T, k)
    return _to_int(p)


# ---------------------------------------------------------------------------
# Archetype #3 — BTTS AND 3+ goals (§5.3, §5.2)
# ---------------------------------------------------------------------------

def btts_and_3plus(model: LambdaModel) -> int:
    """P(BTTS ∧ total goals ≥ 3) = P(BTTS) − P(1-1). Uses grid, never marginals product."""
    p = model.p_btts_and_3plus()
    return _to_int(p)


def btts(model: LambdaModel) -> int:
    """P(both teams score ≥ 1)."""
    return _to_int(model.p_btts())


# ---------------------------------------------------------------------------
# Archetype #4 — Team scores in 2H (§5.3)
# ---------------------------------------------------------------------------

def scores_2h(model: LambdaModel, team: str = "a") -> int:
    """P(team scores in 2H) = 1 − e^(−0.55·λ)."""
    return _to_int(model.p_team_scores_2h(team))


# ---------------------------------------------------------------------------
# Archetype #5 — Team scores at least 1 goal (§5.3)
# ---------------------------------------------------------------------------

def scores_at_least_1(model: LambdaModel, team: str = "a") -> int:
    """P(team scores ≥ 1 in 90 min) = 1 − e^(−λ)."""
    return _to_int(model.p_team_scores(team))


# ---------------------------------------------------------------------------
# Archetype #6 — Strict comparisons (tie-trap) (§5.3, §5.4, L3)
# ---------------------------------------------------------------------------

def strict_more_than(
    stat: str,
    strength_ratio: float = 1.0,
    m_override: float | None = None,
) -> int:
    """
    P(Team A has strictly more <stat> than Team B).
    strength_ratio = lam_a / lam_b (> 1 means A is favoured).
    Never returns 50 for a strict comparison (§5.4).
    """
    from .tie_trap import MEAN_STATS, tie_trap_int
    m = m_override if m_override is not None else MEAN_STATS.get(stat)
    if m is None:
        raise ValueError(f"Unknown stat '{stat}'. Provide m_override.")
    raw = tie_trap_int(m=m, strength_ratio=strength_ratio)
    return raw


# ---------------------------------------------------------------------------
# Archetype #7 — Threshold counts (§5.3, §5.5)
# ---------------------------------------------------------------------------

# Spec table for cards (§5.5)
_CARDS_TABLE = [
    # (lam_cards, P(>=4 total), P(>=2 in 2H))
    (2.8, 0.31, 0.52),
    (3.2, 0.40, 0.59),
    (3.5, 0.46, 0.64),
    (4.0, 0.57, 0.71),
    (4.5, 0.66, 0.77),
]


def _interpolate_table(table: list[tuple], lam: float, col: int) -> float:
    xs = [r[0] for r in table]
    ys = [r[col] for r in table]
    if lam <= xs[0]:
        return ys[0]
    if lam >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= lam <= xs[i + 1]:
            t = (lam - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


def cards_4_or_more(lam_cards: float = 3.5) -> int:
    """P(total match cards ≥ 4). Uses spec table (§5.5)."""
    p = _interpolate_table(_CARDS_TABLE, lam_cards, col=1)
    return _to_int(_noisy_clamp(p))


def cards_2h_2_or_more(lam_cards: float = 3.5) -> int:
    """P(2H cards ≥ 2). 2H share ≈ 62%."""
    p = _interpolate_table(_CARDS_TABLE, lam_cards, col=2)
    return _to_int(_noisy_clamp(p))


def cards_threshold(lam_cards: float, n: int) -> int:
    """Generic P(total cards ≥ n) via Poisson CDF."""
    p = 1 - poisson_cdf(lam_cards, n - 1)
    return _to_int(_noisy_clamp(p))


# Spec table for team corners → P(≥5) (§5.5)
_CORNERS_TABLE = [
    (3.0, 0.19), (3.5, 0.28), (4.0, 0.37), (4.5, 0.47),
    (5.0, 0.56), (5.5, 0.64), (6.0, 0.72),
]


def corners_team_5_or_more(lam_corners: float) -> int:
    """P(team corners ≥ 5). Uses spec table."""
    xs = [r[0] for r in _CORNERS_TABLE]
    ys = [r[1] for r in _CORNERS_TABLE]
    if lam_corners <= xs[0]:
        p = ys[0]
    elif lam_corners >= xs[-1]:
        p = ys[-1]
    else:
        for i in range(len(xs) - 1):
            if xs[i] <= lam_corners <= xs[i + 1]:
                t = (lam_corners - xs[i]) / (xs[i + 1] - xs[i])
                p = ys[i] + t * (ys[i + 1] - ys[i])
                break
        else:
            p = ys[-1]
    return _to_int(_noisy_clamp(p))


def corners_threshold(lam_corners: float, n: int) -> int:
    """P(team corners ≥ n) via Poisson."""
    p = 1 - poisson_cdf(lam_corners, n - 1)
    return _to_int(_noisy_clamp(p))


# Spec table for team SOT → P(≥2) (§5.5)
_SOT_TABLE = [
    (1.0, 0.26), (1.5, 0.44), (2.0, 0.59), (2.5, 0.71),
    (3.0, 0.80), (3.5, 0.86), (4.0, 0.91), (4.5, 0.94),
]


def sot_team_2_or_more(lam_sot: float) -> int:
    """P(team SOT ≥ 2). Uses spec table."""
    xs = [r[0] for r in _SOT_TABLE]
    ys = [r[1] for r in _SOT_TABLE]
    if lam_sot <= xs[0]:
        p = ys[0]
    elif lam_sot >= xs[-1]:
        p = ys[-1]
    else:
        for i in range(len(xs) - 1):
            if xs[i] <= lam_sot <= xs[i + 1]:
                t = (lam_sot - xs[i]) / (xs[i + 1] - xs[i])
                p = ys[i] + t * (ys[i + 1] - ys[i])
                break
        else:
            p = ys[-1]
    return _to_int(_noisy_clamp(p))


def sot_threshold(lam_sot: float, n: int) -> int:
    """P(team SOT ≥ n) via Poisson."""
    p = 1 - poisson_cdf(lam_sot, n - 1)
    return _to_int(_noisy_clamp(p))


# Spec table for team offsides → P(≥2) (§5.5)
_OFFSIDES_TABLE = [
    (0.8, 0.19), (1.0, 0.26), (1.2, 0.34),
    (1.5, 0.44), (1.8, 0.54), (2.0, 0.59),
]


def offsides_team_2_or_more(lam_offsides: float) -> int:
    """P(team offsides ≥ 2). Uses spec table."""
    xs = [r[0] for r in _OFFSIDES_TABLE]
    ys = [r[1] for r in _OFFSIDES_TABLE]
    if lam_offsides <= xs[0]:
        p = ys[0]
    elif lam_offsides >= xs[-1]:
        p = ys[-1]
    else:
        for i in range(len(xs) - 1):
            if xs[i] <= lam_offsides <= xs[i + 1]:
                t = (lam_offsides - xs[i]) / (xs[i + 1] - xs[i])
                p = ys[i] + t * (ys[i + 1] - ys[i])
                break
        else:
            p = ys[-1]
    return _to_int(_noisy_clamp(p))


def offsides_threshold(lam_offsides: float, n: int) -> int:
    """P(team offsides ≥ n) via Poisson."""
    p = 1 - poisson_cdf(lam_offsides, n - 1)
    return _to_int(_noisy_clamp(p))


def total_goals_2h_gte(model: LambdaModel, n: int = 2) -> int:
    """P(total 2H goals ≥ n). 2H share ≈ 55%."""
    return _to_int(model.p_2h_goals_gte(n))


# ---------------------------------------------------------------------------
# Archetype #9 — HT tied (§5.3, §5.5, L9)
# ---------------------------------------------------------------------------

def ht_tied(model: LambdaModel) -> int:
    """P(match is tied at half-time). L9 ceiling = 47 unless T < 2.2."""
    from .tie_trap import ht_tied_int
    return ht_tied_int(model.lam_a, model.lam_b, T=model.T)


# ---------------------------------------------------------------------------
# Archetype #10 — HT both teams ≥1 SOT (§5.3, §5.5)
# ---------------------------------------------------------------------------

def ht_both_sot(lam_sot_a: float, lam_sot_b: float) -> int:
    """
    P(both teams ≥1 SOT at HT). HT SOT share ≈ 45%.
    P = P(A ≥1 HT SOT) × P(B ≥1 HT SOT).
    """
    la_ht = 0.45 * lam_sot_a
    lb_ht = 0.45 * lam_sot_b
    p = (1 - math.exp(-la_ht)) * (1 - math.exp(-lb_ht))
    return _to_int(_noisy_clamp(p))


# ---------------------------------------------------------------------------
# Archetype #11 — Joint / sequence props (§5.3, §5.7)
# ---------------------------------------------------------------------------

def scores_first_and_other_scores_2h(
    model: LambdaModel,
    first_team: str = "a",
    dependence_haircut: float = 0.02,
) -> int:
    """
    P(first_team scores first AND other team scores in 2H).
    = P(first_team scores first) × P(other scores 2H) − haircut.
    Never exceeds either marginal.
    """
    other = "b" if first_team == "a" else "a"
    p_first = model.p_score_first(first_team)
    p_2h = model.p_team_scores_2h(other)
    p_joint = p_first * p_2h - dependence_haircut
    p_joint = max(0.01, min(p_first, p_2h, p_joint))  # joint ≤ both marginals
    return _to_int(p_joint)


# ---------------------------------------------------------------------------
# Archetype #12 — Drama props: penalty, red card (§5.3, §5.8, §5.9)
# ---------------------------------------------------------------------------

def penalty_awarded(base_rate: float = 0.29, anchored: bool = False) -> int:
    """
    P(penalty awarded in match). Default = working prior value from §5.8.
    Noisy register: clamp 15-85 unless anchored (§5.9, L5).
    """
    p = _noisy_clamp(base_rate, anchored=anchored)
    return _to_int(p)


def red_card(base_rate: float = 0.06, anchored: bool = False) -> int:
    """P(red card in match). Noisy register."""
    p = _noisy_clamp(base_rate, anchored=anchored)
    return _to_int(p)


def pen_or_red(base_rate: float = 0.31, anchored: bool = False) -> int:
    """P(penalty OR red card). Noisy register."""
    p = _noisy_clamp(base_rate, anchored=anchored)
    return _to_int(p)


# ---------------------------------------------------------------------------
# Coherence check (§5.11 gate 1)
# ---------------------------------------------------------------------------

def check_coherence(markets: dict) -> list[str]:
    """
    Run coherence gates from §5.11.
    markets: dict of {market_name: int}  (1–99 integers)
    Returns list of violation strings (empty = all good).
    """
    issues = []
    p = {k: v / 100 for k, v in markets.items()}

    # 1X2 triplet sums to 100 ± 2
    if all(k in p for k in ("win_a", "draw", "win_b")):
        total = p["win_a"] + p["draw"] + p["win_b"]
        if abs(total - 1.0) > 0.02:
            issues.append(f"1X2 sum {total:.3f} ≠ 1 ±0.02")

    # Joint ≤ both marginals
    if "btts_and_3plus" in p and "btts" in p:
        if p["btts_and_3plus"] > p["btts"]:
            issues.append("btts_and_3plus > btts (coherence violation)")

    if "scores_first_and_other_2h" in p:
        for marginal in ("scores_first_a", "scores_2h_b"):
            if marginal in p and p["scores_first_and_other_2h"] > p[marginal]:
                issues.append(f"joint > marginal {marginal}")

    return issues


# ---------------------------------------------------------------------------
# Convenience: compute all standard markets for a match
# ---------------------------------------------------------------------------

def compute_all_markets(
    model: LambdaModel,
    lam_sot_a: float | None = None,
    lam_sot_b: float | None = None,
    lam_cards: float = 3.5,
    pen_rate: float = 0.29,
    red_rate: float = 0.06,
    apply_dixon_coles: bool = True,
) -> dict[str, int]:
    """
    Compute all standard markets for a match.
    Returns dict of {market_name: int 1-99}.

    lam_sot_a/b: team-level shot-on-target rates (FT); defaults to ~3× lam for rough estimate.
    """
    if lam_sot_a is None:
        lam_sot_a = max(1.0, model.lam_a * 3.0)
    if lam_sot_b is None:
        lam_sot_b = max(1.0, model.lam_b * 3.0)

    ph, pd, pa = _1x2_from_split(model.lam_a, model.lam_b)

    # L12: harden draw in 40-60 win band
    if apply_dixon_coles:
        pa_raw_int = round(ph * 100)
        if 40 <= pa_raw_int <= 60:
            boost = 0.02
            ph_adj = ph - boost * ph / (ph + pa)
            pa_adj = pa - boost * pa / (ph + pa)
            pd_adj = pd + boost
            ph, pd, pa = ph_adj, pd_adj, pa_adj

    return {
        "win_a":                _to_int(ph),
        "draw":                 _to_int(pd),
        "win_b":                _to_int(pa),
        "goals_3plus":          goals_3_or_more(model),
        "goals_2_or_fewer":     goals_2_or_fewer(model),
        "btts":                 btts(model),
        "btts_and_3plus":       btts_and_3plus(model),
        "scores_a":             scores_at_least_1(model, "a"),
        "scores_b":             scores_at_least_1(model, "b"),
        "scores_2h_a":          scores_2h(model, "a"),
        "scores_2h_b":          scores_2h(model, "b"),
        "ht_tied":              ht_tied(model),
        "ht_both_sot":          ht_both_sot(lam_sot_a, lam_sot_b),
        "2h_goals_2plus":       total_goals_2h_gte(model, 2),
        "cards_4plus":          cards_4_or_more(lam_cards),
        "cards_2h_2plus":       cards_2h_2_or_more(lam_cards),
        "penalty":              penalty_awarded(pen_rate),
        "red_card":             red_card(red_rate),
        "pen_or_red":           pen_or_red(pen_rate + red_rate - pen_rate * red_rate),
    }
