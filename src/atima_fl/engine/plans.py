"""Save portable, validated experiment plans. Does not submit or launch training."""

from pathlib import Path
import json
import zipfile


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
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as stream:
        for name in ("experiment.toml", "run_cluster.sh", "plan.json"):
            stream.write(directory / name, name)
    return directory
