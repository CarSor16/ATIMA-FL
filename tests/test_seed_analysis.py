"""Fail-closed seed cohort identity; no training or dataset access."""
from copy import deepcopy

import pytest

from atima_fl.ui.seed_analysis import seed_condition, sensitivity_conditions


def manifest(seed=0):
    return {
        "status": "complete",
        "last_valid_round": 30,
        "config": {
            "name": f"LCG_seed{seed}",
            "seed": seed,
            "attack": "local_class_gradient",
            "attack_params": {"fixture": 1},
            "malicious_clients": [0],
            "clients": 2,
            "servers": 1,
            "dataset": "edge_iiot",
            "dataset_params": {"task": "prepared_5"},
            "partition": "dirichlet",
            "partition_params": {"alpha": 0.5},
            "model": "lopez_cnn",
            "model_params": {},
            "rounds": 30,
            "local_epochs": 3,
            "aggregation": "fedavg",
            "aggregation_params": {},
            "defenses": [],
            "optimizer": "adam",
            "optimizer_params": {},
            "loss": "cross_entropy",
            "loss_params": {},
            "batch_size": 128,
            "learning_rate": 0.001,
            "attack_start": 10,
            "attack_end": 30,
            "training_method": "standard",
            "evaluation_scope": "shared",
            "output_root": "/fixture/results",
            "paired_clean": f"/fixture/clean_seed{seed}",
        },
        "dataset_audit": {
            "task": "prepared_5",
            "classes": ["benign", "dos", "infog", "inject", "malware"],
            "hashes": {key: f"fixture-{key}" for key in (
                "train", "validation", "test", "feature_schema.json",
                "label_mapping.json", "preprocessor.json", "assignment",
                "client_0", "client_1",
            )},
        },
        "source_identity": {"version": "fixture-v1"},
        "runtime": {"device": "cpu"},
        "attack_source": "fixture",
    }


def test_seed_and_paths_may_vary_but_condition_remains_equal():
    first, second = manifest(0), manifest(10)
    second["config"]["output_root"] = "/elsewhere"
    a, b = seed_condition(first), seed_condition(second)
    assert a["key"] and a == b


@pytest.mark.parametrize("field,value", [
    ("attack", "label_flip"),
    ("malicious_clients", [0, 1]),
    ("malicious_clients", [1]),
    ("attack_params", {"fixture": 2}),
    ("partition", "iid"),
    ("partition_params", {"alpha": 0.1}),
    ("training_method", "hyperfl_plus_plus"),
    ("evaluation_scope", "slice"),
    ("model", "mlp"),
    ("rounds", 50),
    ("local_epochs", 1),
    ("defenses", [{"id": "fixture", "params": {}}]),
])
def test_different_scientific_conditions_do_not_merge(field, value):
    first, second = manifest(), manifest(1)
    second["config"][field] = value
    assert seed_condition(first)["key"] != seed_condition(second)["key"]


@pytest.mark.parametrize("field", ["assignment", "client_0", "train", "test"])
def test_different_shards_or_global_splits_do_not_merge(field):
    a, b = manifest(), manifest(1)
    b["dataset_audit"]["hashes"][field] = "different"
    assert seed_condition(a)["key"] != seed_condition(b)["key"]


@pytest.mark.parametrize("field,value", [
    ("source_identity", {"version": "fixture-v2"}),
    ("runtime", {"device": "cuda"}),
    ("last_valid_round", 29),
])
def test_source_runtime_and_horizon_are_part_of_the_condition(field, value):
    first, second = manifest(), manifest(1)
    second[field] = value
    assert seed_condition(first)["key"] != seed_condition(second)["key"]


def test_legacy_or_invalid_manifest_is_not_silently_aggregated():
    missing = manifest()
    del missing["dataset_audit"]["hashes"]["assignment"]
    assert seed_condition(missing)["key"] is None
    bad = manifest()
    bad["config"]["seed"] = True
    assert seed_condition(bad)["key"] is None
    incomplete = manifest()
    incomplete["status"] = "running"
    assert seed_condition(incomplete)["key"] is None
    no_identity = manifest()
    del no_identity["source_identity"]
    assert seed_condition(no_identity)["key"] is None


def test_grouping_is_read_only():
    original = manifest()
    copy = deepcopy(original)
    seed_condition(original)
    assert original == copy


def test_sensitivity_changes_only_declared_variable():
    a, b = manifest(), manifest(1)
    b["config"]["attack_params"]["fixture"] = 2

    def key(m, axis):
        return next(x["key"] for x in sensitivity_conditions(m, seed_condition(m))
                    if x["axis"] == axis)

    assert key(a, "attack_params.fixture") == key(b, "attack_params.fixture")
    assert key(a, "model") != key(b, "model")
    b["dataset_audit"]["hashes"]["client_0"] = "different"
    assert key(a, "attack_params.fixture") != key(b, "attack_params.fixture")


def test_model_contrast_allows_only_selected_component_source_to_change():
    a, b = manifest(), manifest(1)
    a["source_identity"]["component/model/lopez_cnn"] = "cnn-source"
    b["config"]["model"] = "mlp"
    b["source_identity"]["component/model/mlp"] = "mlp-source"

    def model_key(m):
        return next(x["key"] for x in sensitivity_conditions(m, seed_condition(m))
                    if x["axis"] == "model")

    assert model_key(a) == model_key(b)
    b["source_identity"]["shared_engine"] = "different"
    assert model_key(a) != model_key(b)


def test_protocol_group_ignores_shard_and_software_variation_but_not_global_data():
    first, second = manifest(0), manifest(1)
    second["dataset_audit"]["hashes"]["client_0"] = "other-shard"
    second["dataset_audit"]["hashes"]["assignment"] = "other-assignment"
    second["source_identity"]["version"] = "other-source"
    second["runtime"]["gpu"] = "other-gpu"
    second["config"]["cpu_budget"] = 96
    a, b = seed_condition(first), seed_condition(second)
    assert a["key"] != b["key"]
    assert a["protocol_key"] == b["protocol_key"]
    second["dataset_audit"]["hashes"]["test"] = "other-test"
    assert seed_condition(second)["protocol_key"] != a["protocol_key"]


@pytest.mark.parametrize("field,value", [
    ("attack_params", {"fixture": 2}),
    ("partition_params", {"alpha": 0.1}),
    ("malicious_clients", [1]),
    ("model", "mlp"),
    ("training_method", "hyperfl_plus_plus"),
    ("evaluation_scope", "slice"),
])
def test_protocol_groups_keep_scientific_settings(field, value):
    a, b = manifest(), manifest(1)
    b["config"][field] = value
    assert seed_condition(a)["protocol_key"] != seed_condition(b)["protocol_key"]
