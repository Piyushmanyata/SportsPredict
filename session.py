"""
Jump Trading Probability Cup — Session protocol helpers (§3).

Provides: triage, coverage-state classification, horizon assignment,
opportunity scoring, depth-pass checklist, and update-threshold checks.
No MCP calls here — pass live API data in; get structured decisions back.

Usage:
    from session import triage, coverage_state, depth_pass_checklist, update_needed
"""

from datetime import datetime, timezone, timedelta
from constants import STAGE_WEIGHTS, DEBIAS_POLICY

IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def now_ist():
    return datetime.now(IST)


def to_ist(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def parse_dt(s):
    """Parse ISO-8601 datetime string (with or without Z). Returns aware datetime."""
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def hours_until(kickoff_ist, now=None):
    if now is None:
        now = now_ist()
    delta = kickoff_ist - now
    return delta.total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# §4.3  Stage and Matchday-3 detection
# ---------------------------------------------------------------------------

def detect_stage(match):
    """
    Infer match stage from name / metadata.
    Returns 'final', 'knockout', or 'group'.
    """
    name = (match.get("name") or "").lower()
    if "final" in name and "semi" not in name and "quarter" not in name:
        return "final"
    knockout_keywords = ("r32", "r16", "qf", "sf", "round of", "quarter", "semi",
                         "knockout", "last 16", "last 32")
    if any(k in name for k in knockout_keywords):
        return "knockout"
    return "group"


def is_matchday_3(match):
    """
    True if this match falls in the MD3 simultaneous-pair window (June 24-28 2026). §3.3
    """
    ko = parse_dt(match.get("opening_time") or match.get("closing_time") or "")
    if ko is None:
        return False
    ko_utc = to_ist(ko)
    return (ko_utc.year == 2026 and ko_utc.month == 6 and 24 <= ko_utc.day <= 28)


# ---------------------------------------------------------------------------
# §2.3 / §2.4  Horizon and coverage state
# ---------------------------------------------------------------------------

def horizon(hours_h):
    """
    Classify match horizon from hours to kickoff.
    Returns 'near' (<48h), 'mid' (48h–7d), 'far' (>7d). §2.3
    """
    if hours_h < 48:
        return "near"
    if hours_h < 168:
        return "mid"
    return "far"


def coverage_state(has_any_predictions, open_market_count, predicted_count,
                   depth_pass_done_within_24h):
    """
    Classify coverage state for a match. §2.4
    Returns one of: 'UNCOVERED', 'PARTIAL', 'COVERED-STALE', 'COVERED-FRESH'.

    Parameters:
        has_any_predictions: bool — at least one prediction exists for this match
        open_market_count: int — total open markets from list_markets
        predicted_count: int — how many we have predictions for
        depth_pass_done_within_24h: bool — Depth Pass completed inside T−24h window
    """
    if not has_any_predictions or predicted_count == 0:
        return "UNCOVERED"
    if open_market_count > 0 and predicted_count < open_market_count:
        return "PARTIAL"
    if not depth_pass_done_within_24h:
        return "COVERED-STALE"
    return "COVERED-FRESH"


# ---------------------------------------------------------------------------
# §3.1 / §3.2  Full triage
# ---------------------------------------------------------------------------

def triage(matches, prediction_counts=None, depth_pass_flags=None, now=None):
    """
    Produce a triage table from the list_matches response.

    Parameters:
        matches: list of dicts from list_matches API
        prediction_counts: dict {match_id: int} — how many predictions exist per match
        depth_pass_flags: set of match_ids that had a Depth Pass within T−24h
        now: datetime (defaults to now_ist())

    Returns: list of triage-row dicts, sorted by kickoff ASC.
    """
    if now is None:
        now = now_ist()
    prediction_counts = prediction_counts or {}
    depth_pass_flags = depth_pass_flags or set()

    rows = []
    for m in matches:
        ko_raw = m.get("opening_time") or m.get("closing_time") or ""
        ko = parse_dt(ko_raw)
        if ko is None:
            continue
        ko_ist = to_ist(ko)
        h = hours_until(ko_ist, now)

        if h < 0:
            continue  # already kicked off

        stage = detect_stage(m)
        sw = STAGE_WEIGHTS.get(stage, 1)
        h_label = horizon(h)
        mid = m.get("id", "")
        open_mkts = m.get("open_market_count", 0)
        pred_n = prediction_counts.get(mid, 0)
        has_preds = pred_n > 0
        dp_done = mid in depth_pass_flags

        state = coverage_state(has_preds, open_mkts, pred_n, dp_done)

        rows.append({
            "match_id":         mid,
            "name":             m.get("name", "?"),
            "kickoff_ist":      ko_ist,
            "kickoff_str":      ko_ist.strftime("%Y-%m-%d %H:%M IST"),
            "hours":            round(h, 1),
            "horizon":          h_label,
            "stage":            stage,
            "stage_weight":     sw,
            "open_markets":     open_mkts,
            "predicted_count":  pred_n,
            "coverage_state":   state,
            "depth_pass_done":  dp_done,
            "matchday_3":       is_matchday_3(m),
            "urgent":           h < 24 and state in ("UNCOVERED", "PARTIAL", "COVERED-STALE"),
        })

    rows.sort(key=lambda r: r["kickoff_ist"])
    return rows


def tier_1_triage_summary(rows):
    """
    Tier 1 output: minimal deadline table for the STATUS BLOCK. §3.1 / §8.1
    Returns a formatted string.
    """
    lines = []
    near  = [r for r in rows if r["horizon"] == "near"]
    mid   = [r for r in rows if r["horizon"] in ("mid", "far") and r["hours"] <= 168]

    urgent = [r for r in near if r["urgent"]]
    if urgent:
        lines.append("⚠  URGENT — action required before kickoff:")
        for r in urgent:
            lines.append(f"   {r['name']} | {r['kickoff_str']} | T−{r['hours']:.1f}h | {r['coverage_state']}")

    if near:
        lines.append("Near horizon (<48h):")
        for r in near:
            md3 = " [MD3]" if r["matchday_3"] else ""
            dp = "✓" if r["depth_pass_done"] else "✗"
            lines.append(
                f"  {r['name']:<25} {r['kickoff_str']}  T−{r['hours']:.1f}h  "
                f"{r['stage_weight']}×  {r['coverage_state']:<16} DP:{dp}{md3}"
            )

    if mid:
        lines.append("Mid/far horizon (≤7d):")
        for r in mid:
            lines.append(f"  {r['name']:<25} {r['kickoff_str']}  T−{r['hours']:.1f}h  {r['coverage_state']}")

    return "\n".join(lines) if lines else "No upcoming matches in the next 7 days."


# ---------------------------------------------------------------------------
# §2.5 / §3.4  RBP opportunity scoring
# ---------------------------------------------------------------------------

_HIGH_OPP_TYPES = {
    "strict_comparison", "tie_trap",
    "star_sot", "star_goal",
    "host_favorite_win", "brand_win",
    "drama_pen", "drama_red", "drama_pen_or_red",
    "correlated_basket",
}
_MED_OPP_TYPES = {
    "btts", "btts3plus", "ht_tied", "player_goal",
    "total_goals", "team_scores", "team_scores_2h",
}


def opportunity_label(market_type, estimated_crowd_gap_pts=None):
    """
    Assign RBP opportunity label. §2.5
    Returns 'STRONG', 'MODERATE', 'THIN', or 'UNKNOWN'.
    Never use to move q — only to allocate research depth.
    """
    if estimated_crowd_gap_pts is not None:
        if estimated_crowd_gap_pts >= DEBIAS_POLICY["strong_opp_threshold"]:
            return "STRONG"
        if estimated_crowd_gap_pts >= DEBIAS_POLICY["moderate_opp_threshold"]:
            return "MODERATE"
        return "THIN"

    if market_type in _HIGH_OPP_TYPES:
        return "STRONG"
    if market_type in _MED_OPP_TYPES:
        return "MODERATE"
    return "THIN"


def opportunity_score(triage_row, market_opportunity_labels):
    """
    Expected RBP Opportunity Score for a match. §2.5
    opportunity = stage_weight × Σ EdgeLabelWeight × ConfidenceWeight

    market_opportunity_labels: list of opportunity strings for each market in the match.
    """
    label_weights = {"STRONG": 2.0, "MODERATE": 1.0, "THIN": 0.3, "UNKNOWN": 0.5}
    edge_sum = sum(label_weights.get(lbl, 0.5) for lbl in market_opportunity_labels)
    return triage_row["stage_weight"] * edge_sum


def sort_by_opportunity(triage_rows, opp_scores):
    """
    Sort near-horizon matches by opportunity score. §3.4
    opp_scores: dict {match_id: float}
    """
    near = [r for r in triage_rows if r["horizon"] == "near"]
    urgent = [r for r in near if r["urgent"]]
    non_urgent = [r for r in near if not r["urgent"]]
    non_urgent.sort(key=lambda r: opp_scores.get(r["match_id"], 0), reverse=True)
    return urgent + non_urgent


# ---------------------------------------------------------------------------
# §6.1 / §6.3  Pass checklists
# ---------------------------------------------------------------------------

def pass1_checklist(match_name, team_a, team_b):
    """
    Minimum research steps for a PASS-1 (mid/far horizon). §6.1
    Returns list of search query strings.
    """
    return [
        f"{team_a} vs {team_b} odds",
        f"{team_a} vs {team_b} over under 2.5 goals",
        f"{team_a} {team_b} injuries news",
    ]


def depth_pass_checklist(match_name, team_a, team_b, city, date_str,
                         is_knockout=False, is_md3=False):
    """
    Full research checklist for a Depth Pass (near horizon, <48h). §6.3
    Returns list of research steps in execution order.
    """
    steps = [
        f'"{team_a} vs {team_b} confirmed lineup {date_str}"',
        f'"{team_a} injuries suspensions {date_str}"',
        f'"{team_b} injuries suspensions {date_str}"',
        f'"{team_a} rotation {date_str}"',
        f'"{team_b} rotation {date_str}"',
        f'"referee {match_name} cards per game"',
        f'"{city} weather {date_str}"',
        f"Fresh odds re-pull ≤2h: {team_a} vs {team_b} 1X2 + O/U 2.5 + BTTS",
        "Polymarket / Betfair exchange cross-check",
        "§5.11 L8: count markets on same axis → >4 → add to batch_mc() call",
        "§5.12: scan all situational overlays (alt, MD3-rotation, rest gap, weather, ref-profile)",
    ]
    if is_knockout:
        steps.insert(0, "§11.1: confirm 'win' wording = regulation or advance")
        steps.append("Exchange/Polymarket cross-check (MANDATORY knockout)")
        steps.append("MC batch almost certainly fires — prep match entry for batch_mc()")
    if is_md3:
        steps.extend([
            "§3.3 MD3: verify qualification scenarios for BOTH teams",
            "§3.3 MD3: expected XI rotation — favourite win −3-6, slash player props if starter rested",
            "§3.3 MD3: research sibling pair match together (shared scenario logic + L8 spans both)",
        ])
    return steps


# ---------------------------------------------------------------------------
# §7  Update-threshold checks
# ---------------------------------------------------------------------------

def update_needed(old_p, new_p, is_player_prop=False, lineups_known=False):
    """
    Returns True if abs(Δ) meets the update threshold. §6.3 / §6.1
    Threshold: ≥3 generally; ≥2 for player props post-lineup (L7).
    """
    delta = abs(new_p - old_p)
    threshold = 2 if (is_player_prop and lineups_known) else 3
    return delta >= threshold


# ---------------------------------------------------------------------------
# §2.4  Next check-in
# ---------------------------------------------------------------------------

def next_checkin_str(now=None, offset_hours=24):
    """Return the next check-in timestamp string (informational). §2.4"""
    if now is None:
        now = now_ist()
    t = now + timedelta(hours=offset_hours)
    return f"NEXT CHECK-IN BY: {t.strftime('%Y-%m-%d %H:%M IST')} (informational — confirmed daily cadence §2.4)"


if __name__ == "__main__":
    import json
    # Quick smoke-test with synthetic matches
    fake_matches = [
        {
            "id": "aaa",
            "name": "BRA vs ARG",
            "opening_time": (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat(),
            "open_market_count": 10,
        },
        {
            "id": "bbb",
            "name": "ESP vs GER",
            "opening_time": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
            "open_market_count": 10,
        },
    ]
    rows = triage(fake_matches, prediction_counts={"aaa": 0, "bbb": 7})
    print(tier_1_triage_summary(rows))
    print(next_checkin_str())
