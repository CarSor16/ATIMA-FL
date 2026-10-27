"""Stable entry points for local experiment design and profile export."""

from pathlib import Path

from atima_fl.core.configuration import ExperimentConfig


def serve(workspace, port=8765, plugins=None):
    """Start the loopback-only designer without importing Flower."""
    from atima_fl.ui.app import serve as serve_ui

    return serve_ui(Path(workspace), port, plugins)


def validate_profile(path):
    """Validate a TOML profile without accessing the cluster or dataset."""
    config = ExperimentConfig.load(path)
    return {
        "configuration": "valid",
        "dataset": "not_checked",
        "gpu": "not_checked",
        "config": config.resolved(),
    }


def export_plan(path, workspace):
    from atima_fl.engine.plans import save_plan

    return save_plan(ExperimentConfig.load(path), workspace)


def export_defense_study(path, workspace):
    from atima_fl.engine.plans import save_defense_study

    return save_defense_study(ExperimentConfig.load(path), workspace)
