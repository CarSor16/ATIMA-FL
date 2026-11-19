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
    easy.add_argument(
        "--evaluation-scope", choices=["shared", "slice"],
        help="Override the profile: shared evaluates every personalized model on the whole "
             "split, slice gives each client a disjoint stratified slice of it",
    )
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
    pattern = commands.add_parser(
        "pattern", help="Per-class signals, damage shape and structure of one run"
    )
    pattern.add_argument("--run", required=True)
    pattern.add_argument("--clean", help="Clean run to pair against (optional)")
    pattern.add_argument("--window", default="41:50")
    pattern.add_argument("--attack-start", type=int, default=10)
    pattern.add_argument("--output")
    thresholds = commands.add_parser(
        "thresholds", help="Noise of a window comparison, measured on clean runs"
    )
    thresholds.add_argument("--clean", nargs="+", required=True)
    thresholds.add_argument("--window", default="41:50")
    thresholds.add_argument("--output")
    detect = commands.add_parser(
        "detect", help="Detection latency of each signal against clean runs"
    )
    detect.add_argument("--run", required=True)
    detect.add_argument("--clean", nargs="+", required=True)
    detect.add_argument("--window", type=int, default=10)
    detect.add_argument("--confirm", type=int, default=2)
    detect.add_argument("--attack-start", type=int, default=10)
    detect.add_argument("--output")
    commands.add_parser(
        "mcp", help="Serve the read-only pattern tools over MCP (stdio)"
    )
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

        run_profile(
            args.profile,
            preflight_only=args.preflight_only,
            local=args.local,
            evaluation_scope=args.evaluation_scope,
        )
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
    elif args.command == "pattern":
        from .engine import pattern as pattern_engine

        start, end = _window(args.window)
        data = pattern_engine.report(args.run, args.clean, start, end, args.attack_start)
        _emit(data, args.output)
    elif args.command == "thresholds":
        from .engine import pattern as pattern_engine

        start, end = _window(args.window)
        histories = [pattern_engine.load_history(path) for path in args.clean]
        _emit(pattern_engine.noise(histories, start, end), args.output)
    elif args.command == "detect":
        from .engine import pattern as pattern_engine

        history = pattern_engine.load_history(args.run)
        clean = [pattern_engine.load_history(path) for path in args.clean]
        _emit(
            pattern_engine.detect(
                history, clean, args.window, 3.0, args.confirm, args.attack_start
            ),
            args.output,
        )
    elif args.command == "mcp":
        from .engine.mcp_server import serve

        serve()


def _window(spec):
    """Parse `start:end` into two ints, rejecting a reversed or empty window."""
    try:
        start, end = (int(part) for part in str(spec).split(":", 1))
    except ValueError as error:
        raise SystemExit(f"Invalid window {spec!r}: expected START:END") from error
    if end < start:
        raise SystemExit(f"Invalid window {spec!r}: end precedes start")
    return start, end


def _emit(data, output=None):
    """Print the payload, and write it when an output path was given."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if output:
        from pathlib import Path

        Path(output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
