"""§10 — lessons ledger, current as of v8/@118. Data only; re-sync grades
from the spec file at each deep audit (§9.5) rather than hand-editing here
without a matching audit event."""

LESSONS = {
    "L1": {"grade": "CONFIRMED (structural)",
           "text": "Don't overrate hosts/favorites; keep win probability at the power-corrected devigged line."},
    "L2": {"grade": "ACTIVE",
           "text": "Even matchups carry heavy draw mass — don't overprice either win or star-player goals."},
    "L2b": {"grade": "PENDING — do not apply",
            "text": "+2-3 to the stronger-on-paper side in technically even matchups (post KOR upset)."},
    "L3": {"grade": "CONFIRMED (n=32 @118)",
           "text": "Strict 'more than' markets lose on ties — use §5.4 exact table."},
    "L4": {"grade": "ACTIVE (see L7/L10 risk)",
           "text": "Player 1+ SOT >> player goal as a value market."},
    "L5": {"grade": "CONFIRMED (n=5 @118)",
           "text": "Penalty/red markets are noise; stay near base rates; absorb bad Briers without reaction."},
    "L6": {"grade": "PROVISIONAL, not strengthening (n=4)",
           "text": "T-floor for technical even matchups; read BTTS+3+ off the grid, never below it."},
    "L7": {"grade": "ACTIVE (absorbed into L10)",
           "text": "Striker 1+ SOT: discount inside team lambda allocation under rotation risk, not final output."},
    "L8": {"grade": "ACTIVE, evidence strengthened",
           "text": "Correlation cap: >4/10 markets on one latent axis -> proactive batched MC over lambda uncertainty."},
    "L9": {"grade": "ACTIVE (n=4, ceiling untested)",
           "text": "HT-tied ceiling 47 unless anchor-implied T < 2.2."},
    "L10": {"grade": "ACTIVE (n=18)",
            "text": "56-70% band runs hot. Input-side fix: striker 1+SOT band lowered to 52-64; driver gate on 63-70."},
    "L11": {"grade": "PROVISIONAL, weakening (n=13)",
            "text": "50-55% band runs cold, mirrors L10. Anchor/devig question, not a shading question."},
    "L12": {"grade": "ACTIVE (n=10)",
            "text": "Win markets run hot both directions (symmetric). Fix: firmer Dixon-Coles draw inflation 40-60 band."},
    "L13": {"grade": "CONFIRMED (contest-rule necessity)",
            "text": "Performance ranking must be RBP-first, not raw-Brier-first."},
    "L14": {"grade": "CONFIRMED (structural, external)",
            "text": "Goal counts are mildly overdispersed vs pure Poisson (Goldman evidence); capped +-3 tilt, §5.2.1."},
    "L15": {"grade": "ACTIVE (research-allocation signal only)",
            "text": "Favourite-longshot crowd bias: crowd over-prices mid-tier names, under-prices the dominant favourite."},
}

# §9.4 lifecycle thresholds — the only path to an operative rule change (D11).
LIFECYCLE = {
    "PROVISIONAL": "n=1-5, inputs only",
    "ACTIVE": "n>=8, directionally consistent, inputs only",
    "CONFIRMED": "n>=20 (or n>=30/class), may become an output rule",
    "RETIRED": "contradicted or absorbed into engine",
}


def active_or_confirmed():
    return {k: v for k, v in LESSONS.items() if v["grade"].startswith(("ACTIVE", "CONFIRMED"))}
