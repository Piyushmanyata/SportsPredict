"""End-to-end worked example: anchors -> full market table (spec sections 5.2, 6.1, 8.2).

Takes one match's anchor prices (1X2 decimal odds + Over/Under 2.5 decimal
odds, optionally player shares) and derives the standard ~10-market table
by composing the other engine/ modules, in the same order a PASS-1 or
Depth Pass would: devig -> lambda split -> per-market closed forms ->
coherence gates.

Usage:
    python3 engine/run_match.py path/to/match.json
    cat path/to/match.json | python3 engine/run_match.py

Input JSON shape -- see engine/example_match.json for a worked sample.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coherence  # noqa: E402
import devig  # noqa: E402
import lambda_engine as lam_eng  # noqa: E402
import player_props  # noqa: E402
import thresholds  # noqa: E402


def _fit_lambda_split(T, target_win, target_draw, target_loss, steps=400):
    """Grid-search lambda_a in (0, T) so win_draw_loss(lambda_a, T-lambda_a) best matches the devigged 1X2."""
    best_lam_a, best_err = T / 2.0, float("inf")
    for i in range(1, steps):
        lam_a = T * i / steps
        lam_b = T - lam_a
        win_a, draw, win_b = lam_eng.win_draw_loss(lam_a, lam_b, max_goals=10)
        err = (win_a - target_win) ** 2 + (draw - target_draw) ** 2 + (win_b - target_loss) ** 2
        if err < best_err:
            best_err = err
            best_lam_a = lam_a
    return best_lam_a, T - best_lam_a


def build_match_report(match):
    """Derive the standard market table for one match from its anchor prices."""
    odds_1x2 = match["odds_1x2"]  # [home, draw, away] decimal odds
    implied_1x2 = [devig.implied_prob(o) for o in odds_1x2]
    devig_1x2 = devig.devig(implied_1x2)
    p_home, p_draw, p_away = devig_1x2["probs"]

    implied_ou = [devig.implied_prob(match["odds_over_2_5"]), devig.implied_prob(match["odds_under_2_5"])]
    p_over25, _ = devig.devig_multiplicative(implied_ou)

    T = lam_eng.total_goals_from_over25(p_over25)
    lam_home, lam_away = _fit_lambda_split(T, p_home, p_draw, p_away)

    rows = []
    rows.append(("1", "Will HOME win?", "ANCHORED", p_home, "devigged 1X2"))
    rows.append(("1", "Will AWAY win?", "ANCHORED", p_away, "devigged 1X2"))
    rows.append(("2", "3+ total goals", "ANCHORED", 1 - lam_eng.poisson_cdf(T, 2), "Over 2.5 anchor -> T"))
    rows.append(("3", "BTTS and 3+ goals", "MODELED", lam_eng.btts_and_3plus(lam_home, lam_away), "lambda grid"))
    rows.append(("4", "HOME scores in 2H", "MODELED", lam_eng.team_scores_2h(lam_home), "lambda_home closed form"))
    rows.append(("4", "AWAY scores in 2H", "MODELED", lam_eng.team_scores_2h(lam_away), "lambda_away closed form"))
    rows.append(("5", "HOME scores 1+", "MODELED", lam_eng.team_scores(lam_home), "lambda_home closed form"))
    rows.append(("5", "AWAY scores 1+", "MODELED", lam_eng.team_scores(lam_away), "lambda_away closed form"))
    rows.append(("9", "HT tied", "MODELED", thresholds.ht_tied(lam_home, lam_away), "HT Bessel table, L9 ceiling 47"))
    rows.append(("-", "HOME clean sheet", "MODELED", lam_eng.clean_sheet(lam_away), "exp(-lambda_away)"))

    for p in match.get("players", []):
        lam_player = p["team_lambda"] * p["goal_share"] * p.get("rotation_factor", 1.0)
        goal_p = player_props.anytime_goal_prob(lam_player)
        rows.append(("8", f"{p['name']} anytime goal", "MODELED", goal_p, f"lambda_share={p['goal_share']}"))

    gates = {
        "1x2_sum_ok": coherence.check_1x2_sum(p_home, p_draw, p_away),
        "ht_tied_within_ceiling": thresholds.ht_tied(lam_home, lam_away) * 100 <= thresholds.HT_TIED_CEILING + 1e-6,
    }

    return {
        "match_name": match.get("match_name", "unknown"),
        "T": T,
        "lam_home": lam_home,
        "lam_away": lam_away,
        "devig_method_1x2": devig_1x2["method"],
        "rows": rows,
        "gates": gates,
    }


def format_report(report):
    """Render the section 8.2 after-action-report style table."""
    lines = [
        f"Match: {report['match_name']}  (T={report['T']:.2f}, "
        f"lam_home={report['lam_home']:.2f}, lam_away={report['lam_away']:.2f}, "
        f"1X2 devig={report['devig_method_1x2']})",
        f"{'#':<3} {'Market':<28} {'Mode':<9} {'p':>6}  Driver",
    ]
    for archetype, market, mode, p, driver in report["rows"]:
        lines.append(f"{archetype:<3} {market:<28} {mode:<9} {p*100:5.1f}%  {driver}")
    lines.append(f"Gates: {report['gates']}")
    return "\n".join(lines)


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            match = json.load(f)
    else:
        match = json.load(sys.stdin)
    report = build_match_report(match)
    print(format_report(report))


if __name__ == "__main__":
    main()
