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
    IncludeResolution,
    Infrastructure,
    MemberReference,
    Migration,
    NameFallback,
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
        "name_ref": "@1",
        "name_fallback": None,
        "description_ref": "@2",
        "member_refs": [],
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


def name_fallback(resource: str = "SPWI101", *, kind: str = "game_resource") -> dict[str, str]:
    return {"kind": kind, "resource": resource}


def member_reference(
    source_spell: str,
    *,
    level: int = 1,
    role: str = "active",
    name_ref: str | None = "@1",
    name_fallback_value: dict[str, str] | None = None,
    description_ref: str = "@2",
) -> dict[str, Any]:
    return {
        "source_spell": source_spell,
        "level": level,
        "role": role,
        "name_ref": name_ref,
        "name_fallback": name_fallback_value,
        "description_ref": description_ref,
    }


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
    ("owner", "setting", "expected_path"),
    [
        ("group", "SR_CONFIG_SCHEMA", "groups[0].setting"),
        ("group", "sr_catalog_fingerprint", "groups[0].setting"),
        ("change", "sr_config_schema", "changes[0].setting"),
        ("change", "SR_CATALOG_FINGERPRINT", "changes[0].setting"),
    ],
)
def test_metadata_setting_names_are_reserved_case_insensitively(
    owner: str, setting: str, expected_path: str
) -> None:
    raw = minimal_catalog(
        groups=[
            group(
                "global",
                setting=setting if owner == "group" else "sr_default",
                parent=None,
                default=1,
            )
        ],
        changes=[change("a", setting=setting)] if owner == "change" else [],
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")
    assert "reserved generated setting" in str(error.value)


@pytest.mark.parametrize(
    ("owner", "setting", "expected_path"),
    [
        ("group", "SR_FEATURE_000003", "groups[0].setting"),
        ("change", "sr_feature_000001", "changes[0].setting"),
        ("change", "Sr_FeAtUrE_999999", "changes[0].setting"),
        ("change", "sr_feature_future", "changes[0].setting"),
    ],
)
def test_generated_feature_namespace_is_reserved_case_insensitively(
    owner: str, setting: str, expected_path: str
) -> None:
    changes = [change("a"), change("b")]
    if owner == "change":
        changes[0]["setting"] = setting
    raw = minimal_catalog(
        groups=[
            group(
                "global",
                setting=setting if owner == "group" else "sr_default",
                parent=None,
                default=1,
            )
        ],
        changes=changes,
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")
    assert "reserved generated setting" in str(error.value)


def test_similar_non_namespace_feature_setting_is_allowed() -> None:
    catalog = Catalog.from_dict(
        minimal_catalog(changes=[change("a", setting="sr_featurex")])
    )

    assert catalog.changes[0].setting == "sr_featurex"


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


def test_singleton_documentation_accepts_exactly_one_name_source() -> None:
    tra_catalog = Catalog.from_dict(minimal_catalog(changes=[change("tra")]))
    fallback_catalog = Catalog.from_dict(
        minimal_catalog(
            changes=[
                change(
                    "fallback",
                    name_ref=None,
                    name_fallback=name_fallback("SPWI101"),
                )
            ]
        )
    )

    assert tra_catalog.changes[0].name_ref == "@1"
    assert tra_catalog.changes[0].name_fallback is None
    assert fallback_catalog.changes[0].name_ref is None
    assert fallback_catalog.changes[0].name_fallback == NameFallback(
        "game_resource", "SPWI101"
    )


@pytest.mark.parametrize(
    ("overrides", "expected_field"),
    [
        ({"name_ref": None, "name_fallback": None}, "name_ref"),
        ({"name_ref": "@1", "name_fallback": name_fallback()}, "name_fallback"),
        ({"description_ref": None}, "description_ref"),
        (
            {
                "member_refs": [member_reference("SPWI101")],
                "name_ref": None,
                "name_fallback": None,
                "description_ref": None,
            },
            "member_refs",
        ),
        (
            {
                "member_refs": [
                    member_reference("SPWI101"),
                    member_reference("SPWI102"),
                ]
            },
            "name_ref",
        ),
    ],
)
def test_documentation_mode_matrix_rejects_missing_mixed_and_one_member_modes(
    overrides: dict[str, Any], expected_field: str
) -> None:
    raw = minimal_catalog(changes=[change("invalid", **overrides)])

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"changes[0].{expected_field}:")


def test_documentation_only_reason_cannot_replace_text_provenance() -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "undocumented",
                name_ref=None,
                name_fallback=None,
                description_ref=None,
                documentation_only_reason="prose is not upstream text provenance",
            )
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].name_ref:")


def test_composite_documentation_preserves_order_and_frozen_member_records() -> None:
    members = [
        member_reference(
            "SPWI101",
            level=1,
            role="active_replacement",
            name_ref="@10",
            description_ref="@11",
        ),
        member_reference(
            "SPWI205",
            level=2,
            role="deprecated_slot",
            name_ref=None,
            name_fallback_value=name_fallback("SPWI205"),
            description_ref="@12",
        ),
    ]
    catalog = Catalog.from_dict(
        minimal_catalog(
            changes=[
                change(
                    "bundle",
                    name_ref=None,
                    name_fallback=None,
                    description_ref=None,
                    member_refs=members,
                )
            ]
        )
    )

    assert catalog.changes[0].member_refs == (
        MemberReference(
            "SPWI101", 1, "active_replacement", "@10", None, "@11"
        ),
        MemberReference(
            "SPWI205",
            2,
            "deprecated_slot",
            None,
            NameFallback("game_resource", "SPWI205"),
            "@12",
        ),
    )
    with pytest.raises(FrozenInstanceError):
        catalog.changes[0].member_refs[0].role = "active"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        catalog.changes[0].member_refs[1].name_fallback.resource = "SPWI999"  # type: ignore[misc,union-attr]


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        (
            lambda raw: raw["changes"][0].pop("name_fallback"),
            "changes[0].name_fallback",
        ),
        (
            lambda raw: raw["changes"][0].pop("member_refs"),
            "changes[0].member_refs",
        ),
        (
            lambda raw: raw["changes"][0]["name_fallback"].pop("kind"),
            "changes[0].name_fallback.kind",
        ),
        (
            lambda raw: raw["changes"][0]["member_refs"][0].pop("description_ref"),
            "changes[0].member_refs[0].description_ref",
        ),
    ],
)
def test_documentation_metadata_missing_fields_are_rejected_strictly(
    mutation: Callable[[dict[str, Any]], object], expected_path: str
) -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "bundle",
                name_ref=None,
                name_fallback=None,
                description_ref=None,
                member_refs=[
                    member_reference("SPWI101"),
                    member_reference("SPWI102"),
                ],
            )
        ]
    )
    if expected_path.startswith("changes[0].name_fallback."):
        raw["changes"][0]["name_ref"] = None
        raw["changes"][0]["name_fallback"] = name_fallback()
        raw["changes"][0]["description_ref"] = "@2"
        raw["changes"][0]["member_refs"] = []
    mutation(raw)

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")
    assert "missing required field" in str(error.value)


@pytest.mark.parametrize(
    ("target", "expected_path"),
    [
        ("change", "changes[0].surprise"),
        ("fallback", "changes[0].name_fallback.surprise"),
        ("member", "changes[0].member_refs[0].surprise"),
        ("member_fallback", "changes[0].member_refs[0].name_fallback.surprise"),
    ],
)
def test_documentation_metadata_unknown_fields_are_rejected_strictly(
    target: str, expected_path: str
) -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "bundle",
                name_ref=None,
                name_fallback=None,
                description_ref=None,
                member_refs=[
                    member_reference(
                        "SPWI101",
                        name_ref=None,
                        name_fallback_value=name_fallback(),
                    ),
                    member_reference("SPWI102"),
                ],
            )
        ]
    )
    record = raw["changes"][0]
    if target == "change":
        record["surprise"] = True
    elif target == "fallback":
        record["name_ref"] = None
        record["name_fallback"] = name_fallback()
        record["description_ref"] = "@2"
        record["member_refs"] = []
        record["name_fallback"]["surprise"] = True
    elif target == "member":
        record["member_refs"][0]["surprise"] = True
    else:
        record["member_refs"][0]["name_fallback"]["surprise"] = True

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")
    assert "unknown field" in str(error.value)


@pytest.mark.parametrize(
    ("target", "value", "expected_path"),
    [
        ("fallback_kind", "installed_resource", "changes[0].name_fallback.kind"),
        ("fallback_resource", "spwi101", "changes[0].name_fallback.resource"),
        ("fallback_resource", "SPWI101.SPL", "changes[0].name_fallback.resource"),
        ("source_spell", "spwi101", "changes[0].member_refs[0].source_spell"),
        ("source_spell", "SPWI101.SPL", "changes[0].member_refs[0].source_spell"),
        ("level", 0, "changes[0].member_refs[0].level"),
        ("level", 11, "changes[0].member_refs[0].level"),
        ("level", True, "changes[0].member_refs[0].level"),
        ("role", "replacement", "changes[0].member_refs[0].role"),
        ("description_ref", None, "changes[0].member_refs[0].description_ref"),
    ],
)
def test_documentation_metadata_uses_closed_exact_vocabularies(
    target: str, value: object, expected_path: str
) -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "bundle",
                name_ref=None,
                name_fallback=None,
                description_ref=None,
                member_refs=[
                    member_reference("SPWI101"),
                    member_reference("SPWI102"),
                ],
            )
        ]
    )
    record = raw["changes"][0]
    if target.startswith("fallback_"):
        record["name_ref"] = None
        record["name_fallback"] = name_fallback()
        record["description_ref"] = "@2"
        record["member_refs"] = []
        record["name_fallback"][target.removeprefix("fallback_")] = value
    else:
        record["member_refs"][0][target] = value

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


@pytest.mark.parametrize(
    ("name_ref", "fallback"),
    [(None, None), ("@1", name_fallback())],
)
def test_member_name_requires_exactly_one_source(
    name_ref: str | None, fallback: dict[str, str] | None
) -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "bundle",
                name_ref=None,
                name_fallback=None,
                description_ref=None,
                member_refs=[
                    member_reference(
                        "SPWI101",
                        name_ref=name_ref,
                        name_fallback_value=fallback,
                    ),
                    member_reference("SPWI102"),
                ],
            )
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].member_refs[0].name_")


def test_member_source_spells_are_unique_case_insensitively() -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "bundle",
                name_ref=None,
                name_fallback=None,
                description_ref=None,
                member_refs=[
                    member_reference("SPWI101"),
                    member_reference("SPWI101"),
                ],
            )
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].member_refs[1].source_spell:")
    assert "duplicate source spell" in str(error.value)


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
        parsed_change.name_fallback,
        parsed_change.description_ref,
        parsed_change.member_refs,
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
        None,
        "@101",
        (),
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


@pytest.mark.parametrize(
    "category", ["derived", "compatibility", "mandatory_metadata"]
)
def test_infrastructure_category_represents_non_public_component_zero_work(
    category: str,
) -> None:
    raw = minimal_catalog(
        infrastructure_records=[infrastructure("internal", category=category)]
    )

    catalog = Catalog.from_dict(raw)

    assert catalog.infrastructure[0].category == category


def test_infrastructure_category_defaults_to_derived_for_existing_records() -> None:
    catalog = Catalog.from_dict(
        minimal_catalog(infrastructure_records=[infrastructure("internal")])
    )

    assert catalog.infrastructure[0].category == "derived"


@pytest.mark.parametrize("category", ["shared", "metadata", "", 1, None])
def test_infrastructure_category_uses_a_closed_explicit_vocabulary(
    category: object,
) -> None:
    raw = minimal_catalog(
        infrastructure_records=[infrastructure("internal", category=category)]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("infrastructure[0].category:")


def test_source_span_can_explicitly_end_at_eof() -> None:
    raw = minimal_catalog(
        changes=[
            change(
                "eof",
                source_spans=[
                    {
                        "path": "spell_rev/components/main_component.tpa",
                        "start": "// final section",
                        "end": None,
                        "sha256": "a" * 64,
                    }
                ],
            )
        ]
    )

    catalog = Catalog.from_dict(raw)

    assert catalog.changes[0].source_spans[0].end is None


def test_source_span_end_is_required_even_when_eof_is_intended() -> None:
    raw = nested_catalog()
    raw["changes"][0]["source_spans"][0].pop("end")

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith("changes[0].source_spans[0].end:")
    assert "missing required field" in str(error.value)


def test_infrastructure_can_resolve_a_dynamic_include_explicitly() -> None:
    raw = minimal_catalog(
        infrastructure_records=[
            infrastructure(
                "game_include",
                include_resolutions=[
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "operand": "spell_rev/lib/%GAME%.tph",
                        "targets": ["spell_rev/lib/bg2ee.tph", "spell_rev/lib/iwdee.tph"],
                    }
                ],
            )
        ]
    )

    catalog = Catalog.from_dict(raw)

    assert catalog.infrastructure[0].include_resolutions == (
        IncludeResolution(
            source="spell_rev/components/main_component.tpa",
            operand="spell_rev/lib/%GAME%.tph",
            targets=("spell_rev/lib/bg2ee.tph", "spell_rev/lib/iwdee.tph"),
        ),
    )


@pytest.mark.parametrize(
    ("resolution", "expected_path"),
    [
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "operand": "spell_rev/lib/%GAME%.tph",
                "targets": [],
            },
            "infrastructure[0].include_resolutions[0].targets",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "operand": "spell_rev/lib/%GAME%.tph",
                "targets": ["spell_rev/lib/%GAME%.tph"],
            },
            "infrastructure[0].include_resolutions[0].targets[0]",
        ),
    ],
)
def test_include_resolution_requires_concrete_targets(
    resolution: dict[str, object], expected_path: str
) -> None:
    raw = minimal_catalog(
        infrastructure_records=[
            infrastructure("game_include", include_resolutions=[resolution])
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


def test_infrastructure_can_resolve_a_dynamic_source_operand() -> None:
    raw = minimal_catalog(
        infrastructure_records=[
            infrastructure(
                "dynamic_source",
                source_resolutions=[
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 10,
                        "command": "COPY",
                        "operand_index": 0,
                        "operand": "spell_rev/assets/%SPELL%.spl",
                        "reason": "Loop expands the exact shipped spell set",
                        "targets": ["spell_rev/assets/a.spl"],
                    },
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 11,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%GAME_SPELL%.spl",
                        "reason": "Resolved from the base game at install time",
                        "external": True,
                    },
                ],
            )
        ]
    )

    catalog = Catalog.from_dict(raw)

    local, external = catalog.infrastructure[0].source_resolutions
    assert (
        local.source,
        local.line,
        local.command,
        local.operand_index,
        local.operand,
        local.reason,
        local.targets,
        local.generated_owners,
        local.external,
    ) == (
        "spell_rev/components/main_component.tpa",
        10,
        "COPY",
        0,
        "spell_rev/assets/%SPELL%.spl",
        "Loop expands the exact shipped spell set",
        ("spell_rev/assets/a.spl",),
        (),
        False,
    )
    assert external.targets == ()
    assert external.generated_owners == ()
    assert external.external is True
    assert external.reason == "Resolved from the base game at install time"


@pytest.mark.parametrize(
    ("resolution", "expected_path"),
    [
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 10,
                "command": "COPY",
                "operand_index": 0,
                "operand": "spell_rev/assets/%SPELL%.spl",
                "reason": "Reviewed occurrence",
            },
            "infrastructure[0].source_resolutions[0]",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 10,
                "command": "COPY",
                "operand_index": 0,
                "operand": "spell_rev/assets/a.spl",
                "reason": "Reviewed occurrence",
                "targets": ["spell_rev/assets/a.spl"],
            },
            "infrastructure[0].source_resolutions[0].operand",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 10,
                "command": "COPY",
                "operand_index": 0,
                "operand": "spell_rev/assets/%SPELL%.spl",
                "reason": "Reviewed occurrence",
                "targets": ["spell_rev/assets/%SPELL%.spl"],
            },
            "infrastructure[0].source_resolutions[0].targets[0]",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 10,
                "command": "COPY",
                "operand_index": 0,
                "operand": "spell_rev/assets/%SPELL%.spl",
                "reason": "Reviewed occurrence",
                "targets": ["spell_rev/assets/a.spl"],
                "external": True,
            },
            "infrastructure[0].source_resolutions[0]",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 10,
                "command": "COPY INVALID",
                "operand_index": 0,
                "operand": "spell_rev/assets/%SPELL%.spl",
                "reason": "Reviewed occurrence",
                "targets": ["spell_rev/assets/a.spl"],
            },
            "infrastructure[0].source_resolutions[0].command",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 10,
                "command": "COPY_EXISTING",
                "operand_index": 0,
                "operand": "%GAME_SPELL%.spl",
                "reason": "  ",
                "external": True,
            },
            "infrastructure[0].source_resolutions[0].reason",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 0,
                "command": "COPY",
                "operand_index": 0,
                "operand": "spell_rev/assets/%SPELL%.spl",
                "reason": "Reviewed occurrence",
                "targets": ["spell_rev/assets/a.spl"],
            },
            "infrastructure[0].source_resolutions[0].line",
        ),
        (
            {
                "source": "spell_rev/components/main_component.tpa",
                "line": 10,
                "command": "COPY",
                "operand_index": -1,
                "operand": "spell_rev/assets/%SPELL%.spl",
                "reason": "Reviewed occurrence",
                "targets": ["spell_rev/assets/a.spl"],
            },
            "infrastructure[0].source_resolutions[0].operand_index",
        ),
    ],
)
def test_source_resolution_requires_one_strict_resolution_mode(
    resolution: dict[str, object], expected_path: str
) -> None:
    raw = minimal_catalog(
        infrastructure_records=[
            infrastructure("dynamic_source", source_resolutions=[resolution])
        ]
    )

    with pytest.raises(CatalogError) as error:
        Catalog.from_dict(raw)

    assert str(error.value).startswith(f"{expected_path}:")


def test_dynamic_source_resolution_key_is_unique_across_infrastructure() -> None:
    resolution = {
        "source": "spell_rev/components/main_component.tpa",
        "line": 10,
        "command": "COPY",
        "operand_index": 0,
        "operand": "spell_rev/assets/%SPELL%.spl",
        "reason": "Reviewed occurrence",
        "targets": ["spell_rev/assets/a.spl"],
    }
    duplicate = {
        **resolution,
        "command": "copy",
        "operand": "spell_rev/assets/%spell%.spl",
    }
    raw = minimal_catalog(
        infrastructure_records=[
            infrastructure("first", source_resolutions=[resolution]),
            infrastructure("second", source_resolutions=[duplicate]),
        ]
    )

    with pytest.raises(CatalogError, match="duplicate dynamic source resolution"):
        Catalog.from_dict(raw)


def test_generated_source_owner_must_name_change_or_infrastructure() -> None:
    raw = minimal_catalog(
        infrastructure_records=[
            infrastructure(
                "generated",
                source_resolutions=[
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 10,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Generated spell lookup",
                        "generated_owners": ["global"],
                    }
                ],
            )
        ]
    )

    with pytest.raises(CatalogError, match="unknown catalog owner ID 'global'"):
        Catalog.from_dict(raw)
