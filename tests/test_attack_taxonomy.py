"""Catalog taxonomy must match the real built-in attack implementations."""

from atima_fl.core.attack_taxonomy import ATTACK_GROUPS, validate_taxonomy
from atima_fl.core.registry import Registry


def test_taxonomy_exactly_covers_implemented_attacks():
    catalog = Registry().catalog()
    ids = {item["id"] for item in catalog["attack"]} - {"none"}
    assert len(ids) == 17
    validate_taxonomy(ids)
    listed = {identifier for group in ATTACK_GROUPS.values() for identifier in group}
    assert listed == ids


def test_attack_catalog_exposes_presentation_metadata_without_changing_ids():
    catalog = Registry().catalog()
    attacks = {entry["id"]: entry for entry in catalog["attack"]}
    assert attacks["none"]["category"] == "baseline"
    assert attacks["update_scaling"]["category"] == "byzantine_aggregation_disruption"
    assert "min_max" not in attacks
    assert attacks["update_scaling"]["survey_references"]
    assert all(a["implementation_status"] == "implemented" for k, a in attacks.items() if k != "none")
