"""One interface shared by the GUI, local inspection, and cluster jobs."""

import argparse
import json
from .core.registry import Registry


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="atima", description="ATIMA-FL · modular experiment layer on Flower"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    datasets = commands.add_parser("datasets", help="Inspect or prepare any supported tabular source")
    dataset_commands = datasets.add_subparsers(dest="dataset_command", required=True)
    di = dataset_commands.add_parser("inspect", help="Suggest labels from a local file/directory")
    di.add_argument("path")
    dp = dataset_commands.add_parser("prepare", help="Prepare immutable FL shards from tabular data")
    dp.add_argument("path")
    dp.add_argument("--output", required=True)
    dp.add_argument("--label-column", required=True)
    dp.add_argument("--benign-label")
    dp.add_argument("--exclude", action="append", default=[])
    dp.add_argument("--clients", type=int, default=10)
    dp.add_argument("--seed", type=int, default=2026)
    dp.add_argument("--max-rows", type=int, default=500000)
    dirichlet = commands.add_parser(
        "prepare-dirichlet", help="Create immutable Edge-IIoT Dirichlet client shards"
    )
    dirichlet.add_argument("--dataset-root", required=True)
    dirichlet.add_argument("--alpha", required=True, type=float)
    dirichlet.add_argument("--clients", type=int, default=10)
    dirichlet.add_argument("--seed", type=int, default=2026)
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
    study = commands.add_parser(
        "defense-study", help="Export four matched conditions without training"
    )
    study.add_argument("--config", required=True)
    study.add_argument("--workspace", default="workspace")
    defense = commands.add_parser(
        "compare-defenses", help="Compare protected/unprotected paired analyses"
    )
    defense.add_argument("--unprotected", required=True)
    defense.add_argument("--protected", required=True)
    defense.add_argument("--output", required=True)
    easy = commands.add_parser("run", help="Preflight then train TOML in an allocated Slurm job")
    easy.add_argument("profile", help="Path to experiment.toml")
    easy.add_argument("--preflight-only", action="store_true")
    easy.add_argument("--local", action="store_true", help="Train on the local CPU without Slurm")
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
    defense_stats = commands.add_parser(
        "defense-statistics", help="Protection effects across independent seed quartets"
    )
    defense_stats.add_argument("--inputs", nargs="+", required=True)
    defense_stats.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "datasets":
        from .core.universal_data import inspect, prepare

        if args.dataset_command == "inspect":
            data = inspect(args.path)
        else:
            data = prepare(args.path, args.output, args.label_column,
                           benign_label=args.benign_label, exclude_columns=args.exclude,
                           clients=args.clients, seed=args.seed, max_rows=args.max_rows)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.command == "prepare-dirichlet":
        from .runtime.dirichlet import prepare_dirichlet

        print(prepare_dirichlet(
            args.dataset_root, alpha=args.alpha, clients=args.clients, seed=args.seed
        ))
    elif args.command == "catalog":
        print(json.dumps(Registry(args.plugins).catalog(), ensure_ascii=False, indent=2))
    elif args.command == "ui":
        from .studio.api import serve

        serve(args.workspace, args.port, args.plugins)
    elif args.command == "validate":
        from .studio.api import validate_profile

        print(json.dumps(validate_profile(args.config), indent=2))
    elif args.command == "plan":
        from .studio.api import export_plan

        print(export_plan(args.config, args.workspace))
    elif args.command == "defense-study":
        from .studio.api import export_defense_study

        print(export_defense_study(args.config, args.workspace))
    elif args.command == "compare-defenses":
        from .runtime.api import compare_defense_profiles

        print(json.dumps(compare_defense_profiles(args.unprotected, args.protected, args.output), indent=2))
    elif args.command == "run":
        from .runtime.api import run_profile

        run_profile(args.profile, preflight_only=args.preflight_only, local=args.local)
    elif args.command == "launch":
        from .runtime.api import launch_profile

        launch_profile(args.config, preflight_only=args.preflight_only)
    elif args.command == "analyze":
        from .runtime.api import compare_profiles

        print(json.dumps(compare_profiles(args.clean, args.attack, args.output), indent=2))
    elif args.command == "statistics":
        from .runtime.api import summarize_profiles

        print(json.dumps(summarize_profiles(args.inputs, args.output), indent=2))
    elif args.command == "defense-statistics":
        from .runtime.api import summarize_defense_profiles

        print(json.dumps(summarize_defense_profiles(args.inputs, args.output), indent=2))


if __name__ == "__main__":
    main()
