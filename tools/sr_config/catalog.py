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
_HEX_DIGITS = frozenset(string.hexdigits)
_SETTING_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_TRA_REFERENCE_PATTERN = re.compile(r"@[0-9]+\Z")
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
    end: str
    sha256: str


@dataclass(frozen=True)
class ResourceOwnership:
    path: str
    kind: str


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
    description_ref: str | None = None
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
    source_spans: tuple[SourceSpan, ...] = field(default_factory=tuple)
    resources: tuple[ResourceOwnership, ...] = field(default_factory=tuple)
    consumers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Catalog:
    schema_version: int
    upstream: Upstream
    migration: Migration
    groups: tuple[Group, ...]
    changes: tuple[Change, ...]
    infrastructure: tuple[Infrastructure, ...]

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
            },
            required={
                "schema_version",
                "upstream",
                "migration",
                "groups",
                "changes",
                "infrastructure",
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

        catalog = cls(
            schema_version=schema_version,
            upstream=upstream,
            migration=migration,
            groups=groups,
            changes=changes,
            infrastructure=infrastructure,
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
        end=_string(raw["end"], f"{path}.end"),
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
        "description_ref",
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
        required={"id", "setting", "display_name", "default", "group"},
    )

    component = _integer(raw.get("component", 0), f"{path}.component")
    if component < 0:
        raise CatalogError(f"{path}.component: expected a non-negative integer")

    source_spans_raw = _list(raw.get("source_spans", []), f"{path}.source_spans")
    resources_raw = _list(raw.get("resources", []), f"{path}.resources")
    return Change(
        id=_identifier(raw["id"], f"{path}.id"),
        setting=_setting(raw["setting"], f"{path}.setting"),
        display_name=_string(raw["display_name"], f"{path}.display_name"),
        default=_tri_state(raw["default"], f"{path}.default"),
        group=_identifier(raw["group"], f"{path}.group"),
        component=component,
        games=_games(raw.get("games", []), f"{path}.games"),
        name_ref=_optional_tra_reference(raw.get("name_ref"), f"{path}.name_ref"),
        description_ref=_optional_tra_reference(
            raw.get("description_ref"), f"{path}.description_ref"
        ),
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


def _parse_infrastructure(value: Any, path: str) -> Infrastructure:
    raw = _mapping(value, path)
    _check_keys(
        raw,
        path=path,
        allowed={"id", "source_spans", "resources", "consumers"},
        required={"id"},
    )
    source_spans_raw = _list(raw.get("source_spans", []), f"{path}.source_spans")
    resources_raw = _list(raw.get("resources", []), f"{path}.resources")
    return Infrastructure(
        id=_identifier(raw["id"], f"{path}.id"),
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
    )


def _validate_catalog(catalog: Catalog) -> None:
    group_ids: dict[str, tuple[str, int]] = {}
    change_ids: dict[str, tuple[str, int]] = {}
    infrastructure_ids: dict[str, tuple[str, int]] = {}
    all_ids: dict[str, tuple[str, int, str]] = {}
    settings: dict[str, tuple[str, int, str]] = {}

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

    for index, record in enumerate(catalog.infrastructure):
        _validate_known_references(
            record.consumers,
            path=f"infrastructure[{index}].consumers",
            known=change_ids,
            description="change ID",
        )

    _validate_processor_consumers(catalog, infrastructure_ids)
    _validate_dependency_cycles(catalog.changes, change_ids)


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


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _optional_tra_reference(value: Any, path: str) -> str | None:
    reference = _optional_string(value, path)
    if reference is not None and _TRA_REFERENCE_PATTERN.fullmatch(reference) is None:
        raise CatalogError(f"{path}: expected a TRA reference such as @123")
    return reference


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
