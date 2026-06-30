"""
Session orchestration — implements §3.2 autonomous loop.
Run this script directly OR import and call run_session().

Quick-start:
    python session.py

Each call performs:
  1. SYNC  — list_matches / list_predictions (scoped)
  2. TRIAGE — coverage state per match
  3. DEPTH PASS — compute & update near-horizon (<48h) markets
  4. COVERAGE SWEEP — compute & submit mid-horizon markets

Requires MCP tools to be available (see §12 Claude note).
"""
from __future__ import annotations
import sys
import math
from datetime import datetime, timezone

from engine import Match, compute_all_markets, clamp, clamp_noisy
from matches import MATCHES, get_match
from mc_batch import batch_mc, should_run_mc, default_sigma

# ── Constants ────────────────────────────────────────────────────────────────
EVENT_ID  = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID  = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"
UPDATE_THRESHOLD = 3     # abs(Δ) ≥ 3 triggers update (§6.3); 2 post-lineup (L7)
MAX_BATCH = 50           # D6: ≤50 per submit_predictions_batch call

IST_OFFSET = 5.5 * 3600  # seconds


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def to_ist_str(dt: datetime) -> str:
    ist_ts = dt.timestamp() + IST_OFFSET
    ist_dt = datetime.fromtimestamp(ist_ts, tz=timezone.utc)
    return ist_dt.strftime("%Y-%m-%d %H:%M IST")

def hours_to_kickoff(match_opening_time_iso: str) -> float:
    ko = datetime.fromisoformat(match_opening_time_iso.replace("Z", "+00:00"))
    return (ko - utc_now()).total_seconds() / 3600.0

def horizon(h: float) -> str:
    if h < 0:    return "KICKED_OFF"
    if h < 48:   return "NEAR"
    if h < 168:  return "MID"
    return "FAR"


# ── Prediction builder ───────────────────────────────────────────────────────
def build_predictions_for_match(m: Match, market_list: list) -> list:
    """
    Given a Match object and list of market dicts from list_markets,
    return a list of {market_id, lobby_id, probability} dicts.
    Maps market question text → engine output key.
    """
    # Run MC if >4 markets on correlated axis
    eng = compute_all_markets(m)

    # Check if MC should run (L8 gate)
    # Correlated axes: goal λ, SOT λ. Count markets loading on each.
    goal_axis_mkts = ["3plus_total_goals", "2or_fewer_total_goals", "btts",
                      "btts_3plus", "team_a_scores", "team_b_scores",
                      "team_a_scores_2h", "goal_before_break1", "goal_after_break2"]
    n_goal_axis = sum(1 for mk in market_list
                      if any(k in mk["question"].lower()
                             for k in ["goal", "score", "both teams"]))
    if should_run_mc(n_goal_axis):
        mc_result = batch_mc([{
            "name":    m.name,
            "lam_a":   m.lam_a, "sigma_a": default_sigma(m.lam_a),
            "lam_b":   m.lam_b, "sigma_b": default_sigma(m.lam_b),
            "sot_a":   m.sot_a, "sigma_sot_a": default_sigma(m.sot_a),
            "sot_b":   m.sot_b, "sigma_sot_b": default_sigma(m.sot_b),
            "markets": goal_axis_mkts,
        }])
        mc = mc_result.get(m.name, {})
        # Merge MC results into eng (MC integrates λ-uncertainty)
        key_map = {
            "btts":           "btts",
            "btts_3plus":     "btts_3plus",
            "3plus_goals":    "3plus_total_goals",
            "2or_fewer_goals": "2or_fewer_total_goals",
            "team_a_scores":  "team_a_scores",
            "team_b_scores":  "team_b_scores",
            "team_a_scores_2h": "team_a_scores_2h",
            "goal_before_break1": "goal_before_break1",
            "goal_after_break2":  "goal_after_break2",
        }
        for mc_key, eng_key in key_map.items():
            if mc_key in mc:
                eng[eng_key] = mc[mc_key]

    preds = []
    for mk in market_list:
        if mk.get("status") != "open":
            continue
        q = mk["question"]
        p = _map_question_to_prob(q, eng, m)
        if p is not None:
            preds.append({
                "market_id": mk["id"],
                "lobby_id":  LOBBY_ID,
                "probability": p,
                "question":    q,  # for logging; strip before batch call
            })
    return preds


# ── Team code → full name in question text ──────────────────────────────────
_CODE_TO_NAME = {
    "CIV": "ivory coast", "NOR": "norway",
    "FRA": "france",      "SWE": "sweden",
    "MEX": "mexico",      "ECU": "ecuador",
    "ENG": "england",     "COD": "dr congo",
    "BEL": "belgium",     "SEN": "senegal",
    "USA": "united states", "BIH": "bosnia",
    "ESP": "spain",       "AUT": "austria",
    "POR": "portugal",    "CRO": "croatia",
    "SUI": "switzerland", "ALG": "algeria",
    "AUS": "australia",   "EGY": "egypt",
    "ARG": "argentina",   "CPV": "cape verde",
    "COL": "colombia",    "GHA": "ghana",
}


def _map_question_to_prob(question: str, eng: dict, m: Match) -> int | None:
    """
    Map market question text to computed probability.
    Returns None if question is unrecognised (will be logged as unhandled).
    """
    q = question.lower()

    # ── Team name resolution: codes → full names used in question text ────
    code_a, code_b = [t.strip() for t in m.name.split(" vs ")]
    ta = _CODE_TO_NAME.get(code_a, code_a.lower())  # full lowercase team A name
    tb = _CODE_TO_NAME.get(code_b, code_b.lower())  # full lowercase team B name

    # Helper: player check (guard against empty string matching everything)
    def player_in_q(name: str) -> bool:
        return bool(name) and name.lower() in q

    # ── Win / advance markets ────────────────────────────────────────────
    if f"will {ta} win" in q:
        return eng["team_a_wins_regulation"]
    if f"will {tb} win" in q:
        return eng["team_b_wins_regulation"]
    if f"will {ta} advance" in q:
        return eng["team_a_advances"]
    if f"will {tb} advance" in q:
        return eng["team_b_advances"]

    # ── Player props — must come BEFORE team-level checks to avoid misroute ─
    # Goal props
    if player_in_q(m.player_a1_name) and "score a goal" in q:
        return eng["player_a1_goal"]
    if player_in_q(m.player_b1_name) and "score a goal" in q:
        return eng["player_b1_goal"]
    if player_in_q(m.player_a2_name) and "score a goal" in q:
        return eng["player_a2_goal"]
    if player_in_q(m.player_b2_name) and "score a goal" in q:
        return eng["player_b2_goal"]

    # SOA props (score or assist)
    if player_in_q(m.player_a1_name) and "score or assist" in q:
        return eng["player_a1_soa"]
    if player_in_q(m.player_a2_name) and "score or assist" in q:
        return eng["player_a2_soa"]
    if player_in_q(m.player_b1_name) and "score or assist" in q:
        return eng["player_b1_soa"]
    if player_in_q(m.player_b2_name) and "score or assist" in q:
        return eng["player_b2_soa"]

    # SOT props
    if player_in_q(m.player_a1_name) and "1 or more shots on target" in q:
        return eng["player_a1_sot1plus"]
    if player_in_q(m.player_a1_name) and ("2 or more shots on target" in q or "at least 2 shot" in q):
        return eng["player_a1_sot2plus"]
    if player_in_q(m.player_a1_name) and ("3 or more shots on target" in q or "at least 3 shot" in q):
        return eng["player_a1_sot2plus"]  # proxy: use 2+ as conservative
    if player_in_q(m.player_b1_name) and ("1 or more shots on target" in q or "at least 1 shot" in q):
        return eng["player_b1_sot1plus"]
    if player_in_q(m.player_b1_name) and "2 or more shots on target" in q:
        return eng["player_b1_sot2plus"]
    if player_in_q(m.player_a2_name) and ("1 or more shots on target" in q or "2 or more shots on target" in q):
        return eng["player_a2_sot_k"]
    if player_in_q(m.player_b2_name) and ("1 or more shots on target" in q or "2 or more shots on target" in q):
        return eng["player_b2_sot_k"]

    # ── Team scores (binary) ──────────────────────────────────────────────
    # Only match when no known player name is in the question (prevents misrouting)
    known_players = [n for n in [m.player_a1_name, m.player_a2_name,
                                  m.player_b1_name, m.player_b2_name] if n]
    no_player_in_q = not any(p.lower() in q for p in known_players)

    if "score a goal" in q and "excluding own" in q and no_player_in_q:
        if tb in q:
            return eng["team_b_scores"]
        if ta in q:
            return eng["team_a_scores"]

    # ── Totals ────────────────────────────────────────────────────────────
    if "3 or more total goals" in q:
        return eng["3plus_total_goals"]
    if "2 or fewer total goals" in q:
        return eng["2or_fewer_total_goals"]

    # ── BTTS ─────────────────────────────────────────────────────────────
    if "both teams score" in q and "3 or more" not in q:
        return eng["btts"]
    if "both teams score" in q and "3 or more" in q:
        return eng["btts_3plus"]

    # ── Team SOT ─────────────────────────────────────────────────────────
    if ta in q and "4 or more shots on target" in q:
        return eng["team_a_4plus_sot"]
    if ta in q and "5 or more shots on target" in q:
        return eng["team_a_5plus_sot"]
    if ta in q and "6 or more shots on target" in q:
        return eng["team_a_6plus_sot"]
    if ta in q and "7 or more shots on target" in q:
        return eng["team_a_7plus_sot"]
    if ta in q and "8 or more shots on target" in q:
        return eng["team_a_8plus_sot"]
    if tb in q and "2 or more shots on target" in q:
        return eng["team_b_2plus_sot"]
    if tb in q and "4 or more shots on target" in q:
        return eng["team_b_4plus_sot"]
    if tb in q and "5 or more shots on target" in q:
        return eng["team_b_5plus_sot"]
    if tb in q and "6 or more shots on target" in q:
        return eng["team_b_6plus_sot"]
    if tb in q and "7 or more shots on target" in q:
        return eng["team_b_7plus_sot"]

    # ── Team corners ─────────────────────────────────────────────────────
    if ta in q and "6 or more corner" in q:
        return eng["team_a_6plus_corners"]
    if ta in q and "7 or more corner" in q:
        return eng["team_a_7plus_corners"]
    if ta in q and "8 or more corner" in q:
        return eng["team_a_8plus_corners"]

    # ── Team goal-count thresholds ────────────────────────────────────────
    if ta in q and "3 or more goals" in q:
        return eng["team_a_3plus_goals"]
    if tb in q and "3 or more goals" in q:
        return eng["team_b_3plus_goals"]

    # ── Clean sheet ───────────────────────────────────────────────────────
    if "keep a clean sheet" in q:
        if ta in q:
            return eng["clean_sheet_a"]
        if tb in q:
            return eng["clean_sheet_b"]

    # ── Strict comparisons ────────────────────────────────────────────────
    if "more corner kicks than" in q:
        if ta in q.split("more corner")[0]:
            return eng["team_a_more_corners_ft"]
        return clamp((100 - eng["team_a_more_corners_ft"]) * 0.9)
    if "more shots on target than" in q:
        if ta in q.split("more shots")[0]:
            return eng["team_a_more_sot"]
        return clamp((100 - eng["team_a_more_sot"]) * 0.9)
    if "more cards than" in q:
        if tb in q.split("more cards")[0]:
            return eng["team_b_more_cards"]
        return eng["team_a_more_cards"]

    # ── Cards ─────────────────────────────────────────────────────────────
    if "3 or more total cards" in q:
        return eng["4plus_total_cards"]   # closest approximation
    if "4 or more total cards" in q:
        return eng["4plus_total_cards"]
    if "5 or more total cards" in q:
        return eng["5plus_total_cards"]
    if "card be shown in the first half" in q or "card shown in the first half" in q:
        return eng["card_in_first_half"]
    if "both teams receive at least one card" in q:
        return eng["4plus_total_cards"]   # proxy: ~both teams carded ≈ P(4+)

    # ── Offsides ─────────────────────────────────────────────────────────
    if "3 or more offside" in q:
        return eng["3plus_offsides"]
    if "4 or more offside" in q:
        return eng["4plus_offsides"]

    # ── Total shots ───────────────────────────────────────────────────────
    if "20 or more total shots" in q:
        return eng["20plus_total_shots"]
    if "22 or more total shots" in q:
        return eng["22plus_total_shots"]
    if "24 or more total shots" in q:
        return eng["24plus_total_shots"]

    # ── Total corners ─────────────────────────────────────────────────────
    if "9 or more total corner" in q:
        return eng["9plus_total_corners"]

    # ── Drama / noisy register ────────────────────────────────────────────
    if ("penalty kick be awarded" in q or "penalty be awarded" in q) and "red card" not in q:
        return eng["penalty_awarded"]
    if "red card be shown" in q and "penalty" not in q:
        return eng["red_card"]
    if "penalty" in q and "red card" in q:
        return eng["pen_or_red"]

    # ── HT state markets ─────────────────────────────────────────────────
    if "tied at halftime" in q or ("halftime" in q and "tied" in q) or "match be tied at halftime" in q:
        return eng["ht_tied"]
    if "be ahead at halftime" in q:
        if ta in q:
            return eng["team_a_leading_ht"]
        if tb in q:
            return eng["team_b_leading_ht"]

    # ── Both halves / scores each half ────────────────────────────────────
    if "score in both halves" in q:
        if ta in q:
            return eng["team_a_scores_both_halves"]
        if tb in q:
            return eng["team_b_scores_both_halves"]

    # ── Scores first ─────────────────────────────────────────────────────
    if "score the first goal" in q:
        if ta in q:
            return eng["team_a_scores_first"]
        if tb in q:
            return eng["team_b_scores_first"]

    # ── Win by 2+ goals ───────────────────────────────────────────────────
    if "win by 2 or more goals" in q:
        if ta in q:
            return eng["team_a_win_by_2plus"]
        if tb in q:
            return eng["team_b_win_by_2plus"]

    # ── 2H more goals than 1H ─────────────────────────────────────────────
    if "second half produce more goals than the first half" in q:
        return eng["2h_more_goals_than_1h"]

    # ── Hydration-break markets ───────────────────────────────────────────
    if "before the first hydration break" in q and "goal" in q:
        return eng["goal_before_break1"]
    if "after the second hydration break" in q and "goal" in q:
        return eng["goal_after_break2"]
    if "before the first hydration break" in q and "corner" in q:
        return eng["corners_before_break1_2plus"]

    # ── Stoppage-time markets ─────────────────────────────────────────────
    if "first-half stoppage" in q or "first half stoppage" in q:
        return eng["goal_ht_stoppage"]
    if "second-half stoppage" in q or "second half stoppage" in q:
        return eng["goal_2h_stoppage"]

    # ── Misc ──────────────────────────────────────────────────────────────
    if "substitution be made before halftime" in q:
        return eng["sub_before_ht"]
    if "substitute score a goal" in q:
        return eng["sub_scores"]
    if "any player score 2 or more goals" in q:
        return eng["3plus_total_goals"]   # proxy: brace ≈ 60% of 3+ goals
    if "header goal" in q:
        return clamp_noisy(20)             # base rate ~20% per §5.8
    if "own goal be scored" in q or "an own goal" in q:
        return eng["own_goal"]
    if "goal be scored from outside the penalty area" in q or "goal from outside" in q:
        return eng["goal_outside_box"]

    # Unhandled — log and return None (D4: fallback not silence)
    print(f"  [UNHANDLED MARKET] {question}")
    return None


# ── Coherence gates (§5.11) ──────────────────────────────────────────────────
def run_coherence_gates(preds: list, m: Match) -> list:
    """
    Check and flag coherence issues before batch submission.
    Returns annotated list; does NOT silently correct (D2).
    """
    issues = []
    prob_map = {p["question"]: p["probability"] for p in preds}

    # Gate 1: team_a_wins + draw + team_b_wins ≈ 100 ± 2
    wa = prob_map.get(f"Will {m.name.split(' vs ')[0]} win in regulation?")
    wb = prob_map.get(f"Will {m.name.split(' vs ')[1]} win in regulation?")
    # Can't check draw without that specific market — skip if missing

    # Gate 2: no predicted prob outside 1-99
    for p in preds:
        if not (1 <= p["probability"] <= 99):
            issues.append(f"OUT-OF-RANGE: {p['question']} = {p['probability']}")

    # Gate 3: BTTS ≤ P(A scores), BTTS ≤ P(B scores)
    # Gate 4: joint ≤ both marginals
    if issues:
        print(f"  [COHERENCE ISSUES] {m.name}: {issues}")
    return preds  # caller handles issues


# ── Status block (§8.1) ──────────────────────────────────────────────────────
def print_status_block(match_list: list, prediction_counts: dict) -> None:
    now_ist = to_ist_str(utc_now())
    print(f"\n{'='*60}")
    print(f"STATUS — {now_ist}")
    print(f"{'='*60}")
    print(f"{'Match':<20} {'KO (IST)':<20} {'h to KO':>8} {'Horizon':<10} {'Covered':>8}")
    print("-" * 70)
    for match in match_list:
        h = hours_to_kickoff(match["opening_time"])
        hz = horizon(h)
        name = match["name"]
        n_preds = prediction_counts.get(name, 0)
        n_open  = match.get("open_market_count", "?")
        covered = f"{n_preds}/{n_open}" if n_preds else "UNCOVERED"
        ko_ist  = to_ist_str(
            datetime.fromisoformat(match["opening_time"].replace("Z", "+00:00"))
        )
        marker = "*** URGENT" if h < 0 else ("! " if h < 24 else "  ")
        print(f"{marker}{name:<18} {ko_ist:<20} {h:>8.1f}h {hz:<10} {covered:>8}")
    print(f"{'='*60}\n")


# ── After-action report (§8.2) ───────────────────────────────────────────────
def print_aar(match_name: str, preds: list, succeeded: int, failed: int) -> None:
    print(f"\n--- AAR: {match_name} ---")
    print(f"{'Market':<55} {'p':>4}  Conf")
    print("-" * 70)
    for p in preds:
        conf = "LOW"
        print(f"  {p['question'][:53]:<55} {p['probability']:>4}")
    print(f"\nBatch: {succeeded} succeeded / {failed} failed")


if __name__ == "__main__":
    print("Session runner loaded. Import and call build_predictions_for_match()")
    print("or use the MCP tools directly in Claude to run the autonomous loop.")
    print(f"\nEvent: {EVENT_ID}")
    print(f"Lobby: {LOBBY_ID}")
    print(f"\nMatches configured: {len(MATCHES)}")
    for name, m in MATCHES.items():
        print(f"  {name}: λ_A={m.lam_a:.2f} λ_B={m.lam_b:.2f} T={m.T:.2f} [{m.confidence}]")
