# engine/

Reusable Python implementation of `probability-cup-system-instructions-v8-final.md`.
Pure standard library — no numpy/scipy install required. Import what you need:

```python
from engine import devig, lambda_engine, tie_trap, rbp

d = devig.devig([0.55, 0.30, 0.20])      # §5.1
T = lambda_engine.fit_T_from_over25(0.46) # §5.2 -> ~2.5
p_a, tie, p_b = tie_trap.p_more(11, 9)    # §5.4 fouls comparison
edge = rbp.rbp_market(crowd_brier=0.30, your_brier=0.18, stage_weight=2)
```

See `engine/__init__.py` for the full module -> spec-section map. Update
`ledger.py`'s grades and `base_rate_tracker.py`'s `PRIORS` when a deep audit
(§9.5) changes them — those two files are the only ones meant to drift
between spec revisions; everything else is fixed formula/mechanics.

Run `python3 -m engine.selftest` for a quick sanity check that every module
imports and its core functions return sane values.
