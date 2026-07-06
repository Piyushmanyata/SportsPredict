"""Router + session-tools tests, pinned to the live market question inventory."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.markets import MatchContext, PlayerCtx, price_question
from session_tools import audit_snapshot, chunk, plan_submissions, plan_updates

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok  {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name} {detail}")


def make_ctx():
    ctx = MatchContext.from_anchors(
        "POR", "ESP",
        odds_1x2=[4.10, 3.60, 1.87], odds_ou25=[2.00, 1.8333],
        odds_advance=[2.80, 1.4444], corners_b=6.2,
    )
    ctx.players["Cristiano Ronaldo"] = PlayerCtx(team="a", goal_share=0.32, sot_lam=1.1)
    ctx.players["Lamine Yamal"] = PlayerCtx(team="b", goal_share=0.28, sot_lam=1.2)
    ctx.players["Bruno Fernandes"] = PlayerCtx(team="a", goal_share=0.20, sot_lam=0.85)
    ctx.players["Diogo Costa"] = PlayerCtx(team="a", is_gk=True)
    return ctx


# The 15 live POR-ESP questions from 2026-07-06 — every one must route.
LIVE_QUESTIONS = [
    "Will Cristiano Ronaldo (Portugal) score a goal (excluding own goals) in regulation (90 minutes + stoppage time)?",
    "Will Lamine Yamal (Spain) score or assist a goal (excluding own goals) in regulation (90 minutes + stoppage time)?",
    "Will Bruno Fernandes (Portugal) have 1 or more shots on target in regulation (90 minutes + stoppage time)?",
    "Will both halves have the same number of goals in regulation (90 minutes + stoppage time)?",
    "Will Portugal score the first goal of the match in regulation (90 minutes + stoppage time)?",
    "Will the match have 3 or more total goals in regulation (90 minutes + stoppage time)?",
    "Will Diogo Costa (Portugal) make 4 or more saves in regulation (90 minutes + stoppage time)?",
    "Will a substitute score a goal (excluding own goals) in regulation (90 minutes + stoppage time)?",
    "Will there be 4 or more total cards shown in regulation (90 minutes + stoppage time)?",
    "Will there be 9 or more total substitutions (both teams combined) in regulation (90 minutes + stoppage time)?",
    "Will Spain have 6 or more corner kicks in regulation (90 minutes + stoppage time)?",
    "Will the match go to extra time?",
    "Will any Portugal player have 2 or more shots on target in regulation (90 minutes + stoppage time)?",
    "Will Spain advance to the quarterfinals?",
    "Will the first card of the match be shown before the first goal is scored?",
]

# High-frequency archetypes from the settled ledger (949 predictions).
LEDGER_QUESTIONS = [
    "Will Portugal be caught offside 3 or more times?",
    "Will Spain win the match?",
    "Will Portugal commit more fouls than Spain?",
    "Will Spain have more shots on target than Portugal in the second half?",
    "Will both teams score AND the match have 3 or more total goals?",
    "Will Portugal score in the second half?",
    "Will Spain have 5 or more shots on target?",
    "Will the match have 2 or fewer total goals?",
    "Will a penalty kick be awarded OR a red card be shown?",
    "Will Portugal receive more cards than Spain?",
    "Will Spain score at least 1 goal?",
    "Will there be 8 or more total shots on target in the second half?",
    "At halftime, will the match be tied?",
    "Will both teams score in regulation (90 minutes + stoppage time)?",
    "Will Spain have 7 or more corner kicks?",
    "Will a goal be scored before the first hydration break?",
    "Will both teams have at least 1 shot on target in the second half?",
    "Will the second half have 2 or more total goals?",
    "Will Spain score more goals than Portugal in the second half?",
    "Will Portugal finish with more corner kicks than Spain?",
    "Will Spain be ahead at halftime?",
    "Will there be 22 or more total shots (on and off target) in regulation (90 minutes + stoppage time)?",
    "Will Spain win in regulation (90 minutes + stoppage time)?",
    "At halftime, will both teams have at least 1 shot on target?",
    "Will Spain keep a clean sheet in regulation (90 minutes + stoppage time)?",
    "Will the second half have more goals than the first half?",
    "Will Spain score the first goal of the second half?",
    "Will regulation (90 minutes + stoppage time) end in a tie?",
    "Will Spain win by 2 or more goals in regulation (90 minutes + stoppage time)?",
    "Will Portugal score in both halves in regulation (90 minutes + stoppage time)?",
    "Will an own goal be scored in regulation (90 minutes + stoppage time)?",
]


def test_router_covers_live_inventory():
    ctx = make_ctx()
    for q in LIVE_QUESTIONS + LEDGER_QUESTIONS:
        out = price_question(q, ctx)
        check(f"routes: {q[:60]}", out is not None)
        if out:
            p, _ = out
            check(f"D3-legal ({p}): {q[:48]}", 1 <= p <= 99 and p != 50)


def test_anchor_passthrough():
    ctx = make_ctx()
    p_adv, _ = price_question("Will Spain advance to the quarterfinals?", ctx)
    check("advance uses devigged anchor (66)", p_adv == 66, p_adv)
    p_et, _ = price_question("Will the match go to extra time?", ctx)
    check("extra time = devigged draw (26)", p_et == 26, p_et)
    p_o25, _ = price_question(
        "Will the match have 3 or more total goals in regulation (90 minutes + stoppage time)?", ctx)
    check("3+ goals ~= devigged over2.5 (48+-1)", 47 <= p_o25 <= 49, p_o25)


def test_ht_tied_ceiling():
    ctx = make_ctx()
    p, _ = price_question("At halftime, will the match be tied?", ctx)
    check("HT-tied respects L9 ceiling", p <= 47, p)


def test_first_goal_partition():
    ctx = make_ctx()
    pa, _ = price_question("Will Portugal score the first goal of the match?", ctx)
    pb, _ = price_question("Will Spain score the first goal of the match?", ctx)
    import math
    p_none = 100 * math.exp(-ctx.t)
    check("first-goal partition sums to ~100", abs(pa + pb + p_none - 100) < 2.5,
          (pa, pb, p_none))


def test_session_tools():
    open_preds = [
        {"id": "x1", "market_id": "m1", "probability": 42, "market_status": "open",
         "question": "q1"},
        {"id": "x2", "market_id": "m2", "probability": 60, "market_status": "open",
         "question": "q2"},
    ]
    ups = plan_updates(open_preds, {"m1": 44, "m2": 51})
    check("plan_updates gates at delta>=3", [u["prediction_id"] for u in ups] == ["x2"])
    markets = [{"id": "m3", "status": "open", "lobby_id": "L"},
               {"id": "m1", "status": "open", "lobby_id": "L"}]
    subs = plan_submissions(markets, open_preds, {"m1": 44, "m3": 30})
    check("plan_submissions only uncovered", [s["market_id"] for s in subs] == ["m3"])
    check("chunk splits at 50", [len(c) for c in chunk([{}] * 120)] == [50, 50, 20])
    snap = audit_snapshot([
        {"market_id": "a", "probability": 70, "brier_score": 0.09, "question": "s1",
         "market_status": "settled"},
        {"market_id": "b", "probability": 30, "brier_score": 0.09, "question": "s2",
         "market_status": "settled"},
    ] + open_preds)
    check("audit_snapshot counts", snap["n"] == 2 and snap["open"] == 2)
    check("audit_snapshot realized", abs(snap["realized"] - 0.09) < 1e-9)


if __name__ == "__main__":
    test_router_covers_live_inventory()
    test_anchor_passthrough()
    test_ht_tied_ceiling()
    test_first_goal_partition()
    test_session_tools()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print("all market/session tests passed")
