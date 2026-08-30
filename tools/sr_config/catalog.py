"""Strict schema and validation for the Spell Revisions change catalog."""

from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
CONFIG_METADATA_SETTINGS = frozenset(
    {"sr_config_schema", "sr_catalog_fingerprint"}
)
SUPPORTED_GAMES = frozenset(
    {
        "soa",
        "tob",
        "bgee",
        "bg2ee",
        "eet",
        "iwdee",
        "tutu",
        "tutu_totsc",
        "bgt",
    }
)
_TRI_STATE_VALUES = frozenset({-1, 0, 1})
INFRASTRUCTURE_CATEGORIES = frozenset(
    {"derived", "compatibility", "mandatory_metadata"}
)
INFRASTRUCTURE_ACTIVATIONS = frozenset({"consumer_selected", "always"})
MEMBER_REFERENCE_ROLES = frozenset(
    {
        "active",
        "active_replacement",
        "deprecated_slot",
        "game_compatibility_slot",
        "ai_deprecated_slot",
    }
)
NAME_FALLBACK_KINDS = frozenset({"game_resource"})
_HEX_DIGITS = frozenset(string.hexdigits)
_SETTING_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_TRA_REFERENCE_PATTERN = re.compile(r"@[0-9]+\Z")
_RESREF_PATTERN = re.compile(r"[A-Z0-9_#]{1,8}\Z")
_RESOURCE_TYPE_PATTERN = re.compile(r"[A-Z0-9]{1,8}\Z")
_WINDOWS_FORBIDDEN_PATH_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_PATH_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


class _JSONObject(list[tuple[str, Any]]):
    """Preserve JSON object pairs until duplicate fields can be path-checked."""


class CatalogError(ValueError):
    """Raised when catalog data violates the schema or its invariants."""


@dataclass(frozen=True)
class Upstream:
    tag: str
    commit: str


@dataclass(frozen=True)
class Migration:
    complete: bool
    installer_source: str


@dataclass(frozen=True)
class Group:
    id: str
    setting: str
    name: str
    default: int
    parent: str | None = None


@dataclass(frozen=True)
class SourceSpan:
    path: str
    start: str
    end: str | None
    sha256: str


@dataclass(frozen=True)
class ResourceOwnership:
    path: str
    kind: str


@dataclass(frozen=True)
class DormantResource:
    path: str
    reason: str


@dataclass(frozen=True)
class DeferredSourceScope:
    id: str
    reason: str
    source_spans: tuple[SourceSpan, ...] = field(default_factory=tuple)
    resources: tuple[ResourceOwnership, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BinaryEdgeResolution:
    source: str
    offset: int
    field: str
    opcode: int | None
    target: str
    expected_types: tuple[str, ...]
    shadowed_candidates: tuple[str, ...]
    classification: str
    reason: str


@dataclass(frozen=True)
class IncludeResolution:
    source: str
    operand: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class SourceResolution:
    source: str
    line: int
    command: str
    operand_index: int
    operand: str
    reason: str
    targets: tuple[str, ...] = field(default_factory=tuple)
    generated_owners: tuple[str, ...] = field(default_factory=tuple)
    external: bool = False
    access: str = "dependency"
    internal_generated_owners: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NameFallback:
    kind: str
    resource: str


@dataclass(frozen=True)
class MemberReference:
    source_spell: str
    level: int
    role: str
    name_ref: str | None
    name_fallback: NameFallback | None
    description_ref: str


@dataclass(frozen=True)
class Change:
    id: str
    setting: str
    display_name: str
    default: int
    group: str
    component: int = 0
    games: tuple[str, ...] = field(default_factory=tuple)
    name_ref: str | None = None
    name_fallback: NameFallback | None = None
    description_ref: str | None = None
    member_refs: tuple[MemberReference, ...] = field(default_factory=tuple)
    source_spans: tuple[SourceSpan, ...] = field(default_factory=tuple)
    resources: tuple[ResourceOwnership, ...] = field(default_factory=tuple)
    atomic_group: str | None = None
    requires: tuple[str, ...] = field(default_factory=tuple)
    conflicts: tuple[str, ...] = field(default_factory=tuple)
    soft_requires: tuple[str, ...] = field(default_factory=tuple)
    processors: tuple[str, ...] = field(default_factory=tuple)
    documentation_only_reason: str | None = None


@dataclass(frozen=True)
class Infrastructure:
    id: str
    activation: str
    infrastructure_requires: tuple[str, ...]
    source_spans: tuple[SourceSpan, ...] = field(default_factory=tuple)
    resources: tuple[ResourceOwnership, ...] = field(default_factory=tuple)
    consumers: tuple[str, ...] = field(default_factory=tuple)
    category: str = "derived"
    include_resolutions: tuple[IncludeResolution, ...] = field(default_factory=tuple)
    source_resolutions: tuple[SourceResolution, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Catalog:
    schema_version: int
    upstream: Upstream
    migration: Migration
    groups: tuple[Group, ...]
    changes: tuple[Change, ...]
    infrastructure: tuple[Infrastructure, ...]
    dormant_resources: tuple[DormantResource, ...]
    deferred_source_scopes: tuple[DeferredSourceScope, ...]
    binary_edge_resolutions: tuple[BinaryEdgeResolution, ...]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Catalog:
        catalog_raw = _mapping(raw, "catalog")
        _check_keys(
            catalog_raw,
            path="catalog",
            allowed={
                "schema_version",
                "upstream",
                "migration",
                "groups",
                "changes",
                "infrastructure",
                "dormant_resources",
                "deferred_source_scopes",
                "binary_edge_resolutions",
            },
            required={
                "schema_version",
                "upstream",
                "migration",
                "groups",
                "changes",
                "infrastructure",
                "dormant_resources",
                "deferred_source_scopes",
                "binary_edge_resolutions",
            },
        )

        schema_version = _integer(catalog_raw["schema_version"], "schema_version")
        if schema_version != SCHEMA_VERSION:
            raise CatalogError(
                f"schema_version: unsupported schema version {schema_version}; "
                f"expected {SCHEMA_VERSION}"
            )

        upstream = _parse_upstream(catalog_raw["upstream"])
        migration = _parse_migration(catalog_raw["migration"])

        groups_raw = _list(catalog_raw["groups"], "groups")
        groups = tuple(
            _parse_group(value, f"groups[{index}]")
            for index, value in enumerate(groups_raw)
        )

        changes_raw = _list(catalog_raw["changes"], "changes")
        changes = tuple(
            _parse_change(value, f"changes[{index}]")
            for index, value in enumerate(changes_raw)
        )

        infrastructure_raw = _list(
            catalog_raw["infrastructure"], "infrastructure"
        )
        infrastructure = tuple(
            _parse_infrastructure(value, f"infrastructure[{index}]")
            for index, value in enumerate(infrastructure_raw)
        )

        dormant_raw = _list(catalog_raw["dormant_resources"], "dormant_resources")
        dormant_resources = tuple(
            _parse_dormant_resource(value, f"dormant_resources[{index}]")
            for index, value in enumerate(dormant_raw)
        )

        deferred_raw = _list(
            catalog_raw["deferred_source_scopes"], "deferred_source_scopes"
        )
        deferred_source_scopes = tuple(
            _parse_deferred_source_scope(
                value, f"deferred_source_scopes[{index}]"
            )
            for index, value in enumerate(deferred_raw)
        )

        binary_raw = _list(
            catalog_raw["binary_edge_resolutions"], "binary_edge_resolutions"
        )
        binary_edge_resolutions = tuple(
            _parse_binary_edge_resolution(
                value, f"binary_edge_resolutions[{index}]"
            )
            for index, value in enumerate(binary_raw)
        )

        catalog = cls(
            schema_version=schema_version,
            upstream=upstream,
            migration=migration,
            groups=groups,
            changes=changes,
            infrastructure=infrastructure,
            dormant_resources=dormant_resources,
            deferred_source_scopes=deferred_source_scopes,
            binary_edge_resolutions=binary_edge_resolutions,
        )
        _validate_catalog(catalog)
        return catalog


def load_catalog(path: str | Path) -> Catalog:
    """Load and validate a UTF-8 JSON catalog from *path*."""

    catalog_path = Path(path)
    try:
        source = catalog_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise CatalogError(
            f"{catalog_path}: catalog is not valid UTF-8 at byte {error.start}"
        ) from error
    except OSError as error:
        raise CatalogError(f"{catalog_path}: unable to read catalog: {error}") from error

    try:
        parsed = json.loads(source, object_pairs_hook=_JSONObject)
    except json.JSONDecodeError as error:
        raise CatalogError(
            f"{catalog_path}:{error.lineno}:{error.colno}: invalid JSON: {error.msg}"
        ) from error

    raw = _materialize_json(parsed, "catalog")
    return Catalog.from_dict(_mapping(raw, "catalog"))


def _parse_upstream(value: Any) -> Upstream:
    raw = _mapping(value, "upstream")
    _check_keys(
        raw,
        path="upstream",
        allowed={"tag", "commit"},
        required={"tag", "commit"},
    )
    tag = _string(raw["tag"], "upstream.tag")
    commit = _string(raw["commit"], "upstream.commit")
    if len(commit) != 40 or any(character not in _HEX_DIGITS for character in commit):
        raise CatalogError("upstream.commit: expected a 40-character hexadecimal commit")
    return Upstream(tag=tag, commit=commit)


def _parse_migration(value: Any) -> Migration:
    raw = _mapping(value, "migration")
    _check_keys(
        raw,
        path="migration",
        allowed={"complete", "installer_source"},
        required={"complete", "installer_source"},
    )
    complete = raw["complete"]
    if type(complete) is not bool:
        raise CatalogError("migration.complete: expected a boolean")
    return Migration(
        complete=complete,
        installer_source=_repository_path(
            raw["installer_source"], "migration.installer_source"
        ),
    )


def _parse_group(value: Any, path: str) -> Group:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"id", "setting", "name", "default", "parent"},
        required={"id", "setting", "name", "default", "parent"},
    )
    return Group(
        id=_identifier(raw["id"], f"{path}.id"),
        setting=_setting(raw["setting"], f"{path}.setting"),
        name=_string(raw["name"], f"{path}.name"),
        default=_tri_state(raw["default"], f"{path}.default"),
        parent=_optional_identifier(raw["parent"], f"{path}.parent"),
    )


def _parse_source_span(value: Any, path: str) -> SourceSpan:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"path", "start", "end", "sha256"},
        required={"path", "start", "end", "sha256"},
    )
    sha256 = _string(raw["sha256"], f"{path}.sha256")
    if len(sha256) != 64 or any(character not in _HEX_DIGITS for character in sha256):
        raise CatalogError(f"{path}.sha256: expected a 64-character hexadecimal hash")
    return SourceSpan(
        path=_repository_path(raw["path"], f"{path}.path"),
        start=_string(raw["start"], f"{path}.start"),
        end=_optional_string(raw["end"], f"{path}.end"),
        sha256=sha256,
    )


def _parse_resource(value: Any, path: str) -> ResourceOwnership:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"path", "kind"},
        required={"path", "kind"},
    )
    return ResourceOwnership(
        path=_repository_path(raw["path"], f"{path}.path"),
        kind=_identifier(raw["kind"], f"{path}.kind"),
    )


def _parse_dormant_resource(value: Any, path: str) -> DormantResource:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"path", "reason"},
        required={"path", "reason"},
    )
    return DormantResource(
        path=_repository_path(raw["path"], f"{path}.path"),
        reason=_nonblank_string(raw["reason"], f"{path}.reason"),
    )


def _parse_deferred_source_scope(value: Any, path: str) -> DeferredSourceScope:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"id", "reason", "source_spans", "resources"},
        required={"id", "reason", "source_spans", "resources"},
    )
    source_spans = _list(raw["source_spans"], f"{path}.source_spans")
    if not source_spans:
        raise CatalogError(
            f"{path}.source_spans: must contain at least one exact source span"
        )
    resources = _list(raw["resources"], f"{path}.resources")
    return DeferredSourceScope(
        id=_identifier(raw["id"], f"{path}.id"),
        reason=_nonblank_string(raw["reason"], f"{path}.reason"),
        source_spans=tuple(
            _parse_source_span(item, f"{path}.source_spans[{index}]")
            for index, item in enumerate(source_spans)
        ),
        resources=tuple(
            _parse_resource(item, f"{path}.resources[{index}]")
            for index, item in enumerate(resources)
        ),
    )


def _parse_binary_edge_resolution(value: Any, path: str) -> BinaryEdgeResolution:
    raw = _mapping(value, path)
    fields = {
        "source",
        "offset",
        "field",
        "opcode",
        "target",
        "expected_types",
        "shadowed_candidates",
        "classification",
        "reason",
    }
    _check_keys(raw, path=path, allowed=fields, required=fields)
    offset = _integer(raw["offset"], f"{path}.offset")
    if offset < 0:
        raise CatalogError(f"{path}.offset: expected a non-negative integer")
    opcode_raw = raw["opcode"]
    if opcode_raw is None:
        opcode = None
    else:
        opcode = _integer(opcode_raw, f"{path}.opcode")
        if opcode < 0:
            raise CatalogError(f"{path}.opcode: expected a non-negative integer or null")

    expected_raw = _list(raw["expected_types"], f"{path}.expected_types")
    if not expected_raw:
        raise CatalogError(f"{path}.expected_types: must contain at least one type")
    expected_types: list[str] = []
    expected_seen: dict[str, int] = {}
    for index, item in enumerate(expected_raw):
        item_path = f"{path}.expected_types[{index}]"
        resource_type = _string(item, item_path)
        if _RESOURCE_TYPE_PATTERN.fullmatch(resource_type) is None:
            raise CatalogError(
                f"{item_path}: expected an uppercase resource type such as SPL"
            )
        normalized = _normalize(resource_type)
        if normalized in expected_seen:
            raise CatalogError(
                f"{item_path}: duplicate resource type {resource_type!r}; first "
                f"declared at {path}.expected_types[{expected_seen[normalized]}]"
            )
        expected_seen[normalized] = index
        expected_types.append(resource_type)

    candidates_raw = _list(
        raw["shadowed_candidates"], f"{path}.shadowed_candidates"
    )
    if not candidates_raw:
        raise CatalogError(
            f"{path}.shadowed_candidates: must contain at least one repository path"
        )
    shadowed_candidates: list[str] = []
    candidate_seen: dict[str, int] = {}
    for index, item in enumerate(candidates_raw):
        item_path = f"{path}.shadowed_candidates[{index}]"
        candidate = _repository_path(item, item_path)
        normalized = _normalize(candidate)
        if normalized in candidate_seen:
            raise CatalogError(
                f"{item_path}: duplicate shadowed candidate {candidate!r}; first "
                f"declared at {path}.shadowed_candidates[{candidate_seen[normalized]}]"
            )
        candidate_seen[normalized] = index
        shadowed_candidates.append(candidate)

    classification = _identifier(raw["classification"], f"{path}.classification")
    if classification != "external":
        raise CatalogError(f"{path}.classification: expected 'external'")
    target = _nonblank_string(raw["target"], f"{path}.target")
    if target != target.strip():
        raise CatalogError(f"{path}.target: must not have leading or trailing whitespace")
    return BinaryEdgeResolution(
        source=_repository_path(raw["source"], f"{path}.source"),
        offset=offset,
        field=_nonblank_string(raw["field"], f"{path}.field"),
        opcode=opcode,
        target=target,
        expected_types=tuple(expected_types),
        shadowed_candidates=tuple(shadowed_candidates),
        classification=classification,
        reason=_nonblank_string(raw["reason"], f"{path}.reason"),
    )


def _parse_include_resolution(value: Any, path: str) -> IncludeResolution:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"source", "operand", "targets"},
        required={"source", "operand", "targets"},
    )
    operand = _string(raw["operand"], f"{path}.operand")
    if "%" not in operand:
        raise CatalogError(f"{path}.operand: expected a dynamic INCLUDE operand")
    targets_raw = _list(raw["targets"], f"{path}.targets")
    if not targets_raw:
        raise CatalogError(f"{path}.targets: must contain at least one target")
    targets: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(targets_raw):
        target_path = f"{path}.targets[{index}]"
        target = _repository_path(value, target_path)
        if "%" in target:
            raise CatalogError(f"{target_path}: target must be concrete")
        normalized = _normalize(target)
        if normalized in seen:
            raise CatalogError(
                f"{target_path}: duplicate target {target!r}; first declared at "
                f"{path}.targets[{seen[normalized]}]"
            )
        seen[normalized] = index
        targets.append(target)
    return IncludeResolution(
        source=_repository_path(raw["source"], f"{path}.source"),
        operand=operand,
        targets=tuple(targets),
    )


def _parse_source_resolution(value: Any, path: str) -> SourceResolution:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={
            "source",
            "line",
            "command",
            "operand_index",
            "operand",
            "reason",
            "targets",
            "generated_owners",
            "external",
            "access",
            "internal_generated_owners",
        },
        required={
            "source",
            "line",
            "command",
            "operand_index",
            "operand",
            "reason",
        },
    )
    line = _integer(raw["line"], f"{path}.line")
    if line < 1:
        raise CatalogError(f"{path}.line: expected a positive line number")
    operand_index = _integer(raw["operand_index"], f"{path}.operand_index")
    if operand_index < 0:
        raise CatalogError(
            f"{path}.operand_index: expected a non-negative integer"
        )
    operand = _string(raw["operand"], f"{path}.operand")
    if "%" not in operand:
        raise CatalogError(f"{path}.operand: expected a dynamic source operand")
    reason = _string(raw["reason"], f"{path}.reason")
    if not reason.strip():
        raise CatalogError(f"{path}.reason: must not be blank")
    targets_raw = _list(raw.get("targets", []), f"{path}.targets")
    targets: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(targets_raw):
        target_path = f"{path}.targets[{index}]"
        target = _repository_path(value, target_path)
        if "%" in target:
            raise CatalogError(f"{target_path}: target must be concrete")
        normalized = _normalize(target)
        if normalized in seen:
            raise CatalogError(
                f"{target_path}: duplicate target {target!r}; first declared at "
                f"{path}.targets[{seen[normalized]}]"
            )
        seen[normalized] = index
        targets.append(target)
    generated_owners = _identifier_tuple(
        raw.get("generated_owners", []), f"{path}.generated_owners"
    )
    generated_seen: dict[str, int] = {}
    for index, owner in enumerate(generated_owners):
        normalized = _normalize(owner)
        if normalized in generated_seen:
            raise CatalogError(
                f"{path}.generated_owners[{index}]: duplicate owner {owner!r}; "
                f"first declared at {path}.generated_owners"
                f"[{generated_seen[normalized]}]"
            )
        generated_seen[normalized] = index
    internal_generated_owners = _identifier_tuple(
        raw.get("internal_generated_owners", []),
        f"{path}.internal_generated_owners",
    )
    internal_generated_seen: dict[str, int] = {}
    for index, owner in enumerate(internal_generated_owners):
        normalized = _normalize(owner)
        if normalized in internal_generated_seen:
            raise CatalogError(
                f"{path}.internal_generated_owners[{index}]: duplicate owner "
                f"{owner!r}; first declared at {path}.internal_generated_owners"
                f"[{internal_generated_seen[normalized]}]"
            )
        internal_generated_seen[normalized] = index
    external = raw.get("external", False)
    if type(external) is not bool:
        raise CatalogError(f"{path}.external: expected a boolean")
    if "external" in raw and not external:
        raise CatalogError(f"{path}.external: external resolution must be true")
    if sum((bool(targets), bool(generated_owners), external)) != 1:
        raise CatalogError(
            f"{path}: expected exactly one of targets, generated_owners, or external"
        )
    access = _string(raw.get("access", "dependency"), f"{path}.access")
    if access not in {"dependency", "read_only"}:
        raise CatalogError(
            f"{path}.access: expected 'dependency' or 'read_only'"
        )
    if access == "read_only" and not targets:
        raise CatalogError(
            f"{path}.access: read_only access requires concrete targets mode"
        )
    if internal_generated_owners and not external:
        raise CatalogError(
            f"{path}.internal_generated_owners: supplemental generated owners "
            "are allowed only with external mode"
        )
    command = _identifier(raw["command"], f"{path}.command")
    if _SETTING_PATTERN.fullmatch(command) is None:
        raise CatalogError(
            f"{path}.command: expected a WeiDU command identifier"
        )
    return SourceResolution(
        source=_repository_path(raw["source"], f"{path}.source"),
        line=line,
        command=command.upper(),
        operand_index=operand_index,
        operand=operand,
        reason=reason,
        targets=tuple(targets),
        generated_owners=generated_owners,
        external=external,
        access=access,
        internal_generated_owners=internal_generated_owners,
    )


def _parse_name_fallback(value: Any, path: str) -> NameFallback:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"kind", "resource"},
        required={"kind", "resource"},
    )
    kind = _identifier(raw["kind"], f"{path}.kind")
    if kind not in NAME_FALLBACK_KINDS:
        expected = ", ".join(sorted(NAME_FALLBACK_KINDS))
        raise CatalogError(f"{path}.kind: expected one of {expected}")
    return NameFallback(
        kind=kind,
        resource=_resref(raw["resource"], f"{path}.resource"),
    )


def _parse_optional_name_fallback(value: Any, path: str) -> NameFallback | None:
    if value is None:
        return None
    return _parse_name_fallback(value, path)


def _parse_member_reference(value: Any, path: str) -> MemberReference:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={
            "source_spell",
            "level",
            "role",
            "name_ref",
            "name_fallback",
            "description_ref",
        },
        required={
            "source_spell",
            "level",
            "role",
            "name_ref",
            "name_fallback",
            "description_ref",
        },
    )
    level = _integer(raw["level"], f"{path}.level")
    if not 1 <= level <= 10:
        raise CatalogError(f"{path}.level: expected an integer from 1 through 10")
    role = _identifier(raw["role"], f"{path}.role")
    if role not in MEMBER_REFERENCE_ROLES:
        expected = ", ".join(sorted(MEMBER_REFERENCE_ROLES))
        raise CatalogError(f"{path}.role: expected one of {expected}")
    name_ref = _optional_tra_reference(raw["name_ref"], f"{path}.name_ref")
    name_fallback = _parse_optional_name_fallback(
        raw["name_fallback"], f"{path}.name_fallback"
    )
    if name_ref is None and name_fallback is None:
        raise CatalogError(
            f"{path}.name_ref: expected exactly one of name_ref or name_fallback"
        )
    if name_ref is not None and name_fallback is not None:
        raise CatalogError(
            f"{path}.name_fallback: expected exactly one of name_ref or name_fallback"
        )
    return MemberReference(
        source_spell=_resref(raw["source_spell"], f"{path}.source_spell"),
        level=level,
        role=role,
        name_ref=name_ref,
        name_fallback=name_fallback,
        description_ref=_tra_reference(
            raw["description_ref"], f"{path}.description_ref"
        ),
    )


def _validate_documentation_mode(change: Change, path: str) -> None:
    member_count = len(change.member_refs)
    if member_count == 0:
        if change.name_ref is None and change.name_fallback is None:
            raise CatalogError(
                f"{path}.name_ref: singleton documentation requires exactly one "
                "of name_ref or name_fallback"
            )
        if change.name_ref is not None and change.name_fallback is not None:
            raise CatalogError(
                f"{path}.name_fallback: singleton documentation requires exactly "
                "one of name_ref or name_fallback"
            )
        if change.description_ref is None:
            raise CatalogError(
                f"{path}.description_ref: singleton documentation requires a "
                "description_ref"
            )
        return
    if member_count == 1:
        raise CatalogError(
            f"{path}.member_refs: composite documentation requires at least two members"
        )
    if change.name_ref is not None:
        raise CatalogError(
            f"{path}.name_ref: composite documentation requires null top-level text refs"
        )
    if change.name_fallback is not None:
        raise CatalogError(
            f"{path}.name_fallback: composite documentation requires null top-level "
            "text refs"
        )
    if change.description_ref is not None:
        raise CatalogError(
            f"{path}.description_ref: composite documentation requires null top-level "
            "text refs"
        )


def _parse_change(value: Any, path: str) -> Change:
    raw = _mapping(value, path)
    allowed = {
        "id",
        "setting",
        "display_name",
        "default",
        "group",
        "component",
        "games",
        "name_ref",
        "name_fallback",
        "description_ref",
        "member_refs",
        "source_spans",
        "resources",
        "atomic_group",
        "requires",
        "conflicts",
        "soft_requires",
        "processors",
        "documentation_only_reason",
    }
    _check_keys(
        raw,
        path=path,
        allowed=allowed,
        required={
            "id",
            "setting",
            "display_name",
            "default",
            "group",
            "name_fallback",
            "member_refs",
        },
    )

    component = _integer(raw.get("component", 0), f"{path}.component")
    if component < 0:
        raise CatalogError(f"{path}.component: expected a non-negative integer")

    source_spans_raw = _list(raw.get("source_spans", []), f"{path}.source_spans")
    resources_raw = _list(raw.get("resources", []), f"{path}.resources")
    member_refs_raw = _list(raw["member_refs"], f"{path}.member_refs")
    member_refs = tuple(
        _parse_member_reference(item, f"{path}.member_refs[{index}]")
        for index, item in enumerate(member_refs_raw)
    )
    seen_source_spells: dict[str, int] = {}
    for index, member in enumerate(member_refs):
        normalized = member.source_spell.casefold()
        previous = seen_source_spells.get(normalized)
        if previous is not None:
            raise CatalogError(
                f"{path}.member_refs[{index}].source_spell: duplicate source spell "
                f"{member.source_spell!r}; first declared at "
                f"{path}.member_refs[{previous}].source_spell"
            )
        seen_source_spells[normalized] = index
    change = Change(
        id=_identifier(raw["id"], f"{path}.id"),
        setting=_setting(raw["setting"], f"{path}.setting"),
        display_name=_string(raw["display_name"], f"{path}.display_name"),
        default=_tri_state(raw["default"], f"{path}.default"),
        group=_identifier(raw["group"], f"{path}.group"),
        component=component,
        games=_games(raw.get("games", []), f"{path}.games"),
        name_ref=_optional_tra_reference(raw.get("name_ref"), f"{path}.name_ref"),
        name_fallback=_parse_optional_name_fallback(
            raw["name_fallback"], f"{path}.name_fallback"
        ),
        description_ref=_optional_tra_reference(
            raw.get("description_ref"), f"{path}.description_ref"
        ),
        member_refs=member_refs,
        source_spans=tuple(
            _parse_source_span(item, f"{path}.source_spans[{index}]")
            for index, item in enumerate(source_spans_raw)
        ),
        resources=tuple(
            _parse_resource(item, f"{path}.resources[{index}]")
            for index, item in enumerate(resources_raw)
        ),
        atomic_group=_optional_identifier(
            raw.get("atomic_group"), f"{path}.atomic_group"
        ),
        requires=_identifier_tuple(raw.get("requires", []), f"{path}.requires"),
        conflicts=_identifier_tuple(
            raw.get("conflicts", []), f"{path}.conflicts"
        ),
        soft_requires=_identifier_tuple(
            raw.get("soft_requires", []), f"{path}.soft_requires"
        ),
        processors=_identifier_tuple(
            raw.get("processors", []), f"{path}.processors"
        ),
        documentation_only_reason=_optional_string(
            raw.get("documentation_only_reason"),
            f"{path}.documentation_only_reason",
        ),
    )
    _validate_documentation_mode(change, path)
    return change


def _parse_infrastructure(value: Any, path: str) -> Infrastructure:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={
            "id",
            "activation",
            "infrastructure_requires",
            "source_spans",
            "resources",
            "consumers",
            "category",
            "include_resolutions",
            "source_resolutions",
        },
        required={"id", "activation", "infrastructure_requires"},
    )
    source_spans_raw = _list(raw.get("source_spans", []), f"{path}.source_spans")
    resources_raw = _list(raw.get("resources", []), f"{path}.resources")
    include_resolutions_raw = _list(
        raw.get("include_resolutions", []), f"{path}.include_resolutions"
    )
    source_resolutions_raw = _list(
        raw.get("source_resolutions", []), f"{path}.source_resolutions"
    )
    return Infrastructure(
        id=_identifier(raw["id"], f"{path}.id"),
        activation=_infrastructure_activation(
            raw["activation"], f"{path}.activation"
        ),
        infrastructure_requires=_identifier_tuple(
            raw["infrastructure_requires"], f"{path}.infrastructure_requires"
        ),
        source_spans=tuple(
            _parse_source_span(item, f"{path}.source_spans[{index}]")
            for index, item in enumerate(source_spans_raw)
        ),
        resources=tuple(
            _parse_resource(item, f"{path}.resources[{index}]")
            for index, item in enumerate(resources_raw)
        ),
        consumers=_identifier_tuple(
            raw.get("consumers", []), f"{path}.consumers"
        ),
        category=_infrastructure_category(
            raw.get("category", "derived"), f"{path}.category"
        ),
        include_resolutions=tuple(
            _parse_include_resolution(
                item, f"{path}.include_resolutions[{index}]"
            )
            for index, item in enumerate(include_resolutions_raw)
        ),
        source_resolutions=tuple(
            _parse_source_resolution(
                item, f"{path}.source_resolutions[{index}]"
            )
            for index, item in enumerate(source_resolutions_raw)
        ),
    )


def _infrastructure_category(value: Any, path: str) -> str:
    category = _identifier(value, path)
    if category not in INFRASTRUCTURE_CATEGORIES:
        expected = ", ".join(sorted(INFRASTRUCTURE_CATEGORIES))
        raise CatalogError(f"{path}: expected one of {expected}")
    return category


def _infrastructure_activation(value: Any, path: str) -> str:
    activation = _identifier(value, path)
    if activation not in INFRASTRUCTURE_ACTIVATIONS:
        expected = ", ".join(sorted(INFRASTRUCTURE_ACTIVATIONS))
        raise CatalogError(f"{path}: expected one of {expected}")
    return activation


def _validate_catalog(catalog: Catalog) -> None:
    group_ids: dict[str, tuple[str, int]] = {}
    change_ids: dict[str, tuple[str, int]] = {}
    infrastructure_ids: dict[str, tuple[str, int]] = {}
    all_ids: dict[str, tuple[str, int, str]] = {}
    settings: dict[str, tuple[str, int, str]] = {}
    reserved_settings = {
        value.casefold(): value for value in CONFIG_METADATA_SETTINGS
    }
    include_resolutions: dict[tuple[str, str], tuple[int, int]] = {}
    source_resolutions: dict[
        tuple[str, int, str, int, str], tuple[int, int]
    ] = {}

    for index, record in enumerate(catalog.groups):
        normalized_id = _normalize(record.id)
        _record_unique_id(
            normalized_id,
            record.id,
            index,
            "groups",
            all_ids,
        )
        group_ids[normalized_id] = (record.id, index)
        _validate_setting_not_reserved(
            record.setting,
            path=f"groups[{index}].setting",
            reserved=reserved_settings,
        )
        _record_unique_setting(record.setting, index, "groups", settings)

    for index, record in enumerate(catalog.changes):
        normalized_id = _normalize(record.id)
        _record_unique_id(
            normalized_id,
            record.id,
            index,
            "changes",
            all_ids,
        )
        change_ids[normalized_id] = (record.id, index)
        _validate_setting_not_reserved(
            record.setting,
            path=f"changes[{index}].setting",
            reserved=reserved_settings,
        )
        _record_unique_setting(record.setting, index, "changes", settings)

    for index, record in enumerate(catalog.infrastructure):
        normalized_id = _normalize(record.id)
        _record_unique_id(
            normalized_id,
            record.id,
            index,
            "infrastructure",
            all_ids,
        )
        infrastructure_ids[normalized_id] = (record.id, index)
        for resolution_index, resolution in enumerate(record.include_resolutions):
            key = (
                _normalize(resolution.source),
                _normalize(resolution.operand.replace("\\", "/")),
            )
            previous = include_resolutions.get(key)
            if previous is not None:
                previous_infrastructure, previous_resolution = previous
                raise CatalogError(
                    f"infrastructure[{index}].include_resolutions[{resolution_index}]: "
                    "duplicate dynamic INCLUDE resolution; first declared at "
                    f"infrastructure[{previous_infrastructure}].include_resolutions"
                    f"[{previous_resolution}]"
                )
            include_resolutions[key] = (index, resolution_index)
        for resolution_index, resolution in enumerate(record.source_resolutions):
            key = (
                _normalize(resolution.source),
                resolution.line,
                _normalize(resolution.command),
                resolution.operand_index,
                _normalize(resolution.operand.replace("\\", "/")),
            )
            previous = source_resolutions.get(key)
            if previous is not None:
                previous_infrastructure, previous_resolution = previous
                raise CatalogError(
                    f"infrastructure[{index}].source_resolutions[{resolution_index}]: "
                    "duplicate dynamic source resolution; first declared at "
                    f"infrastructure[{previous_infrastructure}].source_resolutions"
                    f"[{previous_resolution}]"
                )
            source_resolutions[key] = (index, resolution_index)

    for index, record in enumerate(catalog.deferred_source_scopes):
        normalized_id = _normalize(record.id)
        _record_unique_id(
            normalized_id,
            record.id,
            index,
            "deferred_source_scopes",
            all_ids,
        )

    dormant_paths: dict[str, int] = {}
    for index, record in enumerate(catalog.dormant_resources):
        normalized_path = _normalize(record.path)
        previous = dormant_paths.get(normalized_path)
        if previous is not None:
            raise CatalogError(
                f"dormant_resources[{index}].path: duplicate dormant resource "
                f"{record.path!r}; first declared at dormant_resources[{previous}].path"
            )
        dormant_paths[normalized_path] = index

    binary_keys: dict[tuple[str, int, str], int] = {}
    for index, record in enumerate(catalog.binary_edge_resolutions):
        key = (
            _normalize(record.source),
            record.offset,
            _normalize(record.field),
        )
        previous = binary_keys.get(key)
        if previous is not None:
            raise CatalogError(
                f"binary_edge_resolutions[{index}]: duplicate binary edge "
                "resolution; first declared at "
                f"binary_edge_resolutions[{previous}]"
            )
        binary_keys[key] = index

    if catalog.migration.complete and catalog.deferred_source_scopes:
        raise CatalogError(
            "migration.complete: cannot be true while deferred source scopes remain"
        )

    for index, record in enumerate(catalog.groups):
        if record.parent is not None and _normalize(record.parent) not in group_ids:
            raise CatalogError(
                f"groups[{index}].parent: unknown group ID {record.parent!r}"
            )

    _validate_group_cycles(catalog.groups, group_ids)
    _validate_root_group(catalog.groups)

    for index, record in enumerate(catalog.changes):
        if record.default != -1:
            raise CatalogError(
                f"changes[{index}].default: public change default must be -1 "
                "so it inherits from its group"
            )
        if _normalize(record.group) not in group_ids:
            raise CatalogError(
                f"changes[{index}].group: unknown group ID {record.group!r}"
            )
        for field_name in ("requires", "conflicts", "soft_requires"):
            values = getattr(record, field_name)
            _validate_change_references(
                values,
                path=f"changes[{index}].{field_name}",
                change_ids=change_ids,
            )
        _validate_change_relation_sets(record, index)
        _validate_known_references(
            record.processors,
            path=f"changes[{index}].processors",
            known=infrastructure_ids,
            description="infrastructure ID",
        )

    catalog_owner_ids = {**change_ids, **infrastructure_ids}
    for index, record in enumerate(catalog.infrastructure):
        if (record.activation == "always") != (
            record.category == "mandatory_metadata"
        ):
            raise CatalogError(
                f"infrastructure[{index}].activation: 'always' is required exactly "
                "when category is 'mandatory_metadata'"
            )
        _validate_known_references(
            record.consumers,
            path=f"infrastructure[{index}].consumers",
            known=change_ids,
            description="change ID",
        )
        _validate_known_references(
            record.infrastructure_requires,
            path=f"infrastructure[{index}].infrastructure_requires",
            known=infrastructure_ids,
            description="infrastructure ID",
        )
        normalized_id = _normalize(record.id)
        for requirement_index, requirement in enumerate(
            record.infrastructure_requires
        ):
            if _normalize(requirement) == normalized_id:
                raise CatalogError(
                    f"infrastructure[{index}].infrastructure_requires"
                    f"[{requirement_index}]: infrastructure dependency cannot "
                    "reference itself"
                )
        for resolution_index, resolution in enumerate(record.source_resolutions):
            _validate_known_references(
                resolution.generated_owners,
                path=(
                    f"infrastructure[{index}].source_resolutions"
                    f"[{resolution_index}].generated_owners"
                ),
                known=catalog_owner_ids,
                description="catalog owner ID",
            )
            _validate_known_references(
                resolution.internal_generated_owners,
                path=(
                    f"infrastructure[{index}].source_resolutions"
                    f"[{resolution_index}].internal_generated_owners"
                ),
                known=catalog_owner_ids,
                description="catalog owner ID",
            )

    _validate_processor_consumers(catalog, infrastructure_ids)
    _validate_dependency_cycles(catalog.changes, change_ids)
    _validate_infrastructure_dependency_cycles(
        catalog.infrastructure, infrastructure_ids
    )


def _validate_root_group(groups: tuple[Group, ...]) -> None:
    root_indices = [index for index, record in enumerate(groups) if record.parent is None]
    if not root_indices:
        raise CatalogError("groups: expected exactly one parentless root group, found 0")
    if len(root_indices) > 1:
        second_root = root_indices[1]
        raise CatalogError(
            f"groups[{second_root}].parent: expected exactly one parentless root "
            f"group, found {len(root_indices)}"
        )
    root_index = root_indices[0]
    if groups[root_index].default == -1:
        raise CatalogError(
            f"groups[{root_index}].default: root group default must be 0 or 1"
        )


def _record_unique_id(
    normalized: str,
    original: str,
    index: int,
    collection: str,
    seen: dict[str, tuple[str, int, str]],
) -> None:
    previous = seen.get(normalized)
    if previous is not None:
        previous_id, previous_index, previous_collection = previous
        raise CatalogError(
            f"{collection}[{index}].id: duplicate ID {original!r}; first declared "
            f"as {previous_id!r} at {previous_collection}[{previous_index}].id"
        )
    seen[normalized] = (original, index, collection)


def _record_unique_setting(
    setting: str,
    index: int,
    collection: str,
    seen: dict[str, tuple[str, int, str]],
) -> None:
    normalized = _normalize(setting)
    previous = seen.get(normalized)
    if previous is not None:
        previous_setting, previous_index, previous_collection = previous
        raise CatalogError(
            f"{collection}[{index}].setting: duplicate setting {setting!r}; first "
            f"declared as {previous_setting!r} at "
            f"{previous_collection}[{previous_index}].setting"
        )
    seen[normalized] = (setting, index, collection)


def _validate_setting_not_reserved(
    setting: str, *, path: str, reserved: Mapping[str, str]
) -> None:
    normalized = _normalize(setting)
    generated_name = reserved.get(normalized)
    if generated_name is not None:
        raise CatalogError(
            f"{path}: setting {setting!r} collides with reserved generated "
            f"setting {generated_name!r}"
        )
    if normalized.startswith("sr_feature_"):
        raise CatalogError(
            f"{path}: setting {setting!r} collides with reserved generated "
            "setting namespace 'sr_feature_*'"
        )


def _validate_group_cycles(
    groups: tuple[Group, ...], group_ids: Mapping[str, tuple[str, int]]
) -> None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(normalized_id: str) -> None:
        state[normalized_id] = 1
        stack.append(normalized_id)
        _, index = group_ids[normalized_id]
        parent = groups[index].parent
        if parent is not None:
            normalized_parent = _normalize(parent)
            parent_state = state.get(normalized_parent, 0)
            if parent_state == 0:
                visit(normalized_parent)
            elif parent_state == 1:
                cycle_start = stack.index(normalized_parent)
                cycle_ids = [
                    groups[group_ids[item][1]].id for item in stack[cycle_start:]
                ]
                cycle_ids.append(groups[group_ids[normalized_parent][1]].id)
                raise CatalogError(
                    f"groups[{index}].parent: group cycle: {' -> '.join(cycle_ids)}"
                )
        stack.pop()
        state[normalized_id] = 2

    for record in groups:
        normalized_id = _normalize(record.id)
        if state.get(normalized_id, 0) == 0:
            visit(normalized_id)


def _validate_change_references(
    values: tuple[str, ...],
    *,
    path: str,
    change_ids: Mapping[str, tuple[str, int]],
) -> None:
    _validate_known_references(
        values,
        path=path,
        known=change_ids,
        description="change ID",
    )


def _validate_change_relation_sets(record: Change, change_index: int) -> None:
    normalized_id = _normalize(record.id)
    seen: dict[str, tuple[str, int]] = {}
    for field_name in ("requires", "conflicts", "soft_requires"):
        for relation_index, value in enumerate(getattr(record, field_name)):
            path = f"changes[{change_index}].{field_name}[{relation_index}]"
            normalized_value = _normalize(value)
            if normalized_value == normalized_id:
                raise CatalogError(f"{path}: change relation cannot reference itself")
            previous = seen.get(normalized_value)
            if previous is not None:
                previous_field, previous_index = previous
                raise CatalogError(
                    f"{path}: relation is already declared in "
                    f"changes[{change_index}].{previous_field}[{previous_index}]"
                )
            seen[normalized_value] = (field_name, relation_index)


def _validate_known_references(
    values: tuple[str, ...],
    *,
    path: str,
    known: Mapping[str, tuple[str, int]],
    description: str,
) -> None:
    seen: dict[str, int] = {}
    for index, value in enumerate(values):
        normalized = _normalize(value)
        if normalized not in known:
            raise CatalogError(f"{path}[{index}]: unknown {description} {value!r}")
        previous_index = seen.get(normalized)
        if previous_index is not None:
            raise CatalogError(
                f"{path}[{index}]: duplicate {description} {value!r}; first declared "
                f"at {path}[{previous_index}]"
            )
        seen[normalized] = index


def _validate_processor_consumers(
    catalog: Catalog,
    infrastructure_ids: Mapping[str, tuple[str, int]],
) -> None:
    for change_index, record in enumerate(catalog.changes):
        normalized_change = _normalize(record.id)
        for processor_index, processor in enumerate(record.processors):
            _, infrastructure_index = infrastructure_ids[_normalize(processor)]
            consumers = catalog.infrastructure[infrastructure_index].consumers
            if not any(_normalize(value) == normalized_change for value in consumers):
                raise CatalogError(
                    f"changes[{change_index}].processors[{processor_index}]: "
                    f"processor edge is not reciprocated by "
                    f"infrastructure[{infrastructure_index}].consumers"
                )
    change_ids = {
        _normalize(record.id): index for index, record in enumerate(catalog.changes)
    }
    for infrastructure_index, record in enumerate(catalog.infrastructure):
        for consumer_index, consumer in enumerate(record.consumers):
            change_index = change_ids[_normalize(consumer)]
            processors = catalog.changes[change_index].processors
            if not any(
                _normalize(value) == _normalize(record.id) for value in processors
            ):
                raise CatalogError(
                    f"infrastructure[{infrastructure_index}].consumers"
                    f"[{consumer_index}]: consumer edge is not reciprocated by "
                    f"changes[{change_index}].processors"
                )


def _validate_dependency_cycles(
    changes: tuple[Change, ...], change_ids: Mapping[str, tuple[str, int]]
) -> None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(normalized_id: str) -> None:
        state[normalized_id] = 1
        stack.append(normalized_id)
        _, change_index = change_ids[normalized_id]
        for requirement_index, requirement in enumerate(
            changes[change_index].requires
        ):
            normalized_requirement = _normalize(requirement)
            requirement_state = state.get(normalized_requirement, 0)
            if requirement_state == 0:
                visit(normalized_requirement)
            elif requirement_state == 1:
                cycle_start = stack.index(normalized_requirement)
                cycle_ids = [
                    changes[change_ids[item][1]].id for item in stack[cycle_start:]
                ]
                cycle_ids.append(changes[change_ids[normalized_requirement][1]].id)
                raise CatalogError(
                    f"changes[{change_index}].requires[{requirement_index}]: "
                    f"dependency cycle: {' -> '.join(cycle_ids)}"
                )
        stack.pop()
        state[normalized_id] = 2

    for record in changes:
        normalized_id = _normalize(record.id)
        if state.get(normalized_id, 0) == 0:
            visit(normalized_id)


def _validate_infrastructure_dependency_cycles(
    infrastructure: tuple[Infrastructure, ...],
    infrastructure_ids: Mapping[str, tuple[str, int]],
) -> None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(normalized_id: str) -> None:
        state[normalized_id] = 1
        stack.append(normalized_id)
        _, infrastructure_index = infrastructure_ids[normalized_id]
        for requirement_index, requirement in enumerate(
            infrastructure[infrastructure_index].infrastructure_requires
        ):
            normalized_requirement = _normalize(requirement)
            requirement_state = state.get(normalized_requirement, 0)
            if requirement_state == 0:
                visit(normalized_requirement)
            elif requirement_state == 1:
                cycle_start = stack.index(normalized_requirement)
                cycle_ids = [
                    infrastructure[infrastructure_ids[item][1]].id
                    for item in stack[cycle_start:]
                ]
                cycle_ids.append(
                    infrastructure[infrastructure_ids[normalized_requirement][1]].id
                )
                raise CatalogError(
                    f"infrastructure[{infrastructure_index}]."
                    f"infrastructure_requires[{requirement_index}]: "
                    "infrastructure dependency cycle: "
                    f"{' -> '.join(cycle_ids)}"
                )
        stack.pop()
        state[normalized_id] = 2

    for record in infrastructure:
        normalized_id = _normalize(record.id)
        if state.get(normalized_id, 0) == 0:
            visit(normalized_id)


def _check_keys(
    raw: Mapping[str, Any],
    *,
    path: str,
    allowed: set[str],
    required: set[str],
) -> None:
    for key in raw:
        if not isinstance(key, str):
            raise CatalogError(f"{path}: mapping keys must be strings")
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise CatalogError(f"{path}.{unknown[0]}: unknown field")
    missing = sorted(required - set(raw))
    if missing:
        raise CatalogError(f"{path}.{missing[0]}: missing required field")


def _materialize_json(value: Any, path: str) -> Any:
    if isinstance(value, _JSONObject):
        result: dict[str, Any] = {}
        for key, item in value:
            child_path = key if path == "catalog" else f"{path}.{key}"
            if key in result:
                raise CatalogError(f"{child_path}: duplicate field")
            result[key] = _materialize_json(item, child_path)
        return result
    if isinstance(value, list):
        return [
            _materialize_json(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogError(f"{path}: expected an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise CatalogError(f"{path}: expected an array")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{path}: expected a string")
    if not value:
        raise CatalogError(f"{path}: must not be empty")
    return value


def _nonblank_string(value: Any, path: str) -> str:
    result = _string(value, path)
    if not result.strip():
        raise CatalogError(f"{path}: must not be blank")
    return result


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _optional_tra_reference(value: Any, path: str) -> str | None:
    reference = _optional_string(value, path)
    if reference is not None and _TRA_REFERENCE_PATTERN.fullmatch(reference) is None:
        raise CatalogError(f"{path}: expected a TRA reference such as @123")
    return reference


def _tra_reference(value: Any, path: str) -> str:
    reference = _optional_tra_reference(value, path)
    if reference is None:
        raise CatalogError(f"{path}: expected a TRA reference such as @123")
    return reference


def _resref(value: Any, path: str) -> str:
    resource = _string(value, path)
    if _RESREF_PATTERN.fullmatch(resource) is None:
        raise CatalogError(
            f"{path}: expected an uppercase Infinity Engine resref of 1 to 8 "
            "letters, digits, underscores, or # characters"
        )
    return resource


def _identifier(value: Any, path: str) -> str:
    identifier = _string(value, path)
    if identifier != identifier.strip():
        raise CatalogError(f"{path}: must not have leading or trailing whitespace")
    return identifier


def _optional_identifier(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, path)


def _setting(value: Any, path: str) -> str:
    setting = _identifier(value, path)
    if _SETTING_PATTERN.fullmatch(setting) is None:
        raise CatalogError(
            f"{path}: expected a WeiDU setting name containing only letters, "
            "digits, and underscores"
        )
    if not setting.casefold().startswith("sr_"):
        raise CatalogError(f"{path}: catalog settings must use the sr_ namespace")
    return setting


def _repository_path(value: Any, path: str) -> str:
    repository_path = _string(value, path)
    segments = repository_path.split("/")
    if (
        "\\" in repository_path
        or repository_path.startswith("/")
        or any(segment in {"", ".", ".."} for segment in segments)
        or any(_windows_invalid_path_segment(segment) for segment in segments)
    ):
        raise CatalogError(f"{path}: expected a portable repository-relative path")
    return repository_path


def _windows_invalid_path_segment(segment: str) -> bool:
    stem = segment.split(".", 1)[0].upper()
    return (
        any(
            ord(character) < 32
            or character in _WINDOWS_FORBIDDEN_PATH_CHARACTERS
            for character in segment
        )
        or segment.endswith((" ", "."))
        or stem in _WINDOWS_RESERVED_PATH_NAMES
    )


def _integer(value: Any, path: str) -> int:
    if type(value) is not int:
        raise CatalogError(f"{path}: expected an integer")
    return value


def _tri_state(value: Any, path: str) -> int:
    default = _integer(value, path)
    if default not in _TRI_STATE_VALUES:
        raise CatalogError(f"{path}: expected one of -1, 0, or 1")
    return default


def _string_tuple(value: Any, path: str) -> tuple[str, ...]:
    values = _list(value, path)
    return tuple(_string(item, f"{path}[{index}]") for index, item in enumerate(values))


def _games(value: Any, path: str) -> tuple[str, ...]:
    games = _string_tuple(value, path)
    if not games:
        raise CatalogError(f"{path}: must contain at least one game or 'all'")
    seen: dict[str, int] = {}
    for index, game in enumerate(games):
        normalized = _normalize(game)
        if normalized != "all" and normalized not in SUPPORTED_GAMES:
            raise CatalogError(f"{path}[{index}]: unsupported game {game!r}")
        if normalized in seen:
            raise CatalogError(
                f"{path}[{index}]: duplicate game {game!r}; first declared at "
                f"{path}[{seen[normalized]}]"
            )
        seen[normalized] = index
    if "all" in seen and len(games) != 1:
        raise CatalogError(f"{path}: 'all' cannot be combined with named games")
    return games


def _identifier_tuple(value: Any, path: str) -> tuple[str, ...]:
    values = _list(value, path)
    return tuple(
        _identifier(item, f"{path}[{index}]") for index, item in enumerate(values)
    )


def _normalize(value: str) -> str:
    return value.casefold()


def feature_symbol(index: int) -> str:
    """Return the stable internal WeiDU symbol for a one-based catalog index."""

    if type(index) is not int or index < 1:
        raise ValueError("feature symbol index must be a positive integer")
    return f"sr_feature_{index:06d}"
