"""Verified constants and standing registers (§4.3, §5.8, §5.9, §1.1).

Re-verify IDs only on API error. Base-rate working values are the §5.8 EB
tracker — update them in the spec file at every settle audit; the copies here
are engine defaults, not the live ledger.
"""

# §4.3 — verified constants (re-verify only on error)
EVENT_ID = "aa5572ec-5930-4d99-b06b-f8966333d172"   # Jump Trading Probability Cup
LOBBY_ID = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"   # classic, shared, free, joined
# Live quirk: list_events returns `type` as a UUID-like string — identify the
# event by id/title, never by filtering type == "probability".

TOURNAMENT_SHAPE = {
    "teams": 48, "groups": 12, "group_matches": 72,
    "knockout_matches": 32, "total_matches": 104,
    "dates": "2026-06-11 → 2026-07-19",
}

# §1.1 — stage weights
STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}

# D5/D6 — API discipline
MAX_BATCH = 50            # submit_predictions_batch limit
RATE_LIMIT_PER_MIN = 60   # global per-IP; on 429 back off 30–60 s

# §5.8 — EB base-rate tracker (working values; spec file is the ledger of record)
BASE_RATES = {
    "penalty_awarded": 0.34,   # → P(pen) ≈ 29
    "red_card": 0.06,          # P ≈ 5–8
    "pen_or_red": 0.31,        # union, small overlap
    "match_cards_mean": 3.5,
    "goals_per_match_group": 2.55,
}
EB_K_EARLY = 7    # first ~30 matches (or until n>=10 for the event type)
EB_K_LATE = 15


def eb_posterior(observed: float, n_matches: int, prior: float, k: int | None = None) -> float:
    """§5.8 empirical-Bayes posterior rate = (observed + k·prior)/(n + k)."""
    if k is None:
        k = EB_K_EARLY if n_matches < 30 else EB_K_LATE
    return (observed + k * prior) / (n_matches + k)


# §5.9 — noisy market register (confidence ceiling = LOW, clamp 15–85 unless anchored)
NOISY_REGISTER = {
    "penalty_awarded", "red_card", "pen_or_red", "cards_2h",
    "ht_sot_comparison", "2h_sot_comparison", "offside_count",
    "ht_corner_comparison", "2h_corner_comparison", "leads_at_ht",
}

# §5.4 — canonical per-team means for strict-comparison stats
STAT_MEANS = {
    "fouls": 11.0,
    "corners_ft": 4.5,
    "corners_2h": 2.4,
    "corners_ht": 2.1,
    "sot_2h": 2.0,
    "cards": 1.8,
    "offsides": 1.5,
}

# §5.2 — half-time goal shares
SHARE_2H = 0.55
SHARE_1H = 0.45
CARDS_SHARE_2H = 0.62  # §5.5

# §5.12 — situational overlay cap (total, probability points)
OVERLAY_CAP_PTS = 8

# §6.3 / L7 — update thresholds (probability points)
UPDATE_DELTA = 3
UPDATE_DELTA_POST_LINEUP = 2
