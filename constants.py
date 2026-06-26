"""
Jump Trading Probability Cup — shared constants and configuration.
Event ID / Lobby ID verified live per §4.3. Update EB_TRACKER and
CALIBRATION_RECORD in place at every settle audit (§5.8 / §10.4).
"""

# §4.3 Verified constants
EVENT_ID = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

# §1.1 Stage weights
STAGE_WEIGHTS = {
    "group":    1,
    "r32":      2,
    "r16":      2,
    "qf":       2,
    "sf":       2,
    "knockout": 2,
    "final":    3,
}

# §5.2 O/U 2.5 → expected total goals T lookup table
OU25_TO_T = [
    (0.32, 2.0),
    (0.38, 2.2),
    (0.46, 2.5),
    (0.51, 2.7),
    (0.58, 3.0),
    (0.64, 3.3),
]

# §5.2 Reference λ splits and BTTS/P(1-1)/BTTS&3+ grid
LAMBDA_SPLITS = {
    "even":    {"lam_a": 1.35, "lam_b": 1.35, "btts": 55, "p11": 12, "btts3plus": 43},
    "mod_fav": {"lam_a": 1.65, "lam_b": 1.05, "btts": 52, "p11": 12, "btts3plus": 41},
    "strong":  {"lam_a": 2.00, "lam_b": 0.75, "btts": 46, "p11": 10, "btts3plus": 36},
    "heavy":   {"lam_a": 2.40, "lam_b": 0.55, "btts": 38, "p11":  7, "btts3plus": 32},
}

# §5.4 Tie-trap reference means and exact tie mass / "A more" for even matchups
TIE_TRAP_REF = {
    "fouls":      {"m": 11.0, "tie_pct": 8.6,  "even_more": 46},
    "corners_ft": {"m":  4.5, "tie_pct": 13.5, "even_more": 43},
    "corners_2h": {"m":  2.4, "tie_pct": 18.8, "even_more": 41},
    "corners_ht": {"m":  2.1, "tie_pct": 20.2, "even_more": 40},
    "sot_2h":     {"m":  2.0, "tie_pct": 20.7, "even_more": 40},
    "cards":      {"m":  1.8, "tie_pct": 21.9, "even_more": 39},
    "offsides":   {"m":  1.5, "tie_pct": 24.3, "even_more": 38},
}

# §5.5 Cards table: lam_cards → {P(≥4 total), P(≥2 in 2H)}; 2H share ≈ 0.62
CARDS_TABLE = {
    2.8: {"gte4": 0.31, "gte2_2h": 0.52},
    3.2: {"gte4": 0.40, "gte2_2h": 0.59},
    3.5: {"gte4": 0.46, "gte2_2h": 0.64},
    4.0: {"gte4": 0.57, "gte2_2h": 0.71},
    4.5: {"gte4": 0.66, "gte2_2h": 0.77},
}

# §5.5 Team corners λ → P(≥5)
CORNERS_TABLE = {3.0: 0.19, 3.5: 0.28, 4.0: 0.37, 4.5: 0.47,
                 5.0: 0.56, 5.5: 0.64, 6.0: 0.72}

# §5.5 Team SOT λ → P(≥2)
SOT_GTE2_TABLE = {1.0: 0.26, 1.5: 0.44, 2.0: 0.59, 2.5: 0.71,
                  3.0: 0.80, 3.5: 0.86, 4.0: 0.91, 4.5: 0.94}

# §5.5 Team offsides λ → P(≥2)
OFFSIDES_TABLE = {0.8: 0.19, 1.0: 0.26, 1.2: 0.34,
                  1.5: 0.44, 1.8: 0.54, 2.0: 0.59}

# §5.5 HT-tied reference table (integer probabilities, %)
HT_TIED_TABLE = {
    ("even",  2.2): 47,
    ("even",  2.5): 44,
    ("even",  2.7): 42,
    ("even",  3.0): 39,
    ("mod_fav", None): 41,
    ("strong",  None): 38,
    ("heavy",   None): 34,
}

# §5.6 Player prop SOT bands (v8, L10 ACTIVE — input-side correction applied)
PLAYER_SOT_BANDS = {
    "main_striker": (52, 64),    # was 60-72, lowered per L10 @118
    "winger_am":    (42, 56),
    "secondary":    (30, 44),
}
PLAYER_GOAL_BANDS = {
    "star_striker": (32, 45),
    "secondary":    (18, 28),
    "mid":          (8, 15),
}

# §5.8 Live base-rate tracker (update in place at every settle audit)
EB_TRACKER = {
    "penalty": {
        "n": 5, "hits": 1, "prior": 0.34, "posterior": 0.29,
        "note": "n≈5 @118, ~20%, noisy; stay on prior per L5",
    },
    "red_card": {
        "n": 0, "hits": 0, "prior": 0.06, "posterior": 0.06,
        "note": "unconfirmed",
    },
    "pen_or_red": {
        "n": 5, "hits": 1, "prior": 0.31, "posterior": 0.31,
        "note": "n≈5 @118, ~20%, noisy-register — stay on prior",
    },
    "cards_mean": {
        "n": 0, "observed": None, "prior": 3.5,
        "note": "small-n, no strong signal yet",
    },
    "goals_per_match_group": {
        "n": 0, "observed": None, "prior": 2.55,
        "note": "mixed across 12 matches @118, no strong drift",
    },
}

# §5.9 Noisy market register — clamp 15-85 unless anchored
NOISY_MARKET_KEYWORDS = [
    "penalty", "red card", "pen or red", "pen/red",
    "2h cards", "cards in 2h",
    "ht sot", "2h sot", "sot comparison",
    "offside", "ht corner comparison", "2h corner comparison",
    "leads at ht", "lead at halftime",
]

# §10 Lessons ledger
LESSONS = {
    "L1":  {"grade": "CONFIRMED",   "summary": "Use power-corrected devigged win line; no host/fav overlay"},
    "L2":  {"grade": "ACTIVE",      "summary": "Even matchups carry heavy draw mass; don't overprice either win"},
    "L2b": {"grade": "PENDING",     "summary": "+2-3 to stronger side in even matchups (n~1-2, do not apply)"},
    "L3":  {"grade": "CONFIRMED",   "summary": "Strict 'more than' loses on ties; use §5.4 table; n=32 @118"},
    "L4":  {"grade": "ACTIVE",      "summary": "1+SOT >> goal as value market (see L7/L10 risk)"},
    "L5":  {"grade": "CONFIRMED",   "summary": "Pen/red = noise; stay near base rates; absorb bad Briers"},
    "L6":  {"grade": "PROVISIONAL", "summary": "T-floor: never drag T >0.1 below anchor; no-anchor +0.2-0.3 bump"},
    "L7":  {"grade": "ACTIVE",      "summary": "Discount inside λ-allocation (not output) for rotation; DP post-lineup mandatory"},
    "L8":  {"grade": "ACTIVE",      "summary": ">4 markets on one axis → proactive batched MC; risk = per-match swing"},
    "L9":  {"grade": "ACTIVE",      "summary": "HT-tied ceiling 47 unless anchor-implied T < 2.2"},
    "L10": {"grade": "ACTIVE",      "summary": "56-70% band hot (−16.8pt, n=18); striker SOT band lowered 52-64; driver gate for top-half 56-70"},
    "L11": {"grade": "PROVISIONAL", "summary": "50-55% band cold (+8.2pt, n=13, weakening); track, do not bump outputs"},
    "L12": {"grade": "ACTIVE",      "summary": "Win markets hot (0.303 vs 0.209 Brier, n=10); hardened DC draw inflation in 40-60 win band"},
    "L13": {"grade": "CONFIRMED",   "summary": "Performance ranking: RBP-first, not raw Brier"},
    "L14": {"grade": "CONFIRMED",   "summary": "Goal overdispersion vs Poisson: extra 0-0/clean-sheet mass; fatter 4+ tail"},
    "L15": {"grade": "ACTIVE",      "summary": "Fav-longshot crowd bias: research-allocation flag only, never a fade rule"},
}

# §10.4 Calibration record — append at every deep audit
CALIBRATION_RECORD = [
    {"n":  20, "realized": 0.2356, "expected": 0.2214, "gap": +0.0142, "sigma": "0.5σ",         "verdict": "GREEN"},
    {"n":  79, "realized": 0.2467, "expected": 0.2225, "gap": +0.0242, "sigma": "1.2-1.8σ",     "verdict": "AMBER"},
    {"n": 118, "realized": 0.2326, "expected": 0.2173, "gap": +0.0152, "sigma": "0.92-1.38σ",   "verdict": "AMBER→GREEN"},
]

# §5.10 Debias thresholds (input-level only)
DEBIAS_POLICY = {
    "llm_intuition_haircut": 0.15,   # 10-20% on LLM-intuition inputs
    "evidence_gate_n":       30,     # n≥30 per class to apply output shade
    "evidence_shrinkage":    0.5,    # observed_drift × 0.5
    "strong_opp_threshold":  8,      # crowd gap ≥8 → STRONG
    "moderate_opp_threshold": 4,     # 4-7 → MODERATE
}
