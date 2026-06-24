"""
Lesson lifecycle management (§9.4).
PROVISIONAL (n=1-5) -> ACTIVE (n>=8 directional) -> CONFIRMED (n>=20) -> RETIRED.
D11: audits may propose PROVISIONAL entries but NOT operative rules until ACTIVE threshold.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from constants import LESSONS


@dataclass
class LessonEntry:
    key: str
    text: str
    grade: str              # PROVISIONAL | ACTIVE | CONFIRMED | RETIRED | PENDING
    status: str             # operative | hold-not-promoting | track-do-not-act | etc.
    n: int = 0              # evidence count
    n_directional: int = 0  # directional consistent count
    action: str = ""
    notes: str = ""
    provisional_proposals: List[str] = field(default_factory=list)


class LessonTracker:
    """
    Tracks lesson grades and handles lifecycle transitions.
    Initialized from the constants.py LESSONS dict.
    """

    GRADE_ORDER = ["PENDING", "PROVISIONAL", "ACTIVE", "CONFIRMED", "RETIRED"]

    def __init__(self):
        self.lessons: Dict[str, LessonEntry] = {}
        for key, data in LESSONS.items():
            self.lessons[key] = LessonEntry(
                key=key,
                text=data["text"],
                grade=data["grade"],
                status=data["status"],
                n=data.get("n", 0),
                action=data.get("action", ""),
            )

    def propose_provisional(self, key: str, text: str, n: int,
                             direction: str, source: str = "session") -> str:
        """
        D11: Log a new PROVISIONAL entry from an audit.
        Does NOT make it operative — only adds to the ledger.
        Returns a confirmation string.
        """
        if key in self.lessons:
            entry = self.lessons[key]
            entry.notes += f"\n[{source}] Evidence n={n}, direction={direction}"
            return f"Updated existing {key}: n evidence logged (not yet operative)"

        self.lessons[key] = LessonEntry(
            key=key,
            text=text,
            grade="PROVISIONAL",
            status="not-yet-operative-D11",
            n=n,
            notes=f"Source: {source}. Direction: {direction}. NOT operative per D11 until §9.4 ACTIVE threshold.",
            action="Pending: n>=8 directional required for ACTIVE; n>=20 for CONFIRMED.",
        )
        return (f"PROVISIONAL entry {key} logged. Grade: PROVISIONAL. n={n}. "
                f"NOT operative per D11 until n>=8 directional (ACTIVE threshold).")

    def try_promote(self, key: str, n: int, directional: bool = True) -> Optional[str]:
        """
        Attempt grade promotion based on new evidence count.
        Returns promotion message or None.
        D11: only the normal lifecycle path can promote.
        """
        if key not in self.lessons:
            return None

        entry = self.lessons[key]
        entry.n = n

        old_grade = entry.grade

        if entry.grade == "PROVISIONAL" and n >= 8 and directional:
            entry.grade = "ACTIVE"
            entry.status = "operative-input-side"
            return (f"LESSON {key} PROMOTED: PROVISIONAL -> ACTIVE (n={n}, directional). "
                    f"Now operative as input-side adjustment per §9.4.")

        if entry.grade == "ACTIVE" and n >= 20:
            # Check if structural/mathematical or needs n>=30
            entry.grade = "CONFIRMED"
            entry.status = "operative"
            return (f"LESSON {key} PROMOTED: ACTIVE -> CONFIRMED (n={n}). "
                    f"Full operative. Output-side adjustments now allowed if n>=30 per class.")

        return None

    def get_operative_lessons(self) -> List[LessonEntry]:
        """Return all lessons that are currently operative."""
        return [e for e in self.lessons.values()
                if e.grade in ("ACTIVE", "CONFIRMED")
                and "not-yet-operative" not in e.status
                and e.grade != "PENDING"
                and e.grade != "PROVISIONAL"]

    def get_input_side_adjustments(self) -> List[LessonEntry]:
        """Lessons that affect engine inputs (all ACTIVE/CONFIRMED)."""
        return self.get_operative_lessons()

    def get_output_side_adjustments(self) -> List[LessonEntry]:
        """
        Only CONFIRMED lessons with n>=30 per class may adjust outputs.
        This is a high bar — most adjustments are input-side.
        """
        return [e for e in self.lessons.values()
                if e.grade == "CONFIRMED" and e.n >= 30]

    def summarize(self) -> str:
        lines = ["LESSONS LEDGER SUMMARY:"]
        for key, entry in sorted(self.lessons.items()):
            operative_str = f"[{entry.status}]" if entry.grade in ("ACTIVE", "CONFIRMED") else "[not yet operative]"
            lines.append(f"  {key} ({entry.grade}) {operative_str}: {entry.text[:80]}...")
        return "\n".join(lines)

    def d11_check(self, proposed_rule: str, source: str,
                   n: int, grade: str) -> str:
        """
        §D11 guardrail: evaluate any proposed rule change.
        Returns a formatted D11 response.
        """
        if grade not in ("ACTIVE", "CONFIRMED"):
            return (
                f"D11 BLOCK: Proposed rule '{proposed_rule[:80]}' from {source} "
                f"at grade {grade} (n={n}) is NOT operative. "
                f"ACTIVE requires n>=8 directionally consistent; CONFIRMED requires n>=20. "
                f"Log as PROVISIONAL; do not implement as floor, ceiling, or band shift."
            )
        return (
            f"D11 OK: Proposed adjustment at grade {grade} (n={n}) may be implemented "
            f"as an input-side correction only. No output floors/ceilings (D2 intact)."
        )


def grade_lesson(key: str, n: int, directional: bool = True) -> str:
    """
    Quick grade computation without a full tracker instance.
    """
    if n < 1:
        return "PENDING"
    if n < 8 or not directional:
        return "PROVISIONAL"
    if n < 20:
        return "ACTIVE"
    return "CONFIRMED"


def format_lesson_lifecycle_note(key: str, current_grade: str, n: int) -> str:
    """Format a human-readable lifecycle note for reports."""
    next_threshold = {
        "PENDING": "n>=1 to enter PROVISIONAL",
        "PROVISIONAL": f"n>=8 directional for ACTIVE (currently n={n})",
        "ACTIVE": f"n>=20 for CONFIRMED (currently n={n})",
        "CONFIRMED": "n>=30/class for output-side adjustments",
        "RETIRED": "retired",
    }
    return f"{key} ({current_grade}): {next_threshold.get(current_grade, '')}"
