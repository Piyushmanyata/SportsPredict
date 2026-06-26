"""
Session protocol helpers (§3 — The Autonomous Loop).
"""
from .triage import classify_matches, Horizon
from .audit import decode_outcome, compute_brier, brier_vs_expected, settle_audit
from .report import status_block, after_action_report, rbp_scoreboard

__all__ = [
    "classify_matches", "Horizon",
    "decode_outcome", "compute_brier", "brier_vs_expected", "settle_audit",
    "status_block", "after_action_report", "rbp_scoreboard",
]
