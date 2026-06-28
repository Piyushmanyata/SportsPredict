"""
State management: coverage tracker, lessons ledger, calibration records, base rates.
All state is persisted to JSON files in data/. Per D10, live truth always from API.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _data_path(fname: str) -> str:
    return os.path.join(DATA_DIR, fname)


def _load(fname: str, default) -> dict:
    path = _data_path(fname)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _save(fname: str, data) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_data_path(fname), "w") as f:
        json.dump(data, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# COVERAGE TRACKER
# ---------------------------------------------------------------------------
# States: UNCOVERED · PARTIAL · COVERED-STALE · COVERED-FRESH
COVERAGE_UNCOVERED    = "UNCOVERED"
COVERAGE_PARTIAL      = "PARTIAL"
COVERAGE_STALE        = "COVERED-STALE"
COVERAGE_FRESH        = "COVERED-FRESH"


class CoverageTracker:
    """
    Per D10: load live from list_predictions each session;
    this tracker caches coverage states for the current session only.
    """

    def __init__(self):
        self._state: Dict[str, Dict] = {}

    def update_from_live(
        self,
        matches: List[Dict],
        predictions: List[Dict],
    ) -> None:
        """
        Reconcile coverage states from fresh API data.
        matches: from list_matches (has id, opening_time, open_market_count)
        predictions: from list_predictions (has market_id, match_id, created_date)
        """
        pred_by_match: Dict[str, List[Dict]] = {}
        for p in predictions:
            mid = p.get("match_id", "")
            pred_by_match.setdefault(mid, []).append(p)

        for m in matches:
            mid = m["id"]
            total_markets = m.get("open_market_count", 10)
            covered = pred_by_match.get(mid, [])
            n_covered = len(covered)

            if n_covered == 0:
                state = COVERAGE_UNCOVERED
            elif n_covered < total_markets:
                state = COVERAGE_PARTIAL
            else:
                # Check freshness: depth pass within last 24h?
                latest_pred_time = max(
                    (p.get("created_date") or p.get("updated_date") or "1970-01-01T00:00:00Z")
                    for p in covered
                )
                from bot.utils import parse_iso
                try:
                    lpt = parse_iso(latest_pred_time)
                    age_h = (datetime.now(tz=timezone.utc) - lpt).total_seconds() / 3600
                    state = COVERAGE_FRESH if age_h < 24 else COVERAGE_STALE
                except Exception:
                    state = COVERAGE_STALE

            self._state[mid] = {
                "match_id":    mid,
                "name":        m.get("name", ""),
                "opening_time": m.get("opening_time", ""),
                "coverage":    state,
                "n_covered":   n_covered,
                "n_markets":   total_markets,
                "predictions": covered,
            }

    def get(self, match_id: str) -> Optional[Dict]:
        return self._state.get(match_id)

    def all_matches(self) -> List[Dict]:
        return list(self._state.values())

    def uncovered_or_partial(self) -> List[Dict]:
        return [m for m in self._state.values()
                if m["coverage"] in (COVERAGE_UNCOVERED, COVERAGE_PARTIAL)]

    def near_horizon_not_depth_passed(self) -> List[Dict]:
        """Near-horizon matches without a fresh Depth Pass."""
        from bot.config import NEAR_HORIZON_SEC
        from bot.utils import seconds_to_kickoff
        result = []
        for m in self._state.values():
            secs = seconds_to_kickoff(m["opening_time"])
            if 0 < secs <= NEAR_HORIZON_SEC and m["coverage"] != COVERAGE_FRESH:
                result.append(m)
        return sorted(result, key=lambda x: x["opening_time"])

    def deadline_table(self) -> List[Dict]:
        """All future matches sorted by kickoff with urgency flags."""
        from bot.utils import seconds_to_kickoff, format_ist
        rows = []
        for m in self._state.values():
            secs = seconds_to_kickoff(m["opening_time"])
            if secs < 0:
                continue
            rows.append({
                **m,
                "secs_to_kickoff": secs,
                "kickoff_ist": format_ist(__import__("bot.utils", fromlist=["parse_iso"]).parse_iso(m["opening_time"])),
                "urgent": secs <= 12 * 3600,
            })
        return sorted(rows, key=lambda x: x["secs_to_kickoff"])


# ---------------------------------------------------------------------------
# LESSONS LEDGER (§9.4 / §10)
# ---------------------------------------------------------------------------

class LessonsLedger:
    """
    Lifecycle: PROVISIONAL (n<8) → ACTIVE (n≥8) → CONFIRMED (n≥20/30) → RETIRED.
    D11: audits may only add PROVISIONAL entries; operative rules require ACTIVE.
    """

    GRADE_PROVISIONAL = "PROVISIONAL"
    GRADE_ACTIVE      = "ACTIVE"
    GRADE_CONFIRMED   = "CONFIRMED"
    GRADE_RETIRED     = "RETIRED"

    def __init__(self):
        self._data = _load("lessons.json", {"lessons": [], "last_updated": ""})

    def all(self) -> List[Dict]:
        return self._data["lessons"]

    def get(self, lesson_id: str) -> Optional[Dict]:
        for l in self._data["lessons"]:
            if l["id"] == lesson_id:
                return l
        return None

    def add_provisional(
        self,
        lesson_id: str,
        description: str,
        direction: str,
        source: str = "audit",
    ) -> Dict:
        """Add a new PROVISIONAL lesson entry (D11 compliant)."""
        entry = {
            "id":          lesson_id,
            "description": description,
            "direction":   direction,
            "grade":       self.GRADE_PROVISIONAL,
            "n":           1,
            "n_consistent": 1,
            "source":      source,
            "created":     datetime.now(tz=timezone.utc).isoformat(),
            "updated":     datetime.now(tz=timezone.utc).isoformat(),
        }
        # Don't duplicate
        existing = self.get(lesson_id)
        if existing:
            return self.record_evidence(lesson_id, True)
        self._data["lessons"].append(entry)
        self._save()
        return entry

    def record_evidence(self, lesson_id: str, directionally_consistent: bool) -> Dict:
        """Add evidence to a lesson and potentially graduate it."""
        from bot.config import LESSON_ACTIVE_N, LESSON_CONFIRMED_N
        entry = self.get(lesson_id)
        if not entry:
            raise KeyError(f"Lesson {lesson_id} not found")
        entry["n"] += 1
        if directionally_consistent:
            entry["n_consistent"] += 1
        entry["updated"] = datetime.now(tz=timezone.utc).isoformat()

        # Auto-graduate
        n = entry["n"]
        n_c = entry["n_consistent"]
        if entry["grade"] == self.GRADE_PROVISIONAL:
            if n >= LESSON_ACTIVE_N and n_c / n >= 0.75:
                entry["grade"] = self.GRADE_ACTIVE
        elif entry["grade"] == self.GRADE_ACTIVE:
            if n >= LESSON_CONFIRMED_N and n_c / n >= 0.80:
                entry["grade"] = self.GRADE_CONFIRMED

        self._save()
        return entry

    def active_or_confirmed(self) -> List[Dict]:
        return [l for l in self._data["lessons"]
                if l["grade"] in (self.GRADE_ACTIVE, self.GRADE_CONFIRMED)]

    def _save(self):
        self._data["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
        _save("lessons.json", self._data)


# ---------------------------------------------------------------------------
# CALIBRATION RECORDS (§9.1 / §10.4)
# ---------------------------------------------------------------------------

class CalibrationRecord:
    def __init__(self):
        self._data = _load("calibration.json", {"checkpoints": [], "last_updated": ""})

    def all(self) -> List[Dict]:
        return self._data["checkpoints"]

    def latest(self) -> Optional[Dict]:
        if not self._data["checkpoints"]:
            return None
        return self._data["checkpoints"][-1]

    def add_checkpoint(
        self,
        n_settled: int,
        realized_brier: float,
        self_expected_brier: float,
        gap_sigma: str,
        verdict: str,
        notes: str = "",
    ) -> Dict:
        from bot.utils import now_ist, format_ist
        checkpoint = {
            "n":                 n_settled,
            "realized_brier":    realized_brier,
            "self_expected":     self_expected_brier,
            "gap":               round(realized_brier - self_expected_brier, 4),
            "gap_sigma":         gap_sigma,
            "verdict":           verdict,  # GREEN / AMBER / RED
            "notes":             notes,
            "date_ist":          format_ist(datetime.now(tz=timezone.utc)),
        }
        self._data["checkpoints"].append(checkpoint)
        self._data["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
        _save("calibration.json", self._data)
        return checkpoint

    def compute_verdicts(self, realized: float, expected: float, n: int) -> str:
        """Classify calibration gap per §9.1 thresholds."""
        gap = realized - expected
        import math
        # Approximate σ for Brier (rough: σ ≈ 0.017 for n~100)
        sigma = 0.017 * math.sqrt(100 / n) if n > 0 else 0.017
        gap_in_sigma = gap / sigma
        if gap_in_sigma < 1.0:
            return "GREEN"
        elif gap_in_sigma < 1.5:
            return "AMBER"
        else:
            return "RED"


# ---------------------------------------------------------------------------
# BASE-RATE TRACKER (empirical Bayes, stepwise k_prior per §5.8)
# ---------------------------------------------------------------------------

class BaseRateTracker:
    """
    Tracks per-market-type observed outcomes to update base rates via empirical Bayes.
    k_prior cycles: 7 → 15 stepwise as evidence accumulates.
    """

    def __init__(self):
        self._data = _load("base_rates.json", {"rates": {}, "observations": {}})

    def get_rate(self, market_type: str) -> float:
        from bot.engine import BASE_RATES
        return self._data["rates"].get(market_type, BASE_RATES.get(market_type, 0.50))

    def record_outcome(self, market_type: str, outcome: int) -> float:
        """Update empirical Bayes rate; return new posterior."""
        obs = self._data["observations"].setdefault(market_type, {"n": 0, "k": 0})
        obs["n"] += 1
        obs["k"] += outcome

        from bot.engine import BASE_RATES
        prior_rate = BASE_RATES.get(market_type, 0.50)
        k_prior = 7 if obs["n"] < 20 else 15
        posterior = (k_prior * prior_rate + obs["k"]) / (k_prior + obs["n"])
        self._data["rates"][market_type] = posterior
        _save("base_rates.json", self._data)
        return posterior

    def all_rates(self) -> Dict[str, float]:
        from bot.engine import BASE_RATES
        merged = dict(BASE_RATES)
        merged.update(self._data["rates"])
        return merged
