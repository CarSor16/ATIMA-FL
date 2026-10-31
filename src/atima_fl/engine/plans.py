"""Save portable, validated experiment plans. Does not submit or launch training."""

from pathlib import Path, PurePosixPath
import json
import zipfile
from dataclasses import replace
from atima_fl.core.io import atomic_json


def _archive_files(destination, files):
    """Write a new portable ZIP from explicit paths and archive names."""
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)


def save_plan(config, workspace):
    config.validate()
    root = Path(workspace).resolve() / "plans"
    root.mkdir(parents=True, exist_ok=True)
    directory = root / config.name
    directory.mkdir(exist_ok=False)
    profile = directory / "experiment.toml"
    config.save(profile)
    script = """#!/usr/bin/env bash
set -euo pipefail
: "${ATIMA_PYTHON:?Set ATIMA_PYTHON to the isolated Python environment on the compute node}"
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export PYTHONUNBUFFERED=1
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-preflight}"
case "$MODE" in
  preflight) exec "$ATIMA_PYTHON" -m atima_fl.cli launch --config "$SCRIPT_DIR/experiment.toml" --preflight-only ;;
  train) exec "$ATIMA_PYTHON" -m atima_fl.cli launch --config "$SCRIPT_DIR/experiment.toml" ;;
  *) printf 'Use preflight or train\\n' >&2; exit 2 ;;
esac
"""
    (directory / "run_cluster.sh").write_text(script, encoding="utf-8", newline="\n")
    # Python entry point uses installed ATIMA Runtime; it is NOT a standalone
    # copy of the Flower engine, attacks, datasets or environment.
    py_script = '''#!/usr/bin/env python3
"""Run a validated ATIMA experiment with the installed Runtime/Flower stack.

Usage: python run_experiment.py preflight [--local]
       python run_experiment.py train [--local]

Requires the matching ATIMA Runtime installation and prepared dataset.
"""
import argparse
from pathlib import Path
from atima_fl.runtime.api import run_profile

def main():
    parser = argparse.ArgumentParser(description="ATIMA experiment launcher")
    parser.add_argument("mode", choices=("preflight", "train"))
    parser.add_argument("--local", action="store_true",
                        help="Run on local CPU rather than allocated Slurm")
    args = parser.parse_args()
    profile = Path(__file__).resolve().parent / "experiment.toml"
    return run_profile(profile, preflight_only=args.mode == "preflight",
                       local=args.local)

if __name__ == "__main__":
    main()
'''
    (directory / "run_experiment.py").write_text(py_script, encoding="utf-8", newline="\\n")
    (directory / "plan.json").write_text(
        json.dumps(
            {
                "name": config.name,
                "config": config.resolved(),
                "checks": {
                    "configuration": "valid",
                    "dataset": "not_checked",
                    "scheduler": "not_checked",
                    "cuda": "not_checked",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    archive = directory / "plan.zip"
    _archive_files(
        archive,
        ((directory / name, name) for name in ("experiment.toml", "run_cluster.sh", "run_experiment.py", "plan.json")),
    )
    return directory


def save_defense_study(config, workspace):
    """Export a seed-matched quartet, with a common horizon declared before training."""
    config.validate()
    if config.attack == "none" or (not config.defenses and config.aggregation == "fedavg"):
        raise ValueError("Select an attack and at least one defense or a robust aggregator")
    root = Path(workspace).resolve() / "plans" / (config.name + "_DefenseStudy")
    root.mkdir(parents=True, exist_ok=False)
    names = {}
    for protection in ("Unprotected", "Protected"):
        protected = protection == "Protected"
        shared = replace(
            config,
            minimum_rounds=config.rounds,
            paired_rounds=config.rounds,
            defenses=config.defenses if protected else (),
            aggregation=config.aggregation if protected else "fedavg",
            aggregation_params=config.aggregation_params if protected else {},
        )
        clean_name = config.name + "_Clean" + protection
        clean = replace(
            shared,
            name=clean_name,
            attack="none",
            attack_params={},
            malicious_clients=(),
            paired_clean="",
        )
        output_path = (
            PurePosixPath(config.output_root)
            if config.output_root.startswith("/")
            else Path(config.output_root)
        )
        attacked = replace(
            shared,
            name=config.name + "_Attack" + protection,
            paired_clean=str(output_path / clean_name),
        )
        for label, profile in (("clean", clean), ("attack", attacked)):
            save_plan(profile, root)
            names[label + protection] = profile.name
    atomic_json(
        root / "study.json",
        {
            "seed": config.seed,
            "rounds": config.rounds,
            "profiles": names,
            "order": [
                names[k]
                for k in (
                    "cleanUnprotected",
                    "attackUnprotected",
                    "cleanProtected",
                    "attackProtected",
                )
            ],
            "stopping": "Common cap: no clean early stopping before the declared cap",
            "inference": "One seed is diagnostic; use at least three independent matched quartets for uncertainty",
        },
    )
    _archive_files(
        root / "plan.zip",
        (
            (path, path.relative_to(root).as_posix())
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name != "plan.zip"
        ),
    )
    return root
