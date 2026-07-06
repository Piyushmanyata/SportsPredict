"""Probability Cup engine — reusable implementation of the v8 spec's math.

Modules map to spec sections (probability-cup-system-instructions-v8-final.md):

    constants   §0/§4.3/§5.8/§5.9  IDs, stage weights, base rates, noisy register
    devig       §5.1               implied probs, multiplicative + power devig
    goals       §5.2/§5.2.1        lambda engine: O/U->T, 1X2 split fit, closed forms
    tietrap     §5.4               strict "A more X than B" with exact tie mass
    thresholds  §5.5               Poisson tails, HT-tied Bessel, HT both-SOT
    players     §5.6               player props (L7/L10 bands, rotation via lambda share)
    jointprops  §5.7               scores-first / joint props with dependence haircut
    mc          §5.11              batched Monte Carlo over lambda uncertainty (L8)
    coherence   §5.11              pre-batch gates
    audit       §9                 outcome decoding, calibration bands, RBP math
    matchsheet  §5.3               one call: anchors in -> all 12 archetypes out
    markets     §5.3-§5.9          MatchContext + live-question router (see reprice.py)

Everything is pure Python (math module only) except mc.py, which uses numpy
when available and falls back to the standard library otherwise.

Quick start:

    from engine.matchsheet import build_match_sheet
    sheet = build_match_sheet(h=48, d=25, a=27, over25=51)
    for row in sheet.rows: print(row)
"""

from engine import audit, coherence, constants, devig, goals, jointprops, markets, mc, players, thresholds, tietrap
from engine.markets import MatchContext, PlayerCtx, price_question
from engine.matchsheet import build_match_sheet

__all__ = [
    "audit", "coherence", "constants", "devig", "goals", "jointprops",
    "markets", "mc", "players", "thresholds", "tietrap", "build_match_sheet",
    "MatchContext", "PlayerCtx", "price_question",
]
