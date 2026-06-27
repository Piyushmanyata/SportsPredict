"""
Verified constants for the Jump Trading Probability Cup (v8).
Pull live: match list, predictions, results, markets.
These values persist: IDs, procedures, lessons, calibration records.
"""

EVENT_ID  = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID  = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}

# §5.8 Live base-rate tracker (update after every settle audit)
BASE_RATES = {
    "penalty_per_match": 0.34,   # P ≈ 29
    "red_card_per_match": 0.06,  # P ≈ 5-8
    "pen_or_red_per_match": 0.31, # P ≈ 31 (union, small overlap)
    "match_cards_mean": 3.5,
    "goals_per_match_group": 2.55,
}

# §5.9 Noisy market register - these get clamped 15-85 unless anchored
NOISY_MARKETS = {
    "penalty_awarded", "red_card", "pen_or_red",
    "cards_2h", "ht_sot_comparison", "sot_2h_comparison",
    "offside_count", "ht_corner_comparison", "2h_corner_comparison",
    "leads_at_ht",
}

# §10 Lessons ledger grades
LESSON_GRADES = {
    "L1":  "CONFIRMED",   # Don't overrate hosts/favorites
    "L2":  "ACTIVE",      # Draw mass in even matchups
    "L2b": "PENDING",     # +2-3 stronger side in even matchups
    "L3":  "CONFIRMED",   # Tie-trap engine (n=32)
    "L4":  "ACTIVE",      # 1+SOT >> goal as value market
    "L5":  "CONFIRMED",   # Pen/red = noise
    "L6":  "PROVISIONAL", # T-floor for technical even matchups
    "L7":  "ACTIVE",      # Striker SOT: discount inside λ allocation
    "L8":  "ACTIVE",      # Correlation cap + proactive MC
    "L9":  "ACTIVE",      # HT-tied ceiling 47
    "L10": "ACTIVE",      # 56-70% band runs hot
    "L11": "PROVISIONAL", # 50-55% band runs cold (weakening)
    "L12": "ACTIVE",      # Win markets run hot (n=10)
    "L13": "CONFIRMED",   # RBP-first ranking
    "L14": "CONFIRMED",   # Goal overdispersion vs Poisson
    "L15": "ACTIVE",      # Favourite-longshot crowd bias (research signal)
}

# §10.4 Calibration record
CALIBRATION_RECORD = [
    {"n": 20,  "realized": 0.2356, "expected": 0.2214, "gap": 0.0142, "verdict": "GREEN"},
    {"n": 79,  "realized": 0.2467, "expected": 0.2225, "gap": 0.0242, "verdict": "AMBER"},
    {"n": 118, "realized": 0.2326, "expected": 0.2173, "gap": 0.0152, "verdict": "AMBER→GREEN"},
]
