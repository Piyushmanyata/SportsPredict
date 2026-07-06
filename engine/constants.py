"""Verified constants and standing parameters (spec §0, §4.3, §5.8, §5.9, §5.12).

Only constants, procedures and priors live here — never prediction values (D10).
"""

# --- §4.3 verified platform constants (re-verify only on error) ---
EVENT_ID = "aa5572ec-5930-4d99-b06b-f8966333d172"   # Jump Trading Probability Cup
LOBBY_ID = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"   # classic, shared, free, joined

# list_events quirk: `type` returns a UUID-like string, not "probability" —
# identify the event by id/title, never by type filter.

# Tournament shape: 48 teams, 12 groups of 4, 72 group + 32 knockout = 104
# matches, June 11 - July 19 2026.

# --- §1.1 stage weights ---
STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}

# --- D3/D6 mechanics ---
P_MIN, P_MAX = 1, 99          # integers only; avoid exactly 50 (breaks §9.2 decode)
BATCH_LIMIT = 50              # submit_predictions_batch max entries
RATE_LIMIT_PER_MIN = 60       # global per-IP; on 429 back off 30-60s

# --- §5.9 noisy market register: clamp 15-85 unless anchored, confidence LOW ---
NOISY_REGISTER = (
    "penalty awarded", "red card", "pen or red", "2h cards",
    "ht/2h sot comparison", "offside count", "ht/2h corner comparison",
    "leads at ht",
)
NOISY_CLAMP = (15, 85)

# --- §5.8 empirical-Bayes base-rate tracker (priors; update working values at
#     each settle audit: posterior = (observed + k*prior) / (n + k)) ---
EB_K_EARLY, EB_K_LATE = 7, 15   # k=7 first ~30 matches / n<10 per type, then 15
BASE_RATES = {
    "pen_per_match":   {"prior": 0.36, "working_p": 29},
    "red_per_match":   {"prior": 0.06, "working_p": 6},
    "pen_or_red":      {"prior": None, "working_p": 31},
    "cards_mean":      {"prior": 3.5,  "working_p": None},
    "goals_per_match": {"prior": 2.55, "working_p": None},
}

# --- §5.2 typical per-team stat means (tie-trap / threshold defaults) ---
STAT_MEANS = {
    "fouls": 11.0, "corners_ft": 4.5, "corners_2h": 2.4, "corners_ht": 2.1,
    "sot_2h": 2.0, "cards": 1.8, "offsides": 1.5,
}
SECOND_HALF_GOAL_SHARE = 0.55   # 2H share of T; HT share = 0.45
SECOND_HALF_CARD_SHARE = 0.62
HT_SOT_SHARE = 0.45

# --- §5.6 player-prop bands (v8: L10 ACTIVE input-side correction) ---
ANYTIME_GOAL_BANDS = {"star_striker": (32, 45), "secondary": (18, 28), "mid": (8, 15)}
SOT_BANDS = {"main_striker": (52, 64), "winger_am": (42, 56)}  # 60-72 band RETIRED
# Driver gate: any MODELED p in the top half of 56-70 requires an explicit
# written driver, else regress toward the lower band edge (§5.6, L10).
DRIVER_GATE_BAND = (56, 70)

# --- §5.11 gates ---
ANCHOR_DEVIATION_GATE = 10    # |final - anchor| > 10 needs a written cause
CORRELATION_AXIS_GATE = 4     # >4 of ~10 markets on one axis -> L8 MC
MC_DEFAULT_SIGMA_FRAC = 0.15  # sigma = 0.15 * lambda_hat placeholder (log it)
UPDATE_DELTA = 3              # update only abs(delta) >= 3
UPDATE_DELTA_POST_LINEUP = 2  # player props once lineups known (L7)

# --- §5.12 situational overlays: each +/-1..4, total cap +/-8 ---
OVERLAY_TOTAL_CAP = 8
DC_OVERDISPERSION_CAP = 3     # combined Dixon-Coles + overdispersion tilt (§5.2.1)

# --- §5.5 standing rule L9 ---
HT_TIED_CEILING = 47          # unless anchor-implied T < 2.2

# --- §9.1 noise bands: sd of mean Brier ~ 0.15/sqrt(n) (range 0.12-0.18) ---
BRIER_SD_PER_MARKET = 0.15
