"""Command line entry point: `radar <stage>` or `radar run` for everything."""

from __future__ import annotations

import argparse

from .config import env


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="radar", description="Monthly AI supply-chain bottleneck research.")
    sub = parser.add_subparsers(dest="command", required=True)

    clone = sub.add_parser("clone", help="Stage 1: copy a fund's long-stock book from its latest 13F")
    clone.add_argument("--cik", default="0002045724", help="fund CIK (default: Situational Awareness LP)")
    clone.add_argument("--account-value", type=float, help="size the order list against this amount instead of your IBKR NAV")
    sub.add_parser("demand", help="Stage 2: hyperscaler capex in physical units")
    sub.add_parser("supply", help="Stage 3a: memory exports, export orders, turbine backlogs, grid queues")
    bottleneck = sub.add_parser("bottleneck", help="Stage 3b: the monthly call and memo")
    bottleneck.add_argument("--dry-run", action="store_true", help="save the prompt instead of calling the model")
    sub.add_parser("ibkr", help="pull positions from your IBKR Flex query into private/")
    sub.add_parser("exposure", help="Stage 4: your exposure to the bottleneck vs the consensus trade")
    sub.add_parser("site", help="render the public outputs in data/ into site/index.html")
    run = sub.add_parser("run", help="every stage in order, then the site; IBKR steps run only when Flex is configured")
    run.add_argument("--dry-run", action="store_true", help="skip the model call")

    args = parser.parse_args(argv)
    from . import bottleneck as bottleneck_stage
    from . import clone as clone_stage
    from . import demand, exposure, ibkr_flex, site, supply

    if args.command == "clone":
        clone_stage.run(args.cik, args.account_value)
    elif args.command == "demand":
        demand.run()
    elif args.command == "supply":
        supply.run()
    elif args.command == "bottleneck":
        bottleneck_stage.run(dry_run=args.dry_run)
    elif args.command == "ibkr":
        ibkr_flex.run()
    elif args.command == "exposure":
        exposure.run()
    elif args.command == "site":
        site.run()
    elif args.command == "run":
        flex_ready = bool(env("IBKR_FLEX_TOKEN") and env("IBKR_FLEX_QUERY_ID"))
        if flex_ready:
            ibkr_flex.run()
        clone_stage.run()
        demand.run()
        supply.run()
        call = bottleneck_stage.run(dry_run=args.dry_run)
        if flex_ready and call:
            exposure.run()
        site.run()


if __name__ == "__main__":
    main()
