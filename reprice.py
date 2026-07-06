#!/usr/bin/env python3
"""Anchors -> full priced sheet -> Δ-gated payloads, in one command.

This is the whole depth-pass math step (§3.2 step 4) as a CLI. Feed it a
match spec (fresh odds + optional player/stat overrides), the live markets
for that match, and (optionally) your open predictions; it prints every
market's routed price and the exact update/submit payloads to send.

    python3 reprice.py --spec por_esp.json --markets markets.json \
                       [--predictions preds.json] [--threshold 3]

Match spec JSON:
    {
      "code_a": "POR", "code_b": "ESP",
      "odds_1x2": [4.10, 3.60, 1.87],        // decimal, listed-team first
      "odds_ou25": [2.00, 1.8333],           // [over, under]
      "odds_advance": [2.80, 1.4444],        // [team_a, team_b] (KO only)
      "overrides": {"corners_b": 6.2, "cards_a": 2.1},
      "players": {
        "Cristiano Ronaldo": {"team": "a", "goal_share": 0.32, "sot_lam": 1.1},
        "Romelu Lukaku":     {"team": "b", "goal_share": 0.35, "minutes": 0.33}
      }
    }

Prices are honest model outputs (D2); FALLBACK-labeled rows are D4 base
rates — report them as such. Anything the router can't price is listed as
UNROUTED and must be priced by hand before the batch goes out (D1).
"""

from __future__ import annotations

import argparse
import json

from engine.markets import MatchContext, PlayerCtx, price_question
from session_tools import plan_submissions, plan_updates


def build_context(spec: dict) -> MatchContext:
    ctx = MatchContext.from_anchors(
        spec["code_a"], spec["code_b"],
        odds_1x2=spec.get("odds_1x2"), odds_ou25=spec.get("odds_ou25"),
        p1x2=tuple(spec["p1x2"]) if "p1x2" in spec else None,
        over25=spec.get("over25"),
        odds_advance=spec.get("odds_advance"),
        **spec.get("overrides", {}),
    )
    for name, p in spec.get("players", {}).items():
        ctx.players[name] = PlayerCtx(**p)
    return ctx


def price_all(ctx: MatchContext, markets: list[dict]) -> tuple[dict, list]:
    prices, unrouted = {}, []
    for m in markets:
        if m.get("status") != "open":
            continue
        out = price_question(m["question"], ctx)
        if out is None:
            unrouted.append(m)
        else:
            prices[m["id"]] = out[0]
    return prices, unrouted


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--markets", required=True)
    ap.add_argument("--predictions", help="list_predictions dump (optional)")
    ap.add_argument("--threshold", type=int, default=3)
    args = ap.parse_args()

    spec = json.load(open(args.spec))
    markets = json.load(open(args.markets))
    ctx = build_context(spec)
    print(f"{spec['code_a']} vs {spec['code_b']}: "
          f"T={ctx.t:.2f} lam=({ctx.lam_a:.2f}, {ctx.lam_b:.2f}) "
          f"1X2={tuple(round(p * 100, 1) for p in ctx.reg_1x2())}")

    prices, unrouted = price_all(ctx, markets)
    for m in markets:
        if m["id"] in prices:
            label = price_question(m["question"], ctx)[1]
            print(f"  {prices[m['id']]:>3}  [{label:<16}] {m['question'][:78]}")
    for m in unrouted:
        print(f"  ---  [UNROUTED        ] {m['question'][:78]}")

    if args.predictions:
        preds = json.load(open(args.predictions))
        open_preds = [p for p in preds if p.get("market_status") == "open"]
        ups = plan_updates(open_preds, prices, args.threshold)
        subs = plan_submissions(markets, preds, prices)
        print(f"\nupdate_prediction payloads (delta >= {args.threshold}): "
              f"{len(ups)}")
        print(json.dumps([{k: u[k] for k in ("prediction_id", "probability")}
                          for u in ups], indent=1))
        print(f"submit_predictions_batch payloads (uncovered): {len(subs)}")
        print(json.dumps(subs, indent=1))


if __name__ == "__main__":
    main()
