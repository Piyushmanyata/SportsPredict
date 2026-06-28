"""
Verified constants from §4.3. Do not edit without re-verifying against live API.
"""

EVENT_ID   = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID   = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

# Rate limit: 60 req/min shared across all tools
RATE_LIMIT_PER_MIN = 60
BATCH_MAX          = 50       # submit_predictions_batch ceiling (D6)
RATE_429_BACKOFF   = 45       # seconds to sleep on 429

# Prediction horizons (seconds from kickoff)
NEAR_HORIZON_SEC  = 48 * 3600   # <48h → Depth Pass required
MID_HORIZON_SEC   = 7 * 24 * 3600  # <7d → PASS-1 sweep
ZERO_MISS_SEC     = 12 * 3600  # T−12h hard lock (D1)
DEPTH_PASS_SEC    = 24 * 3600  # T−24h Depth Pass deadline (D1)

# Probability bounds
P_MIN = 1
P_MAX = 99
NOISY_REGISTER_LOW  = 15   # §5.9 clamp
NOISY_REGISTER_HIGH = 85

# Stage weights for RBP
STAGE_WEIGHTS = {
    "group":    1.0,
    "knockout": 2.0,
    "final":    3.0,
}

# Dixon-Coles / overdispersion adjustments (§5.2.1)
DC_DRAW_BONUS_TIGHT    = 2    # pts to add to draw in tight matchups
DC_BTTS_PENALTY_DEF    = 2    # pts to remove from BTTS in defensive matchups
OD_GOALLESS_ADD        = 1    # pts to add to 0-0 / clean sheet (overdispersion)
OD_FOURPLUS_ADD        = 1    # pts to add to 4+ goals (fat tail)

# L8 correlation cap threshold
L8_AXIS_MARKET_THRESHOLD = 4  # >4 markets on one axis → batched MC

# Coherence gate tolerances (§5.11)
TRIPLET_SUM_TOLERANCE = 2     # 1X2 must sum to 100 ± 2
COMPLEMENT_TOLERANCE  = 2     # p + complement must be 100 ± 2

# Audit graduation thresholds (§9.4)
LESSON_ACTIVE_N    = 8
LESSON_CONFIRMED_N = 20

# IST offset
IST_OFFSET_HOURS = 5.5
