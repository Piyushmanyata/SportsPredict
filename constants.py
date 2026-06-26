"""
Global constants for the Jump Trading Probability Cup bot.
Values come from the spec (§4.3). Never write prediction values here.
"""

EVENT_ID  = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID  = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

# Stage weights
STAGE_WEIGHT = {
    "group":    1,
    "r32":      2,
    "r16":      2,
    "qf":       2,
    "sf":       2,
    "final":    3,
}

# Coverage states
UNCOVERED      = "UNCOVERED"
PARTIAL        = "PARTIAL"
COVERED_STALE  = "COVERED-STALE"
COVERED_FRESH  = "COVERED-FRESH"

# Depth Pass thresholds (§6.3 / §7)
UPDATE_THRESHOLD_DEFAULT  = 3   # abs(Δ) ≥ 3 for normal markets
UPDATE_THRESHOLD_POST_XI  = 2   # abs(Δ) ≥ 2 once lineups are known (L7)

# Rate-limit back-off seconds on 429
RATE_LIMIT_BACKOFF = 45

# IST offset from UTC in hours
IST_OFFSET_HOURS = 5.5
