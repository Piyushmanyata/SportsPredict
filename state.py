"""
Persistent state: constants, lessons ledger, calibration record, base-rate tracker.
§4.1 — this file stores what persists; predictions/results always pulled live.
"""

# ─── §4.3  Verified constants (re-verify only on error) ──────────────────────

EVENT_ID  = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID  = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

TOURNAMENT = {
    "name":             "Jump Trading Probability Cup",
    "teams":            48,
    "groups":           12,
    "group_matches":    72,
    "knockout_matches": 32,
    "total_matches":    104,
    "markets_approx":   1040,
    "start":            "2026-06-11",
    "end":              "2026-07-19",
}

# Stage weights: group 1× · knockout 2× · final 3×
STAGE_WEIGHTS: dict[str, int] = {"group": 1, "knockout": 2, "final": 3}

# ─── §2.3 / §3.1  Horizon thresholds (hours) ─────────────────────────────────

NEAR_HORIZON_H = 48       # Depth Pass mandatory
MID_HORIZON_H  = 7 * 24  # PASS-1 required
URGENT_H       = 24       # UNCOVERED/PARTIAL + <24h → urgent cover

COVERAGE_STATES = ("UNCOVERED", "PARTIAL", "COVERED-STALE", "COVERED-FRESH")

# ─── §5.8  Base-rate tracker — update in place each settle audit ──────────────

BASE_RATES: dict = {
    # Working values (posterior, updated from EB tracker)
    "penalty_awarded_per_match": 0.29,  # prior 0.34; EB @~5 obs → ~0.29
    "red_card_per_match":        0.06,
    "pen_or_red_per_match":      0.31,
    "match_cards_mean":          3.5,
    "goals_per_match_group":     2.55,

    # Raw observation counts (update after each settle audit)
    "_penalty_n_obs": 5,
    "_penalty_n_yes": 1,
    "_red_n_obs":     0,
    "_red_n_yes":     0,
    "_cards_n_obs":   12,
    "_cards_sum":     42,  # total cards across observed matches
}

# ─── §10  Lessons ledger ─────────────────────────────────────────────────────

LESSONS: dict[str, dict] = {
    "L1": {
        "text": (
            "Don't overrate hosts/favourites; keep win probability at the "
            "(power-corrected) devigged line."
        ),
        "grade":     "CONFIRMED",
        "operative": True,
    },
    "L2": {
        "text":      "Even matchups carry heavy draw mass — don't overprice either win or star-player goals.",
        "grade":     "ACTIVE",
        "operative": True,
    },
    "L2b": {
        "text":      "+2–3 to stronger-on-paper side in technically even matchups.",
        "grade":     "PENDING",
        "operative": False,
        "note":      "n~1-2; revisit at n≥5 even-matchup wins.",
    },
    "L3": {
        "text":      "Strict 'more than' markets lose on ties — use §5.4 exact table; tie-blind 50 is the richest well.",
        "grade":     "CONFIRMED",
        "operative": True,
        "evidence":  "n=32 @118, avg Brier 0.248 vs self-exp 0.227, +0.021 within noise.",
    },
    "L4": {
        "text":      "Player 1+ SOT >> player goal as a value market.",
        "grade":     "ACTIVE",
        "operative": True,
    },
    "L5": {
        "text":      "Penalty/red markets are noise; stay near base rates; absorb bad Briers without reaction.",
        "grade":     "CONFIRMED",
        "operative": True,
        "evidence":  "n≈5 @118; lone YES (MEX-RSA) logged as pure-noise.",
    },
    "L6": {
        "text":      (
            "T-floor: never let fundamentals drag T >0.1 below anchor-implied; "
            "no-anchor cases get +0.2–0.3 technical-depth bump. "
            "Read BTTS^3+ off the grid, never below it."
        ),
        "grade":     "PROVISIONAL",
        "operative": True,
        "note":      "Evidence not strengthening (n=4 @79); hold, do not expect promotion.",
    },
    "L7": {
        "text":      (
            "Striker 1+ SOT: discount inside team λ allocation (not final output) "
            "under rotation risk. Mandatory Depth Pass post-lineup."
        ),
        "grade":     "ACTIVE",
        "operative": True,
        "note":      "Absorbed into L10. L7 sets the method (λ-allocation), L10 sets the band.",
    },
    "L8": {
        "text":      (
            "Correlation cap: >4 markets on one latent axis → proactive batched MC "
            "over λ-uncertainty. ≤3pt logged uncertainty adjustment as fallback. "
            "Never manual output flattening. Risk unit = per-match swing."
        ),
        "grade":     "ACTIVE",
        "operative": True,
        "evidence":  (
            "QAT-SUI canonical: 4/10 markets on Qatar attacking axis, all underpriced "
            "12–35, all YES — 27% of total @79 damage from one match."
        ),
    },
    "L9": {
        "text":      "HT-tied ceiling 47 unless anchor-implied T < 2.2 (Bessel table §5.5).",
        "grade":     "ACTIVE",
        "operative": True,
        "evidence":  "n=4 @79, ceiling untested; all calls ≤47.",
    },
    "L10": {
        "text":      (
            "56–70% probability band runs hot (overpriced). "
            "Input-side correction: main-striker SOT band lowered 60–72 → 52–64; "
            "any modeled p in top half of 56–70 requires an explicit written driver."
        ),
        "grade":     "ACTIVE",
        "operative": True,
        "evidence":  "@118: n=18, hit 44.4% vs avg predicted 61.2%, gap −16.8pt, ~1.0–1.3σ.",
        "correction": "Input-side band only — no output ceiling (D2/D11 intact).",
    },
    "L11": {
        "text":      "50–55% probability band runs cold (underpriced).",
        "grade":     "PROVISIONAL",
        "operative": False,
        "evidence":  "@118: n=13, +8.2pt cold (was +17.4 at n=7) — weakening.",
        "note":      "Track; if survives n≥30 with drift, re-examine devig power-k. Do not bump outputs.",
    },
    "L12": {
        "text":      (
            "Win markets (archetype #1) run hot. "
            "Hardened Dixon–Coles draw inflation in 40–60 win band; "
            "give fundamentals marginally more weight vs raw devig there."
        ),
        "grade":     "ACTIVE",
        "operative": True,
        "evidence":  "@118: n=10, avg Brier 0.303 vs self-expected 0.209, ~1.4σ; symmetric pattern.",
        "correction": "Input-side (DC draw inflation) — no floor (rejected proposal stays rejected per D11).",
    },
    "L13": {
        "text":      "Performance ranking must be RBP-first, not raw-Brier-first.",
        "grade":     "CONFIRMED",
        "operative": True,
        "note":      "Mathematical/contest-rule necessity. Does not authorize output shading; D2 intact.",
    },
    "L14": {
        "text":      (
            "Goal counts are mildly overdispersed vs pure Poisson (Goldman evidence). "
            "Extra clean-sheet/0-0/low-total mass in cagey games; "
            "fatter blow-out tail in mismatches."
        ),
        "grade":     "CONFIRMED",
        "operative": True,
        "evidence":  "~1,200 excess goalless team-games and ~566 excess 4+ games in ≈20k internationals.",
        "note":      "Captured as ±3 tilts in §5.2.1, merged with Dixon–Coles — do not double-count.",
    },
    "L15": {
        "text":      (
            "Favourite–longshot crowd bias is structural. "
            "Crowd spreads probability too far down the field; "
            "over-prices salient mid-tier names, under-prices the dominant favourite."
        ),
        "grade":     "ACTIVE",
        "operative": True,
        "note":      "Research-allocation signal only (§2.5/§5.13). Never a fade rule. Submit p (D2).",
        "evidence":  "Goldman: England mkt 11.5% vs model 5%; Spain mkt 16% vs model 26%.",
    },
}

# ─── §10.4  Calibration record — append at every deep audit ──────────────────

CALIBRATION_RECORD: list[dict] = [
    {
        "at":             20,
        "date":           "2026-06-12",
        "realized_brier": 0.2356,
        "self_expected":  0.2214,
        "gap":            0.0142,
        "sigma":          "0.5σ",
        "verdict":        "GREEN",
        "per_match_range": "MEX-RSA 0.185 – KOR-CZE 0.286",
        "notes":          "No global recalibration.",
    },
    {
        "at":             79,
        "date":           "2026-06-14",
        "realized_brier": 0.2467,
        "self_expected":  0.2225,
        "gap":            0.0242,
        "sigma":          "1.2–1.8σ",
        "verdict":        "AMBER",
        "per_match_range": "CAN-BIH 0.179 – QAT-SUI 0.315",
        "notes":          (
            "Gap grew from @20 but no class at n≥30. "
            "New PROVISIONAL: L10, L11, L12. Cross-checked vs GPT audit; "
            "one misread caught and excluded (Enciso §10.4)."
        ),
    },
    {
        "at":             118,
        "date":           "2026-06-15",
        "realized_brier": 0.2326,
        "self_expected":  0.2173,
        "gap":            0.0152,
        "sigma":          "0.92–1.38σ",
        "verdict":        "AMBER softening → GREEN",
        "per_match_range": "GER-CUR 0.132 – QAT-SUI 0.315",
        "notes":          (
            "Gap SHRANK vs @79 — D11 vindicated. "
            "L10 → ACTIVE, L12 → ACTIVE, L11 weakening. "
            "No global recalibration; no class at n≥30 with consistent drift."
        ),
    },
]

# ─── §2.5  Opportunity labels (crowd-edge triage) ────────────────────────────

OPPORTUNITY_LABELS = {
    "STRONG":   "≥8 pts crowd gap or structurally biased — extra source + MC if correlated",
    "MODERATE": "4–7 pts crowd gap — normal Depth Pass; update if abs(Δ) threshold met",
    "THIN":     "1–3 pts — anchor/engine is enough unless lineup/news moves it",
    "UNKNOWN":  "No crowd-bias read — treat as MODERATE if noisy; else THIN",
}

HIGH_OPPORTUNITY_ARCHETYPES = [
    "strict_compare",   # L3: tie-trap richest well
    "player_prop",      # L4: SOT props; L15: name inflation
    "win",              # L12: win markets hot; L1/L15: host/fav bias
    "drama",            # L5: penny/red overbought by crowd
    "btts3plus",        # correlated λ basket
]

# ─── §9.4  Lesson lifecycle thresholds ───────────────────────────────────────

LIFECYCLE = {
    "PROVISIONAL":  {"min_n": 1,  "requires_directional": False},
    "ACTIVE":       {"min_n": 8,  "requires_directional": True},
    "CONFIRMED":    {"min_n": 20, "requires_directional": True},
    "RETIRED":      {"min_n": 0,  "requires_directional": False},
}
