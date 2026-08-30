"""Deterministic tri-state resolution for public Spell Revisions changes."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .catalog import Catalog, Change, SUPPORTED_GAMES, feature_symbol


_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9_]*)\s*=\s*(?P<value>-?[0-9]+)\Z"
)
_VALID_VALUES = frozenset({-1, 0, 1})


class ConfigError(ValueError):
    """One or more deterministic configuration errors."""

    def __init__(self, errors: str | Iterable[str]) -> None:
        if isinstance(errors, str):
            normalized = (errors,)
        else:
            normalized = tuple(errors)
        if not normalized:
            raise ValueError("ConfigError requires at least one error")
        self.errors = normalized
        super().__init__(
            "invalid Spell Revisions configuration:\n"
            + "\n".join(f"- {error}" for error in normalized)
        )


@dataclass(frozen=True)
class Assignment:
    name: str
    value: object
    line: int | None = None


@dataclass(frozen=True)
class Resolution:
    """Resolved choices in canonical catalog order."""

    catalog: Catalog
    selected_ids: tuple[str, ...]
    active_soft_edges: tuple[tuple[str, str], ...]
    game: str

    def enabled(self, change_id: str) -> bool:
        normalized = change_id.casefold()
        known = {record.id.casefold() for record in self.catalog.changes}
        if normalized not in known:
            raise KeyError(change_id)
        return any(value.casefold() == normalized for value in self.selected_ids)

    def soft_edge_active(self, source_id: str, target_id: str) -> bool:
        source = source_id.casefold()
        target = target_id.casefold()
        return any(
            left.casefold() == source and right.casefold() == target
            for left, right in self.active_soft_edges
        )


def parse_assignments(source: str) -> tuple[Assignment, ...]:
    """Parse simple ordered ``NAME = tri-state`` assignments.

    Metadata statements such as ``SPRINT`` deliberately are not accepted here;
    callers separate those from the catalog assignments before resolution.
    """

    assignments: list[Assignment] = []
    errors: list[str] = []
    for line_number, original in enumerate(source.splitlines(), start=1):
        content = original.split("//", 1)[0].strip()
        if not content:
            continue
        match = _ASSIGNMENT_PATTERN.fullmatch(content)
        if match is None:
            errors.append(f"line {line_number}: expected NAME = -1, 0, or 1")
            continue
        value = int(match.group("value"))
        if value not in _VALID_VALUES:
            errors.append(
                f"line {line_number}: {match.group('name')}: expected -1, 0, or 1"
            )
            continue
        assignments.append(Assignment(match.group("name"), value, line_number))
    if errors:
        raise ConfigError(errors)
    return tuple(assignments)


def feature_symbols(catalog: Catalog, game: str | None = None) -> dict[str, str]:
    """Return collision-free feature flags assigned by complete catalog order."""

    if game is not None:
        _validate_game(game)
    return {
        record.id: feature_symbol(index)
        for index, record in enumerate(catalog.changes, start=1)
    }


def resolve(
    catalog: Catalog,
    assignments: Mapping[str, object]
    | Iterable[Assignment]
    | Iterable[tuple[str, object]],
    *,
    game: str = "bg2ee",
) -> Resolution:
    """Resolve catalog settings for *game* or raise an aggregate ``ConfigError``."""

    normalized_game = _validate_game(game)
    ordered = _coerce_assignments(assignments)
    known_settings = {
        record.setting.casefold(): record.setting
        for record in (*catalog.groups, *catalog.changes)
    }
    values: dict[str, int] = {}
    originals: dict[str, Assignment] = {}
    errors: list[str] = []

    for assignment in ordered:
        normalized_name = assignment.name.casefold()
        location = _location(assignment)
        previous = originals.get(normalized_name)
        if previous is not None:
            previous_location = (
                f"line {previous.line}" if previous.line is not None else "an earlier entry"
            )
            errors.append(
                f"{location}duplicate setting {assignment.name!r}; first assigned "
                f"on {previous_location} as {previous.name!r}"
                if previous.line is not None
                else f"{location}duplicate setting {assignment.name!r}; first assigned "
                f"as {previous.name!r}"
            )
            continue
        originals[normalized_name] = assignment
        canonical = known_settings.get(normalized_name)
        if canonical is None:
            errors.append(f"{location}unknown setting {assignment.name!r}")
            continue
        value = assignment.value
        if type(value) is not int or value not in _VALID_VALUES:
            errors.append(f"{location}{canonical}: expected -1, 0, or 1")
            continue
        values[normalized_name] = value

    if errors:
        raise ConfigError(errors)

    groups = {record.id.casefold(): record for record in catalog.groups}
    group_values = {
        record.id.casefold(): values.get(record.setting.casefold(), record.default)
        for record in catalog.groups
    }

    def inherited_group_value(group_id: str) -> int:
        current = groups[group_id.casefold()]
        while True:
            value = group_values[current.id.casefold()]
            if value != -1:
                return value
            if current.parent is None:  # guarded by catalog validation
                raise AssertionError("root group unexpectedly inherits")
            current = groups[current.parent.casefold()]

    change_by_id = {record.id.casefold(): record for record in catalog.changes}
    explicitly_disabled: set[str] = set()
    explicitly_enabled: set[str] = set()
    active: set[str] = set()
    semantic_errors: list[str] = []
    recorded_errors: set[str] = set()

    def add_error(message: str) -> None:
        if message not in recorded_errors:
            recorded_errors.add(message)
            semantic_errors.append(message)

    for record in catalog.changes:
        normalized_id = record.id.casefold()
        setting_key = record.setting.casefold()
        leaf_value = values.get(setting_key, record.default)
        if setting_key in values:
            if leaf_value == 0:
                explicitly_disabled.add(normalized_id)
            elif leaf_value == 1:
                explicitly_enabled.add(normalized_id)
        desired = leaf_value if leaf_value != -1 else inherited_group_value(record.group)
        available = _available(record, normalized_game)
        if normalized_id in explicitly_enabled and not available:
            add_error(
                f"{record.setting} is explicitly enabled but unavailable on game "
                f"{normalized_game!r}"
            )
        elif desired == 1 and available:
            active.add(normalized_id)

    atomic_families: dict[str, list[Change]] = {}
    atomic_names: dict[str, str] = {}
    for record in catalog.changes:
        if record.atomic_group is not None:
            normalized_family = record.atomic_group.casefold()
            atomic_families.setdefault(normalized_family, []).append(record)
            atomic_names.setdefault(normalized_family, record.atomic_group)

    changed = True
    while changed:
        changed = False
        for record in catalog.changes:
            normalized_id = record.id.casefold()
            if normalized_id not in active:
                continue
            targets: list[tuple[Change, str]] = []
            for requirement in record.requires:
                target = change_by_id[requirement.casefold()]
                targets.append((target, "hard"))
            if record.atomic_group is not None:
                for target in atomic_families[record.atomic_group.casefold()]:
                    if target.id.casefold() != normalized_id:
                        targets.append((target, "atomic"))
            for target, relation in targets:
                target_id = target.id.casefold()
                if target_id in active:
                    continue
                if target_id in explicitly_disabled:
                    if relation == "hard":
                        add_error(
                            f"{record.setting} requires {target.setting}, but "
                            f"{target.setting} is explicitly disabled"
                        )
                    else:
                        family = atomic_names[record.atomic_group.casefold()]
                        add_error(
                            f"atomic family {family!r} requires {target.setting}, but "
                            f"{target.setting} is explicitly disabled"
                        )
                    continue
                if not _available(target, normalized_game):
                    if relation == "hard":
                        add_error(
                            f"{record.setting} requires {target.setting}, which is "
                            f"unavailable on game {normalized_game!r}"
                        )
                    else:
                        family = atomic_names[record.atomic_group.casefold()]
                        add_error(
                            f"atomic family {family!r} requires {target.setting}, which "
                            f"is unavailable on game {normalized_game!r}"
                        )
                    continue
                active.add(target_id)
                changed = True

    conflict_pairs: set[tuple[str, str]] = set()
    for record in catalog.changes:
        normalized_id = record.id.casefold()
        if normalized_id not in active:
            continue
        for conflict in record.conflicts:
            target = change_by_id[conflict.casefold()]
            target_id = target.id.casefold()
            if target_id not in active:
                continue
            pair = tuple(sorted((normalized_id, target_id)))
            if pair in conflict_pairs:
                continue
            conflict_pairs.add(pair)
            add_error(f"{record.setting} conflicts with {target.setting}")

    if semantic_errors:
        raise ConfigError(semantic_errors)

    selected_ids = tuple(
        record.id for record in catalog.changes if record.id.casefold() in active
    )
    soft_edges = tuple(
        (record.id, change_by_id[target.casefold()].id)
        for record in catalog.changes
        if record.id.casefold() in active
        for target in record.soft_requires
        if target.casefold() in active
    )
    return Resolution(catalog, selected_ids, soft_edges, normalized_game)


def _coerce_assignments(
    assignments: Mapping[str, object]
    | Iterable[Assignment]
    | Iterable[tuple[str, object]],
) -> tuple[Assignment, ...]:
    source: Iterable[tuple[str, object] | Assignment]
    if isinstance(assignments, Mapping):
        source = assignments.items()
    else:
        source = assignments
    result: list[Assignment] = []
    for item in source:
        if isinstance(item, Assignment):
            result.append(item)
        else:
            try:
                name, value = item
            except (TypeError, ValueError) as error:
                raise ConfigError(
                    "configuration entries must be Assignment or (name, value)"
                ) from error
            if not isinstance(name, str):
                raise ConfigError("configuration setting names must be strings")
            result.append(Assignment(name, value))
    return tuple(result)


def _location(assignment: Assignment) -> str:
    return f"line {assignment.line}: " if assignment.line is not None else ""


def _validate_game(game: str) -> str:
    if not isinstance(game, str):
        raise ConfigError(f"unknown game {game!r}")
    normalized = game.casefold()
    if normalized not in SUPPORTED_GAMES:
        raise ConfigError(f"unknown game {game!r}")
    return normalized


def _available(record: Change, game: str) -> bool:
    normalized_games = {value.casefold() for value in record.games}
    return "all" in normalized_games or game in normalized_games
