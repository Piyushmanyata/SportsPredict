"""
SportsPredict Probability Engine v3
Implements §5 of the Jump Trading Probability Cup system instructions v8.

All 12 live market archetypes, λ-engine, tie-trap, L8 batch MC, coherence gates.
"""

from __future__ import annotations
import math
import numpy as np
from scipy.optimize import root_scalar
from scipy.special import i0 as scipy_i0


# ─── §5.1  Anchor extraction / devig ─────────────────────────────────────────

def power_devig(implied: list[float]) -> list[float]:
    """
    Power devig: solve k s.t. Σ imp_i^k = 1.
    Mandatory when overround >5% AND favourite implied >65% (§5.1).
    Falls back to multiplicative on solver failure.
    """
    def f(k):
        return sum(p ** k for p in implied) - 1
    try:
        k = root_scalar(f, bracket=[0.5, 2.0]).root
        return [p ** k for p in implied]
    except Exception:
        total = sum(implied)
        return [p / total for p in implied]


def devig_3way(p_home: float, p_draw: float, p_away: float) -> tuple[float, float, float]:
    """
    Devig a 1X2 market.
    Uses power devig when overround > 5% AND favourite > 65%; else multiplicative.
    Returns (p_win_a, p_draw, p_win_b) summing to 1.0.
    """
    implied = [p_home, p_draw, p_away]
    overround = sum(implied) - 1.0
    fav = max(implied)
    if overround > 0.05 and fav > 0.65:
        result = power_devig(implied)
    else:
        total = sum(implied)
        result = [p / total for p in implied]
    return tuple(result)  # type: ignore[return-value]


def devig_2way(p_yes: float, p_no: float) -> tuple[float, float]:
    """Simple 2-way multiplicative devig."""
    total = p_yes + p_no
    return p_yes / total, p_no / total


# ─── §5.2  λ-engine ──────────────────────────────────────────────────────────

_OU25_TABLE = [
    (0.32, 2.0), (0.38, 2.2), (0.46, 2.5),
    (0.51, 2.7), (0.58, 3.0), (0.64, 3.3),
]


def ou25_to_T(p_over: float) -> float:
    """
    Convert P(over 2.5 goals) → expected total goals T via §5.2 table.
    Linear interpolation between table rows.
    """
    if p_over <= _OU25_TABLE[0][0]:
        return _OU25_TABLE[0][1]
    if p_over >= _OU25_TABLE[-1][0]:
        return _OU25_TABLE[-1][1]
    for i in range(len(_OU25_TABLE) - 1):
        p0, t0 = _OU25_TABLE[i]
        p1, t1 = _OU25_TABLE[i + 1]
        if p0 <= p_over <= p1:
            frac = (p_over - p0) / (p1 - p0)
            return t0 + frac * (t1 - t0)
    return 2.5


def poisson_pmf(lam: float, k: int) -> float:
    """P(X = k) for Poisson(lam)."""
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def poisson_cdf(lam: float, k: int) -> float:
    """P(X ≤ k) for Poisson(lam)."""
    return sum(poisson_pmf(lam, i) for i in range(k + 1))


def poisson_tail(lam: float, k: int) -> float:
    """P(X ≥ k) for Poisson(lam)."""
    return 1.0 - poisson_cdf(lam, k - 1)


def poisson_1x2(la: float, lb: float, max_goals: int = 10) -> tuple[float, float, float]:
    """Compute P(A wins), P(Draw), P(B wins) from Poisson(la) × Poisson(lb)."""
    p_a_wins = p_draw = p_b_wins = 0.0
    for a in range(max_goals + 1):
        pa = poisson_pmf(la, a)
        for b in range(max_goals + 1):
            p = pa * poisson_pmf(lb, b)
            if a > b:
                p_a_wins += p
            elif a == b:
                p_draw += p
            else:
                p_b_wins += p
    return p_a_wins, p_draw, p_b_wins


def fit_lambda_split(T: float, p_win_a: float, p_draw: float,
                     p_win_b: float) -> tuple[float, float]:
    """
    Find (λ_A, λ_B) with λ_A + λ_B = T reproducing the devigged 1X2 within ±2pp.
    Grid search over fractions [0.30, 0.70] in steps of 0.01.
    """
    best_la, best_err = T / 2.0, float('inf')
    for frac in (i / 100 for i in range(30, 71)):
        la = T * frac
        lb = T - la
        p_a, p_d, p_b = poisson_1x2(la, lb)
        err = abs(p_a - p_win_a) + abs(p_d - p_draw) + abs(p_b - p_win_b)
        if err < best_err:
            best_err = err
            best_la = la
    return best_la, T - best_la


# ─── §5.2  Core market formulas ───────────────────────────────────────────────

def market_scores_gte1(lam: float) -> float:
    """P(team scores ≥1 goal) = 1 − e^(−λ). Archetype #5."""
    return 1.0 - math.exp(-lam)


def market_scores_2h(lam: float) -> float:
    """P(team scores in 2H) = 1 − e^(−0.55λ). Archetype #4."""
    return 1.0 - math.exp(-0.55 * lam)


def market_scores_1h(lam: float) -> float:
    """P(team scores in 1H) = 1 − e^(−0.45λ)."""
    return 1.0 - math.exp(-0.45 * lam)


def market_btts(la: float, lb: float) -> float:
    """P(BTTS) = (1 − e^(−λA))(1 − e^(−λB))."""
    return (1.0 - math.exp(-la)) * (1.0 - math.exp(-lb))


def market_p11(la: float, lb: float) -> float:
    """P(1-1) = λA · λB · e^(−T)."""
    return la * lb * math.exp(-(la + lb))


def market_btts_3plus(la: float, lb: float) -> float:
    """P(BTTS ∧ 3+ goals) = P(BTTS) − P(1-1). Never multiply marginals. Archetype #3."""
    return market_btts(la, lb) - market_p11(la, lb)


def market_totals(T: float, threshold: float = 2.5) -> dict[str, float]:
    """
    P(over/under threshold total goals) via Poisson(T).
    e.g. threshold=2.5 → P(≤2) and P(≥3).
    """
    k = math.floor(threshold)
    p_under = poisson_cdf(T, k)
    return {'over': 1.0 - p_under, 'under': p_under}


def market_clean_sheet(lam_opponent: float) -> float:
    """P(clean sheet for A) = e^(−λ_B)."""
    return math.exp(-lam_opponent)


def p_scores_first(la: float, T: float) -> float:
    """P(team A scores first) ≈ (λA/T) · (1 − e^(−T))."""
    if T <= 0:
        return 0.0
    return (la / T) * (1.0 - math.exp(-T))


# ─── §5.4  Tie-trap engine ────────────────────────────────────────────────────

def _bessel_i0(x: float) -> float:
    """Modified Bessel function I₀(x) via scipy."""
    return float(scipy_i0(x))


def poisson_tie_mass_symmetric(m: float) -> float:
    """P(tie) for two independent Poisson(m): e^(−2m) · I₀(2m)."""
    return math.exp(-2 * m) * _bessel_i0(2 * m)


def poisson_tie_exact(m_a: float, m_b: float, max_k: int = 40) -> float:
    """P(X_a = X_b) for independent Poisson(m_a), Poisson(m_b)."""
    return sum(poisson_pmf(m_a, k) * poisson_pmf(m_b, k) for k in range(max_k + 1))


def p_a_strictly_more(m_a: float, m_b: float, max_k: int = 40) -> float:
    """P(X_a > X_b) for independent Poisson(m_a), Poisson(m_b)."""
    p = 0.0
    for a in range(1, max_k + 1):
        pa = poisson_pmf(m_a, a)
        for b in range(a):
            p += pa * poisson_pmf(m_b, b)
    return p


# §5.4 exact table — (per-team mean m, P_tie, P_even "A more")
TIE_TRAP_TABLE: dict[str, dict] = {
    'fouls':       {'m': 11.0, 'p_tie': 0.086, 'p_even': 0.46},
    'corners_ft':  {'m': 4.5,  'p_tie': 0.135, 'p_even': 0.43},
    'corners_2h':  {'m': 2.4,  'p_tie': 0.188, 'p_even': 0.41},
    'corners_ht':  {'m': 2.1,  'p_tie': 0.202, 'p_even': 0.40},
    'sot_2h':      {'m': 2.0,  'p_tie': 0.207, 'p_even': 0.40},
    'cards':       {'m': 1.8,  'p_tie': 0.219, 'p_even': 0.39},
    'offsides':    {'m': 1.5,  'p_tie': 0.243, 'p_even': 0.38},
}


def tie_trap_market(stat: str, strength_ratio: float = 1.0) -> int:
    """
    P(A has MORE stat than B) for a strict comparison.
    strength_ratio = m_a / m_b  (>1 means A is dominant side).
    Returns integer 1–99.
    Always < 50 for an even matchup (never hand 50 to a strict comparison — L3).
    """
    if stat not in TIE_TRAP_TABLE:
        stat = 'fouls'  # safe fallback
    entry = TIE_TRAP_TABLE[stat]
    m = entry['m']

    if abs(strength_ratio - 1.0) < 0.15:
        p = entry['p_even']
    else:
        # Dominant side captures ~55–65% of non-tie scenarios
        total_m = 2 * m
        m_a = total_m * strength_ratio / (1 + strength_ratio)
        m_b = total_m / (1 + strength_ratio)
        p = p_a_strictly_more(m_a, m_b)

    return to_int(p)


# ─── §5.5  Threshold / state tables ─────────────────────────────────────────

_CARDS_TABLE = {
    2.8: {'ge4': 0.31, 'ge2_2h': 0.52},
    3.2: {'ge4': 0.40, 'ge2_2h': 0.59},
    3.5: {'ge4': 0.46, 'ge2_2h': 0.64},
    4.0: {'ge4': 0.57, 'ge2_2h': 0.71},
    4.5: {'ge4': 0.66, 'ge2_2h': 0.77},
}

_CORNERS_TABLE = {3.0: 0.19, 3.5: 0.28, 4.0: 0.37, 4.5: 0.47,
                  5.0: 0.56, 5.5: 0.64, 6.0: 0.72}

_SOT_TABLE = {1.0: 0.26, 1.5: 0.44, 2.0: 0.59, 2.5: 0.71,
              3.0: 0.80, 3.5: 0.86, 4.0: 0.91, 4.5: 0.94}

_OFFSIDES_TABLE = {0.8: 0.19, 1.0: 0.26, 1.2: 0.34,
                   1.5: 0.44, 1.8: 0.54, 2.0: 0.59}


def _interp(table: dict[float, float], key: float) -> float:
    """Linear interpolation in a {float: float} lookup table."""
    keys = sorted(table.keys())
    if key <= keys[0]:
        return table[keys[0]]
    if key >= keys[-1]:
        return table[keys[-1]]
    for i in range(len(keys) - 1):
        k0, k1 = keys[i], keys[i + 1]
        if k0 <= key <= k1:
            frac = (key - k0) / (k1 - k0)
            return table[k0] + frac * (table[k1] - table[k0])
    return table[keys[-1]]


def market_cards_ge4(lam_cards: float) -> float:
    """P(≥4 total cards) — §5.5 table."""
    return _interp({k: v['ge4'] for k, v in _CARDS_TABLE.items()}, lam_cards)


def market_cards_ge2_2h(lam_cards: float) -> float:
    """P(≥2 cards in 2H) — §5.5 table (2H share ≈ 0.62)."""
    return _interp({k: v['ge2_2h'] for k, v in _CARDS_TABLE.items()}, lam_cards)


def market_sot_ge2(lam_sot: float) -> float:
    """P(team ≥2 SOT) — §5.5 table."""
    return _interp(_SOT_TABLE, lam_sot)


def market_corners_ge5(lam_corners: float) -> float:
    """P(team ≥5 corners) — §5.5 table."""
    return _interp(_CORNERS_TABLE, lam_corners)


def market_offsides_ge2(lam_offsides: float) -> float:
    """P(team ≥2 offsides) — §5.5 table."""
    return _interp(_OFFSIDES_TABLE, lam_offsides)


def market_ht_tied(la: float, lb: float) -> float:
    """
    P(tied at HT) via Bessel formula (§5.5).
    HT λ shares: 0.45× each team's FT rate.
    L9: ceiling 47 unless T < 2.2.
    """
    la_ht = 0.45 * la
    lb_ht = 0.45 * lb
    T_ht = la_ht + lb_ht
    inner = 2.0 * math.sqrt(la_ht * lb_ht) if la_ht * lb_ht > 0 else 0.0
    p = math.exp(-T_ht) * _bessel_i0(inner)
    # L9 ceiling
    if (la + lb) >= 2.2:
        p = min(p, 0.47)
    return p


def market_ht_both_sot(lam_sot_a: float, lam_sot_b: float) -> float:
    """
    P(both teams ≥1 SOT at HT) = (1 − e^(−0.45·λSOT_A)) × (1 − e^(−0.45·λSOT_B)).
    HT SOT share ≈ 0.45.
    """
    return (1.0 - math.exp(-0.45 * lam_sot_a)) * (1.0 - math.exp(-0.45 * lam_sot_b))


# ─── §5.6  Player prop engine ─────────────────────────────────────────────────

# v8 bands (L10 ACTIVE — old main-striker SOT band 60–72 retired)
PLAYER_BAND_GOAL = {'striker': (0.32, 0.45), 'secondary': (0.18, 0.28), 'mid': (0.08, 0.15)}
PLAYER_BAND_SOT  = {'striker': (0.52, 0.64), 'winger_am': (0.42, 0.56)}


def player_goal_prob(lam_team: float, player_share: float) -> float:
    """P(player scores anytime) = 1 − e^(−λ_team × share)."""
    return 1.0 - math.exp(-lam_team * player_share)


def player_sot_prob(lam_team_sot: float, player_sot_share: float,
                    half: str = 'ft') -> float:
    """
    P(player ≥1 SOT). half: 'ft' | '2h' | '1h'.
    2H share ≈ 0.55; 1H share ≈ 0.45.
    """
    lam = lam_team_sot * player_sot_share
    if half == '2h':
        lam *= 0.55
    elif half == '1h':
        lam *= 0.45
    return 1.0 - math.exp(-lam)


def player_score_or_assist(goal_prob: float, position: str = 'creator') -> float:
    """
    P(score or assist) ≈ goal_prob × mult, overlap-corrected.
    creator mult: 1.5–1.8 (use 1.65); striker mult: 1.2–1.4 (use 1.30).
    """
    mult = 1.65 if position == 'creator' else 1.30
    return min(goal_prob * mult, 0.99)


def apply_l10_driver_gate(p: float, has_driver: bool) -> float:
    """
    L10 ACTIVE (§5.6): if modeled p lands in top half of 56–70% band (≥0.63)
    without an explicit written driver, regress to lower band edge.
    Input-side correction only — D2/D11 intact.
    """
    if p >= 0.63 and not has_driver:
        return 0.62
    return p


# ─── §5.7  Joint / sequence props ────────────────────────────────────────────

def joint_prop(p_a_first: float, p_b_2h: float,
               dependence_haircut: float = -0.015) -> float:
    """
    P(A scores first AND B scores in 2H).
    Applies small negative dependence haircut (−1 to −2pp).
    Never prices above either marginal.
    """
    raw = p_a_first * p_b_2h + dependence_haircut
    return max(0.01, min(raw, p_a_first, p_b_2h, 0.99))


# ─── §5.8  Base-rate tracker (EB) ────────────────────────────────────────────

BASE_RATES: dict[str, float] = {
    'penalty_awarded_per_match': 0.29,
    'red_card_per_match': 0.06,
    'pen_or_red_per_match': 0.31,
    'match_cards_mean': 3.5,
    'goals_per_match_group': 2.55,
}

NOISY_CLAMP = (15, 85)  # §5.9 — clamp noisy register markets to this range


def drama_market_prob(base_rate: float, n_obs: int = 0, n_yes: int = 0,
                      prior_k: float = 7.0) -> float:
    """
    EB posterior for drama markets: (n_yes + k·prior) / (n_obs + k).
    §5.8 stepwise k: 7 for first ~30 matches, 15 thereafter.
    Clamps to NOISY_CLAMP unless anchored.
    """
    posterior = (n_yes + prior_k * base_rate) / (n_obs + prior_k)
    lo, hi = NOISY_CLAMP[0] / 100.0, NOISY_CLAMP[1] / 100.0
    return max(lo, min(hi, posterior))


# ─── §5.11  Coherence gates + L8 batch MC ────────────────────────────────────

def coherence_check(p_win_a: float, p_draw: float, p_win_b: float,
                    anchor: float | None = None,
                    candidate: float | None = None) -> dict:
    """
    §5.11 coherence gates. Returns {'pass': bool, 'issues': [str]}.
    Gate 1: 1X2 triplet sums to 100 ± 2.
    Gate 2: |candidate − anchor| > 0.10 requires written cause.
    """
    issues: list[str] = []
    triplet = p_win_a + p_draw + p_win_b
    if not (0.98 <= triplet <= 1.02):
        issues.append(f"1X2 triplet = {triplet:.3f} (expected 1.00 ± 0.02)")
    if anchor is not None and candidate is not None:
        if abs(candidate - anchor) > 0.10:
            issues.append(
                f"|candidate {candidate:.2f} − anchor {anchor:.2f}| = "
                f"{abs(candidate-anchor):.2f} > 0.10 — needs concrete cause"
            )
    return {'pass': len(issues) == 0, 'issues': issues}


def batch_mc(matches: list[dict], n_draws: int = 2000,
             seed: int = 42) -> dict[str, dict[str, float]]:
    """
    §5.11 L8 batch Monte-Carlo over λ-uncertainty.

    matches: list of dicts, each:
      { 'name': str,
        'lam_a': float, 'sigma_a': float (optional, defaults to 0.15·λ̂),
        'lam_b': float, 'sigma_b': float (optional),
        'markets': ['btts3plus', 'clean_sheet_a', 'scores_2h_a', ...] }

    Supported market keys:
      btts3plus, btts, p_2h_2plus, clean_sheet_a, clean_sheet_b,
      scores_2h_a, scores_2h_b, scores_1h_a, scores_1h_b,
      scores_gte1_a, scores_gte1_b, ht_tied, over25, under25, p11

    Returns: {match_name: {market_key: mc_probability}}
    """
    rng = np.random.default_rng(seed)
    out: dict[str, dict[str, float]] = {}

    for m in matches:
        la_hat = float(m['lam_a'])
        lb_hat = float(m['lam_b'])
        sig_a = float(m.get('sigma_a', 0.15 * la_hat))
        sig_b = float(m.get('sigma_b', 0.15 * lb_hat))

        la = np.clip(rng.normal(la_hat, sig_a, n_draws), 0.05, None)
        lb = np.clip(rng.normal(lb_hat, sig_b, n_draws), 0.05, None)
        T = la + lb
        mkts = set(m.get('markets', []))
        res: dict[str, float] = {}

        if 'btts3plus' in mkts:
            btts = (1 - np.exp(-la)) * (1 - np.exp(-lb))
            p11 = la * lb * np.exp(-T)
            res['btts3plus'] = float(np.mean(np.maximum(btts - p11, 0)))

        if 'btts' in mkts:
            res['btts'] = float(np.mean((1 - np.exp(-la)) * (1 - np.exp(-lb))))

        if 'p11' in mkts:
            res['p11'] = float(np.mean(la * lb * np.exp(-T)))

        if 'p_2h_2plus' in mkts:
            lam_2h = 0.55 * T
            res['p_2h_2plus'] = float(np.mean(1 - np.exp(-lam_2h) * (1 + lam_2h)))

        if 'clean_sheet_a' in mkts:
            res['clean_sheet_a'] = float(np.mean(np.exp(-lb)))

        if 'clean_sheet_b' in mkts:
            res['clean_sheet_b'] = float(np.mean(np.exp(-la)))

        if 'scores_2h_a' in mkts:
            res['scores_2h_a'] = float(np.mean(1 - np.exp(-0.55 * la)))

        if 'scores_2h_b' in mkts:
            res['scores_2h_b'] = float(np.mean(1 - np.exp(-0.55 * lb)))

        if 'scores_1h_a' in mkts:
            res['scores_1h_a'] = float(np.mean(1 - np.exp(-0.45 * la)))

        if 'scores_1h_b' in mkts:
            res['scores_1h_b'] = float(np.mean(1 - np.exp(-0.45 * lb)))

        if 'scores_gte1_a' in mkts:
            res['scores_gte1_a'] = float(np.mean(1 - np.exp(-la)))

        if 'scores_gte1_b' in mkts:
            res['scores_gte1_b'] = float(np.mean(1 - np.exp(-lb)))

        if 'ht_tied' in mkts:
            la_ht = 0.45 * la
            lb_ht = 0.45 * lb
            T_ht = la_ht + lb_ht
            inner = 2.0 * np.sqrt(np.maximum(la_ht * lb_ht, 0))
            p_ht = np.exp(-T_ht) * np.array([float(scipy_i0(x)) for x in inner])
            # L9 ceiling: don't exceed 0.47 unless T < 2.2
            T_full = la + lb
            p_ht = np.where(T_full >= 2.2, np.minimum(p_ht, 0.47), p_ht)
            res['ht_tied'] = float(np.mean(p_ht))

        if 'over25' in mkts:
            p_under = np.exp(-T) * (1 + T + T ** 2 / 2)
            res['over25'] = float(np.mean(1 - p_under))

        if 'under25' in mkts:
            p_under = np.exp(-T) * (1 + T + T ** 2 / 2)
            res['under25'] = float(np.mean(p_under))

        out[m['name']] = res

    return out


# ─── §5.12  Situational overlays ─────────────────────────────────────────────

OVERLAY_TOTAL_CAP = 0.08  # ±8 pp


def apply_overlays(base_p: float, overlays: list[dict]) -> tuple[float, float]:
    """
    Apply situational overlays (§5.12). Each overlay: {'name': str, 'delta': float (pp)}.
    Total capped ±8 pp.
    Returns (adjusted_p, total_delta_pp).
    """
    total_delta = sum(o['delta'] / 100.0 for o in overlays)
    total_delta = max(-OVERLAY_TOTAL_CAP, min(OVERLAY_TOTAL_CAP, total_delta))
    adjusted = max(0.01, min(0.99, base_p + total_delta))
    return adjusted, round(total_delta * 100, 1)


# ─── §5.2 / L12  Dixon–Coles draw inflation ───────────────────────────────────

def dixon_coles_draw_adjust(p_win_a: float, p_draw: float,
                             p_win_b: float) -> tuple[float, float, float]:
    """
    L12 (ACTIVE): hardened Dixon–Coles draw inflation in the 40–60 win band.
    Near-coinflip win markets carry more draw/upset mass than raw devig implies.
    Input-side correction; no output floor/ceiling (D11 intact).
    """
    if 0.40 <= p_win_a <= 0.60 or 0.40 <= p_win_b <= 0.60:
        draw_add = 0.015  # +1.5pp to draw in the coinflip zone
        half = draw_add / 2.0
        p_draw_adj = p_draw + draw_add
        p_win_a_adj = p_win_a - half
        p_win_b_adj = p_win_b - half
        # Renormalize
        total = p_win_a_adj + p_draw_adj + p_win_b_adj
        return p_win_a_adj / total, p_draw_adj / total, p_win_b_adj / total
    return p_win_a, p_draw, p_win_b


# ─── Utility ─────────────────────────────────────────────────────────────────

def to_int(p: float) -> int:
    """
    Convert probability float → integer 1–99.
    D3: avoid exactly 50 (submit 49 or 51 for near-coinflips).
    """
    i = max(1, min(99, round(p * 100)))
    if i == 50:
        # Near 50: nudge by true p direction; default 49 (slight under)
        i = 49
    return i


def from_api_decimal(p_decimal: float) -> int:
    """API returns 0–1 decimals — ×100 to compare with our 1–99 integers."""
    return round(p_decimal * 100)


def clamp_noisy(p: float) -> float:
    """§5.9 noisy register clamp: 15–85 unless anchored."""
    lo, hi = NOISY_CLAMP[0] / 100.0, NOISY_CLAMP[1] / 100.0
    return max(lo, min(hi, p))
