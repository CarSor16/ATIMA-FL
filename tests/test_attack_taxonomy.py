"""Catalog taxonomy must match the real built-in attack implementations."""

from atima_fl.core.attack_taxonomy import ATTACK_GROUPS, validate_taxonomy
from atima_fl.core.registry import Registry


def test_taxonomy_exactly_covers_implemented_attacks():
    catalog = Registry().catalog()
    ids = {item["id"] for item in catalog["attack"]} - {"none"}
    assert len(ids) == 20
    validate_taxonomy(ids)
    listed = {identifier for group in ATTACK_GROUPS.values() for identifier in group}
    assert listed == ids


def test_attack_catalog_exposes_presentation_metadata_without_changing_ids():
    catalog = Registry().catalog()
    attacks = {entry["id"]: entry for entry in catalog["attack"]}
    assert attacks["none"]["category"] == "baseline"
    assert attacks["update_scaling"]["category"] == "byzantine_aggregation_disruption"
    assert attacks["min_max"]["category"] == "byzantine_aggregation_disruption"
    assert attacks["min_sum"]["category"] == "byzantine_aggregation_disruption"
    assert attacks["update_scaling"]["survey_references"]
    assert all(a["implementation_status"] == "implemented" for k, a in attacks.items() if k != "none")


def test_min_max_and_min_sum_are_real_plugins():
    attacks = Registry()
    for kind in ("min_max", "min_sum"):
        component = attacks.get("attack", kind)
        assert callable(component.hooks["transform"])
        assert callable(component.hooks["validate"])
        assert component.references


def test_random_byzantine_is_classified():
    attacks = {item["id"]: item for item in Registry().catalog()["attack"]}
    assert attacks["random_byzantine"]["category"] == "byzantine_aggregation_disruption"
