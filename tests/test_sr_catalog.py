from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from tools.sr_config.catalog import (
    Catalog,
    CatalogError,
    Change,
    Group,
    Infrastructure,
    Migration,
    ResourceOwnership,
    SourceSpan,
    Upstream,
    load_catalog,
)


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "af1dedb6d211f86ad7a321d4080e46c748e8abac"


def group(
    group_id: str,
    *,
    setting: str | None = None,
    parent: str | None = "global",
    default: int = -1,
) -> dict[str, Any]:
    return {
        "id": group_id,
        "setting": setting or f"sr_{group_id.replace('.', '_')}_default",
        "name": group_id,
        "default": default,
        "parent": parent,
    }


def change(change_id: str, **overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": change_id,
        "setting": f"sr_{change_id.replace('.', '_').lower()}",
        "display_name": change_id,
        "default": -1,
        "group": "global",
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
        "documentation_only_reason": "schema test fixture",
    }
    raw.update(overrides)
    return raw


def infrastructure(infrastructure_id: str, **overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": infrastructure_id,
        "source_spans": [],
        "resources": [],
        "consumers": [],
    }
    raw.update(overrides)
    return raw


def minimal_catalog(
    *,
    groups: list[dict[str, Any]] | None = None,
    changes: list[dict[str, Any]] | None = None,
    infrastructure_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "upstream": {"tag": "v4.21", "commit": UPSTREAM_COMMIT},
        "migration": {
            "complete": False,
            "installer_source": "spell_rev/components/main_component.tpa",
        },
        "groups": groups
        if groups is not None
        else [group("global", setting="sr_default", parent=None, default=1)],
        "changes": changes if changes is not None else [],
        "infrastructure": infrastructure_records
        if infrastructure_records is not None
        else [],
    }


def nested_catalog() -> dict[str, Any]:
    return minimal_catalog(
        changes=[
            change(
                "a",
                source_spans=[
                    {
                        "path": "spell_rev/components/main_component.tpa",
                        "start": "// start",
                        "end": "// end",
                        "sha256": "0" * 64,
                    }
                ],
                resources=[{"path": "spell_rev/a.spl", "kind": "resource"}],
            )
        ],
        infrastructure_records=[infrastructure("shared")],
    )


def test_seed_catalog_loads_with_pinned_provenance_and_closed_migration() -> None:
    catalog = load_catalog(ROOT / "spell_rev/catalog/changes.json")

    assert catalog.schema_version == 1
    assert catalog.upstream.tag == "v4.21"
    assert catalog.upstream.commit == UPSTREAM_COMMIT
    assert catalog.migration.complete is False
    assert (
        catalog.migration.installer_source
        == "spell_rev/components/main_component.tpa"
    )
    assert catalog.changes == ()


def test_catalog_preserves_group_source_order() -> None:
    catalog = load_catalog(ROOT / "spell_rev/catalog/changes.json")

    assert [
        (record.id, record.setting, record.parent, record.default)
        for record in catalog.groups
    ] == [
        ("global", "sr_default", None, 1),
        ("arcane", "sr_arcane_default", "global", -1),
        *[
            (
                f"arcane.level{level}",
                f"sr_arcane_level_{level}_default",
                "arcane",
                -1,
            )
            for level in range(1, 10)
        ],
        ("divine", "sr_divine_default", "global", -1),
        *[
            (
                f"divine.level{level}",
                f"sr_divine_level_{level}_default",
                "divine",
                -1,
            )
            for level in range(1, 8)
        ],
    ]


def test_catalog_records_are_frozen() -> None:
    catalog = Catalog.from_dict(minimal_catalog())

    with pytest.raises(FrozenInstanceError):
        catalog.upstream.tag = "v-next"  # type: ignore[misc]


def test_invalid_utf8_is_reported_as_a_catalog_error(tmp_path: Path) -> None:
    path = tmp_path / "changes.json"
    path.write_bytes(b"\xff")

    with pytest.raises(CatalogError) as error:
        load_catalog(path)

    assert str(error.value).startswith(f"{path}:")
    assert "UTF-8" in str(error.value)


def test_duplicate_json_members_are_rejected_with_their_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "changes.json"
    source = json.dumps(minimal_catalog()).replace(
        '"tag": "v4.21"', '"tag": "v4.21", "tag": "v-next"'
    )
    path.write_text(source, encoding="utf-8")

    with pytest.raises(CatalogError) as error:
        load_catalog(path)

    assert str(error.value).startswith("upstream.tag:")
    assert "duplicate field" in str(error.value)


def test_unsupported_schema_version_is_rejected() -> None:
    raw = minimal_catalog()
    raw["schema_version"] = 2

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("schema_version:")
    assert "unsupported schema version 2" in str(error.value)


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (lambda raw: raw["upstream"].update(commit="z" * 40), "upstream.commit"),
        (
            lambda raw: raw["changes"][0]["source_spans"][0].update(
                sha256="g" * 64
            ),
            "changes[0].source_spans[0].sha256",
        ),
    ],
)
def test_malformed_provenance_hashes_are_rejected(
    mutate: Callable[[dict[str, Any]], None], expected_path: str
) -> None:
    raw = nested_catalog()
    mutate(raw)

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")
    assert "hexadecimal" in str(error.value)


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (lambda raw: raw.pop("upstream"), "catalog.upstream"),
        (lambda raw: raw["upstream"].pop("tag"), "upstream.tag"),
        (lambda raw: raw["migration"].pop("complete"), "migration.complete"),
        (lambda raw: raw["groups"][0].pop("name"), "groups[0].name"),
        (lambda raw: raw["changes"][0].pop("id"), "changes[0].id"),
        (
            lambda raw: raw["changes"][0]["source_spans"][0].pop("end"),
            "changes[0].source_spans[0].end",
        ),
        (
            lambda raw: raw["changes"][0]["resources"][0].pop("kind"),
            "changes[0].resources[0].kind",
        ),
        (
            lambda raw: raw["infrastructure"][0].pop("id"),
            "infrastructure[0].id",
        ),
    ],
)
def test_missing_required_fields_are_rejected_with_their_path(
    mutate: Callable[[dict[str, Any]], object], expected_path: str
) -> None:
    raw = nested_catalog()
    mutate(raw)

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")
    assert "missing required field" in str(error.value)


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (lambda raw: raw.update(schema_version=True), "schema_version"),
        (lambda raw: raw["upstream"].update(tag=421), "upstream.tag"),
        (lambda raw: raw["migration"].update(complete=0), "migration.complete"),
        (lambda raw: raw["groups"][0].update(name=1), "groups[0].name"),
        (lambda raw: raw["groups"][0].update(default=True), "groups[0].default"),
        (lambda raw: raw["changes"][0].update(component=False), "changes[0].component"),
        (lambda raw: raw["changes"][0].update(games="bg2ee"), "changes[0].games"),
        (
            lambda raw: raw["changes"][0]["source_spans"][0].update(start=1),
            "changes[0].source_spans[0].start",
        ),
        (
            lambda raw: raw["changes"][0]["resources"][0].update(kind=1),
            "changes[0].resources[0].kind",
        ),
        (
            lambda raw: raw["infrastructure"][0].update(consumers="a"),
            "infrastructure[0].consumers",
        ),
    ],
)
def test_wrong_scalar_types_are_rejected_with_their_path(
    mutate: Callable[[dict[str, Any]], None], expected_path: str
) -> None:
    raw = nested_catalog()
    mutate(raw)

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


def test_negative_component_is_rejected() -> None:
    raw = minimal_catalog(changes=[change("a", component=-1)])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].component:")
    assert "non-negative integer" in str(error.value)


UnknownFieldMutation = Callable[[dict[str, Any]], str]


def _unknown_at_catalog(raw: dict[str, Any]) -> str:
    raw["surprise"] = True
    return "catalog.surprise"


def _unknown_at_upstream(raw: dict[str, Any]) -> str:
    raw["upstream"]["surprise"] = True
    return "upstream.surprise"


def _unknown_at_migration(raw: dict[str, Any]) -> str:
    raw["migration"]["surprise"] = True
    return "migration.surprise"


def _unknown_at_group(raw: dict[str, Any]) -> str:
    raw["groups"][0]["surprise"] = True
    return "groups[0].surprise"


def _unknown_at_change(raw: dict[str, Any]) -> str:
    raw["changes"][0]["surprise"] = True
    return "changes[0].surprise"


def _unknown_at_source_span(raw: dict[str, Any]) -> str:
    raw["changes"][0]["source_spans"][0]["surprise"] = True
    return "changes[0].source_spans[0].surprise"


def _unknown_at_resource(raw: dict[str, Any]) -> str:
    raw["changes"][0]["resources"][0]["surprise"] = True
    return "changes[0].resources[0].surprise"


def _unknown_at_infrastructure(raw: dict[str, Any]) -> str:
    raw["infrastructure"][0]["surprise"] = True
    return "infrastructure[0].surprise"


@pytest.mark.parametrize(
    "mutate",
    [
        _unknown_at_catalog,
        _unknown_at_upstream,
        _unknown_at_migration,
        _unknown_at_group,
        _unknown_at_change,
        _unknown_at_source_span,
        _unknown_at_resource,
        _unknown_at_infrastructure,
    ],
)
def test_unknown_fields_are_rejected_with_their_path(
    mutate: UnknownFieldMutation,
) -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "a",
                source_spans=[
                    {
                        "path": "spell_rev/components/main_component.tpa",
                        "start": "// start",
                        "end": "// end",
                        "sha256": "0" * 64,
                    }
                ],
                resources=[{"path": "spell_rev/a.spl", "kind": "resource"}],
            )
        ],
        infrastructure_records=[infrastructure("shared")],
    )
    expected_path = mutate(raw)

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


@pytest.mark.parametrize(
    ("records", "expected_path"),
    [
        ([change("same"), change("SAME", setting="sr_other")], "changes[1].id"),
        (
            [change("one", setting="sr_same"), change("two", setting="SR_SAME")],
            "changes[1].setting",
        ),
    ],
)
def test_duplicate_change_ids_and_settings_are_rejected_after_normalization(
    records: list[dict[str, Any]], expected_path: str
) -> None:
    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(minimal_catalog(changes=records))

    assert str(error.value).startswith(f"{expected_path}:")


def test_setting_must_be_unique_across_groups_and_changes() -> None:
    raw = minimal_catalog(changes=[change("a", setting="SR_DEFAULT")])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].setting:")


@pytest.mark.parametrize("setting", ["sr_bad=value", "sr_bad\nvalue"])
def test_setting_rejects_unsafe_assignment_syntax(setting: str) -> None:
    raw = minimal_catalog(changes=[change("a", setting=setting)])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].setting:")


def test_setting_cannot_collide_with_non_catalog_configuration() -> None:
    raw = minimal_catalog(changes=[change("a", setting="install_tobex")])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].setting:")
    assert "sr_" in str(error.value)


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (
            lambda raw: raw["migration"].update(
                installer_source="../main_component.tpa"
            ),
            "migration.installer_source",
        ),
        (
            lambda raw: raw["changes"][0]["source_spans"][0].update(
                path="C:/outside/main_component.tpa"
            ),
            "changes[0].source_spans[0].path",
        ),
        (
            lambda raw: raw["changes"][0]["resources"][0].update(
                path=r"spell_rev\outside.spl"
            ),
            "changes[0].resources[0].path",
        ),
    ],
)
def test_repository_paths_must_be_portable_and_relative(
    mutate: Callable[[dict[str, Any]], None], expected_path: str
) -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "a",
                source_spans=[
                    {
                        "path": "spell_rev/components/main_component.tpa",
                        "start": "// start",
                        "end": "// end",
                        "sha256": "0" * 64,
                    }
                ],
                resources=[{"path": "spell_rev/a.spl", "kind": "resource"}],
            )
        ]
    )
    mutate(raw)

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "spell_rev/sub:dir/file.tpa",
        "spell_rev/*.spl",
        "spell_rev/bad\0name.spl",
        "spell_rev/trailing./file.tpa",
        "spell_rev/NUL/file.tpa",
    ],
)
def test_repository_paths_reject_windows_invalid_segments(
    unsafe_path: str,
) -> None:
    raw = minimal_catalog(
        changes=[change("a", resources=[{"path": unsafe_path, "kind": "resource"}])]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].resources[0].path:")


@pytest.mark.parametrize(
    ("raw", "expected_path"),
    [
        (
            minimal_catalog(
                groups=[group("global", parent=None, default=2, setting="sr_default")]
            ),
            "groups[0].default",
        ),
        (minimal_catalog(changes=[change("a", default=-2)]), "changes[0].default"),
    ],
)
def test_invalid_tri_state_defaults_are_rejected(
    raw: dict[str, Any], expected_path: str
) -> None:
    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


def test_public_change_default_must_inherit() -> None:
    raw = minimal_catalog(changes=[change("a", default=0)])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].default:")
    assert "public change default must be -1" in str(error.value)


@pytest.mark.parametrize(
    "games",
    [[], ["unknown"], ["all", "bg2ee"], ["bg2ee", "BG2EE"]],
)
def test_change_games_use_supported_unique_nonempty_vocabulary(
    games: list[str],
) -> None:
    raw = minimal_catalog(changes=[change("a", games=games)])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].games")


@pytest.mark.parametrize("field", ["name_ref", "description_ref"])
@pytest.mark.parametrize("reference", ["1", "@", "@-1", "@name", "@1 trailing"])
def test_tra_references_must_use_at_decimal_syntax(
    field: str, reference: str
) -> None:
    raw = minimal_catalog(changes=[change("a", **{field: reference})])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"changes[0].{field}:")


def test_catalog_requires_one_root_group() -> None:
    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(minimal_catalog(groups=[]))

    assert str(error.value).startswith("groups:")
    assert "exactly one parentless root group" in str(error.value)


def test_catalog_rejects_a_second_root_group() -> None:
    raw = minimal_catalog(
        groups=[
            group("global", setting="sr_default", parent=None, default=1),
            group("arcane", parent=None),
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("groups[1].parent:")
    assert "exactly one parentless root group" in str(error.value)


def test_root_group_default_cannot_inherit() -> None:
    raw = minimal_catalog(
        groups=[group("global", setting="sr_default", parent=None, default=-1)]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("groups[0].default:")
    assert "root group default must be 0 or 1" in str(error.value)


@pytest.mark.parametrize(
    ("raw", "expected_path"),
    [
        (
            minimal_catalog(
                groups=[
                    group("global", parent=None, setting="sr_default", default=1),
                    group("arcane", parent="missing"),
                ]
            ),
            "groups[1].parent",
        ),
        (
            minimal_catalog(changes=[change("a", group="missing")]),
            "changes[0].group",
        ),
    ],
)
def test_missing_parent_groups_are_rejected(
    raw: dict[str, Any], expected_path: str
) -> None:
    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


def test_unknown_parent_is_reported_before_missing_root() -> None:
    raw = minimal_catalog(
        groups=[group("orphan", parent="typo")]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("groups[0].parent:")
    assert "unknown group ID 'typo'" in str(error.value)


def test_group_cycle_is_rejected_deterministically() -> None:
    raw = minimal_catalog(
        groups=[
            group("global", setting="sr_default", parent=None, default=1),
            group("a", parent="b"),
            group("b", parent="a"),
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("groups[2].parent:")
    assert "group cycle: a -> b -> a" in str(error.value)


def test_rootless_group_cycle_is_reported_before_missing_root() -> None:
    raw = minimal_catalog(
        groups=[
            group("a", parent="b"),
            group("b", parent="a"),
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("groups[1].parent:")
    assert "group cycle: a -> b -> a" in str(error.value)


def test_dependency_cycle_is_rejected_deterministically() -> None:
    raw = minimal_catalog(
        changes=[change("a", requires=["b"]), change("b", requires=["a"])]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[1].requires[0]:")
    assert "dependency cycle: a -> b -> a" in str(error.value)


@pytest.mark.parametrize("field", ["requires", "conflicts", "soft_requires"])
def test_dependencies_on_unknown_change_ids_are_rejected(field: str) -> None:
    raw = minimal_catalog(changes=[change("a", **{field: ["missing"]})])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"changes[0].{field}[0]:")
    assert "unknown change ID 'missing'" in str(error.value)


@pytest.mark.parametrize("field", ["conflicts", "soft_requires"])
def test_change_relations_cannot_reference_the_change_itself(field: str) -> None:
    raw = minimal_catalog(changes=[change("Mixed.Case", **{field: ["MIXED.CASE"]})])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"changes[0].{field}[0]:")
    assert "cannot reference itself" in str(error.value)


@pytest.mark.parametrize(
    ("first_field", "later_field"),
    [
        ("requires", "conflicts"),
        ("requires", "soft_requires"),
        ("conflicts", "soft_requires"),
    ],
)
def test_change_relation_sets_must_be_pairwise_disjoint(
    first_field: str, later_field: str
) -> None:
    subject = change("subject")
    subject[first_field] = ["Dependency"]
    subject[later_field] = ["DEPENDENCY"]
    raw = minimal_catalog(changes=[subject, change("dependency")])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"changes[0].{later_field}[0]:")
    assert first_field in str(error.value)


def test_change_processor_edge_requires_reciprocal_infrastructure_consumer() -> None:
    raw = minimal_catalog(
        changes=[change("Mixed.Change", processors=["SHARED"])],
        infrastructure_records=[infrastructure("shared")],
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].processors[0]:")
    assert "infrastructure[0].consumers" in str(error.value)


def test_infrastructure_consumer_can_describe_generic_shared_substrate() -> None:
    raw = minimal_catalog(
        changes=[change("mixed.change")],
        infrastructure_records=[infrastructure("Shared", consumers=["MIXED.CHANGE"])],
    )

    catalog = Catalog.from_dict(raw)

    assert catalog.infrastructure[0].consumers == ("MIXED.CHANGE",)
    assert catalog.changes[0].processors == ()


def test_change_processor_rejects_unknown_infrastructure() -> None:
    raw = minimal_catalog(changes=[change("a", processors=["missing"])])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].processors[0]:")
    assert "unknown infrastructure ID" in str(error.value)


def test_infrastructure_consumer_rejects_unknown_change() -> None:
    raw = minimal_catalog(
        infrastructure_records=[infrastructure("shared", consumers=["missing"])]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("infrastructure[0].consumers[0]:")
    assert "unknown change ID" in str(error.value)


def test_change_processors_reject_normalized_duplicates() -> None:
    raw = minimal_catalog(
        changes=[change("a", processors=["shared", "SHARED"])],
        infrastructure_records=[infrastructure("shared", consumers=["a"])],
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].processors[1]:")
    assert "duplicate infrastructure ID" in str(error.value)


def test_infrastructure_consumers_reject_normalized_duplicates() -> None:
    raw = minimal_catalog(
        changes=[change("a", processors=["shared"])],
        infrastructure_records=[infrastructure("shared", consumers=["a", "A"])],
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("infrastructure[0].consumers[1]:")
    assert "duplicate change ID" in str(error.value)


def test_id_normalization_does_not_rewrite_catalog_values() -> None:
    catalog = Catalog.from_dict(
        minimal_catalog(
            changes=[change("Mixed.Case"), change("consumer", requires=["MIXED.CASE"])]
        )
    )

    assert catalog.changes[0].id == "Mixed.Case"
    assert catalog.changes[1].requires == ("MIXED.CASE",)


def test_populated_catalog_preserves_all_fields_and_records_are_frozen() -> None:
    spans = [
        {
            "path": "spell_rev/components/main_component.tpa",
            "start": "// first start",
            "end": "// first end",
            "sha256": "a" * 64,
        },
        {
            "path": "spell_rev/lib/processor.tpa",
            "start": "// second start",
            "end": "// second end",
            "sha256": "b" * 64,
        },
    ]
    resources = [
        {"path": "spell_rev/spwi1##/spell.spl", "kind": "resource"},
        {"path": "SPELL.IDS", "kind": "ids_write"},
    ]
    raw = minimal_catalog(
        groups=[
            group("Global", setting="sr_default", parent=None, default=1),
            group("Arcane", setting="sr_arcane_default", parent="GLOBAL"),
        ],
        changes=[
            change(
                "Mixed.Change",
                setting="sr_mixed_change",
                display_name="Mixed change",
                default=-1,
                group="ARCANE",
                component=65,
                games=["bg2ee", "iwdee"],
                name_ref="@100",
                description_ref="@101",
                source_spans=spans,
                resources=resources,
                atomic_group="Atomic.Family",
                requires=["Required"],
                conflicts=["Conflict"],
                soft_requires=["Soft"],
                processors=["Shared.Processor"],
                documentation_only_reason="Documented test fixture",
            ),
            change("Required"),
            change("Conflict"),
            change("Soft"),
        ],
        infrastructure_records=[
            infrastructure(
                "shared.processor",
                source_spans=[spans[1]],
                resources=[resources[1]],
                consumers=["MIXED.CHANGE"],
            ),
            infrastructure("other.processor"),
        ],
    )

    catalog = Catalog.from_dict(json.loads(json.dumps(raw)))

    assert catalog.schema_version == 1
    assert catalog.upstream == Upstream(tag="v4.21", commit=UPSTREAM_COMMIT)
    assert catalog.migration == Migration(
        complete=False,
        installer_source="spell_rev/components/main_component.tpa",
    )
    assert catalog.groups == (
        Group("Global", "sr_default", "Global", 1, None),
        Group("Arcane", "sr_arcane_default", "Arcane", -1, "GLOBAL"),
    )
    assert tuple(record.id for record in catalog.changes) == (
        "Mixed.Change",
        "Required",
        "Conflict",
        "Soft",
    )

    parsed_change = catalog.changes[0]
    assert isinstance(parsed_change, Change)
    assert (
        parsed_change.id,
        parsed_change.setting,
        parsed_change.display_name,
        parsed_change.default,
        parsed_change.group,
        parsed_change.component,
        parsed_change.games,
        parsed_change.name_ref,
        parsed_change.description_ref,
        parsed_change.atomic_group,
        parsed_change.requires,
        parsed_change.conflicts,
        parsed_change.soft_requires,
        parsed_change.processors,
        parsed_change.documentation_only_reason,
    ) == (
        "Mixed.Change",
        "sr_mixed_change",
        "Mixed change",
        -1,
        "ARCANE",
        65,
        ("bg2ee", "iwdee"),
        "@100",
        "@101",
        "Atomic.Family",
        ("Required",),
        ("Conflict",),
        ("Soft",),
        ("Shared.Processor",),
        "Documented test fixture",
    )
    assert parsed_change.source_spans == (
        SourceSpan(
            "spell_rev/components/main_component.tpa",
            "// first start",
            "// first end",
            "a" * 64,
        ),
        SourceSpan(
            "spell_rev/lib/processor.tpa",
            "// second start",
            "// second end",
            "b" * 64,
        ),
    )
    assert parsed_change.resources == (
        ResourceOwnership("spell_rev/spwi1##/spell.spl", "resource"),
        ResourceOwnership("SPELL.IDS", "ids_write"),
    )
    assert catalog.infrastructure == (
        Infrastructure(
            id="shared.processor",
            source_spans=(parsed_change.source_spans[1],),
            resources=(parsed_change.resources[1],),
            consumers=("MIXED.CHANGE",),
        ),
        Infrastructure(id="other.processor"),
    )

    frozen_records: list[tuple[object, str, object]] = [
        (catalog, "schema_version", 2),
        (catalog.upstream, "tag", "v-next"),
        (catalog.migration, "complete", True),
        (catalog.groups[0], "name", "changed"),
        (parsed_change.source_spans[0], "path", "changed"),
        (parsed_change.resources[0], "kind", "changed"),
        (parsed_change, "display_name", "changed"),
        (catalog.infrastructure[0], "id", "changed"),
    ]
    for record, attribute, replacement in frozen_records:
        with pytest.raises(FrozenInstanceError):
            setattr(record, attribute, replacement)
