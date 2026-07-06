#!/usr/bin/env python3
"""CLI: full engine baseline for a match from its two anchored numbers.

Usage:
    python3 run_match.py --home 48 --draw 25 --away 27 --over25 51 \
        [--team-a NED] [--team-b JPN] [--cards-lam 3.5]

    # from raw decimal odds instead of devigged probs:
    python3 run_match.py --odds-1x2 2.05 3.4 3.9 --odds-ou 1.95 1.87 \
        [--team-a NED] [--team-b JPN]

Prints the §5.3 archetype sheet with drivers. Outputs are engine BASELINES —
overlays (§5.12), L12 draw inflation in the 40-60 win band, player/joint
props and the L10 driver gate remain operator steps.
"""

import argparse

from engine.devig import devig
from engine.matchsheet import build_match_sheet


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", type=int, help="devigged home-win prob (int)")
    ap.add_argument("--draw", type=int, help="devigged draw prob (int)")
    ap.add_argument("--away", type=int, help="devigged away-win prob (int)")
    ap.add_argument("--over25", type=int, help="devigged P(Over 2.5) (int)")
    ap.add_argument("--odds-1x2", nargs=3, type=float, metavar=("H", "D", "A"),
                    help="decimal odds; devig applied (§5.1)")
    ap.add_argument("--odds-ou", nargs=2, type=float, metavar=("OVER", "UNDER"),
                    help="decimal O/U 2.5 odds; devig applied")
    ap.add_argument("--team-a", default="A")
    ap.add_argument("--team-b", default="B")
    ap.add_argument("--cards-lam", type=float, default=None)
    args = ap.parse_args()

    if args.odds_1x2:
        r = devig(args.odds_1x2)
        h, d, a = (round(100 * p) for p in r["probs"])
        print(f"1X2 devig ({r['method']}, overround {r['overround']:.1%}): {h}/{d}/{a}")
    else:
        h, d, a = args.home, args.draw, args.away
    if args.odds_ou:
        r = devig(args.odds_ou)
        over25 = round(100 * r["probs"][0])
        print(f"O/U devig ({r['method']}): Over 2.5 = {over25}")
    else:
        over25 = args.over25
    if None in (h, d, a, over25):
        ap.error("need --home/--draw/--away/--over25 or --odds-1x2/--odds-ou")

    sheet = build_match_sheet(h, d, a, over25, team_a=args.team_a,
                              team_b=args.team_b, cards_lam=args.cards_lam)
    print(sheet.table())


if __name__ == "__main__":
    main()
