from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from tools.sr_config.catalog import Catalog, CatalogError, load_catalog


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


def infrastructure(infrastructure_id: str) -> dict[str, Any]:
    return {
        "id": infrastructure_id,
        "source_spans": [],
        "resources": [],
        "consumers": [],
    }


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

    assert [record.id for record in catalog.groups[:3]] == [
        "global",
        "arcane",
        "arcane.level1",
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


def test_id_normalization_does_not_rewrite_catalog_values() -> None:
    catalog = Catalog.from_dict(
        minimal_catalog(
            changes=[change("Mixed.Case"), change("consumer", requires=["MIXED.CASE"])]
        )
    )

    assert catalog.changes[0].id == "Mixed.Case"
    assert catalog.changes[1].requires == ("MIXED.CASE",)
