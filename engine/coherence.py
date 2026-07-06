"""§5.11 coherence gates + correlation cap -- run before every batch write."""


def check_1x2_sum(p_home, p_draw, p_away, tol=2):
    total = (p_home + p_draw + p_away) * 100
    return {"ok": abs(total - 100) <= tol, "total": total}


def check_ou_monotone(prob_by_threshold):
    """prob_by_threshold: {goal_threshold: P(over threshold)} -- must be
    non-increasing as the threshold rises."""
    items = sorted(prob_by_threshold.items())
    for (t0, p0), (t1, p1) in zip(items, items[1:]):
        if p1 > p0 + 1e-9:
            return {"ok": False, "violation": (t0, p0, t1, p1)}
    return {"ok": True}


def check_complement(p_a, p_b, tol=2):
    """e.g. clean_sheet_a vs 'opponent scores' should sum to ~100."""
    total = (p_a + p_b) * 100
    return {"ok": abs(total - 100) <= tol, "total": total}


def check_joint_leq_marginals(p_joint, p_marginal_a, p_marginal_b):
    ok = p_joint <= min(p_marginal_a, p_marginal_b) + 1e-9
    return {"ok": ok, "p_joint": p_joint, "min_marginal": min(p_marginal_a, p_marginal_b)}


def check_anchor_deviation(final_p, anchor_p, tol=10):
    """|final - anchor| > 10 requires a written concrete cause, else regress
    to anchor (§5.11.2 / §13 'sharp anchor is innocent until proven guilty')."""
    deviation = (final_p - anchor_p) * 100
    return {"ok": abs(deviation) <= tol, "deviation": deviation}


def clamp_noisy(p, lo=0.15, hi=0.85, near_certainty_floor=0.03, near_certainty_ceiling=0.97):
    """Noisy register clamp: 15-85 unless anchored; reserve <=3 />=97 for
    near-certainties with concrete drivers (call with those bounds explicitly
    when a concrete driver justifies it)."""
    return max(lo, min(hi, p))


def correlation_axis_flag(markets_on_same_axis, total_markets=10, threshold=4):
    """L8: if more than `threshold` of `total_markets` share a latent axis,
    this match must go into the batched MC call (mc_batch.batch_mc), not be
    priced as independent deterministic point estimates."""
    return markets_on_same_axis > threshold


def situational_overlay_cap(overlay_points, cap=8):
    """§5.12: situational overlays are capped at +/-8 total."""
    total = sum(overlay_points)
    capped = max(-cap, min(cap, total))
    return {"raw_total": total, "capped_total": capped, "was_capped": capped != total}
