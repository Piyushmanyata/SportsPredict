"""
Reporting formats — §8 of the system instructions.
All times displayed in IST (UTC+5:30) per D8.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))


# ─── Time helpers ─────────────────────────────────────────────────────────────

def to_ist(dt: datetime) -> str:
    """Format a UTC-aware datetime as 'YYYY-MM-DD HH:MM IST'."""
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def now_ist() -> str:
    return to_ist(datetime.now(timezone.utc))


def next_checkin_ist(hours: float = 24.0) -> str:
    return to_ist(datetime.now(timezone.utc) + timedelta(hours=hours))


# ─── §8.1  STATUS BLOCK ───────────────────────────────────────────────────────

def status_block(
    settled_count: int,
    session_brier: float | None,
    self_expected: float | None,
    cum_rbp_note: str,
    near_matches: list[dict],
    mid_far_matches: list[dict],
    actions: dict,
    flags: list[str],
    next_checkin: str | None = None,
) -> str:
    """
    §8.1 STATUS BLOCK — opens every session unprompted.

    near_matches / mid_far_matches: list of dicts with keys:
      'name', 'kickoff_ist', 'state', 'depth_pass_done' (bool, near only).
    actions: {'depth_pass_matches', 'depth_pass_markets',
              'sweep_matches', 'sweep_markets', 'top_ups'}
    flags: list of string warnings (stale matches, gate failures, etc.)
    """
    brier_str = (
        f"session Brier {session_brier:.3f} vs self-expected {self_expected:.3f}"
        if session_brier is not None
        else "no new settlements this session"
    )

    near_lines = "\n  ".join(
        f"{m['name']} — {m['kickoff_ist']} — "
        f"Depth Pass: {'✓' if m.get('depth_pass_done') else 'PENDING'}"
        for m in near_matches
    ) or "(none in next 48h)"

    mid_far_lines = "\n  ".join(
        f"{m['name']} — {m['kickoff_ist']} — {m.get('state', 'UNCOVERED')}"
        for m in mid_far_matches
    ) or "(none in next 7d)"

    flags_str = " · ".join(flags) if flags else "none"
    checkin = next_checkin or next_checkin_ist(24)

    dp = actions.get
    return (
        f"STATUS — {now_ist()}\n"
        f"Settled since last: {settled_count} markets | {brier_str} | {cum_rbp_note}\n"
        f"Near horizon (<48h IST):\n"
        f"  {near_lines}\n"
        f"Mid/far horizon (≤7d IST):\n"
        f"  {mid_far_lines}\n"
        f"Actions this session:\n"
        f"  Depth Pass: {dp('depth_pass_matches',0)} matches / {dp('depth_pass_markets',0)} markets\n"
        f"  Coverage sweep: {dp('sweep_matches',0)} matches / {dp('sweep_markets',0)} markets\n"
        f"  Top-ups: {dp('top_ups',0)}\n"
        f"Flags: {flags_str}\n"
        f"NEXT CHECK-IN BY: {checkin}"
    )


# ─── §8.2  AFTER-ACTION REPORT ────────────────────────────────────────────────

def after_action_report(
    match_name: str,
    kickoff_ist: str,
    stage: str,
    horizon: str,
    markets: list[dict],
    top_edges: list[str],
    watchlist: list[str],
    batch_result: dict,
) -> str:
    """
    §8.2 AFTER-ACTION REPORT per match.

    markets: list of dicts — {'num', 'market', 'mode', 'p', 'conf', 'driver'}
    top_edges: 2–3 sentences on biggest edges.
    watchlist: news that would move any number ≥3.
    batch_result: {'succeeded': int, 'failed': int, 'prediction_ids': [str]}
    """
    from state import STAGE_WEIGHTS
    weight = STAGE_WEIGHTS.get(stage, 1)

    header = (
        f"── {match_name} ──\n"
        f"Kickoff: {kickoff_ist}  |  Stage: {stage} ({weight}×)  |  "
        f"Horizon: {horizon}"
    )
    sep = "─" * 76

    col = "  {:>2}  {:<38}  {:>10}  {:>3}  {:>5}  {}"
    table_hdr = col.format("#", "Market", "Mode", "p", "Conf", "Driver")
    rows = "\n".join(
        col.format(
            m.get('num', i + 1),
            m.get('market', m.get('question', '?'))[:38],
            m.get('mode', 'MODELED'),
            m.get('p', '?'),
            m.get('conf', 'MED'),
            m.get('driver', '—')[:50],
        )
        for i, m in enumerate(markets)
    )

    edges_str = "\n".join(f"  • {e}" for e in top_edges) or "  (none noted)"
    watch_str = "\n".join(f"  • {w}" for w in watchlist) or "  (none)"
    batch_str = (
        f"Batch: {batch_result.get('succeeded', 0)} succeeded / "
        f"{batch_result.get('failed', 0)} failed"
    )
    ids = batch_result.get('prediction_ids', [])
    ids_str = f"  IDs: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}" if ids else ""

    return "\n".join([
        header, sep, table_hdr, sep, rows, sep,
        "Top edges:", edges_str,
        "Watchlist:", watch_str,
        batch_str, ids_str,
    ])


# ─── §8.3  DEPTH PASS DELTA REPORT ───────────────────────────────────────────

def depth_pass_delta(
    match_name: str,
    changes: list[dict],
    unchanged_count: int,
) -> str:
    """
    §8.3: only changed markets listed; unchanged in one line.
    changes: list of {'market', 'old', 'new', 'driver'}
    """
    if not changes:
        return (
            f"DEPTH PASS Δ — {match_name}: "
            f"{unchanged_count} markets re-verified, no Δ ≥ 3"
        )
    change_lines = "\n".join(
        f"  {c['market']}: {c['old']} → {c['new']} | {c['driver']}"
        for c in changes
    )
    suffix = (
        f"\n  ({unchanged_count} others re-verified, no Δ ≥ 3)"
        if unchanged_count > 0 else ""
    )
    return f"DEPTH PASS Δ — {match_name}:\n{change_lines}{suffix}"


# ─── §8.4  RBP SCOREBOARD ────────────────────────────────────────────────────

def rbp_scoreboard(stats: dict, best_match: str = "n/a",
                   worst_match: str = "n/a", best_brier_match: str = "n/a") -> str:
    """
    §8.4 RBP scoreboard block. Leads every settle/deep-audit report.
    stats: output of feedback.aggregate_rbp().
    """
    if not stats.get('available', True):
        return (
            "RBP SCOREBOARD\n"
            "  crowd_brier unavailable — run §9.5 raw calibration audit only.\n"
            "  Leaderboard RBP requires front-end or crowd data."
        )

    def row(label: str, value: Any) -> str:
        return f"  {label:<30} {value}"

    lines = [
        "RBP SCOREBOARD",
        "  " + "─" * 50,
        row("Settled markets audited",    stats.get('n_markets', 0)),
        row("Total weighted RBP",         f"{stats.get('total_weighted_rbp', 0):.2f}"),
        row("Avg RBP / market",           f"{stats.get('avg_rbp_per_market', 0):.3f}"),
        row("Markets beat crowd",
            f"{stats.get('beat_crowd_count', 0)} / {stats.get('n_markets', 0)} "
            f"({stats.get('beat_crowd_pct', 0):.1f}%)"),
        row("Best match by RBP",          best_match),
        row("Worst match by RBP",         worst_match),
        row("Best raw-Brier match [2°]",  best_brier_match),
        "  " + "─" * 50,
    ]
    return "\n".join(lines)


# ─── §2.5  Opportunity register table ────────────────────────────────────────

def opportunity_register(markets: list[dict]) -> str:
    """
    §5.13 crowd-edge register table for a Depth Pass.
    markets: list of {'market', 'p', 'anchor', 'crowd_bias', 'opportunity', 'action'}
    """
    col = "  {:<35}  {:>3}  {:<25}  {:>15}  {:<10}  {}"
    header = col.format(
        "Market", "p", "Anchor / model basis",
        "Est. crowd bias", "Opportunity", "Action"
    )
    sep = "  " + "─" * 110
    rows = "\n".join(
        col.format(
            m.get('market', '?')[:35],
            m.get('p', '?'),
            str(m.get('anchor', '—'))[:25],
            str(m.get('crowd_bias', '—'))[:15],
            m.get('opportunity', 'UNKNOWN'),
            m.get('action', '—')[:40],
        )
        for m in markets
    )
    return f"CROWD-EDGE REGISTER\n{header}\n{sep}\n{rows}"


# ─── §9.5  Deep-audit report ─────────────────────────────────────────────────

def deep_audit_report(
    n: int,
    realized: float,
    expected: float,
    verdict: str,
    sigma: str,
    per_match: list[dict],
    band_decomp: list[dict],
    rbp_stats: dict,
    new_lessons: list[str],
) -> str:
    """Full §9.5 deep-audit report combining RBP scoreboard + raw calibration."""
    gap = realized - expected
    lines = [
        f"DEEP AUDIT — @{n} settled",
        f"Realized Brier:  {realized:.4f}",
        f"Self-expected:   {expected:.4f}",
        f"Gap:             +{gap:.4f} ({sigma}σ) — {verdict}",
        "",
        rbp_scoreboard(rbp_stats),
        "",
        "PER-MATCH BRIER (dominant variance axis):",
    ]
    for m in per_match:
        lines.append(f"  {m['match']:<25}  n={m['n']:<3}  avg Brier {m['avg_brier']:.3f}")

    lines += ["", "BAND DECOMPOSITION:"]
    bh = f"  {'Band':<12} {'n':>4} {'Pred%':>6} {'Hit%':>6} {'Gap pp':>7} {'σ':>6} {''}"
    lines.append(bh)
    for b in band_decomp:
        lines.append(
            f"  {b['band']:<12} {b['n']:>4} {b['avg_predicted_pct']:>6.1f} "
            f"{b['hit_rate_pct']:>6.1f} {b['gap_pp']:>+7.1f} {b['sigma']:>6.2f} {b.get('flag','')}"
        )

    if new_lessons:
        lines += ["", "NEW / UPDATED LEDGER ENTRIES:"]
        lines.extend(f"  • {l}" for l in new_lessons)

    return "\n".join(lines)
