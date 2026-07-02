"""Situational overlays: +/-1-4 points each, total capped at +/-8 (spec section 5.12)."""

OVERLAY_REGISTRY = {
    "must_win_vs_dead_rubber": (-4, 4),
    "rotation": (-6, -3),
    "rest_gap": (-2, 2),
    "travel_heat_unders": (2, 3),
    "altitude_lowland_favorite": (-4, -2),
    "winners_slump": (-2, -1),
    "knockout_compression": (-3, 3),
    "weather_unders": (2, 4),
    "referee_card_strict": (-8, 8),
}


def apply_overlays(base_p, overlays, cap_pts=8.0):
    """Sum named overlay deltas and cap the combined movement at +/-cap_pts."""
    raw_sum = sum(delta for _, delta in overlays)
    if abs(raw_sum) > cap_pts:
        net_delta = cap_pts if raw_sum > 0 else -cap_pts
    else:
        net_delta = raw_sum
    adjusted_p = min(1.0, max(0.0, base_p + net_delta / 100.0))
    return {
        "adjusted_p": adjusted_p,
        "total_delta_pts": net_delta,
        "capped": abs(raw_sum) > cap_pts,
        "raw_sum_pts": raw_sum,
    }


def altitude_adjustment(is_lowland_favorite_at_azteca):
    """Documented drag on a lowland favorite playing at Azteca (~2,240m)."""
    return -3.0 if is_lowland_favorite_at_azteca else 0.0


def winners_slump_adjustment(is_reigning_champion_deep_run_market):
    """Judgement-call drag on the reigning champion's deep-run/advance markets.

    Never let this move an anchored 90-min win line away from the devigged
    price -- it only applies to advance/deep-run markets, and if it ever
    conflicts with a sharp anchor, the anchor wins.
    """
    return -1.5 if is_reigning_champion_deep_run_market else 0.0


if __name__ == "__main__":
    r = apply_overlays(0.50, [("rotation", -4), ("rest_gap", -1)])
    assert r["capped"] is False
    assert abs(r["total_delta_pts"] - (-5)) < 1e-9
    assert abs(r["adjusted_p"] - 0.45) < 1e-9
    print("check 1 (under cap) OK")

    r = apply_overlays(0.50, [("rotation", -5), ("travel_heat_unders", -3), ("weather_unders", -2)])
    assert r["capped"] is True
    assert abs(r["total_delta_pts"] - (-8.0)) < 1e-9
    assert abs(r["adjusted_p"] - 0.42) < 1e-9
    print("check 2 (capped at -8) OK")

    r = apply_overlays(0.05, [("weather_unders", -10)])
    assert abs(r["adjusted_p"] - 0.0) < 1e-9
    print("check 3 (clamp to 0) OK")

    assert altitude_adjustment(True) == -3.0
    assert altitude_adjustment(False) == 0.0
    print("check 4 (altitude) OK")

    assert winners_slump_adjustment(True) == -1.5
    assert winners_slump_adjustment(False) == 0.0
    print("check 5 (winner's slump) OK")

    print("overlays.py: all checks passed")
