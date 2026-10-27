"""Runtime entry points, separate from Studio's UI and export concerns."""

from atima_fl.core.configuration import ExperimentConfig


def run_profile(profile, *, preflight_only=False, local=False):
    """Run a validated TOML using the existing Flower execution adapter."""
    from atima_fl.adapters.flower.launch import allocated_config, launch

    config = ExperimentConfig.load(profile)
    if local:
        from dataclasses import replace
        import os

        available = (
            len(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else os.cpu_count() or 0
        )
        if available < config.servers + 2:
            raise RuntimeError("Local run needs at least servers + 2 available CPU cores")
        config = replace(
            config,
            cpu_budget=available,
            client_cpus=1,
            compute_device="cpu",
            client_gpu_fraction=1.0,
        ).validate()
        return launch(config, preflight_only=preflight_only, local=True)
    return launch(allocated_config(config), preflight_only=preflight_only)


def launch_profile(profile, *, preflight_only=False):
    """Launch under an existing cluster allocation (original CLI semantics)."""
    from atima_fl.adapters.flower.launch import launch

    return launch(ExperimentConfig.load(profile), preflight_only)


def compare_profiles(clean, attacked, output):
    from atima_fl.engine.analysis import compare

    return compare(clean, attacked, output)["summary"]


def compare_defense_profiles(unprotected, protected, output):
    from atima_fl.engine.defense_analysis import compare_defenses

    return compare_defenses(unprotected, protected, output)


def summarize_profiles(inputs, output):
    from atima_fl.engine.statistics import summarize

    return summarize(inputs, output)


def summarize_defense_profiles(inputs, output):
    from atima_fl.engine.statistics import summarize_defenses

    return summarize_defenses(inputs, output)
