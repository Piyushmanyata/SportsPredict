"""
Research helpers for Probability Cup session protocol.
Provides odds-fetching search query templates and coverage-state logic.
"""
from datetime import datetime, timezone
from typing import Optional


# ── Coverage state helpers ────────────────────────────────────────────────────

def hours_to_kickoff(opening_time_utc: str) -> float:
    """Returns hours until kickoff from now (UTC)."""
    ko = datetime.fromisoformat(opening_time_utc.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (ko - now).total_seconds() / 3600


def coverage_state(has_predictions: bool, n_predictions: int, n_markets: int,
                   has_depth_pass: bool, hours_out: float) -> str:
    """
    Returns: UNCOVERED · PARTIAL · COVERED-STALE · COVERED-FRESH
    """
    if not has_predictions or n_predictions == 0:
        return "UNCOVERED"
    if n_predictions < n_markets:
        return "PARTIAL"
    if hours_out < 24 and not has_depth_pass:
        return "COVERED-STALE"
    return "COVERED-FRESH"


def horizon(hours_out: float) -> str:
    """Returns: NEAR (<48h) · MID (48h-7d) · FAR (>7d)"""
    if hours_out < 48:
        return "NEAR"
    elif hours_out < 168:
        return "MID"
    return "FAR"


def ist_time(utc_iso: str) -> str:
    """Convert UTC ISO string to IST (UTC+5:30) display string."""
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    from datetime import timedelta
    ist = dt + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d %H:%M IST")


# ── Research query templates ──────────────────────────────────────────────────

def depth_pass_queries(team_a: str, team_b: str, date_str: str) -> list[str]:
    """Standard Depth Pass query set for a near-horizon match."""
    return [
        f"{team_a} vs {team_b} confirmed lineup {date_str}",
        f"{team_a} {team_b} injuries suspensions {date_str}",
        f"{team_a} vs {team_b} odds betting lines {date_str}",
        f"{team_a} {team_b} referee {date_str}",
        f"{team_a} {team_b} preview prediction {date_str}",
        f"{team_a} vs {team_b} World Cup 2026",
    ]


def pass1_query(team_a: str, team_b: str) -> list[str]:
    """PASS-1 query set for mid/far horizon matches."""
    return [
        f"{team_a} vs {team_b} odds over under 2.5",
        f"{team_a} {team_b} match preview",
    ]


# ── Market classification helpers ─────────────────────────────────────────────

def classify_market(question: str) -> str:
    """
    Returns archetype number string for a market question per §5.3.
    """
    q = question.lower()
    if "win in regulation" in q or "win the match" in q:
        return "1_win"
    if "3 or more total goals" in q or "2 or fewer total goals" in q:
        return "2_totals"
    if "both teams score" in q and ("3+" in q or "3 or more" in q):
        return "3_btts3plus"
    if "both teams score" in q:
        return "3_btts"
    if "score in the second half" in q or "score in second half" in q:
        return "4_scores2h"
    if "score at least 1 goal" in q or "score a goal" in q:
        return "5_scores"
    if "score the first goal" in q or "score first" in q:
        return "5_first"
    if "score in both halves" in q:
        return "5_both_halves"
    if "more" in q and any(s in q for s in ["corner", "foul", "card", "shots on target", "offside"]):
        return "6_comparison"
    if "or more" in q and any(s in q for s in ["offside", "card", "corner", "shots on target", "goal"]):
        return "7_threshold"
    if "shots on target" in q and any(p in q for p in ["havertz", "musiala", "enciso", "wirtz",
                                                          "brobbey", "saibari", "kane", "mbappe",
                                                          "messi", "ronaldo", "neymar"]):
        return "8_player_sot"
    if "score or assist" in q or "goal" in q and any(s in q for s in ["will ", "havertz", "musiala", "wirtz",
                                                                          "brobbey", "saibari"]):
        return "8_player_goal"
    if "halftime" in q and "tied" in q:
        return "9_ht_tied"
    if "halftime" in q and "shots on target" in q:
        return "10_ht_sot"
    if "penalty" in q:
        return "12_penalty"
    if "red card" in q:
        return "12_red"
    if "ahead at halftime" in q or "be ahead" in q:
        return "ht_lead"
    if "first half" in q and "goal" in q:
        return "7_1h_goals"
    if "second half" in q and ("more goals" in q or "goal" in q):
        return "7_2h"
    if "hydration break" in q:
        return "novel_hydration"
    if "stoppage time" in q:
        return "novel_stoppage"
    if "both teams receive" in q and "card" in q:
        return "7_both_teams_carded"
    if "card be shown after" in q:
        return "novel_card_after"
    return "unknown"


# ── Stage weight ──────────────────────────────────────────────────────────────

def stage_weight(stage: str) -> float:
    """Returns stage weight: group=1, knockout=2, final=3."""
    s = stage.lower()
    if "final" in s and "semi" not in s and "quarter" not in s:
        return 3.0
    if any(k in s for k in ["knockout", "r32", "r16", "quarter", "semi", "round of"]):
        return 2.0
    return 1.0


# ── Coherence gates ───────────────────────────────────────────────────────────

def check_coherence(p_home: int, p_draw: int, p_away: int,
                    tolerance: int = 2) -> tuple[bool, str]:
    """Gate: 1X2 triplet sums to 100 ± tolerance."""
    total = p_home + p_draw + p_away
    if abs(total - 100) > tolerance:
        return False, f"1X2 sum={total}, expected 100±{tolerance}"
    return True, "OK"


def check_complement(p_yes: int, p_no: int, tolerance: int = 3) -> tuple[bool, str]:
    """Gate: complementary markets sum to 100 ± tolerance."""
    total = p_yes + p_no
    if abs(total - 100) > tolerance:
        return False, f"Complement sum={total}, expected 100±{tolerance}"
    return True, "OK"
