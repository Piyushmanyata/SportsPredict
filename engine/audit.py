"""§9 — Feedback loop: outcome decoding, settle audit, deep audit, RBP scoreboard.

Feed it the raw settled rows from `list_results` / `list_predictions`
(probabilities as 0–1 decimals — read endpoints return decimals, ×100 only
for display). No web lookups needed: outcomes decode from (p, brier) alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def decode_outcome(p: float, brier: float, eps: float = 1e-4) -> int | None:
    """§9.2 — o = 1 iff (p−1)² == brier (within ε), else 0.
    Undefined at p = 0.50 exactly (hence D3's 'avoid exactly 50') → None."""
    if abs(p - 0.5) < 1e-9:
        return None
    d1 = abs((p - 1.0) ** 2 - brier)
    d0 = abs(p ** 2 - brier)
    if min(d1, d0) > max(eps, 1e-3):  # neither fits — data problem, flag it
        return None
    return 1 if d1 < d0 else 0


def self_expected_brier(ps: list[float]) -> float:
    """§9.1 — benchmark realized Brier against Σ p(1−p)/n, never against 0.25."""
    return sum(p * (1 - p) for p in ps) / len(ps)


def noise_band(n: int, sd: float = 0.15) -> float:
    """§9.1 — sd of the mean Brier ≈ sd/√n (sd in [0.12, 0.18]; state which)."""
    return sd / math.sqrt(n)


@dataclass
class SettledMarket:
    match: str
    market: str
    p: float                    # submitted probability, 0–1
    brier: float
    stage_weight: int = 1
    crowd_brier: float | None = None
    outcome: int | None = None  # decoded lazily

    def decode(self) -> "SettledMarket":
        if self.outcome is None:
            self.outcome = decode_outcome(self.p, self.brier)
        return self

    @property
    def rbp(self) -> float | None:
        """§9.6 raw RBP; None when crowd data is unavailable — never invent it."""
        if self.crowd_brier is None:
            return None
        return (self.crowd_brier - self.brier) * 100.0

    @property
    def weighted_rbp(self) -> float | None:
        r = self.rbp
        return None if r is None else r * self.stage_weight


@dataclass
class AuditReport:
    n: int
    realized: float
    expected: float
    gap: float
    gap_sigma_range: tuple[float, float]     # at sd=0.18 and sd=0.12
    verdict: str
    per_match: list[tuple[str, float, int]]  # (match, avg brier, n) sorted worst-first
    bands: list[tuple[str, int, float, float]]  # (band, n, avg predicted, hit rate)
    worst: list[SettledMarket]
    rbp: dict | None = None
    flags: list[str] = field(default_factory=list)


def settle_audit(rows: list[SettledMarket], worst_k: int = 3) -> AuditReport:
    """§9.1/§9.3/§9.5 — realized vs self-expected, per-match table (the
    dominant variance axis), ~10-pt band decomposition, worst-Brier autopsy
    list, and the §9.6 RBP scoreboard when crowd_brier is present."""
    rows = [r.decode() for r in rows]
    usable = [r for r in rows if r.outcome is not None]
    flags = []
    if len(usable) < len(rows):
        flags.append(f"{len(rows) - len(usable)} rows undecodable (p=0.50 or inconsistent brier)")

    n = len(usable)
    ps = [r.p for r in usable]
    realized = sum(r.brier for r in usable) / n
    expected = self_expected_brier(ps)
    gap = realized - expected
    sig = (abs(gap) / noise_band(n, 0.18), abs(gap) / noise_band(n, 0.12))
    # React only beyond ~1.5 bands (§9.1); AMBER zone in between.
    verdict = "GREEN" if sig[1] < 1.0 else ("AMBER" if sig[1] < 1.8 else "RED (check per-class n≥30 before acting — D11)")

    by_match: dict[str, list[SettledMarket]] = {}
    for r in usable:
        by_match.setdefault(r.match, []).append(r)
    per_match = sorted(
        ((m, sum(x.brier for x in xs) / len(xs), len(xs)) for m, xs in by_match.items()),
        key=lambda t: -t[1],
    )

    bands = []
    for lo in range(0, 100, 10):
        hi = lo + 10
        band_rows = [r for r in usable if lo <= r.p * 100 < hi]
        if band_rows:
            avg_p = sum(r.p for r in band_rows) / len(band_rows) * 100
            hit = sum(r.outcome for r in band_rows) / len(band_rows) * 100
            bands.append((f"{lo}-{hi}", len(band_rows), avg_p, hit))

    worst = sorted(usable, key=lambda r: -r.brier)[:worst_k]

    rbp = rbp_scoreboard(usable)
    if rbp is None:
        flags.append("RBP unavailable — crowd_brier missing; raw calibration audit only (§9.6)")

    return AuditReport(n, realized, expected, gap, sig, verdict, per_match, bands, worst, rbp, flags)


def rbp_scoreboard(rows: list[SettledMarket]) -> dict | None:
    """§8.4/§9.6 — RBP-first scoreboard. Returns None if no crowd data (do not
    invent it). Rank matches by weighted RBP, NOT raw Brier (D12/L13)."""
    with_crowd = [r for r in rows if r.crowd_brier is not None]
    if not with_crowd:
        return None
    total = sum(r.weighted_rbp for r in with_crowd)
    beat = sum(1 for r in with_crowd if r.brier < r.crowd_brier)
    by_match: dict[str, float] = {}
    for r in with_crowd:
        by_match[r.match] = by_match.get(r.match, 0.0) + r.weighted_rbp
    ranked = sorted(by_match.items(), key=lambda t: -t[1])
    return {
        "n": len(with_crowd),
        "total_weighted_rbp": total,
        "avg_rbp_per_market": total / len(with_crowd),
        "markets_beat_crowd": f"{beat} / {len(with_crowd)}",
        "best_match_by_rbp": ranked[0],
        "worst_match_by_rbp": ranked[-1],
        "match_rbp_table": ranked,
    }


def format_report(rep: AuditReport) -> str:
    """Render an AuditReport in the §8.4/§9.5 shape for the session report."""
    lines = [
        f"SETTLE AUDIT — n={rep.n}",
        f"realized {rep.realized:.4f} vs self-expected {rep.expected:.4f} → "
        f"gap {rep.gap:+.4f} ≈ {rep.gap_sigma_range[0]:.2f}σ(sd=.18)–"
        f"{rep.gap_sigma_range[1]:.2f}σ(sd=.12) — {rep.verdict}",
    ]
    if rep.rbp:
        r = rep.rbp
        lines += [
            "",
            "RBP SCOREBOARD (primary — D12):",
            f"  total weighted RBP {r['total_weighted_rbp']:+.2f} · "
            f"avg/market {r['avg_rbp_per_market']:+.3f} · beat crowd {r['markets_beat_crowd']}",
            f"  best by RBP: {r['best_match_by_rbp'][0]} {r['best_match_by_rbp'][1]:+.2f} · "
            f"worst: {r['worst_match_by_rbp'][0]} {r['worst_match_by_rbp'][1]:+.2f}",
        ]
    lines += ["", "Per-match avg Brier (worst first — dominant variance axis §9.5):"]
    lines += [f"  {m}: {b:.3f} (n={k})" for m, b, k in rep.per_match]
    lines += ["", "Band decomposition (band · n · avg predicted · hit rate):"]
    lines += [f"  {band}: n={k} · pred {ap:.1f} · hit {hr:.1f}" for band, k, ap, hr in rep.bands]
    lines += ["", "Worst-Brier autopsy candidates (§9.3 — diagnose from taxonomy):"]
    lines += [f"  {r.match} · {r.market} · p={r.p * 100:.0f} · o={r.outcome} · brier {r.brier:.3f}"
              for r in rep.worst]
    if rep.flags:
        lines += ["", "Flags: " + " | ".join(rep.flags)]
    return "\n".join(lines)
