"""
Session orchestration — §3 (complete protocol).

Each session:
  1. TRIAGE (2 min): list_matches + list_predictions + list_results → coverage states
  2. SETTLE AUDIT: decode outcomes, update base rates, grade lessons
  3. DEPTH PASS (near <48h): full §6.3 spec per match
  4. COVERAGE SWEEP (mid/far): PASS-1, 12–16 target/session
  5. REPORT: after-action + STATUS BLOCK + NEXT CHECK-IN

This module provides functions that an autonomous agent session calls sequentially.
It does NOT call MCP tools directly — it prepares tool call lists and
processes responses, so it works equally in Claude Projects and any MCP host.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from bot.config import (
    EVENT_ID, LOBBY_ID,
    NEAR_HORIZON_SEC, MID_HORIZON_SEC, ZERO_MISS_SEC, DEPTH_PASS_SEC,
    STAGE_WEIGHTS, L8_AXIS_MARKET_THRESHOLD,
)
from bot.utils import (
    now_ist, format_ist, seconds_to_kickoff, horizon_label,
    decode_outcome_from_brier, noisy_register_clamp, clamp,
)
from bot.state import CoverageTracker, LessonsLedger, CalibrationRecord, BaseRateTracker
from bot.engine import (
    devig_power, fit_lambda, poisson_prob_over, btts_prob,
    archetype_win, archetype_goals_over_under, archetype_btts_and_over,
    archetype_team_scores_2h, archetype_team_scores, archetype_strict_comparison,
    archetype_threshold_count, archetype_player_prop_goal, archetype_player_prop_sot,
    archetype_ht_tied, archetype_ht_both_sot, archetype_joint_sequence, archetype_drama,
    dixon_coles_adjust, overlay_scan, run_mc_correlation, coherence_check,
    l10_l12_corrections, BASE_RATES,
)
from bot.api import (
    call_list_matches, call_list_markets, call_list_predictions, call_list_results,
    call_join_lobby, build_batch, quality_gates_pass, triage_tool_calls,
    handle_409_already_predicted,
)
from bot.reporting import (
    status_block, after_action_report, rbp_scoreboard,
    settle_audit_report, deep_audit_report,
)


# ---------------------------------------------------------------------------
# SESSION STATE (ephemeral, lives for one session per D10)
# ---------------------------------------------------------------------------

class Session:
    def __init__(self):
        self.coverage    = CoverageTracker()
        self.lessons     = LessonsLedger()
        self.calibration = CalibrationRecord()
        self.base_rates  = BaseRateTracker()

        self.matches:     List[Dict] = []
        self.predictions: List[Dict] = []
        self.results:     List[Dict] = []
        self.flags:       List[str]  = []

        self.depth_pass_count    = 0
        self.depth_market_count  = 0
        self.sweep_count         = 0
        self.sweep_market_count  = 0

        self._pred_by_market: Dict[str, Dict] = {}

    # -----------------------------------------------------------------------
    # 1. TRIAGE (§3.1)
    # -----------------------------------------------------------------------

    def ingest_triage(
        self,
        matches: List[Dict],
        predictions: List[Dict],
        results: List[Dict],
    ) -> str:
        """Load live API data and reconcile coverage states."""
        self.matches     = matches
        self.predictions = predictions
        self.results     = results

        # Index predictions by market_id for quick lookup
        self._pred_by_market = {p["market_id"]: p for p in predictions if "market_id" in p}

        # Reconcile coverage
        self.coverage.update_from_live(matches, predictions)

        # Check for zero-miss violations (D1)
        for m in self.coverage.all_matches():
            secs = seconds_to_kickoff(m["opening_time"])
            if 0 < secs <= ZERO_MISS_SEC and m["coverage"] == "UNCOVERED":
                self.flags.append(f"URGENT: {m['name']} reaches T-12h UNCOVERED — cover immediately!")

        return self._build_triage_summary()

    def _build_triage_summary(self) -> str:
        """Print deadline table sorted by urgency."""
        table = self.coverage.deadline_table()
        lines = ["TRIAGE — " + now_ist().strftime("%Y-%m-%d %H:%M IST")]
        lines.append(f"  Matches tracked: {len(self.matches)}")
        lines.append(f"  Open predictions: {len(self.predictions)}")
        lines.append(f"  Settled results: {len(self.results)}")
        lines.append("")
        lines.append(f"  {'Match':<25} {'Kickoff (IST)':<20} {'Horizon':<6} {'Coverage':<18} {'Urgency'}")
        lines.append("  " + "-" * 90)
        for row in table[:20]:
            urg = "URGENT" if row["urgent"] else ""
            lines.append(
                f"  {row['name']:<25} {row['kickoff_ist']:<20} "
                f"{horizon_label(row['opening_time']):<6} {row['coverage']:<18} {urg}"
            )
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # 2. SETTLE AUDIT (§3.2)
    # -----------------------------------------------------------------------

    def run_settle_audit(self) -> str:
        """Decode outcomes, update base rates, grade lessons, trigger deep audit if due."""
        newly_settled = [r for r in self.results if r.get("brier_score") is not None]

        for r in newly_settled:
            p_sub = r.get("probability_submitted", r.get("probability", 0))
            if isinstance(p_sub, float) and p_sub <= 1:
                p_sub = int(round(p_sub * 100))
            outcome = decode_outcome_from_brier(p_sub, r["brier_score"])
            if outcome is not None:
                # Update base rates via empirical Bayes
                market_type = r.get("market_type", "")
                if market_type:
                    self.base_rates.record_outcome(market_type, outcome)

        report = settle_audit_report(self.results, self.calibration)

        # Check deep audit threshold
        if len(newly_settled) >= 50 or (len(self.results) > 0 and len(self.results) % 60 < 5):
            report += "\n\n" + deep_audit_report(self.results, self.calibration, self.lessons)

        return report

    # -----------------------------------------------------------------------
    # 3. MARKET CLASSIFICATION & PROBABILITY COMPUTATION
    # -----------------------------------------------------------------------

    def classify_market(self, market: Dict) -> str:
        """
        §5.0: ANCHORED vs MODELED.
        ANCHORED: 1X2, O/U, BTTS, anytime scorer (60-70% devigged odds + 30-40% fundamentals).
        MODELED: 2H splits, corners, SOT, cards, combos (~50% fundamentals).
        """
        q = market.get("question", "").lower()
        anchored_keywords = [
            "win", "draw", "over 2.5", "under 2.5", "both teams to score",
            "anytime scorer", "goal scorer",
        ]
        for kw in anchored_keywords:
            if kw in q:
                return "ANCHORED"
        return "MODELED"

    def compute_probability(
        self,
        market: Dict,
        lam_h: float,
        lam_a: float,
        devigged_1x2: Optional[Tuple[float, float, float]] = None,
        odds_anchor_fresh: bool = True,
        situational_kwargs: Optional[Dict] = None,
    ) -> Dict:
        """
        Route market to the correct archetype and return enriched market dict with 'p'.
        Applies coherence, L10/L12 corrections, overlays, and DC adjustments.

        Returns: market dict with keys: p, mode, confidence, driver, anchored, odds_anchor_fresh.
        """
        q = market.get("question", "").lower()
        mode = self.classify_market(market)
        result = dict(market)
        result["mode"] = mode
        result["odds_anchor_fresh"] = odds_anchor_fresh
        sit = situational_kwargs or {}

        p = 50.0  # fallback
        driver = "base-rate fallback"
        confidence = "LOW"

        lam_total = lam_h + lam_a

        # 12-archetype dispatch
        if "home win" in q or ("win" in q and "home" in q):
            if devigged_1x2:
                p = devigged_1x2[0] * 100
                p = l10_l12_corrections(p, "win", bool(sit.get("driver")))
                driver = "devigged 1X2 home win + DC-draw"
            else:
                p = archetype_win(0.40)  # fallback
                driver = "base-rate fallback: no 1X2 odds"
                confidence = "LOW"

        elif "away win" in q or ("win" in q and "away" in q):
            if devigged_1x2:
                p = devigged_1x2[2] * 100
                p = l10_l12_corrections(p, "win", bool(sit.get("driver")))
                driver = "devigged 1X2 away win + DC-draw"
            else:
                p = 35.0
                driver = "base-rate fallback"
                confidence = "LOW"

        elif "draw" in q and "win" not in q.replace("draw", ""):
            if devigged_1x2:
                _, p_draw_raw, _ = devigged_1x2
                # Dixon-Coles: inflate draw in tight matches (L12)
                is_tight = lam_h > 0 and abs(lam_h - lam_a) / lam_total < 0.3
                p_draw_adj, p_btts_adj, p_over_adj = dixon_coles_adjust(
                    p_draw_raw * 100,
                    btts_prob(lam_h, lam_a) * 100,
                    poisson_prob_over(lam_total, 2.5) * 100,
                    is_tight_match=is_tight,
                    is_defensive_match=lam_total < 2.0,
                )
                p = p_draw_adj
                driver = "devigged draw + DC draw-inflation"
            else:
                p = BASE_RATES["btts"] * 50  # rough fallback
                driver = "base-rate fallback"
                confidence = "LOW"

        elif "over 2.5" in q:
            p = archetype_goals_over_under(lam_total, 2.5, "over")
            driver = f"Poisson O/U 2.5 λ={lam_total:.2f}"

        elif "under 2.5" in q:
            p = archetype_goals_over_under(lam_total, 2.5, "under")
            driver = f"Poisson U/O 2.5 λ={lam_total:.2f}"

        elif "over 1.5" in q:
            p = archetype_goals_over_under(lam_total, 1.5, "over")
            driver = f"Poisson O/U 1.5 λ={lam_total:.2f}"

        elif "over 3.5" in q:
            p = archetype_goals_over_under(lam_total, 3.5, "over")
            driver = f"Poisson O/U 3.5 λ={lam_total:.2f}"

        elif "both teams to score" in q or "btts" in q:
            p = btts_prob(lam_h, lam_a) * 100
            driver = f"BTTS Poisson λ_h={lam_h:.2f} λ_a={lam_a:.2f}"

        elif "btts and" in q and ("3+" in q or "over 2" in q):
            p = archetype_btts_and_over(lam_h, lam_a, 2.0)
            driver = f"BTTS AND 3+ = BTTS − P(1-1)"

        elif "score" in q and "2nd half" in q or "score in" in q and "half" in q:
            # Determine which team
            lam_team = lam_h  # default home; caller should pass correct lambda
            if "away" in q:
                lam_team = lam_a
            p = archetype_team_scores_2h(lam_team)
            driver = f"2H Poisson 1−e^(−0.55λ) λ={lam_team:.2f}"

        elif "score" in q and ("anytime" in q or "to score" in q) and "player" not in q:
            lam_team = lam_h
            if "away" in q:
                lam_team = lam_a
            p = archetype_team_scores(lam_team)
            driver = f"team scores ≥1 Poisson λ={lam_team:.2f}"

        elif "more corner" in q or "more fouls" in q or "more shot" in q:
            # Strict comparison — tie-trap
            lam_a_count = sit.get("lam_a_corners", 5.0)
            lam_b_count = sit.get("lam_b_corners", 5.0)
            p = archetype_strict_comparison(lam_a_count, lam_b_count)
            driver = f"tie-trap §5.4 grid lam_h={lam_a_count:.1f} lam_a={lam_b_count:.1f}"

        elif "corner" in q and any(f"{n}+" in q for n in range(3, 15)):
            for n in range(3, 15):
                if f"{n}+" in q:
                    lam_corners = sit.get("lam_corners", 10.0)
                    p = archetype_threshold_count(lam_corners, n)
                    driver = f"Poisson corners ≥{n} λ_corners={lam_corners:.1f}"
                    break

        elif "card" in q and any(f"{n}+" in q for n in range(1, 10)):
            for n in range(1, 10):
                if f"{n}+" in q:
                    lam_cards = sit.get("lam_cards", 4.0)
                    p = archetype_threshold_count(lam_cards, n)
                    driver = f"Poisson cards ≥{n} λ_cards={lam_cards:.1f}"
                    break

        elif "shot on target" in q or "sot" in q:
            if "player" in q or "anytime" in q:
                p = archetype_player_prop_sot(
                    lam_team_sot=sit.get("lam_team_sot", 4.5),
                    share_of_team_sot=sit.get("player_sot_share", 0.22),
                    rotation_risk=sit.get("rotation_risk", 0.0),
                )
                has_driver = bool(sit.get("driver"))
                p = l10_l12_corrections(p, "player_sot", has_driver)
                driver = f"player 1+SOT L10-corrected band"
            else:
                lam_sot = sit.get("lam_sot", 4.5)
                threshold = sit.get("sot_threshold", 2)
                p = archetype_threshold_count(lam_sot, threshold)
                driver = f"Poisson SOT ≥{threshold} λ={lam_sot:.1f}"

        elif "score" in q and ("anytime" in q or "goal" in q) and "player" in q:
            p = archetype_player_prop_goal(
                lam_team=lam_h,
                share_of_team_goals=sit.get("player_goal_share", 0.20),
                is_starting=sit.get("is_starting", True),
                rotation_risk=sit.get("rotation_risk", 0.0),
            )
            driver = f"player anytime goal L7+λ_share"

        elif "half time" in q and "draw" in q or "ht" in q and ("tied" in q or "draw" in q):
            p = archetype_ht_tied(lam_h, lam_a)
            driver = f"HT tied Poisson+Bessel-ceiling (L9) λ_h={lam_h:.2f} λ_a={lam_a:.2f}"

        elif "penalty" in q or "pen" in q:
            br = self.base_rates.get_rate("penalty")
            p = archetype_drama("penalty", br, sit.get("eb_n", 0), sit.get("eb_k", 0))
            driver = f"penalty base-rate EB p={br:.2f} (§5.8)"

        elif "red card" in q:
            br = self.base_rates.get_rate("red_card")
            p = archetype_drama("red_card", br, sit.get("eb_n", 0), sit.get("eb_k", 0))
            driver = f"red card base-rate EB p={br:.2f} (§5.8)"

        else:
            # Unknown archetype → base-rate fallback (D4)
            p = 50.0
            driver = "unknown archetype — base-rate fallback (D4)"
            confidence = "LOW"
            result["research_tier"] = "base_rate_fallback"

        # Situational overlays (§5.12)
        if sit:
            p, overlay_notes = overlay_scan(
                p,
                altitude_m=sit.get("altitude_m", 0),
                is_reigning_champion=sit.get("reigning_champion", False),
                is_lowland_side_vs_altitude=sit.get("lowland_vs_altitude", False),
                matchday3_rotation_risk=sit.get("matchday3_rotation_risk", 0.0),
            )
            if overlay_notes:
                driver += " | overlays: " + "; ".join(overlay_notes)

        # Noisy-register clamp (§5.9 / D2/D11)
        anchored = mode == "ANCHORED" and odds_anchor_fresh
        p_int = noisy_register_clamp(p, anchored=anchored)

        # Don't submit exactly 50 (D3)
        if p_int == 50:
            p_int = 51

        result["p"]               = p_int
        result["driver"]          = driver
        result["confidence"]      = confidence if confidence == "LOW" else ("HIGH" if odds_anchor_fresh else "MED")
        result["anchored"]        = anchored
        result["match_id"]        = market.get("match_id", "")
        result["market_id"]       = market.get("id", market.get("market_id", ""))
        result["anchor_p"]        = round(p, 1)  # pre-clamp, for coherence gate
        return result

    # -----------------------------------------------------------------------
    # 4. DEPTH PASS (§6.3) — near-horizon <48h
    # -----------------------------------------------------------------------

    def prepare_depth_pass(self, match: Dict, markets: List[Dict]) -> Dict:
        """
        Prepare the Depth Pass packet for a near-horizon match.
        Returns a dict of required lookups and market computations.
        The caller (agent) must execute the lookups and call finalize_depth_pass().
        """
        secs = seconds_to_kickoff(match.get("opening_time", ""))
        assert secs < DEPTH_PASS_SEC, "Not a near-horizon match"

        return {
            "match":           match,
            "markets":         markets,
            "required_lookups": [
                "lineups_confirmed",        # today's date
                "injuries_suspensions",
                "referee_profile_cards",
                "weather_check",
                "fresh_odds_within_2h",     # ≤2h to kickoff
                "polymarket_exchange_cross", # cross-check
            ],
            "l8_required": len(markets) > L8_AXIS_MARKET_THRESHOLD,
            "update_threshold": 3,          # abs(Δ) ≥ 3 triggers update (≥2 for props post-lineup)
        }

    def finalize_depth_pass(
        self,
        match: Dict,
        markets: List[Dict],
        lam_h: float,
        lam_a: float,
        devigged_1x2: Optional[Tuple[float, float, float]],
        situational_kwargs: Dict,
        existing_predictions: List[Dict],
        run_l8_mc: bool = False,
    ) -> Tuple[List[Dict], List[Dict], str]:
        """
        Compute probabilities for all markets, apply coherence gates,
        build batch submissions or updates.

        Returns: (new_predictions, update_predictions, after_action_text)
        """
        computed = []
        for m in markets:
            enriched = self.compute_probability(
                m, lam_h, lam_a,
                devigged_1x2=devigged_1x2,
                odds_anchor_fresh=True,
                situational_kwargs=situational_kwargs,
            )
            computed.append(enriched)

        # L8 correlation cap: run MC if >4 markets share one latent axis
        if run_l8_mc:
            computed = run_mc_correlation(lam_h, lam_a, computed)
            # Replace p with p_mc if available and abs(Δ) significant
            for m in computed:
                if "p_mc" in m and abs(m["p_mc"] - m["p"]) >= 2:
                    m["p"] = clamp(m["p_mc"])
                    m["driver"] += f" | L8-MC p_mc={m['p_mc']:.1f}"

        # Coherence gates (§5.11)
        violations = coherence_check(computed)
        if violations:
            self.flags.extend([f"COHERENCE: {v}" for v in violations])

        # Split into new vs update
        new_preds   = []
        update_preds = []
        for m in computed:
            passed, gate_violations = quality_gates_pass(m)
            if not passed:
                self.flags.append(f"GATE_FAIL {m.get('question','')[:30]}: {gate_violations}")
                continue

            mid = m.get("market_id") or m.get("id", "")
            existing = self._pred_by_market.get(mid)
            if existing:
                old_p = existing.get("probability", 0)
                if isinstance(old_p, float) and old_p <= 1:
                    old_p = int(round(old_p * 100))
                delta = abs(m["p"] - old_p)
                # §6.3: update only abs(Δ) ≥ 3 (≥ 2 for props post-lineup)
                prop_threshold = 2 if "player" in m.get("question", "").lower() else 3
                if delta >= prop_threshold:
                    update_preds.append({**m, "prediction_id": existing["id"], "old_p": old_p})
            else:
                new_preds.append(m)

        self.depth_pass_count   += 1
        self.depth_market_count += len(new_preds) + len(update_preds)

        # RBP Opportunity Pass (§6.5)
        opportunity_pass = self._rbp_opportunity_pass(computed)

        report = after_action_report(
            match, new_preds + update_preds,
            stage=_infer_stage(match),
            opportunity_pass=opportunity_pass,
        )

        return new_preds, update_preds, report

    # -----------------------------------------------------------------------
    # 5. COVERAGE SWEEP (§3.4 / §6.4) — mid/far horizon PASS-1
    # -----------------------------------------------------------------------

    def prepare_pass1_sweep(self, target_per_session: int = 14) -> List[Dict]:
        """
        Return list of matches to cover in this session's PASS-1 sweep.
        Priority: UNCOVERED > PARTIAL, ordered by kickoff (chronological §13.9).
        """
        candidates = self.coverage.uncovered_or_partial()
        mid_far = [
            m for m in candidates
            if horizon_label(m["opening_time"]) in ("mid", "far")
        ]
        # Sort chronologically
        mid_far.sort(key=lambda x: x["opening_time"])
        return mid_far[:target_per_session]

    def finalize_pass1(
        self,
        match: Dict,
        markets: List[Dict],
        lam_h: float,
        lam_a: float,
        devigged_1x2: Optional[Tuple[float, float, float]],
        situational_kwargs: Optional[Dict] = None,
    ) -> Tuple[List[Dict], str]:
        """
        PASS-1: 2–4 lookups/match. Compute probabilities, no Depth Pass overhead.
        Returns (new_predictions, brief_report).
        """
        sit = situational_kwargs or {}
        computed = []
        for m in markets:
            enriched = self.compute_probability(
                m, lam_h, lam_a,
                devigged_1x2=devigged_1x2,
                odds_anchor_fresh=False,  # mid/far: anchor may be older
                situational_kwargs=sit,
            )
            computed.append(enriched)

        violations = coherence_check(computed)
        if violations:
            self.flags.extend([f"COHERENCE (PASS-1): {v}" for v in violations])

        new_preds = []
        for m in computed:
            passed, _ = quality_gates_pass(m)
            if passed:
                new_preds.append(m)

        self.sweep_count       += 1
        self.sweep_market_count += len(new_preds)

        brief = (
            f"PASS-1 {match.get('name','?')}: "
            f"{len(new_preds)}/{len(markets)} markets queued | "
            f"λ_h={lam_h:.2f} λ_a={lam_a:.2f}"
        )
        return new_preds, brief

    # -----------------------------------------------------------------------
    # 6. RBP OPPORTUNITY PASS (§6.5)
    # -----------------------------------------------------------------------

    def _rbp_opportunity_pass(self, computed_markets: List[Dict]) -> Dict:
        """
        Per match: identify top-3 RBP-opportunity markets and ask "why is crowd wrong?"
        """
        # Sort by distance from 50 (most opinionated = most RBP opportunity)
        sorted_m = sorted(computed_markets, key=lambda m: abs(m.get("p", 50) - 50), reverse=True)
        opportunities = []
        for m in sorted_m[:3]:
            p = m.get("p", 50)
            label = "STRONG" if abs(p - 50) > 20 else ("MODERATE" if abs(p - 50) > 10 else "THIN")
            opportunities.append({
                "market":          m.get("question", "")[:50],
                "p":               p,
                "label":           label,
                "driver":          m.get("driver", ""),
                "why_crowd_wrong": _infer_crowd_error(m, label),
            })
        return {"opportunities": opportunities}

    # -----------------------------------------------------------------------
    # 7. SESSION REPORT ASSEMBLY
    # -----------------------------------------------------------------------

    def build_session_report(
        self,
        submitted_count: int,
        updated_count: int,
        crowd_briers: Optional[Dict] = None,
        next_checkin_ist: Optional[str] = None,
    ) -> str:
        status = status_block(
            matches=self.matches,
            predictions=self.predictions,
            results=self.results,
            coverage_tracker=self.coverage,
            next_checkin_ist=next_checkin_ist,
            flags=self.flags,
            actions_depth=self.depth_pass_count,
            actions_markets_depth=self.depth_market_count,
            actions_sweep=self.sweep_count,
            actions_markets_sweep=self.sweep_market_count,
        )

        # Stage is group for now; override when knockout
        scoreboard = rbp_scoreboard(self.results, crowd_briers, stage="group")

        summary = (
            f"\nSESSION SUMMARY\n"
            f"  Submitted: {submitted_count} new | Updated: {updated_count}\n"
            f"  Depth Passes: {self.depth_pass_count} matches / {self.depth_market_count} markets\n"
            f"  Sweeps:       {self.sweep_count} matches / {self.sweep_market_count} markets\n"
        )
        return "\n\n".join([status, scoreboard, summary])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_stage(match: Dict) -> str:
    name = match.get("name", "").lower()
    if "final" in name:
        return "final"
    if any(k in name for k in ["quarter", "semi", "round", "r32", "r16", "knockout"]):
        return "knockout"
    return "group"


def _infer_crowd_error(market: Dict, label: str) -> str:
    """Heuristic explanation of why crowd might be wrong (§6.5)."""
    q = market.get("question", "").lower()
    p = market.get("p", 50)
    if "player" in q and "sot" in q and label in ("STRONG", "MODERATE"):
        return "L10: player SOT 56-70 band runs HOT; lineup not yet fully public"
    if "win" in q and 40 <= p <= 60:
        return "L12: win markets in 40-60 band run HOT; DC-draw correction applied"
    if "penalty" in q or "red" in q:
        return "L5: crowd over-reacts to last-match drama events; base-rate anchors"
    if p > 70:
        return "L15: fav-longshot crowd bias may over-price hot favourite"
    if p < 30:
        return "L15: fav-longshot crowd bias may under-price longshot"
    return "no specific crowd-error thesis; calibrated estimate"


# ---------------------------------------------------------------------------
# Lambda estimation helpers (called by agent with real odds data)
# ---------------------------------------------------------------------------

def estimate_lambdas(
    ou25_odds: Optional[List[float]] = None,
    home_odds: Optional[float] = None,
    draw_odds: Optional[float] = None,
    away_odds: Optional[float] = None,
    fallback_total_goals: float = 2.5,
) -> Tuple[float, float, Optional[Tuple[float, float, float]]]:
    """
    Given raw decimal odds, devig and fit lambdas.
    Returns (lam_h, lam_a, devigged_1x2) or sensible defaults.
    """
    devigged_1x2 = None

    # Devig O/U 2.5
    if ou25_odds and len(ou25_odds) == 2:
        fair_ou = devig_power(ou25_odds)
        ou_over_prob = fair_ou[0]  # over is typically first
    else:
        ou_over_prob = 0.56  # base rate fallback

    # Devig 1X2
    if home_odds and draw_odds and away_odds:
        fair_1x2 = devig_power([home_odds, draw_odds, away_odds])
        devigged_1x2 = tuple(fair_1x2)
        lam_h, lam_a = fit_lambda(ou_over_prob, *fair_1x2)
    else:
        lam_total = fallback_total_goals
        lam_h, lam_a = lam_total / 2, lam_total / 2

    return lam_h, lam_a, devigged_1x2
