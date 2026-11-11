"""Architectural smoke tests: Studio must remain usable without the training stack."""

import json
import sys

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.studio.api import export_plan, validate_profile


def test_studio_profile_validation_and_export_without_training_import(tmp_path):
    config = ExperimentConfig(name="StudioSplit").validate()
    profile = tmp_path / "experiment.toml"
    config.save(profile)
    before = {name for name in sys.modules if name == "flwr" or name.startswith("flwr.")}
    checked = validate_profile(profile)
    assert checked["configuration"] == "valid"
    assert checked["dataset"] == "not_checked"
    assert checked["config"]["name"] == "StudioSplit"
    destination = export_plan(profile, tmp_path / "workspace")
    assert (destination / "plan.zip").is_file()
    assert (destination / "run_cluster.sh").is_file()
    after = {name for name in sys.modules if name == "flwr" or name.startswith("flwr.")}
    assert after == before


def test_cli_studio_commands_keep_output_contract(tmp_path, capsys):
    from atima_fl.cli import main

    profile = tmp_path / "input.toml"
    ExperimentConfig(name="CliSplit").validate().save(profile)
    main(["validate", "--config", str(profile)])
    output = json.loads(capsys.readouterr().out)
    assert output["config"]["name"] == "CliSplit"
    assert output["gpu"] == "not_checked"
    main(["plan", "--config", str(profile), "--workspace", str(tmp_path / "work")])
    assert (tmp_path / "work" / "plans" / "CliSplit" / "plan.zip").is_file()


def test_runtime_package_import_is_lightweight():
    from atima_fl.runtime import api

    assert callable(api.run_profile)
    assert callable(api.launch_profile)
    assert callable(api.compare_profiles)


def test_separate_console_entry_points_restrict_commands(tmp_path, capsys):
    import pytest
    from atima_fl.studio.cli import main as studio_main
    from atima_fl.runtime.cli import main as runtime_main

    profile = tmp_path / "profile.toml"
    ExperimentConfig(name="SplitEntrypoint").validate().save(profile)
    studio_main(["validate", "--config", str(profile)])
    assert json.loads(capsys.readouterr().out)["configuration"] == "valid"
    with pytest.raises(SystemExit, match="ATIMA Studio commands"):
        studio_main(["run", str(profile)])
    with pytest.raises(SystemExit, match="ATIMA Runtime commands"):
        runtime_main(["ui"])
