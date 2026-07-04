"""Reusable implementation of the Jump Trading Probability Cup engine
described in probability-cup-system-instructions-v8-final.md — pure
stdlib, no numpy/scipy required, so a session can `import engine` and call
functions directly instead of re-deriving formulas from the spec each time.

Module -> spec section:
  constants          §4.3 (event/lobby IDs, tournament shape), D8 (IST)
  devig              §5.1 (multiplicative + power devig)
  lambda_engine      §5.2 / §5.2.1 (T fit, splits, closed forms, tilts)
  tie_trap           §5.4 (strict comparison markets)
  thresholds         §5.5 (count/state tables, HT-tied ceiling L9)
  player_props       §5.6 (bands post-L10, driver gate, L7 rotation)
  joint_props        §5.7 (sequence props, dependence haircut)
  monte_carlo        §5.11 L8 (correlated-basket MC, pure-python port)
  base_rate_tracker  §5.8 (empirical Bayes tracker)
  coherence          §5.11 (coherence gates + correlation-axis flag)
  overlays           §5.12 (situational overlay cap +-8)
  rbp                §1 / §9.1 / §9.6 (Brier, RBP, noise bands)
  outcome_decode     §9.2 (decode o from p, brier)
  ledger             §10 (lessons L1-L15, current grades)
  reports            §8 (status block / after-action / RBP scoreboard)
"""
from . import (
    base_rate_tracker,
    coherence,
    constants,
    devig,
    joint_props,
    lambda_engine,
    ledger,
    monte_carlo,
    outcome_decode,
    overlays,
    player_props,
    rbp,
    reports,
    thresholds,
    tie_trap,
    utils,
)

__all__ = [
    "base_rate_tracker", "coherence", "constants", "devig", "joint_props",
    "lambda_engine", "ledger", "monte_carlo", "outcome_decode", "overlays",
    "player_props", "rbp", "reports", "thresholds", "tie_trap", "utils",
]
