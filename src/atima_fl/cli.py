"""One interface shared by the GUI, local inspection, and cluster jobs."""

import argparse
import json
from pathlib import Path
from .core.configuration import ExperimentConfig
from .core.registry import Registry


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="atima", description="ATIMA-FL · modular experiment layer on Flower"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog", help="List discovered interchangeable components")
    catalog.add_argument("--plugins")
    ui = commands.add_parser("ui", help="Open the local experiment designer")
    ui.add_argument("--workspace", default="workspace")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--plugins")
    validate = commands.add_parser(
        "validate", help="Validate a profile without hardware/data access"
    )
    validate.add_argument("--config", required=True)
    plan = commands.add_parser("plan", help="Export a profile and New Batch Job script")
    plan.add_argument("--config", required=True)
    plan.add_argument("--workspace", default="workspace")
    launch = commands.add_parser(
        "launch", help="Preflight or run inside an allocated Slurm GPU job"
    )
    launch.add_argument("--config", required=True)
    launch.add_argument("--preflight-only", action="store_true")
    analyze = commands.add_parser(
        "analyze", help="Compare a clean/attack pair and write metrics/plots"
    )
    analyze.add_argument("--clean", required=True)
    analyze.add_argument("--attack", required=True)
    analyze.add_argument("--output", required=True)
    stats = commands.add_parser(
        "statistics", help="Paired effect estimates across independent seeds"
    )
    stats.add_argument("--inputs", nargs="+", required=True)
    stats.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "catalog":
        print(json.dumps(Registry(args.plugins).catalog(), ensure_ascii=False, indent=2))
    elif args.command == "ui":
        from .ui.app import serve

        serve(Path(args.workspace), args.port, args.plugins)
    elif args.command == "validate":
        config = ExperimentConfig.load(args.config)
        print(
            json.dumps(
                {
                    "configuration": "valid",
                    "dataset": "not_checked",
                    "gpu": "not_checked",
                    "config": config.resolved(),
                },
                indent=2,
            )
        )
    elif args.command == "plan":
        from .engine.plans import save_plan

        print(save_plan(ExperimentConfig.load(args.config), args.workspace))
    elif args.command == "launch":
        from .adapters.flower.launch import launch as run

        run(ExperimentConfig.load(args.config), args.preflight_only)
    elif args.command == "analyze":
        from .engine.analysis import compare

        print(json.dumps(compare(args.clean, args.attack, args.output)["summary"], indent=2))
    elif args.command == "statistics":
        from .engine.statistics import summarize

        print(json.dumps(summarize(args.inputs, args.output), indent=2))


if __name__ == "__main__":
    main()
