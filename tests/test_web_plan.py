"""Verify web draft conversion using the actual Core validators and exporters."""
import json

import pytest

from atima_fl.studio.web_plan import export_draft


def draft(mode="single"):
    return {
        "schema_version": 1, "mode": mode,
        "config": {
            "name": "WebDraft", "attack": "update_scaling", "attack_params": {"factor": 2},
            "malicious_clients": [0], "rounds": 5, "attack_start": 1, "attack_end": 5,
            "minimum_rounds": 5,
        },
        "seeds": [] if mode == "single" else [0, 1],
        "axis": "attack_params.factor" if mode == "sweep" else None,
        "levels": [1, 2] if mode == "sweep" else [],
    }


@pytest.mark.parametrize("mode,count", [("single", 1), ("batch", 4), ("sweep", 6)])
def test_web_draft_export(tmp_path, mode, count):
    root = export_draft(draft(mode), tmp_path, str(tmp_path / "data"))
    assert len(list(root.rglob("experiment.toml"))) == count
    if mode != "single":
        assert json.loads((root / "campaign.json").read_text())["runs"] == count
    assert not (tmp_path / "results").exists()


def test_web_draft_rejects_deployment_fields_and_invalid_levels(tmp_path):
    doc = draft()
    doc["config"]["plugin_directory"] = "/untrusted/plugin"
    with pytest.raises(ValueError, match="deployment fields"):
        export_draft(doc, tmp_path, "data")
    doc = draft("sweep")
    doc["levels"] = [1, 1]
    with pytest.raises(ValueError):
        export_draft(doc, tmp_path, "data")
    assert not (tmp_path / "plans").exists()
