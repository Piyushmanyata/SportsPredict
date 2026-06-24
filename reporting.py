"""
Reporting module (§8): STATUS BLOCK, after-action reports, RBP scoreboard.
All output in plain text formatted for Claude's responses.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from feedback.outcomes import compute_rbp_scoreboard, self_expected_brier


def format_after_action_report(
    match_name: str,
    kickoff_ist: str,
    stage: str,
    horizon: str,
    markets: List[Dict],
    submission_result: Dict,
    top_edges: Optional[str] = None,
    watchlist: Optional[str] = None,
) -> str:
    """
    §8.2 After-action report for one match.

    markets: list of {market_name, mode, p_int, confidence, driver}
    submission_result: {succeeded, failed, prediction_ids}
    """
    stage_weights = {"group": "1×", "knockout": "2×", "final": "3×"}
    weight = stage_weights.get(stage.lower(), "1×")

    lines = [
        f"### {match_name}",
        f"Kickoff: {kickoff_ist} | Stage weight: {weight} | Horizon: {horizon} | Mode: mixed",
        "",
        f"{'#':<3} {'Market':<35} {'Mode':<10} {'p':>4} {'Conf':<6} {'Driver'}",
        "-" * 90,
    ]

    for i, m in enumerate(markets, 1):
        lines.append(
            f"{i:<3} {m.get('market_name',''):<35} {m.get('mode','MODELED'):<10} "
            f"{m.get('p_int',0):>4} {m.get('confidence','MED'):<6} {m.get('driver','')[:50]}"
        )

    lines.append("")

    if top_edges:
        lines.append(f"**Top edges:** {top_edges}")

    if watchlist:
        lines.append(f"**Watchlist:** {watchlist}")

    lines.append("")
    succeeded = submission_result.get("succeeded", 0)
    failed = submission_result.get("failed", 0)
    pred_ids = submission_result.get("prediction_ids", [])
    lines.append(f"**Batch:** {succeeded} succeeded / {failed} failed | IDs: {pred_ids[:5]}{'...' if len(pred_ids) > 5 else ''}")

    return "\n".join(lines)


def format_delta_report(
    match_name: str,
    changed_markets: List[Dict],
    n_unchanged: int,
) -> str:
    """
    §8.3 Depth Pass delta report — only changed markets.
    """
    lines = [f"**{match_name} — Depth Pass Delta:**"]

    if not changed_markets:
        lines.append(f"  {n_unchanged} markets re-verified, no Δ ≥ 3.")
        return "\n".join(lines)

    lines.append(f"  {'Market':<35} {'Old':>4} {'New':>4} {'Driver'}")
    lines.append("  " + "-" * 70)
    for m in changed_markets:
        lines.append(
            f"  {m.get('market_name',''):<35} {m.get('old_p',0):>4} -> {m.get('new_p',0):>4} "
            f"  {m.get('driver','')[:40]}"
        )
    if n_unchanged > 0:
        lines.append(f"  ({n_unchanged} markets re-verified, no Δ)")

    return "\n".join(lines)


def format_rbp_scoreboard(settled: List[Dict]) -> str:
    """
    §8.4 RBP scoreboard — every settle/deep audit starts with this.
    """
    sb = compute_rbp_scoreboard(settled)

    if not sb.get("available"):
        return (
            "RBP SCOREBOARD: crowd_brier unavailable — "
            "reporting raw Brier only; crowd data needed for true performance ranking."
        )

    n = sb["n_markets_with_crowd"]
    total_rbp = sb["total_weighted_rbp"]
    avg_rbp = sb["avg_rbp_per_market"]
    beat_n = sb["beat_crowd_count"]
    beat_rate = sb["beat_crowd_rate"]
    best = sb.get("best_match")
    worst = sb.get("worst_match")

    lines = [
        "RBP SCOREBOARD:",
        f"  Settled markets audited : {n}",
        f"  Total weighted RBP      : {total_rbp:+.2f}",
        f"  Avg RBP / market        : {avg_rbp:+.2f}",
        f"  Markets beat crowd      : {beat_n} / {n} ({beat_rate:.1%})",
    ]

    if best:
        best_name, best_data = best
        lines.append(f"  Best match by RBP       : {best_name} ({best_data['rbp']:+.2f})")
    if worst:
        worst_name, worst_data = worst
        lines.append(f"  Worst match by RBP      : {worst_name} ({worst_data['rbp']:+.2f})")

    return "\n".join(lines)


def format_opportunity_table(markets: List[Dict]) -> str:
    """
    §6.5 RBP Opportunity table — end of every Depth Pass.
    markets: list of {market_name, p_int, opportunity_label, driver, why_crowd_wrong}
    """
    lines = [
        f"{'Market':<35} {'p':>4} {'Opp':>8} {'Driver':<30} {'Why crowd may be wrong'}",
        "-" * 100,
    ]
    for m in markets:
        lines.append(
            f"{m.get('market_name',''):<35} {m.get('p_int',0):>4} "
            f"{m.get('opportunity_label','UNKNOWN'):>8} "
            f"{m.get('driver',''):<30} {m.get('why_crowd_wrong','')[:40]}"
        )
    return "\n".join(lines)


def format_calibration_record_line(
    n: int, realized: float, expected: float, per_match_range: str
) -> str:
    """Format a single calibration record entry for §10.4."""
    gap = realized - expected
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    from feedback.outcomes import calibration_verdict
    verdict = calibration_verdict(gap, n)

    return (
        f"@{n} ({date_str}): realized {realized:.4f} vs expected {expected:.4f} "
        f"→ gap +{gap:.4f} | verdict: {verdict} | per-match range: {per_match_range}"
    )


def opportunity_label(crowd_gap_pts: float) -> str:
    """§2.5 opportunity label from expected crowd gap."""
    if crowd_gap_pts >= 8:
        return "STRONG"
    if crowd_gap_pts >= 4:
        return "MODERATE"
    if crowd_gap_pts >= 1:
        return "THIN"
    return "UNKNOWN"


def format_session_summary(
    triage_report: Dict,
    actions: Dict,
    flags: List[str],
    session_brier: Optional[float] = None,
    expected_brier: Optional[float] = None,
    settled_n: int = 0,
    next_checkin_ist: str = "",
) -> str:
    """
    Full session summary combining STATUS BLOCK + after-action notes.
    """
    from session.protocol import format_status_block
    lines = [format_rbp_scoreboard(actions.get("settled", [])), ""]

    # Build status block
    all_statuses = (triage_report.get("near", []) +
                    triage_report.get("mid", []) +
                    triage_report.get("far", []))
    actions_str = (
        f"Depth Pass: {actions.get('depth_passes', 0)} matches / "
        f"{actions.get('dp_markets', 0)} markets · "
        f"Coverage sweep: {actions.get('pass1_matches', 0)} matches / "
        f"{actions.get('pass1_markets', 0)} markets · "
        f"top-ups: {actions.get('topups', 0)}"
    )

    status = format_status_block(
        match_statuses=all_statuses,
        settled_since_last=settled_n,
        session_brier=session_brier,
        expected_brier=expected_brier,
        actions_taken=actions_str,
        flags=flags + triage_report.get("flags", []),
        next_checkin=None,
    )
    lines.append(status)

    return "\n".join(lines)
