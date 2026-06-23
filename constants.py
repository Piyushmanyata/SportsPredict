"""
Jump Trading Probability Cup — Shared constants, tables, and spec references.
v8 spec (probability-cup-system-instructions-v8-final.md).
"""

# ── Verified IDs (§4.3) ───────────────────────────────────────────────────────
EVENT_ID = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

# ── Stage weights (§1.1) ─────────────────────────────────────────────────────
STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}

# ── Update thresholds (§6.3) ─────────────────────────────────────────────────
UPDATE_THRESHOLD_DEFAULT = 3          # abs(delta) >= 3 to update
UPDATE_THRESHOLD_POST_LINEUP = 2      # drops to 2 for player props once lineups known (L7)

# ── §5.2 O/U 2.5 → T reference grid ─────────────────────────────────────────
# (P_over, T, P_le2, P_00, P_2h_ge2)
OU_TO_T_GRID = [
    (0.32, 2.0, 68, 14, 30),
    (0.38, 2.2, 62, 11, 34),
    (0.46, 2.5, 54,  8, 40),
    (0.51, 2.7, 49,  7, 44),
    (0.58, 3.0, 42,  5, 49),
    (0.64, 3.3, 36,  4, 54),
]

# ── §5.2 BTTS/combo grid (exact, reference splits) ──────────────────────────
# (description, lam_a, lam_b, BTTS, P11, BTTS3plus)
BTTS_GRID = [
    ("even 1.35/1.35",   1.35, 1.35, 55, 12, 43),
    ("mod fav 1.65/1.05",1.65, 1.05, 52, 12, 41),
    ("strong 2.0/0.75",  2.00, 0.75, 46, 10, 36),
    ("heavy 2.4/0.55",   2.40, 0.55, 38,  7, 32),
]

# ── §5.4 Tie-trap reference table ─────────────────────────────────────────────
# (stat, per_team_mean_m, tie_pct, even_matchup_a_more)
TIE_TRAP_TABLE = [
    ("fouls",       11.0, 8.6,  46),
    ("FT corners",   4.5, 13.5, 43),
    ("2H corners",   2.4, 18.8, 41),
    ("HT corners",   2.1, 20.2, 40),
    ("2H SOT",       2.0, 20.7, 40),
    ("cards",        1.8, 21.9, 39),
    ("offsides",     1.5, 24.3, 38),
]

# ── §5.5 Threshold tables (exact Poisson / Bessel) ───────────────────────────

# Match cards λ → tail probabilities
# (lam, P_ge4_total, P_ge2_in_2h)
CARDS_TABLE = [
    (2.8, 31, 52),
    (3.2, 40, 59),
    (3.5, 46, 64),
    (4.0, 57, 71),
    (4.5, 66, 77),
]

# Team corners λ → P(≥5)
CORNERS_GE5 = {
    3.0: 19, 3.5: 28, 4.0: 37, 4.5: 47,
    5.0: 56, 5.5: 64, 6.0: 72,
}

# Team SOT λ → P(≥2)
SOT_GE2 = {
    1.0: 26, 1.5: 44, 2.0: 59, 2.5: 71,
    3.0: 80, 3.5: 86, 4.0: 91, 4.5: 94,
}

# Team offsides λ → P(≥2)
OFFSIDES_GE2 = {
    0.8: 19, 1.0: 26, 1.2: 34,
    1.5: 44, 1.8: 54, 2.0: 59,
}

# HT-tied table (§5.5): (situation, ht_tied_pct)
HT_TIED_TABLE = [
    ("even split, T=2.2",        47),
    ("even split, T=2.5",        44),
    ("even split, T=2.7",        42),
    ("even split, T=3.0",        39),
    ("mod fav 1.65/1.05",        41),
    ("strong 2.0/0.75",          38),
    ("heavy 2.4/0.55",           34),
]
HT_TIED_CEILING = 47  # L9 standing rule

# HT both teams ≥1 SOT reference (FT SOT pairs)
# (lam_a_ft, lam_b_ft, p_both_ht_sot)
HT_BOTH_SOT_TABLE = [
    (4.5, 4.5, 75),
    (4.0, 3.0, 62),
    (5.5, 3.0, 68),
    (6.0, 2.2, 59),
]

# ── §5.6 Player-prop bands (v8 L10 ACTIVE correction) ───────────────────────
PLAYER_GOAL_BANDS = {
    "star_striker":  (32, 45),
    "secondary":     (18, 28),
    "mid":           (8,  15),
}
PLAYER_SOT_BANDS = {
    "main_striker":  (52, 64),   # was 60-72, lowered v8 L10 ACTIVE
    "winger_am":     (42, 56),
}
# Top half of 56-70 band requires explicit written driver (L10 gate)
L10_DRIVER_GATE_LOW  = 63   # ≥ this in 56-70 band requires driver
L10_DRIVER_GATE_HIGH = 70

# Score-or-assist multipliers (§5.6)
SOA_MULTIPLIER_CREATOR = (1.5, 1.8)
SOA_MULTIPLIER_PURE_9  = (1.2, 1.4)

# ── §5.8 Live base-rate tracker ──────────────────────────────────────────────
BASE_RATES = {
    "penalty_per_match": 0.34,   # prior 0.36; posterior ≈ 0.34 @118
    "red_per_match":     0.06,
    "pen_or_red":        0.31,
    "match_cards_mean":  3.5,
    "goals_per_match":   2.55,
}
# Implied probabilities from base rates
BASE_RATE_PROBS = {
    "penalty":   29,   # P(pen awarded) ≈ 29%
    "red_card":  6,
    "pen_or_red":31,
}

# ── §5.9 Noisy register clamp ────────────────────────────────────────────────
NOISY_REGISTER_CLAMP = (15, 85)
NOISY_MARKETS = {
    "penalty_awarded", "red_card", "pen_or_red",
    "cards_2h", "ht_sot_comparison", "2h_sot_comparison",
    "offsides", "ht_corner_comparison", "2h_corner_comparison",
    "leads_at_ht",
}

# ── §5.12 Situational overlay caps ───────────────────────────────────────────
OVERLAY_CAP_TOTAL = 8           # ±8 pts total across all overlays
ALTITUDE_AZTECA_M  = 2240       # Estadio Azteca, Mexico City
ALTITUDE_GUADALAJARA_M = 1560   # Jalisco/Akron stadium

# ── §9.1 Feedback noise bands ────────────────────────────────────────────────
NOISE_BANDS = {
    10:  0.050,
    20:  0.034,
    50:  0.021,
    100: 0.015,
}

# ── §9.4 Lesson lifecycle thresholds ─────────────────────────────────────────
LESSON_ACTIVE_N    = 8    # n ≥ 8 directionally consistent → ACTIVE
LESSON_CONFIRMED_N = 20   # n ≥ 20 (or ≥ 30/class) → CONFIRMED

# ── §10 Lessons ledger summary (operative corrections only) ──────────────────
# L10: 56-70 band hot → main striker SOT band 52-64, driver gate in top half
# L12: win markets hot in 40-60 band → Dixon-Coles draw inflation input-side only
# L9:  HT-tied ceiling 47
WIN_BAND_DC_RANGE = (40, 60)    # L12: apply hardened Dixon-Coles here
DC_DRAW_BUMP = (1, 3)           # +1 to +3 added to draw-flavored outcomes (§5.2)
