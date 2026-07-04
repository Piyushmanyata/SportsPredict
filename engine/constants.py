"""§4.3 verified constants — re-verify only on error, never guess."""
from datetime import timedelta

EVENT_ID = "aa5572ec-5930-4d99-b06b-f8966333d172"  # Jump Trading Probability Cup
LOBBY_ID = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"  # classic, shared, free, joined

TOURNAMENT_GROUPS = 12
TEAMS_PER_GROUP = 4
GROUP_MATCHES = 72
KNOCKOUT_MATCHES = 32
TOTAL_MATCHES = 104

STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}

IST_OFFSET = timedelta(hours=5, minutes=30)


def utc_to_ist(dt_utc):
    """§D8 — always display times in IST (UTC+5:30) with the date."""
    return dt_utc + IST_OFFSET
