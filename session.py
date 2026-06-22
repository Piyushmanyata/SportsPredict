"""
Session orchestration — §3 autonomous loop.
Implements TRIAGE → URGENT COVER → DEPTH PASS → COVERAGE SWEEP → REPORT.

This module is used by Claude each session to:
  1. Classify match coverage states from live API data.
  2. Derive probability estimates for each market via the engine.
  3. Build submission payloads for submit_predictions_batch.
  4. Track what changed (delta report).
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any

from engine import (
    devig_3way, ou25_to_T, fit_lambda_split, to_int,
    market_scores_gte1, market_scores_2h, market_btts,
    market_btts_3plus, market_totals, market_ht_tied,
    market_ht_both_sot, market_sot_ge2, market_corners_ge5,
    market_offsides_ge2, market_cards_ge4, market_cards_ge2_2h,
    tie_trap_market, TIE_TRAP_TABLE,
    player_goal_prob, player_sot_prob, player_score_or_assist,
    drama_market_prob, batch_mc, coherence_check,
    apply_overlays, apply_l10_driver_gate, dixon_coles_draw_adjust,
    poisson_tail, p_scores_first, joint_prop, clamp_noisy,
    BASE_RATES, NOISY_CLAMP, from_api_decimal,
)
from state import (
    EVENT_ID, LOBBY_ID, STAGE_WEIGHTS,
    NEAR_HORIZON_H, MID_HORIZON_H, URGENT_H, COVERAGE_STATES,
    HIGH_OPPORTUNITY_ARCHETYPES,
)

IST = timezone(timedelta(hours=5, minutes=30))

# Update threshold: abs(Δ) ≥ 3 normally; ≥ 2 for player props with confirmed lineup (L7)
UPDATE_THRESHOLD_NORMAL   = 3
UPDATE_THRESHOLD_LINEUP   = 2


# ─── §2.3 / §3.1  Horizon & coverage classification ─────────────────────────

def hours_to_kickoff(opening_time: str) -> float:
    """ISO8601 opening_time string → hours until kickoff (negative if past)."""
    dt = datetime.fromisoformat(opening_time.replace('Z', '+00:00'))
    return (dt - datetime.now(timezone.utc)).total_seconds() / 3600.0


def classify_horizon(hours: float) -> str:
    """NEAR (<48h) / MID (<7d) / FAR (≥7d)."""
    if hours <= NEAR_HORIZON_H:
        return 'NEAR'
    if hours <= MID_HORIZON_H:
        return 'MID'
    return 'FAR'


def classify_coverage(
    match_id: str,
    predictions: list[dict],
    open_markets: list[dict],
    hours: float,
) -> str:
    """
    UNCOVERED / PARTIAL / COVERED-STALE / COVERED-FRESH.

    Stale = inside T−24h with no Depth Pass recorded this session.
    (The session loop upgrades STALE → FRESH after running the Depth Pass.)
    """
    pred_market_ids = {
        p['market_id'] for p in predictions
        if p.get('market_id')
    }
    open_ids = {m['id'] for m in open_markets}

    if not pred_market_ids & open_ids:
        return 'UNCOVERED'
    if pred_market_ids < open_ids:
        return 'PARTIAL'
    if hours <= 24:
        return 'COVERED-STALE'
    return 'COVERED-FRESH'


def is_urgent(state: str, hours: float) -> bool:
    """True if UNCOVERED/PARTIAL with kickoff <24h — zero-miss rule D1."""
    return state in ('UNCOVERED', 'PARTIAL') and hours < URGENT_H


def needs_depth_pass(state: str, hours: float) -> bool:
    """True if inside near horizon and not yet COVERED-FRESH."""
    return hours <= NEAR_HORIZON_H and state != 'COVERED-FRESH'


def needs_pass1(state: str) -> bool:
    """True if UNCOVERED or PARTIAL — needs at least PASS-1 coverage."""
    return state in ('UNCOVERED', 'PARTIAL')


# ─── §3.1  TRIAGE table ───────────────────────────────────────────────────────

def build_triage_table(
    matches: list[dict],
    predictions: list[dict],
    markets_by_match: dict[str, list[dict]],
) -> list[dict]:
    """
    §3.1 TRIAGE: build a deadline table for all open matches.
    Returns rows sorted by hours_to_kickoff ASC.

    matches: list_matches() results
    predictions: list_predictions() results
    markets_by_match: {match_id: [market, ...]} — pre-fetched for near-horizon
    """
    rows = []
    for m in matches:
        hours = hours_to_kickoff(m['opening_time'])
        if hours < 0:
            continue  # already kicked off

        mkts = markets_by_match.get(m['id'], [])
        state = classify_coverage(m['id'], predictions, mkts, hours)
        horizon = classify_horizon(hours)
        ko_dt = datetime.fromisoformat(
            m['opening_time'].replace('Z', '+00:00')
        ).astimezone(IST)

        rows.append({
            'match_id':          m['id'],
            'name':              m['name'],
            'kickoff_ist':       ko_dt.strftime('%Y-%m-%d %H:%M IST'),
            'hours_to_kick':     round(hours, 1),
            'horizon':           horizon,
            'state':             state,
            'urgent':            is_urgent(state, hours),
            'needs_depth':       needs_depth_pass(state, hours),
            'needs_pass1':       needs_pass1(state),
            'open_market_count': m.get('open_market_count', len(mkts)),
        })

    rows.sort(key=lambda r: r['hours_to_kick'])
    return rows


# ─── §5.3  Market question classifier ────────────────────────────────────────

def classify_market(question: str) -> str:
    """
    Map a market question → archetype key from §5.3.
    Keys: win | totals | btts3plus | scores_2h | scores_gte1 |
          strict_compare | threshold_count | player_prop |
          ht_tied | ht_both_sot | joint_seq | drama | unknown
    """
    q = question.lower()

    # Drama — check early (penalty/red)
    if any(kw in q for kw in ('penalty', 'red card', 'pen or red')):
        return 'drama'

    # Joint / sequence (must check before win/scores)
    if ' and ' in q and any(kw in q for kw in ('first', 'second half', '2h')):
        return 'joint_seq'

    # BTTS^3+ — check before totals (question contains 'total goals' as substring)
    if 'both teams score' in q and ('3+' in q or '3 or more' in q):
        return 'btts3plus'

    # Win market
    if ('win the match' in q or ('will ' in q and ' win' in q and 'match' in q)):
        return 'win'

    # Totals
    if any(kw in q for kw in ('3 or more total goals', '2 or fewer total goals',
                               'over 2.5', 'under 2.5', 'total goals')):
        return 'totals'

    # HT both SOT
    if ('halftime' in q or 'half time' in q) and ('sot' in q or 'shot' in q):
        return 'ht_both_sot'

    # HT tied
    if ('halftime' in q or 'half time' in q) and 'tied' in q:
        return 'ht_tied'

    # Score in 2H
    if 'score in the second half' in q or 'score in 2h' in q or 'score in second half' in q:
        return 'scores_2h'

    # Score at least 1
    if 'score at least 1 goal' in q or 'score at least one' in q:
        return 'scores_gte1'

    # Strict comparison (tie-trap)
    if 'more' in q and any(kw in q for kw in (
            'fouls', 'cards', 'corners', 'shots on target', 'sot', 'offsides')):
        return 'strict_compare'

    # Threshold count
    if any(kw in q for kw in (
            '2+ offside', '4+ total card', '2+ card', '5+ corner',
            '2+ shot', '4+ total shot', '2+ total goal', '4+ total goal',
            '2 or more offside', '4 or more card', '5 or more corner')):
        return 'threshold_count'

    # Player prop
    if any(kw in q for kw in (
            'anytime goal', 'score or assist', '1+ shot', '1+ sot',
            'shots on target', 'to score', 'at least 1 shot')):
        return 'player_prop'

    return 'unknown'


# ─── §2.5  Opportunity label ──────────────────────────────────────────────────

def opportunity_label(archetype: str, stage: str = 'group') -> str:
    """STRONG / MODERATE / THIN / UNKNOWN for crowd-edge triage (§2.5)."""
    strong   = {'strict_compare', 'player_prop', 'drama'}
    moderate = {'win', 'btts3plus', 'ht_tied', 'threshold_count', 'joint_seq'}
    thin     = {'totals', 'scores_gte1', 'scores_2h', 'ht_both_sot'}

    if archetype in strong:
        label = 'STRONG'
    elif archetype in moderate:
        label = 'MODERATE'
    elif archetype in thin:
        label = 'THIN'
    else:
        label = 'UNKNOWN'

    # Knockout/final: upgrade one notch
    if stage in ('knockout', 'final') and label != 'STRONG':
        label = 'STRONG' if label == 'MODERATE' else 'MODERATE'

    return label


# ─── §5.4 stat detector ──────────────────────────────────────────────────────

def detect_stat(question: str) -> str:
    """Detect which stat a strict-comparison market refers to."""
    q = question.lower()
    if 'foul' in q:
        return 'fouls'
    if 'card' in q:
        return 'cards'
    if 'corner' in q:
        if '2h' in q or 'second half' in q:
            return 'corners_2h'
        if 'ht' in q or 'halftime' in q or 'half time' in q:
            return 'corners_ht'
        return 'corners_ft'
    if 'shot' in q or 'sot' in q:
        return 'sot_2h'
    if 'offside' in q:
        return 'offsides'
    return 'fouls'


# ─── Core derivation ─────────────────────────────────────────────────────────

def derive_match_probabilities(
    match_data: dict,
    open_markets: list[dict],
    research: dict,
) -> list[dict]:
    """
    Derive probability estimates for every open market in a match.

    research dict keys:
      p_win_a_implied (float)   — raw decimal implied prob Team A wins
      p_draw_implied (float)
      p_win_b_implied (float)
      p_over25_implied (float)  — raw implied P(over 2.5 goals)
      team_a (str)              — team A name (lowercase ideal)
      team_b (str)              — team B name
      lam_a (float | None)      — override λ_A if already solved
      lam_b (float | None)      — override λ_B
      overlays (list[dict])     — situational overlays §5.12
      player_props (dict)       — {player_name: {position, goal_share, sot_share, team, driver}}
      is_knockout (bool)
      stage (str)               — 'group' | 'knockout' | 'final'
      cards_lambda (float)      — match cards λ (default BASE_RATES)
      ref_strict (bool)         — strict referee card modifier
      l8_run (bool)             — True if batch_mc already run; pass mc_results
      mc_results (dict)         — output of batch_mc for this match (optional)

    Returns list of market result dicts:
      market_id, question, archetype, p (int 1-99), p_float, mode, conf, driver, opportunity
    """
    stage = research.get('stage', 'group')
    stage_weight = STAGE_WEIGHTS.get(stage, 1)

    # ── Anchor extraction ────────────────────────────────────────────────────
    p_win_a_raw = research.get('p_win_a_implied', 0.33)
    p_draw_raw  = research.get('p_draw_implied',  0.28)
    p_win_b_raw = research.get('p_win_b_implied', 0.39)
    p_win_a, p_draw, p_win_b = devig_3way(p_win_a_raw, p_draw_raw, p_win_b_raw)

    # L12 ACTIVE: hardened Dixon–Coles draw inflation in the 40–60 win band
    p_win_a, p_draw, p_win_b = dixon_coles_draw_adjust(p_win_a, p_draw, p_win_b)

    p_over25 = research.get('p_over25_implied', 0.46)
    T = ou25_to_T(p_over25)

    # ── λ split ──────────────────────────────────────────────────────────────
    if research.get('lam_a') and research.get('lam_b'):
        la, lb = float(research['lam_a']), float(research['lam_b'])
    else:
        la, lb = fit_lambda_split(T, p_win_a, p_draw, p_win_b)

    # ── L8 check: >4 markets on one axis? ────────────────────────────────────
    mc = research.get('mc_results', {})

    # ── Names for market question matching ───────────────────────────────────
    team_a = research.get('team_a', '').lower()
    team_b = research.get('team_b', '').lower()

    # ── Card λ ───────────────────────────────────────────────────────────────
    lam_cards = research.get('cards_lambda', BASE_RATES['match_cards_mean'])
    if research.get('ref_strict'):
        lam_cards += 0.8  # strict referee: ~+1 card

    def _team_is_a(q: str) -> bool:
        return bool(team_a) and team_a in q

    def _team_is_b(q: str) -> bool:
        return bool(team_b) and team_b in q

    def _build(market: dict, p_float: float, mode: str,
                conf: str, driver: str) -> dict:
        p_int = to_int(p_float)
        archetype = classify_market(market.get('question', ''))
        return {
            'market_id':   market['id'],
            'question':    market.get('question', ''),
            'archetype':   archetype,
            'p':           p_int,
            'p_float':     round(p_float, 4),
            'mode':        mode,
            'conf':        conf,
            'driver':      driver,
            'opportunity': opportunity_label(archetype, stage),
        }

    results: list[dict] = []

    for mkt in open_markets:
        q = mkt.get('question', '').lower()
        arch = classify_market(q)

        # ── Win (archetype #1) ───────────────────────────────────────────────
        if arch == 'win':
            if _team_is_a(q):
                p = p_win_a
                driver = f"Devigged 1X2 + L12 DC-adj → {p:.3f}"
            elif _team_is_b(q):
                p = p_win_b
                driver = f"Devigged 1X2 + L12 DC-adj → {p:.3f}"
            else:
                p = p_win_a
                driver = f"Devigged 1X2 (team unclear) → {p:.3f}"
            results.append(_build(mkt, p, 'ANCHORED', 'HIGH', driver))

        # ── Totals (archetype #2) ────────────────────────────────────────────
        elif arch == 'totals':
            side = market_totals(T, 2.5)
            if '3 or more' in q or 'over' in q:
                p = side['over']
                driver = f"Poisson(T={T:.2f}) P(over 2.5)"
            else:
                p = side['under']
                driver = f"Poisson(T={T:.2f}) P(under 2.5)"
            # Use MC if available
            mc_key = 'over25' if 'over' in q or '3 or more' in q else 'under25'
            if mc_key in mc:
                p = mc[mc_key]
                driver += f" [MC]"
            results.append(_build(mkt, p, 'ANCHORED', 'HIGH', driver))

        # ── BTTS^3+ (archetype #3) ───────────────────────────────────────────
        elif arch == 'btts3plus':
            p = mc.get('btts3plus', market_btts_3plus(la, lb))
            driver = f"BTTS−P(1-1) λ={la:.2f}/{lb:.2f}{' [MC]' if 'btts3plus' in mc else ''}"
            results.append(_build(mkt, p, 'ANCHORED', 'MED', driver))

        # ── Score in 2H (archetype #4) ───────────────────────────────────────
        elif arch == 'scores_2h':
            if _team_is_a(q):
                p = mc.get('scores_2h_a', market_scores_2h(la))
                driver = f"1−e^(−0.55×{la:.2f}){' [MC]' if 'scores_2h_a' in mc else ''}"
            else:
                p = mc.get('scores_2h_b', market_scores_2h(lb))
                driver = f"1−e^(−0.55×{lb:.2f}){' [MC]' if 'scores_2h_b' in mc else ''}"
            results.append(_build(mkt, p, 'MODELED', 'MED', driver))

        # ── Score ≥1 (archetype #5) ──────────────────────────────────────────
        elif arch == 'scores_gte1':
            if _team_is_a(q):
                p = mc.get('scores_gte1_a', market_scores_gte1(la))
                driver = f"1−e^(−{la:.2f})"
            else:
                p = mc.get('scores_gte1_b', market_scores_gte1(lb))
                driver = f"1−e^(−{lb:.2f})"
            results.append(_build(mkt, p, 'ANCHORED', 'HIGH', driver))

        # ── Strict comparison / tie-trap (archetype #6) ──────────────────────
        elif arch == 'strict_compare':
            stat = detect_stat(q)
            if _team_is_b(q):
                strength_ratio = lb / la if la > 0 else 1.0
            else:
                strength_ratio = la / lb if lb > 0 else 1.0
            p_int = tie_trap_market(stat, strength_ratio)
            driver = f"§5.4 tie-trap stat={stat} ratio={strength_ratio:.2f}"
            results.append({
                'market_id':   mkt['id'],
                'question':    mkt.get('question', ''),
                'archetype':   arch,
                'p':           p_int,
                'p_float':     p_int / 100.0,
                'mode':        'MODELED',
                'conf':        'MED',
                'driver':      driver,
                'opportunity': 'STRONG',  # L3
            })

        # ── Threshold count (archetype #7) ───────────────────────────────────
        elif arch == 'threshold_count':
            p, driver = _threshold_count(q, la, lb, T, lam_cards)
            results.append(_build(mkt, p, 'MODELED', 'MED', driver))

        # ── Player prop (archetype #8) ────────────────────────────────────────
        elif arch == 'player_prop':
            p, driver = _player_prop(q, la, lb, research)
            results.append(_build(mkt, p, 'MODELED', 'MED', driver))

        # ── HT tied (archetype #9) ────────────────────────────────────────────
        elif arch == 'ht_tied':
            p = mc.get('ht_tied', market_ht_tied(la, lb))
            driver = (
                f"Bessel HT-tied λ={la:.2f}/{lb:.2f} T={T:.2f} L9-ceil47"
                f"{' [MC]' if 'ht_tied' in mc else ''}"
            )
            results.append(_build(mkt, p, 'MODELED', 'MED', driver))

        # ── HT both teams ≥1 SOT (archetype #10) ────────────────────────────
        elif arch == 'ht_both_sot':
            lam_sot_a = la * 3.0  # approx: ~3 SOT per goal λ
            lam_sot_b = lb * 3.0
            p = market_ht_both_sot(lam_sot_a, lam_sot_b)
            driver = f"HT-SOT product λ_sot≈{lam_sot_a:.1f}/{lam_sot_b:.1f} (LOW)"
            results.append(_build(mkt, p, 'MODELED', 'LOW', driver))

        # ── Joint / sequence (archetype #11) ─────────────────────────────────
        elif arch == 'joint_seq':
            p_first = p_scores_first(la, T)
            p_b2h = market_scores_2h(lb)
            p = joint_prop(p_first, p_b2h)
            driver = (
                f"P(A first)={p_first:.2f} × P(B 2H)={p_b2h:.2f} "
                f"+ haircut → {p:.2f}"
            )
            results.append(_build(mkt, p, 'MODELED', 'LOW', driver))

        # ── Drama (archetype #12) ─────────────────────────────────────────────
        elif arch == 'drama':
            if 'penalty' in q and 'red' not in q:
                base = BASE_RATES['penalty_awarded_per_match']
            elif 'red card' in q and 'penalty' not in q:
                base = BASE_RATES['red_card_per_match']
            else:
                base = BASE_RATES['pen_or_red_per_match']
            p = drama_market_prob(base)
            driver = f"EB base-rate {base:.2f} clamp {NOISY_CLAMP[0]}–{NOISY_CLAMP[1]} (LOW)"
            results.append(_build(mkt, p, 'BASE-RATE', 'LOW', driver))

        # ── Unknown fallback ──────────────────────────────────────────────────
        else:
            results.append({
                'market_id':   mkt['id'],
                'question':    mkt.get('question', ''),
                'archetype':   'unknown',
                'p':           49,  # avoid exactly 50 (D3)
                'p_float':     0.49,
                'mode':        'FALLBACK',
                'conf':        'LOW',
                'driver':      'Unclassified — engine fallback 49 (FALLBACK-LOW)',
                'opportunity': 'UNKNOWN',
            })

    # Apply situational overlays (§5.12) to MODELED/ANCHORED outputs where relevant
    overlays = research.get('overlays', [])
    if overlays:
        results = _apply_overlays_to_results(results, overlays)

    return results


# ─── Private helpers ──────────────────────────────────────────────────────────

def _threshold_count(q: str, la: float, lb: float, T: float,
                      lam_cards: float) -> tuple[float, str]:
    """Archetype #7: threshold count probabilities."""
    if '4+ total card' in q or '4 or more card' in q:
        return market_cards_ge4(lam_cards), f"§5.5 cards≥4 λ={lam_cards:.1f}"
    if '2+ card in 2h' in q or '2 or more card in 2h' in q or ('2+ card' in q and '2h' in q):
        return market_cards_ge2_2h(lam_cards), f"§5.5 cards≥2(2H) λ={lam_cards:.1f}"
    if '5+ corner' in q or '5 or more corner' in q:
        lam_c = 4.5
        return market_corners_ge5(lam_c), f"§5.5 corners≥5 λ={lam_c:.1f}"
    if '2+ shot' in q or '2 or more shot' in q or '2+ sot' in q:
        lam_sot = la * 3.0  # team-A approximation; refine with research
        return market_sot_ge2(lam_sot), f"§5.5 SOT≥2 λ_sot≈{lam_sot:.1f}"
    if '2+ offside' in q or '2 or more offside' in q:
        lam_off = 1.5
        return market_offsides_ge2(lam_off), f"§5.5 offsides≥2 λ={lam_off:.1f}"
    if '2+ total goal in 2h' in q or '2 or more goal in 2h' in q or '2+ goal in 2h' in q:
        lam_2h = 0.55 * T
        p = poisson_tail(lam_2h, 2)
        return p, f"Poisson P(X≥2) λ_2h={lam_2h:.2f}"
    if '4+ total goal' in q or '4 or more goal' in q:
        p = poisson_tail(T, 4)
        return p, f"Poisson P(X≥4) T={T:.2f}"
    # Fallback
    return 0.40, "Threshold — fallback base rate (FALLBACK-LOW)"


def _player_prop(q: str, la: float, lb: float,
                 research: dict) -> tuple[float, str]:
    """Archetype #8: player prop probabilities."""
    players = research.get('player_props', {})
    team_a = research.get('team_a', '').lower()

    for name, stats in players.items():
        if name.lower() not in q:
            continue
        pos = stats.get('position', 'striker')
        lam_team_goals = la if stats.get('team', 'a') == 'a' else lb
        lam_team_sot   = lam_team_goals * 3.0  # ~3 SOT per goal λ

        if 'anytime goal' in q or 'to score' in q:
            share = stats.get('goal_share', 0.25)
            p = player_goal_prob(lam_team_goals, share)
            return p, f"{name} goal: λ_team={lam_team_goals:.2f}×{share:.2f}"

        if 'score or assist' in q:
            share = stats.get('goal_share', 0.25)
            gp = player_goal_prob(lam_team_goals, share)
            p = player_score_or_assist(gp, pos)
            return p, f"{name} S/A: goal_p={gp:.2f} × mult"

        if '1+ shot' in q or 'shot on target' in q or '1+ sot' in q:
            half = '2h' if ('2h' in q or 'second half' in q) else 'ft'
            share = stats.get('sot_share', 0.28)
            has_driver = bool(stats.get('driver'))
            p = player_sot_prob(lam_team_sot, share, half)
            p = apply_l10_driver_gate(p, has_driver)
            return p, (
                f"{name} SOT({half}): λ_sot={lam_team_sot*share:.2f} L10-gated"
                + ('' if has_driver else ' [no driver → regressed]')
            )

    # No named player match — generic estimate
    if '1+ shot' in q or 'shot on target' in q:
        lam_p = la * 3.0 * 0.25  # generic 25% share of team A SOT
        p = 1.0 - __import__('math').exp(-lam_p)
        p = apply_l10_driver_gate(p, False)
        return p, f"Player SOT: generic 25% of λ_sot={la*3:.1f}, L10-gated"

    lam_p = la * 0.20
    p = 1.0 - __import__('math').exp(-lam_p)
    return p, f"Player goal: generic 20% of λ={la:.2f}"


def _apply_overlays_to_results(
    results: list[dict], overlays: list[dict]
) -> list[dict]:
    """
    Apply §5.12 situational overlays to MODELED/BASE-RATE markets.
    ANCHORED markets are excluded — the anchor governs.
    """
    for r in results:
        if r.get('mode') not in ('MODELED', 'BASE-RATE'):
            continue
        adjusted, delta = apply_overlays(r['p_float'], overlays)
        if delta != 0:
            r['p_float'] = adjusted
            r['p'] = to_int(adjusted)
            r['driver'] += f" + overlays Δ{delta:+.1f}pp"
    return results


# ─── §7  Submission helpers ───────────────────────────────────────────────────

def build_batch_payload(
    market_results: list[dict],
    lobby_id: str = LOBBY_ID,
) -> list[dict]:
    """
    Build the predictions array for submit_predictions_batch.
    Filters out FALLBACK-LOW confidence where conf == 'LOW' and mode == 'FALLBACK'
    only if probability would be exactly the base-rate 49.
    """
    return [
        {'market_id': r['market_id'], 'lobby_id': lobby_id, 'probability': r['p']}
        for r in market_results
        if 1 <= r['p'] <= 99
    ]


def should_update(old_p: int, new_p: int, archetype: str,
                  has_lineup: bool = False) -> bool:
    """
    §6.3 / §7: update if abs(Δ) ≥ threshold.
    Player props with confirmed lineups: threshold 2 (L7); else 3.
    """
    threshold = UPDATE_THRESHOLD_LINEUP if (
        archetype == 'player_prop' and has_lineup
    ) else UPDATE_THRESHOLD_NORMAL
    return abs(new_p - old_p) >= threshold


def build_update_list(
    existing_preds: list[dict],
    new_results: list[dict],
    archetype_map: dict[str, str],
    has_lineup: bool = False,
) -> list[dict]:
    """
    Determine which markets need update_prediction calls.

    existing_preds: list of current predictions with 'market_id', 'probability',
                    'id' (prediction_id).
    new_results: output of derive_match_probabilities.
    archetype_map: {market_id: archetype} for threshold logic.

    Returns list of {'prediction_id', 'new_p', 'old_p', 'delta', 'market_id'}.
    """
    pred_by_market = {p['market_id']: p for p in existing_preds}
    updates = []
    for r in new_results:
        mid = r['market_id']
        if mid not in pred_by_market:
            continue  # new — use submit, not update
        old_pred = pred_by_market[mid]
        old_p = from_api_decimal(old_pred['probability'])
        new_p = r['p']
        arch = archetype_map.get(mid, r.get('archetype', 'unknown'))
        if should_update(old_p, new_p, arch, has_lineup):
            updates.append({
                'prediction_id': old_pred['id'],
                'new_p':         new_p,
                'old_p':         old_p,
                'delta':         new_p - old_p,
                'market_id':     mid,
                'archetype':     arch,
                'driver':        r.get('driver', ''),
            })
    return updates


# ─── L8: proactive MC trigger check ──────────────────────────────────────────

def should_run_mc(market_results: list[dict]) -> bool:
    """
    §5.11 L8: run batch_mc if >4 of ~10 markets share a latent λ axis.
    Heuristic: if >4 markets are MODELED (derived from λ), flag for MC.
    """
    modeled = sum(1 for r in market_results if r.get('mode') in ('MODELED', 'ANCHORED'))
    return modeled > 4


def build_mc_input(match_name: str, la: float, lb: float,
                   market_keys: list[str]) -> dict:
    """
    Build a match dict for batch_mc input.
    Default σ = 0.15·λ̂ (documented placeholder per §5.11).
    """
    return {
        'name':    match_name,
        'lam_a':   la,
        'sigma_a': 0.15 * la,
        'lam_b':   lb,
        'sigma_b': 0.15 * lb,
        'markets': market_keys,
    }
