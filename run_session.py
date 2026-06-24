"""
Autonomous session runner — §3.2 full loop.

Usage (Claude runs this via Bash or imports functions directly):

  from run_session import (
      run_triage, run_settle_audit, price_match,
      prepare_batch, validate_prediction
  )

Steps the autonomous loop MUST complete every session:
  1. SYNC     — call list_matches, list_predictions, list_results via MCP
  2. TRIAGE   — classify coverage states + horizons
  3. SETTLE AUDIT — decode outcomes, update EB tracker, run feedback loop
  4. DEPTH PASS   — full §6.3 for every near-horizon match
  5. COVERAGE SWEEP — PASS-1 for uncovered mid/far matches
  6. REPORT   — status block + after-action
"""

import json
import math
import sys
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from constants import (
    EVENT_ID, LOBBY_ID, STAGE_WEIGHTS, BASE_RATES,
    UPDATE_THRESHOLD_DEFAULT, UPDATE_THRESHOLD_PLAYER_PROP,
    MAX_BATCH_SIZE,
)
from engine import (
    power_devig, multiplicative_devig, devig_1x2, devig_ou,
    ou_to_T, find_split, poisson_p, LambdaEngine,
    price_market, p_strict_more, tie_trap_table,
    player_props, batch_mc, check_coherence, count_correlated_axes,
)
from session import triage, format_deadline_table, CoverageState, classify_horizon
from session.coverage import build_match_status, sort_by_priority, MatchStatus
from feedback import decode_outcome, brier_score, self_expected_brier, rbp
from feedback.outcomes import (
    decode_settled_batch, worst_brier_autopsy,
    probability_band_decomposition, compute_rbp_scoreboard,
    calibration_verdict,
)
from feedback.lessons import LessonTracker
from reporting import (
    format_rbp_scoreboard, format_after_action_report,
    format_delta_report, format_opportunity_table,
    format_session_summary, opportunity_label,
)


# Global lesson tracker — persists within a session
_lesson_tracker = LessonTracker()


# ─── Step helpers ─────────────────────────────────────────────────────────────

def run_triage(matches: List[Dict], predictions: List[Dict],
               depth_passes: Optional[Dict] = None) -> Dict:
    """
    §3.2 Steps 1-2: build MatchStatus for each match and run triage.

    matches:     from list_matches
    predictions: from list_predictions (0-1 decimals)
    depth_passes: {match_id: datetime} from session memory

    Returns triage report dict.
    """
    statuses = [
        build_match_status(m, predictions, depth_passes)
        for m in matches
    ]
    report = triage(statuses)
    print(format_deadline_table(statuses))
    if report["flags"]:
        print("\n".join(f"FLAG: {f}" for f in report["flags"]))
    return report


def run_settle_audit(predictions: List[Dict], results: List[Dict],
                     since_last_deep_audit: int = 0) -> Dict:
    """
    §3.2 Step 3: SETTLE AUDIT.
    Decodes outcomes, updates EB base rates, computes calibration stats.
    Triggers §9.5 Periodic Deep Audit if cumulative settled >= 50-80.
    """
    settled = decode_settled_batch(predictions, results)
    if not settled:
        return {"settled": [], "n": 0, "deep_audit": False}

    # Calibration
    realized_brier = sum(s["brier"] for s in settled) / len(settled)
    exp_brier = self_expected_brier([s["p_decimal"] for s in settled])
    gap = realized_brier - exp_brier
    verdict = calibration_verdict(gap, len(settled))

    print(f"\nSETTLE AUDIT: n={len(settled)} | Brier {realized_brier:.4f} vs expected {exp_brier:.4f} | gap {gap:+.4f} | {verdict}")

    # Worst Brier autopsy
    autopsy = worst_brier_autopsy(settled)
    if autopsy:
        print("\nWORST BRIER AUTOPSY (top 3):")
        for item in autopsy:
            print(f"  {item.get('market_name','?')} p={item.get('p_int','?')} Brier={item.get('brier',0):.3f} → {item.get('autopsy','')}")

    # Deep audit trigger
    deep_audit = False
    if since_last_deep_audit + len(settled) >= 50:
        deep_audit = True
        print(f"\n§9.5 PERIODIC DEEP AUDIT TRIGGERED (n={since_last_deep_audit + len(settled)} since last)")
        _run_deep_audit(settled)

    return {
        "settled": settled,
        "n": len(settled),
        "realized_brier": realized_brier,
        "exp_brier": exp_brier,
        "gap": gap,
        "verdict": verdict,
        "deep_audit": deep_audit,
    }


def _run_deep_audit(settled: List[Dict]) -> None:
    """§9.5 + §9.6 Periodic Deep Audit."""
    print("\n--- PERIODIC DEEP AUDIT ---")

    # Per-match Brier table
    per_match: Dict[str, List[float]] = {}
    for s in settled:
        m = s.get("match_name", "unknown")
        per_match.setdefault(m, []).append(s["brier"])

    print("Per-match avg Brier:")
    for match, briers in sorted(per_match.items(), key=lambda x: sum(x[1]) / len(x[1])):
        avg = sum(briers) / len(briers)
        print(f"  {match}: {avg:.3f} (n={len(briers)})")

    # Probability band decomposition
    bands = probability_band_decomposition([s for s in settled if s.get("outcome") is not None])
    print("\nProbability band decomposition (~10pt):")
    for band, data in bands.items():
        if data is None:
            continue
        flag = " *** PROVISIONAL FLAG" if data.get("provisional_flag") else ""
        print(f"  {band}%: n={data['n']} | avg_pred={data['avg_predicted_pct']}% | "
              f"hit={data['hit_rate_pct']}% | gap={data['gap_pts']:+.1f}pt | "
              f"sigma={data['sigma_range']}{flag}")

    # RBP scoreboard
    print("\n" + format_rbp_scoreboard(settled))
    print("--- END DEEP AUDIT ---\n")


def price_match(
    team_a: str, team_b: str,
    dec_home: float, dec_draw: float, dec_away: float,
    dec_over25: float, dec_under25: float,
    markets: List[Dict],
    extras: Optional[Dict] = None,
) -> List[Dict]:
    """
    Price all markets for a match using the λ-engine.

    Inputs (deciamls odds):
      dec_home/draw/away: 1X2 decimal odds
      dec_over25/under25: O/U 2.5 decimal odds
      markets: list of {market_id, market_name, archetype, extras}

    Returns list of {market_id, market_name, p_int, mode, driver, archetype}
    """
    extras = extras or {}

    # Devig 1X2
    dv = devig_1x2(dec_home, dec_draw, dec_away)
    p_home, p_draw, p_away = dv["home"], dv["draw"], dv["away"]
    print(f"  1X2 devigged ({dv['method']}): H={p_home:.3f} D={p_draw:.3f} A={p_away:.3f}")

    # Devig O/U
    dv_ou = devig_ou(dec_over25, dec_under25)
    p_over25 = dv_ou["over"]
    T = ou_to_T(p_over25)
    print(f"  O/U 2.5 -> T={T:.2f} (over25={p_over25:.3f})")

    # Find split
    lam_a, lam_b = find_split(T, p_home, p_draw, p_away)
    print(f"  Split: lam_a={lam_a:.3f} lam_b={lam_b:.3f}")

    engine = LambdaEngine(lam_a, lam_b)

    # L12: is this a near-coinflip win market? (40-60 win band)
    win_band = 0.40 <= p_home <= 0.60 or 0.40 <= p_away <= 0.60

    # L8: count correlated axes
    l8_check = count_correlated_axes(markets)
    if l8_check.get("l8_triggered"):
        print(f"  L8 TRIGGERED: {l8_check['dominant_axis']} axis has "
              f"{l8_check['counts']} markets -> running batch MC")
        sigma_a = extras.get("sigma_a", 0.15 * lam_a)
        sigma_b = extras.get("sigma_b", 0.15 * lam_b)
        mc_mkt_keys = [m.get("mc_key", "scores_ft_a") for m in markets if m.get("use_mc")]
        mc_result = batch_mc([{
            "name": f"{team_a} vs {team_b}",
            "lam_a": lam_a, "sigma_a": sigma_a,
            "lam_b": lam_b, "sigma_b": sigma_b,
            "markets": mc_mkt_keys,
        }])
        mc_probs = mc_result.get(f"{team_a} vs {team_b}", {})
    else:
        mc_probs = {}

    # Price each market
    results = []
    for mkt in markets:
        mid = mkt["market_id"]
        name = mkt.get("market_name", "")
        arch = mkt.get("archetype", 0)
        mkt_extras = {**extras, **mkt.get("extras", {}), "win_band_40_60": win_band}

        # Override with MC result if available
        mc_key = mkt.get("mc_key")
        if mc_key and mc_key in mc_probs:
            p_int = int(round(mc_probs[mc_key] * 100))
            p_int = max(1, min(99, p_int))
            mode = "MC-integrated"
            driver = f"L8 MC (sigma_a={extras.get('sigma_a', 0.15*lam_a):.3f})"
        else:
            priced = price_market(name, arch, engine, mkt_extras)
            p_int = priced["p_int"]
            mode = priced["mode"]
            driver = mkt.get("driver", f"λ-engine lam_a={lam_a:.2f}/lam_b={lam_b:.2f}")

        results.append({
            "market_id": mid,
            "market_name": name,
            "archetype": arch,
            "p_int": p_int,
            "mode": mode,
            "driver": driver,
            "confidence": "MED",  # will be refined by Depth Pass
        })

    return results


def prepare_batch(
    lobby_id: str,
    priced_markets: List[Dict],
    existing_predictions: List[Dict],
    update_threshold: int = UPDATE_THRESHOLD_DEFAULT,
) -> Tuple[List[Dict], List[Dict]]:
    """
    §7 Split markets into new submissions vs updates.

    Returns (to_submit, to_update).
    to_submit: new markets for submit_predictions_batch
    to_update: {prediction_id, probability} for update_prediction calls
    """
    existing_by_market = {
        p["market_id"]: p for p in existing_predictions
    }

    to_submit = []
    to_update = []

    for m in priced_markets:
        mid = m["market_id"]
        p_new = m["p_int"]

        if mid not in existing_by_market:
            # New market
            to_submit.append({
                "market_id": mid,
                "lobby_id": lobby_id,
                "probability": p_new,
                "_name": m.get("market_name", ""),
            })
        else:
            existing = existing_by_market[mid]
            p_old = int(round(existing["probability"] * 100))
            delta = abs(p_new - p_old)

            if delta >= update_threshold and existing.get("status") == "open":
                to_update.append({
                    "prediction_id": existing["id"],
                    "probability": p_new,
                    "_old": p_old,
                    "_new": p_new,
                    "_market": m.get("market_name", ""),
                })

    # Chunk submissions into batches of MAX_BATCH_SIZE
    batches = [to_submit[i:i + MAX_BATCH_SIZE]
               for i in range(0, len(to_submit), MAX_BATCH_SIZE)]

    print(f"  Batch prep: {len(to_submit)} new | {len(to_update)} updates | "
          f"{len(batches)} batch(es)")

    return to_submit, to_update


def validate_prediction(p_int: int, market_name: str = "",
                         anchor_p: Optional[int] = None,
                         driver: Optional[str] = None,
                         anchored: bool = False) -> Tuple[bool, str]:
    """
    Run quality gates before any write (§0.1).
    Returns (pass, message).
    """
    issues = []

    # Gate (a): integer 1-99
    if not isinstance(p_int, int) or not 1 <= p_int <= 99:
        issues.append(f"p={p_int} not in 1-99 (D3)")

    # Gate (b): coherence — run in batch context via check_coherence
    # Individual checks here:
    if p_int == 50:
        issues.append("Exactly 50 — avoid (D3, breaks §9.2 decode)")

    # Gate (c): driver
    if not driver or driver.strip() == "":
        issues.append("No driver stated (D4/D9)")

    # Gate (d): anchor deviation
    if anchor_p is not None and abs(p_int - anchor_p) > 10 and not driver:
        issues.append(f"|final-anchor|={abs(p_int-anchor_p)} > 10, no driver (§5.11)")

    # Gate (e): noisy register clamp
    from constants import NOISY_MARKETS
    if any(n.lower() in market_name.lower() for n in NOISY_MARKETS):
        if not anchored and (p_int < 15 or p_int > 85):
            issues.append(f"Noisy market '{market_name}' outside 15-85 (§5.9)")

    if issues:
        return False, " | ".join(issues)
    return True, "PASS"


# ─── Quick calculation helpers (run via Bash) ─────────────────────────────────

def calc_devig(odds_str: str) -> None:
    """CLI: python run_session.py devig 1.80 3.40 5.00"""
    parts = list(map(float, odds_str.split()))
    if len(parts) == 3:
        result = devig_1x2(*parts)
        print(json.dumps(result, indent=2))
    elif len(parts) == 2:
        result = devig_ou(*parts)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: devig <home_odds> <draw_odds> <away_odds>")


def calc_lambda(odds_str: str) -> None:
    """CLI: python run_session.py lambda 1.80 3.40 5.00 1.80 2.10"""
    parts = list(map(float, odds_str.split()))
    if len(parts) == 5:
        dec_h, dec_d, dec_a, dec_o, dec_u = parts
        dv = devig_1x2(dec_h, dec_d, dec_a)
        dv_ou = devig_ou(dec_o, dec_u)
        T = ou_to_T(dv_ou["over"])
        lam_a, lam_b = find_split(T, dv["home"], dv["draw"], dv["away"])
        engine = LambdaEngine(lam_a, lam_b)
        print(json.dumps(engine.summary(), indent=2))
    else:
        print("Usage: lambda <h_odds> <d_odds> <a_odds> <over_odds> <under_odds>")


def calc_mc(matches_json: str) -> None:
    """CLI: python run_session.py mc '[{"name":"A vs B","lam_a":1.5,"sigma_a":0.2,"lam_b":1.2,"sigma_b":0.18,"markets":["btts3plus","over_2.5"]}]'"""
    matches = json.loads(matches_json)
    result = batch_mc(matches)
    for name, probs in result.items():
        print(f"\n{name}:")
        for mkt, p in probs.items():
            print(f"  {mkt}: {int(round(p*100))}")


def calc_tie_trap(stat: str, m_a: float, m_b: float) -> None:
    """CLI: python run_session.py tie_trap corners 4.5 3.5"""
    p = p_strict_more(m_a, m_b)
    print(f"P({stat} A more than B): {int(round(p*100))} (raw {p:.4f})")
    print(f"m_a={m_a}, m_b={m_b}, tie mass approx={1-p/(0.5):.3f}")


# ─── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nSubcommands: devig | lambda | mc | tie_trap")
        sys.exit(0)

    cmd = sys.argv[1]
    args = " ".join(sys.argv[2:])

    if cmd == "devig":
        calc_devig(args)
    elif cmd == "lambda":
        calc_lambda(args)
    elif cmd == "mc":
        calc_mc(args)
    elif cmd == "tie_trap":
        parts = args.split()
        if len(parts) == 3:
            calc_tie_trap(parts[0], float(parts[1]), float(parts[2]))
        else:
            print("Usage: tie_trap <stat> <m_a> <m_b>")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
