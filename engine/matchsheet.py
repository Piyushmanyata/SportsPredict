"""One-call match sheet: devigged anchors in -> all 12 archetypes out (§5.3).

This is the PASS-1 accelerator. Feed it the two anchored numbers (devigged
1X2 and P(Over 2.5), integers 0-100) plus optional stat means, and it returns
every market-archetype baseline with drivers, gates already applied where
mechanical (noisy clamp, HT-tied ceiling, integer bounds, no exact 50).

Outputs are ENGINE BASELINES: situational overlays (§5.12), Dixon-Coles tilt
in the 40-60 win band (L12), lineup gating (L7) and the L10 driver gate still
belong to the operator. Player and joint props need player inputs — use
engine.players / engine.jointprops directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine import goals, thresholds, tietrap
from engine.coherence import clamp_noisy
from engine.constants import BASE_RATES, STAT_MEANS


@dataclass
class MatchSheet:
    t: float
    lam_a: float
    lam_b: float
    rows: list[dict] = field(default_factory=list)

    def add(self, market: str, p: float, driver: str, noisy: bool = False):
        pi = round(100 * p) if p <= 1.0 else round(p)
        pi = max(1, min(99, pi))
        if noisy:
            clamped = clamp_noisy(pi)
            if clamped != pi:
                driver += f" | clamped {pi}->{clamped} (§5.9, unanchored)"
                pi = clamped
        if pi == 50:
            pi = 49  # D3: never submit exactly 50
        self.rows.append({"market": market, "p": pi, "driver": driver})

    def table(self) -> str:
        w = max(len(r["market"]) for r in self.rows)
        lines = [f"T={self.t:.2f}  split {self.lam_a:.2f}/{self.lam_b:.2f}"]
        lines += [f"{r['market']:<{w}}  {r['p']:>3}  {r['driver']}" for r in self.rows]
        return "\n".join(lines)


def build_match_sheet(h: int, d: int, a: int, over25: int,
                      team_a: str = "A", team_b: str = "B",
                      cards_lam: float | None = None,
                      stat_means: dict | None = None) -> MatchSheet:
    """h/d/a: devigged 1X2 as integers summing ~100. over25: devigged
    P(Over 2.5) as an integer. cards_lam: match cards mean (default tracker
    working value). stat_means: per-team overrides for STAT_MEANS keys."""
    t = goals.t_from_over25(over25 / 100.0)
    lam_a, lam_b = goals.fit_split(t, h / 100.0)
    sheet = MatchSheet(t=t, lam_a=lam_a, lam_b=lam_b)
    means = {**STAT_MEANS, **(stat_means or {})}
    cl = cards_lam if cards_lam is not None else BASE_RATES["cards_mean"]["prior"]

    anchor = f"devig 1X2 {h}/{d}/{a}, O/U {over25} -> T={t:.2f}"
    # 1 — win markets (L12: apply DC draw inflation in the 40-60 band yourself)
    sheet.add(f"{team_a} win", h / 100.0, f"anchored: {anchor}")
    sheet.add(f"{team_b} win", a / 100.0, f"anchored: {anchor}")
    # 2 — totals
    sheet.add("3+ total goals", goals.p_total_goals_geq(3, t), f"Poisson tail, T={t:.2f}")
    sheet.add("2 or fewer total goals", 1 - goals.p_total_goals_geq(3, t), "complement")
    # 3 — BTTS & 3+ (L6: read off the grid, never below)
    sheet.add("BTTS and 3+ goals", goals.p_btts_and_3plus(lam_a, lam_b),
              "BTTS - P(1-1), grid §5.2")
    # 4/5 — team scoring
    sheet.add(f"{team_a} scores 1+", goals.p_scores(lam_a), f"1-e^-{lam_a:.2f}")
    sheet.add(f"{team_b} scores 1+", goals.p_scores(lam_b), f"1-e^-{lam_b:.2f}")
    sheet.add(f"{team_a} scores in 2H", goals.p_scores_2h(lam_a), "0.55 share")
    sheet.add(f"{team_b} scores in 2H", goals.p_scores_2h(lam_b), "0.55 share")
    # 6 — strict comparisons (even-matchup baseline; skew with p_more_exact)
    for stat, key in (("fouls", "fouls"), ("FT corners", "corners_ft"),
                      ("2H corners", "corners_2h"), ("cards", "cards"),
                      ("2H SOT", "sot_2h"), ("offsides", "offsides")):
        m = means[key]
        noisy = key in ("corners_2h", "sot_2h", "offsides")
        sheet.add(f"{team_a} more {stat} (even baseline)",
                  tietrap.p_more_even(m),
                  f"tie-trap m={m}, tie={100 * tietrap.tie_mass(m):.1f}%", noisy=noisy)
    # 7 — threshold counts
    sheet.add("4+ total cards", thresholds.p_cards_4plus(cl), f"cards lam={cl}")
    sheet.add("2+ cards in 2H", thresholds.p_cards_2h_2plus(cl),
              f"0.62 share of lam={cl}", noisy=True)
    sheet.add("2+ total goals in 2H", goals.p_2h_goals_geq(2, t), "2H T share 0.55")
    # 9 — HT tied (L9 ceiling applied)
    sheet.add("HT tied", thresholds.ht_tied_capped(lam_a, lam_b) / 100.0,
              "Bessel §5.5 + L9 ceiling")
    # 12 — drama props from the EB tracker (noisy register)
    sheet.add("penalty awarded", BASE_RATES["pen_per_match"]["working_p"] / 100.0,
              "EB tracker §5.8", noisy=True)
    sheet.add("red card", BASE_RATES["red_per_match"]["working_p"] / 100.0,
              "EB tracker §5.8", noisy=True)
    sheet.add("pen or red", BASE_RATES["pen_or_red"]["working_p"] / 100.0,
              "EB tracker §5.8", noisy=True)
    return sheet
