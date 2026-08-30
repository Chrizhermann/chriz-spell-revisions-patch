from __future__ import annotations

from typing import Any

import pytest

from tools.sr_config.catalog import Catalog
from tools.sr_config.resolve import (
    Assignment,
    ConfigError,
    feature_symbols,
    parse_assignments,
    resolve,
)


UPSTREAM_COMMIT = "af1dedb6d211f86ad7a321d4080e46c748e8abac"


def _group(
    group_id: str,
    setting: str,
    parent: str | None,
    default: int = -1,
) -> dict[str, Any]:
    return {
        "id": group_id,
        "setting": setting,
        "name": group_id,
        "default": default,
        "parent": parent,
    }


def _change(change_id: str, setting: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": change_id,
        "setting": setting,
        "display_name": change_id,
        "default": -1,
        "group": "arcane.level1",
        "component": 0,
        "games": ["all"],
        "name_ref": None,
        "description_ref": None,
        "source_spans": [],
        "resources": [],
        "atomic_group": None,
        "requires": [],
        "conflicts": [],
        "soft_requires": [],
        "processors": [],
        "documentation_only_reason": "resolver test fixture",
    }
    value.update(overrides)
    return value


def sample_catalog(*changes: dict[str, Any]) -> Catalog:
    raw = {
        "schema_version": 1,
        "upstream": {"tag": "v4.21", "commit": UPSTREAM_COMMIT},
        "migration": {
            "complete": False,
            "installer_source": "spell_rev/components/main_component.tpa",
        },
        "groups": [
            _group("global", "sr_default", None, 1),
            _group("arcane", "sr_arcane_default", "global"),
            _group(
                "arcane.level1",
                "sr_arcane_level_1_default",
                "arcane",
            ),
        ],
        "changes": list(changes),
        "infrastructure": [],
    }
    return Catalog.from_dict(raw)


def test_leaf_overrides_every_parent() -> None:
    catalog = sample_catalog(
        _change("arcane.level1.magic_missile", "sr_wizard_magic_missile")
    )
    values = {
        "sr_default": 0,
        "sr_arcane_default": 1,
        "sr_arcane_level_1_default": 0,
        "sr_wizard_magic_missile": 1,
    }

    assert resolve(catalog, values).enabled("arcane.level1.magic_missile")


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"sr_default": 0, "sr_arcane_default": 1}, True),
        (
            {
                "sr_default": 1,
                "sr_arcane_default": 0,
                "sr_arcane_level_1_default": 1,
            },
            True,
        ),
        (
            {
                "sr_default": 0,
                "sr_arcane_default": 1,
                "sr_arcane_level_1_default": 0,
            },
            False,
        ),
    ],
)
def test_resolution_uses_nearest_non_inherited_parent(
    values: dict[str, int], expected: bool
) -> None:
    catalog = sample_catalog(_change("spell", "sr_spell"))

    assert resolve(catalog, values).enabled("spell") is expected


@pytest.mark.parametrize("bad_value", [-2, 2, True, False, "1", None])
def test_only_integer_tri_state_values_are_accepted(bad_value: object) -> None:
    catalog = sample_catalog(_change("spell", "sr_spell"))

    with pytest.raises(ConfigError, match="sr_spell: expected -1, 0, or 1"):
        resolve(catalog, {"sr_spell": bad_value})


def test_assignment_parser_preserves_order_and_ignores_comments() -> None:
    source = """// generated settings\n\nSR_DEFAULT = 1 // enabled\nsr_spell=-1\n"""

    assert parse_assignments(source) == (
        Assignment("SR_DEFAULT", 1, 3),
        Assignment("sr_spell", -1, 4),
    )


def test_unknown_and_duplicate_settings_are_case_insensitive_and_aggregated() -> None:
    catalog = sample_catalog(_change("spell", "sr_spell"))
    assignments = (
        Assignment("sr_unknown", 1, 1),
        Assignment("SR_SPELL", 1, 2),
        Assignment("sr_spell", 0, 3),
        Assignment("another_unknown", 1, 4),
    )

    with pytest.raises(ConfigError) as caught:
        resolve(catalog, assignments)

    assert caught.value.errors == (
        "line 1: unknown setting 'sr_unknown'",
        "line 3: duplicate setting 'sr_spell'; first assigned on line 2 as 'SR_SPELL'",
        "line 4: unknown setting 'another_unknown'",
    )


def test_duplicate_unknown_setting_is_still_reported_as_a_duplicate() -> None:
    catalog = sample_catalog(_change("spell", "sr_spell"))

    with pytest.raises(ConfigError) as caught:
        resolve(
            catalog,
            (
                Assignment("sr_missing", 1, 1),
                Assignment("SR_MISSING", 0, 2),
            ),
        )

    assert caught.value.errors == (
        "line 1: unknown setting 'sr_missing'",
        "line 2: duplicate setting 'SR_MISSING'; first assigned on line 1 as 'sr_missing'",
    )

def test_assignment_syntax_errors_are_aggregated_in_source_order() -> None:
    with pytest.raises(ConfigError) as caught:
        parse_assignments("sr_good = 1\nnot an assignment\nsr_bad = yes\n")

    assert caught.value.errors == (
        "line 2: expected NAME = -1, 0, or 1",
        "line 3: expected NAME = -1, 0, or 1",
    )


def test_explicitly_disabled_requirement_is_an_error() -> None:
    catalog = sample_catalog(
        _change(
            "spell_shield",
            "sr_spell_shield",
            requires=["antimagic_suite"],
        ),
        _change("antimagic_suite", "sr_antimagic_suite"),
    )

    with pytest.raises(
        ConfigError,
        match=(
            "sr_spell_shield requires sr_antimagic_suite, but "
            "sr_antimagic_suite is explicitly disabled"
        ),
    ):
        resolve(
            catalog,
            {"sr_spell_shield": 1, "sr_antimagic_suite": 0},
        )


def test_inherited_disabled_requirement_is_enabled_by_transitive_closure() -> None:
    catalog = sample_catalog(
        _change("a", "sr_a", requires=["b"]),
        _change("b", "sr_b", requires=["c"]),
        _change("c", "sr_c"),
    )

    result = resolve(
        catalog,
        {
            "sr_default": 0,
            "sr_a": 1,
            "sr_b": -1,
            "sr_c": -1,
        },
    )

    assert result.selected_ids == ("a", "b", "c")


def test_atomic_family_closes_and_respects_an_explicit_leaf_veto() -> None:
    catalog = sample_catalog(
        _change("a", "sr_a", atomic_group="paired"),
        _change("b", "sr_b", atomic_group="PAIRED"),
    )

    assert resolve(catalog, {"sr_default": 0, "sr_a": 1}).selected_ids == (
        "a",
        "b",
    )
    with pytest.raises(ConfigError, match="atomic family 'paired'.*sr_b.*explicitly disabled"):
        resolve(catalog, {"sr_default": 0, "sr_a": 1, "sr_b": 0})


def test_conflicts_are_checked_after_dependency_and_atomic_closure() -> None:
    catalog = sample_catalog(
        _change("a", "sr_a", requires=["b"]),
        _change("b", "sr_b", conflicts=["c"]),
        _change("c", "sr_c"),
    )

    with pytest.raises(ConfigError, match="sr_b conflicts with sr_c"):
        resolve(catalog, {"sr_default": 0, "sr_a": 1, "sr_c": 1})


def test_soft_edges_never_force_or_fail_but_report_when_both_are_active() -> None:
    catalog = sample_catalog(
        _change("protection", "sr_protection", soft_requires=["offense"]),
        _change("offense", "sr_offense"),
    )

    one = resolve(catalog, {"sr_default": 0, "sr_protection": 1})
    both = resolve(
        catalog,
        {"sr_default": 0, "sr_protection": 1, "sr_offense": 1},
    )

    assert one.selected_ids == ("protection",)
    assert not one.soft_edge_active("protection", "offense")
    assert both.soft_edge_active("protection", "offense")


def test_game_applicability_disables_inherited_leaf_but_rejects_explicit_enable() -> None:
    catalog = sample_catalog(
        _change("ee_only", "sr_ee_only", games=["bg2ee"])
    )

    assert not resolve(catalog, {}, game="soa").enabled("ee_only")
    with pytest.raises(
        ConfigError,
        match="sr_ee_only is explicitly enabled but unavailable on game 'soa'",
    ):
        resolve(catalog, {"sr_ee_only": 1}, game="soa")


def test_active_hard_requirement_that_is_unavailable_is_an_error() -> None:
    catalog = sample_catalog(
        _change("portable", "sr_portable", requires=["ee_only"]),
        _change("ee_only", "sr_ee_only", games=["bg2ee"]),
    )

    with pytest.raises(
        ConfigError,
        match="sr_portable requires sr_ee_only, which is unavailable on game 'soa'",
    ):
        resolve(catalog, {"sr_portable": 1}, game="soa")


def test_unknown_game_is_rejected() -> None:
    catalog = sample_catalog(_change("spell", "sr_spell"))

    with pytest.raises(ConfigError, match="unknown game 'planescape'"):
        resolve(catalog, {}, game="planescape")


def test_resolution_errors_are_aggregated_in_catalog_order() -> None:
    catalog = sample_catalog(
        _change("a", "sr_a", requires=["b"]),
        _change("b", "sr_b"),
        _change("c", "sr_c", requires=["d"]),
        _change("d", "sr_d"),
    )

    with pytest.raises(ConfigError) as caught:
        resolve(
            catalog,
            {"sr_default": 0, "sr_a": 1, "sr_b": 0, "sr_c": 1, "sr_d": 0},
        )

    assert caught.value.errors == (
        "sr_a requires sr_b, but sr_b is explicitly disabled",
        "sr_c requires sr_d, but sr_d is explicitly disabled",
    )


def test_feature_symbols_use_complete_catalog_order_and_never_raw_ids() -> None:
    catalog = sample_catalog(
        _change("arcane.level1.a-b", "sr_a"),
        _change("arcane_level1_a_b", "sr_b", games=["iwdee"]),
    )

    assert feature_symbols(catalog) == {
        "arcane.level1.a-b": "sr_feature_000001",
        "arcane_level1_a_b": "sr_feature_000002",
    }
    assert feature_symbols(catalog, game="bg2ee") == feature_symbols(catalog)
