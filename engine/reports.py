"""§8 — reporting formats. Renders the exact block shapes so a session
doesn't reinvent formatting from scratch each time."""


def status_block(date_ist, settled_since_last, session_brier, self_expected_brier,
                   cum_rbp_note, near_horizon_rows, mid_far_rows, actions_taken, flags, next_checkin_ist):
    near = "\n".join(f"  - {r}" for r in near_horizon_rows) or "  (none)"
    mid_far = "\n".join(f"  - {r}" for r in mid_far_rows) or "  (none)"
    return (
        f"STATUS — {date_ist}\n"
        f"Settled since last: {settled_since_last} markets | session Brier "
        f"{session_brier:.4f} vs self-expected {self_expected_brier:.4f} | {cum_rbp_note}\n"
        f"Near horizon (<48h, IST):\n{near}\n"
        f"Mid/far horizon (<=7d, IST):\n{mid_far}\n"
        f"Actions taken this session: {actions_taken}\n"
        f"Flags: {flags}\n"
        f"NEXT CHECK-IN BY: {next_checkin_ist}"
    )


def after_action_report(match_header, market_rows, edge_notes, watchlist, batch_result):
    """market_rows: iterable of (n, market, mode, p, conf, driver)."""
    lines = [match_header, "# | Market | Mode | p | Conf | Driver"]
    for n, market, mode, p, conf, driver in market_rows:
        lines.append(f"{n} | {market} | {mode} | {p} | {conf} | {driver}")
    lines.append("")
    lines.append(edge_notes)
    lines.append(f"Watchlist: {watchlist}")
    lines.append(f"Batch: {batch_result}")
    return "\n".join(lines)


def depth_pass_delta_report(changed_rows, unchanged_count):
    if not changed_rows:
        return f"{unchanged_count} markets re-verified, no delta >= 3."
    lines = ["Market | old -> new | driver"]
    for market, old, new, driver in changed_rows:
        lines.append(f"{market} | {old} -> {new} | {driver}")
    return "\n".join(lines)


def rbp_scoreboard_block(settled_audited, total_weighted_rbp, avg_rbp_per_market,
                          beat_crowd, best_match_rbp, worst_match_rbp, best_raw_brier_match):
    return (
        f"Settled markets audited | {settled_audited}\n"
        f"Total weighted RBP      | {total_weighted_rbp:.2f}\n"
        f"Avg RBP / market        | {avg_rbp_per_market:.3f}\n"
        f"Markets beat crowd      | {beat_crowd}\n"
        f"Best match by RBP       | {best_match_rbp}\n"
        f"Worst match by RBP      | {worst_match_rbp}\n"
        f"Best raw-Brier match    | {best_raw_brier_match} (secondary)"
    )
