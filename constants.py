"""
Verified constants, lessons ledger, and live base-rate tracker.
Re-derive nothing here — pull live data for predictions/results.
Update base-rate tracker in-place after each settle audit.
"""

# §4.3 Verified constants
EVENT_ID = "aa5572ec-5930-4d99-b06b-f8966333d172"
LOBBY_ID = "8df8038c-fd2c-4a5f-be4e-0e11d5966c05"

STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}

# §5.8 Live base-rate tracker — update working values after every settle audit
# Format: {metric: {prior, n_matches, n_yes, working_value, note}}
BASE_RATES = {
    "penalty_per_match": {
        "prior": 0.36,           # VAR-era majors
        "p_prior": 29,           # P(pen) ≈ 26–34
        "n_matches": 5,          # @118
        "n_yes": 1,              # 1 YES @ MEX-RSA
        "working_p": 29,         # stay near prior on noisy small n (L5)
        "k_eb": 7,               # empirical Bayes shrinkage; auto-escalate to 15 at n>=10
        "note": "~20% raw @118, running under prior; L5 says absorb without reaction",
    },
    "red_card_per_match": {
        "prior": 0.06,
        "p_prior": 6,
        "n_matches": 0,
        "n_yes": 0,
        "working_p": 6,
        "k_eb": 7,
        "note": "unconfirmed @118",
    },
    "pen_or_red_per_match": {
        "prior": 0.34,           # union, small overlap
        "p_prior": 31,
        "n_matches": 5,
        "n_yes": 1,
        "working_p": 31,
        "k_eb": 7,
        "note": "~20% raw @118, noisy — stay on prior (L5)",
    },
    "match_cards_mean": {
        "prior_low": 3.2,
        "prior_high": 4.2,
        "working_lambda": 3.5,
        "n_matches": 0,
        "note": "small-n, no strong signal yet",
    },
    "goals_per_match_group": {
        "prior_low": 2.4,
        "prior_high": 2.7,
        "working_lambda": 2.55,
        "n_matches": 0,
        "note": "mixed across 12 matches @118",
    },
}

# §10 Lessons ledger — operative status drives engine behaviour
# Grades: PROVISIONAL (n=1-5) | ACTIVE (n>=8 directional) | CONFIRMED (n>=20) | RETIRED
LESSONS = {
    "L1": {
        "text": "Don't overrate hosts/favorites; keep win prob at power-corrected devigged line.",
        "grade": "CONFIRMED",
        "status": "operative",
        "action": "No host/favourite uplift on win markets. Anchor wins (L1/L12 interact).",
    },
    "L2": {
        "text": "Even matchups carry heavy draw mass — don't overprice either win or star-player goals.",
        "grade": "ACTIVE",
        "status": "operative",
        "action": "In 40-60 win band let draw breathe; don't split non-fav mass evenly into two win sides.",
    },
    "L2b": {
        "text": "+2-3 to stronger-on-paper side in technically even matchups (post KOR upset).",
        "grade": "PENDING",
        "status": "do-not-apply",
        "n_effective": 1,
        "action": "Revisit at n>=5 even-matchup wins.",
    },
    "L3": {
        "text": "Strict 'more than' markets lose on ties — use §5.4 exact Bessel table; crowd's tie-blind 50 is richest well.",
        "grade": "CONFIRMED",
        "n": 32,
        "calibration_note": "avg Brier 0.248 vs self-exp 0.227, +0.021 within noise @118",
        "status": "operative",
        "action": "Always use tie_trap engine for strict comparisons; never assign 50.",
    },
    "L4": {
        "text": "Player 1+ SOT >> player goal as a value market.",
        "grade": "ACTIVE",
        "status": "operative-with-caution",
        "action": "Prefer SOT props; cross-flag with L7/L10 risk bands.",
    },
    "L5": {
        "text": "Penalty/red markets are noise; stay near base rates; absorb bad Briers without reaction.",
        "grade": "CONFIRMED",
        "n": 5,
        "status": "operative",
        "action": "Clamp 15-85; stay near prior; no adjustment after individual bad outcomes.",
    },
    "L6": {
        "text": "T-floor for technical even matchups: don't let fundamentals drag T >0.1 below anchor; no-anchor +0.2-0.3 bump; BTTS&3+ off grid only.",
        "grade": "PROVISIONAL",
        "n": 4,
        "status": "hold-not-promoting",
        "action": "Hold. Evidence not strengthening. Read BTTS&3+ off grid at anchor-implied T.",
    },
    "L7": {
        "text": "Striker 1+ SOT: discount inside team λ allocation (not final output) under rotation risk.",
        "grade": "ACTIVE",
        "status": "absorbed-into-L10",
        "action": "λ-allocation discipline stays the method; L10 sets the band (52-64).",
    },
    "L8": {
        "text": "Correlation cap: >4 markets on one latent axis -> proactive batched MC integration. Risk unit = per-match RBP swing.",
        "grade": "ACTIVE",
        "status": "mandatory-near-horizon",
        "action": "For every near-horizon match: count correlated markets; if >4/10, run batch_mc. QAT-SUI is canonical worked example.",
    },
    "L9": {
        "text": "HT-tied ceiling 47 unless anchor-implied T < 2.2.",
        "grade": "ACTIVE",
        "n": 4,
        "status": "operative",
        "action": "Cap HT-tied at 47; lower table value if T >= 2.2.",
    },
    "L10": {
        "text": "56-70% probability band runs hot (overpriced). @118: n=18, hit 44.4% vs predicted 61.2% -> -16.8pt.",
        "grade": "ACTIVE",
        "n": 18,
        "status": "operative-input-side",
        "action": "Main-striker 1+SOT band 52-64 (was 60-72). Any modeled p in top half of 56-70 requires explicit written driver; else regress to lower edge. No output ceiling (D2/D11).",
    },
    "L11": {
        "text": "50-55% band runs cold (underpriced). @118: n=13, hit 61.5% vs 53.3% -> +8.2pt (weakening).",
        "grade": "PROVISIONAL",
        "n": 13,
        "status": "track-do-not-act",
        "action": "Do not bump outputs. Track to n>=30. This is a devig/anchor question, not a shading question.",
    },
    "L12": {
        "text": "Win markets (archetype #1) run hot. @118: n=10, avg Brier 0.303 vs self-exp 0.209 (~1.4σ). Symmetric: low-p underdogs over-winning AND modest faves not winning.",
        "grade": "ACTIVE",
        "n": 10,
        "status": "operative-input-side",
        "action": "Apply hardened Dixon-Coles + overdispersion draw inflation firmly in 40-60 win band. More fundamentals weight vs raw devig. NOT a floor (D11: rejected proposal to raise underdog floor stays rejected).",
    },
    "L13": {
        "text": "Performance ranking must be RBP-first, not raw-Brier-first.",
        "grade": "CONFIRMED",
        "status": "operative",
        "action": "All reports rank by weighted RBP. CAN-BIH canonical: +60.67 RBP is the measure, not low avg Brier alone.",
    },
    "L14": {
        "text": "Goal counts are mildly overdispersed vs Poisson. ~1,200 excess goalless, ~566 excess 4+ in 20k internationals.",
        "grade": "CONFIRMED",
        "status": "operative",
        "action": "Small documented tilts in §5.2.1 (capped ±3, merged with Dixon-Coles — do not double-count). Engine stays Poisson.",
    },
    "L15": {
        "text": "Favourite-longshot crowd bias is structural. Crowd over-prices salient mid-tier, under-prices dominant favourite.",
        "grade": "ACTIVE",
        "status": "research-allocation-signal-only",
        "action": "Flag STRONG for dominant favourites/boring high-prob outcomes. Confirm true p, then submit p. Never a fade rule (D2).",
    },
}

# Calibration record — append at every deep audit
CALIBRATION_RECORD = [
    {"n": 20, "date": "2026-06-12", "realized": 0.2356, "expected": 0.2214, "gap": 0.014, "sigma": "~0.5", "verdict": "GREEN"},
    {"n": 79, "date": "2026-06-14", "realized": 0.2467, "expected": 0.2225, "gap": 0.0242, "sigma": "1.2-1.8", "verdict": "AMBER",
     "per_match_range": "CAN-BIH 0.179 (A-) ... QAT-SUI 0.315 (F)"},
    {"n": 118, "date": "2026-06-15", "realized": 0.2326, "expected": 0.2173, "gap": 0.0152, "sigma": "0.92-1.38", "verdict": "AMBER->GREEN",
     "per_match_range": "GER-CUR 0.132 (A) ... QAT-SUI 0.315 (worst)"},
]

# Source trust order for odds (§5.1)
SOURCE_TRUST = [
    "Betfair Exchange",
    "Pinnacle",
    "Oddschecker",
    "OddsPortal",
    "Oddspedia",
    "single soft book",
]

# §5.9 Noisy market register — clamp 15-85 unless anchored
NOISY_MARKETS = [
    "penalty awarded",
    "red card",
    "pen or red",
    "2H cards",
    "HT/2H SOT comparisons",
    "offside counts",
    "HT/2H corner comparisons",
    "leads at HT",
]

# Update threshold for re-submission (§6.3)
UPDATE_THRESHOLD_DEFAULT = 3       # abs(Δ) >= 3 triggers update
UPDATE_THRESHOLD_PLAYER_PROP = 2   # drops to 2 once lineups are known (L7)

# Rate limit (§D6)
RATE_LIMIT_PER_MIN = 60
BACKOFF_429_SECONDS = (30, 60)
MAX_BATCH_SIZE = 50
