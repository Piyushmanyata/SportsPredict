#!/usr/bin/env python3
"""
Quick market calculator — run from the bash tool to get integer probabilities fast.

Usage examples:

  # Full match from O/U 2.5 and 1X2 prices:
  python3 calc.py match --ou25 0.46 --home 0.52 --draw 0.27 --away 0.21

  # Lambda model directly:
  python3 calc.py match --lam-a 1.6 --lam-b 1.0

  # Monte Carlo (L8) on a single match:
  python3 calc.py mc --lam-a 1.6 --lam-b 1.0 --sigma-a 0.24 --sigma-b 0.15

  # Tie-trap:
  python3 calc.py tie-trap --stat ft_corners --ratio 1.3

  # HT-tied:
  python3 calc.py ht-tied --lam-a 1.2 --lam-b 1.0

  # Player props:
  python3 calc.py player --team-lam 1.6 --goal-share 0.35 --role main_striker

  # Devig 3-way:
  python3 calc.py devig --odds 2.10 2.80 3.60

  # Power devig:
  python3 calc.py devig --odds 2.10 2.80 3.60 --method power

  # Brier audit:
  python3 calc.py brier --p 0.62 --b 0.1444       # decode outcome + stats
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from engine.devig import devig_3way, devig_2way, power_devig
from engine.lambda_engine import LambdaModel, ou25_to_T, fit_lambda_split
from engine.markets import compute_all_markets, check_coherence
from engine.tie_trap import tie_trap_prob, tie_trap_int, ht_tied_int, MEAN_STATS
from engine.player_props import PlayerPropEngine
from engine.mc_engine import mc_single, mc_to_int
from session.audit import decode_outcome, brier_vs_expected, expected_brier


def cmd_match(args):
    if args.lam_a and args.lam_b:
        model = LambdaModel(lam_a=args.lam_a, lam_b=args.lam_b)
    elif args.ou25 and args.home:
        p_h, p_d, p_a = devig_3way(1/args.home, 1/args.draw, 1/args.away) \
            if args.home < 1 else (args.home, args.draw, args.away)
        model = LambdaModel.from_ou25_and_1x2(args.ou25, p_h, p_d)
    else:
        print("Provide --lam-a/--lam-b or --ou25/--home/--draw/--away")
        sys.exit(1)

    print(f"\nλ_A={model.lam_a:.3f}  λ_B={model.lam_b:.3f}  T={model.T:.3f}")
    print(f"σ_A={model.sigma_a:.3f}  σ_B={model.sigma_b:.3f}  (L8 defaults)")
    print()

    lam_sot_a = args.sot_a or model.lam_a * 3.0
    lam_sot_b = args.sot_b or model.lam_b * 3.0
    mkts = compute_all_markets(
        model,
        lam_sot_a=lam_sot_a,
        lam_sot_b=lam_sot_b,
        lam_cards=args.lam_cards or 3.5,
    )

    print(f"{'Market':<28} {'p':>4}")
    print("-" * 34)
    for k, v in mkts.items():
        print(f"  {k:<26} {v:>4}")

    issues = check_coherence(mkts)
    if issues:
        print("\n⚠ Coherence issues:")
        for iss in issues:
            print(f"  • {iss}")
    else:
        print("\n✓ Coherence gates passed")


def cmd_mc(args):
    lam_a   = args.lam_a
    lam_b   = args.lam_b
    sigma_a = args.sigma_a or 0.15 * lam_a
    sigma_b = args.sigma_b or 0.15 * lam_b

    print(f"\nMC (n=2000): λ_A={lam_a:.3f}±{sigma_a:.3f}  λ_B={lam_b:.3f}±{sigma_b:.3f}")
    result = mc_single(lam_a, lam_b, sigma_a, sigma_b)
    ints   = mc_to_int(result)
    print(f"\n{'Market':<28} {'p (float)':>10} {'p (int)':>8}")
    print("-" * 50)
    for k in sorted(result.keys()):
        print(f"  {k:<26} {result[k]:>10.4f} {ints[k]:>8}")


def cmd_tie_trap(args):
    stat   = args.stat
    m      = args.m or MEAN_STATS.get(stat)
    ratio  = args.ratio or 1.0
    if m is None:
        print(f"Unknown stat '{stat}'. Choose from: {list(MEAN_STATS)}")
        sys.exit(1)
    p    = tie_trap_prob(stat=stat, m=m, strength_ratio=ratio)
    pint = tie_trap_int(stat=stat, m=m, strength_ratio=ratio)
    print(f"\n{stat} (m={m}, ratio={ratio}): P(A more) = {p:.3f} → {pint}")


def cmd_ht_tied(args):
    lam_a = args.lam_a
    lam_b = args.lam_b
    T     = lam_a + lam_b
    pint  = ht_tied_int(lam_a, lam_b, T=T)
    print(f"\nHT-tied: λ_A={lam_a} λ_B={lam_b} T={T:.2f} → {pint} (L9 ceiling 47 if T≥2.2)")


def cmd_player(args):
    eng = PlayerPropEngine(
        team_lam=args.team_lam,
        player_goal_share=args.goal_share,
        role=args.role or "main_striker",
        rotation_factor=args.rotation or 1.0,
    )
    props = eng.all_props(driver=args.driver)
    print(f"\nPlayer props (team_λ={args.team_lam}, goal_share={args.goal_share}, "
          f"role={args.role}, rotation={args.rotation or 1.0})")
    for k, v in props.items():
        print(f"  {k:<24} {v:>4}")


def cmd_devig(args):
    odds = args.odds
    if len(odds) == 2:
        p_yes, p_no = devig_2way(odds[0], odds[1], method=args.method or "auto")
        print(f"\nDevig 2-way: YES={p_yes:.3f} ({round(p_yes*100)}) | NO={p_no:.3f} ({round(p_no*100)})")
    elif len(odds) == 3:
        ph, pd, pa = devig_3way(odds[0], odds[1], odds[2], method=args.method or "auto")
        print(f"\nDevig 3-way: home={ph:.3f} ({round(ph*100)}) | draw={pd:.3f} ({round(pd*100)}) | away={pa:.3f} ({round(pa*100)})")
    else:
        print("Provide 2 or 3 decimal odds values.")
        sys.exit(1)


def cmd_brier(args):
    p = args.p
    b = args.b
    o = decode_outcome(p, b)
    exp = expected_brier(p)
    print(f"\np={p} | brier={b:.4f} | decoded outcome={o} | self-expected={exp:.4f} | gap={b-exp:+.4f}")


def main():
    parser = argparse.ArgumentParser(description="SportsPredict probability calculator")
    sub    = parser.add_subparsers(dest="cmd")

    # match
    p_match = sub.add_parser("match", help="Compute all markets for a match")
    p_match.add_argument("--lam-a",    type=float)
    p_match.add_argument("--lam-b",    type=float)
    p_match.add_argument("--ou25",     type=float, help="P(Over 2.5) devigged")
    p_match.add_argument("--home",     type=float, help="home win prob (or decimal odds if >1)")
    p_match.add_argument("--draw",     type=float)
    p_match.add_argument("--away",     type=float)
    p_match.add_argument("--sot-a",    type=float)
    p_match.add_argument("--sot-b",    type=float)
    p_match.add_argument("--lam-cards",type=float)

    # mc
    p_mc = sub.add_parser("mc", help="MC integration (L8)")
    p_mc.add_argument("--lam-a",   type=float, required=True)
    p_mc.add_argument("--lam-b",   type=float, required=True)
    p_mc.add_argument("--sigma-a", type=float)
    p_mc.add_argument("--sigma-b", type=float)

    # tie-trap
    p_tt = sub.add_parser("tie-trap", help="Strict comparison probability")
    p_tt.add_argument("--stat",  choices=list(MEAN_STATS.keys()), required=True)
    p_tt.add_argument("--m",     type=float, help="Override mean m")
    p_tt.add_argument("--ratio", type=float, help="strength_ratio lam_a/lam_b (default 1.0)")

    # ht-tied
    p_ht = sub.add_parser("ht-tied", help="HT-tied probability")
    p_ht.add_argument("--lam-a", type=float, required=True)
    p_ht.add_argument("--lam-b", type=float, required=True)

    # player
    p_pl = sub.add_parser("player", help="Player prop engine")
    p_pl.add_argument("--team-lam",   type=float, required=True)
    p_pl.add_argument("--goal-share", type=float, required=True)
    p_pl.add_argument("--role",       default="main_striker")
    p_pl.add_argument("--rotation",   type=float, default=1.0)
    p_pl.add_argument("--driver",     type=str,   help="Explicit driver to unlock L10 band top")

    # devig
    p_dv = sub.add_parser("devig", help="Devig decimal odds")
    p_dv.add_argument("--odds",   type=float, nargs="+", required=True)
    p_dv.add_argument("--method", choices=["auto", "multiplicative", "power"], default="auto")

    # brier
    p_br = sub.add_parser("brier", help="Decode outcome from Brier score")
    p_br.add_argument("--p", type=float, required=True, help="submitted probability (0-1 decimal)")
    p_br.add_argument("--b", type=float, required=True, help="Brier score")

    args = parser.parse_args()

    dispatch = {
        "match":    cmd_match,
        "mc":       cmd_mc,
        "tie-trap": cmd_tie_trap,
        "ht-tied":  cmd_ht_tied,
        "player":   cmd_player,
        "devig":    cmd_devig,
        "brier":    cmd_brier,
    }
    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
