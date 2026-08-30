"""Generate the synchronized editable config and public change catalogs."""

from __future__ import annotations

import difflib
import hashlib
import html
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from .catalog import (
    Catalog,
    Change,
    Group,
    MemberReference,
    NameFallback,
    SourceSpan,
    load_catalog,
)
from .resolve import feature_symbols
from .source import SourceError, inventory, resolve_span_offsets_in_source
from .text import TraError, load_english_tra, resolve_tra_reference


BEGIN_MARKER = "<!-- SR_CONFIG_CATALOG_BEGIN -->"
END_MARKER = "<!-- SR_CONFIG_CATALOG_END -->"
CONFIG_GUIDE_BEGIN_MARKER = "<!-- SR_CONFIG_GUIDE_BEGIN -->"
CONFIG_GUIDE_END_MARKER = "<!-- SR_CONFIG_GUIDE_END -->"

_CATALOG_PATH = Path("spell_rev/catalog/changes.json")
_CONFIG_PATH = Path("spell_rev/settings.ini")
_MARKDOWN_PATH = Path("docs/spell-revisions-change-catalog.md")
_HTML_PATH = Path("spell_rev/readme-spell_rev.html")
_WEIDU_SCHEMA_PATH = Path("spell_rev/generated/config_schema.tpa")
_WEIDU_SELECTION_PATH = Path("spell_rev/generated/selection.tpa")
_LEGACY_START = re.compile(
    rb'(?m)^  <p>\r?\n    <a id="spell_changes"></a>'
    rb"<strong>Overview of Divine Spell Changes</strong>"
)
_LEGACY_END = re.compile(
    rb'(?m)^</div>\r?\n\r?\n<h2>Contact Information</h2>'
)
_LEGACY_CONFIG_GUIDE_START = re.compile(
    rb"(?m)^  <p><strong>How to Prevent Certain Spells from Being Installed</strong>"
)
_LEGACY_CONFIG_GUIDE_END = re.compile(
    rb"(?m)^</div>\r?\n\r?\n<h2>Components</h2>"
)


class GenerationError(ValueError):
    """Raised when generated artifacts cannot be validated safely."""


@dataclass(frozen=True)
class GenerationResult:
    paths: tuple[Path, ...]
    changed_paths: tuple[Path, ...]
    diff: str

    @property
    def changed(self) -> bool:
        return bool(self.changed_paths)


def catalog_fingerprint(catalog: Catalog) -> str:
    """Hash canonical semantic catalog JSON, independent of source formatting."""

    payload = json.dumps(
        asdict(catalog),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def render_component_zero_sources(
    root: str | Path, catalog: Catalog
) -> dict[Path, bytes]:
    """Render guarded component-zero source variants from exact catalog spans."""

    root_path = Path(root).resolve()
    feature_flags = feature_symbols(catalog)
    infrastructure_flags = {
        record.id: f"sr_infra_{index:06d}"
        for index, record in enumerate(catalog.infrastructure, start=1)
    }
    owned: list[tuple[str, SourceSpan, str | None]] = []
    for record in catalog.changes:
        if record.component != 0:
            continue
        for span in record.source_spans:
            owned.append(
                (f"change:{record.id}", span, feature_flags[record.id])
            )
    for record in catalog.infrastructure:
        guard = (
            None
            if record.activation == "always"
            else infrastructure_flags[record.id]
        )
        for span in record.source_spans:
            owned.append((f"infrastructure:{record.id}", span, guard))
    for record in catalog.deferred_source_scopes:
        guard = "exclude" if record.id.casefold() == "excluded.hardiness_spcl907" else None
        for span in record.source_spans:
            owned.append((f"deferred:{record.id}", span, guard))

    closure_spans = {
        (
            root.source_span.path.casefold(),
            root.source_span.start,
            root.source_span.end,
            root.source_span.sha256.casefold(),
        )
        for root in catalog.component_zero_closure_roots
    }
    by_path_spans: dict[str, list[tuple[str, SourceSpan, str | None]]] = {}
    for owner, span, guard in owned:
        if (
            span.path.casefold(),
            span.start,
            span.end,
            span.sha256.casefold(),
        ) in closure_spans:
            continue
        by_path_spans.setdefault(span.path, []).append((owner, span, guard))

    by_path: dict[str, list[tuple[int, int, str, str | None]]] = {}
    sources: dict[str, bytes] = {}
    for source_path, declarations in sorted(by_path_spans.items()):
        try:
            source = (root_path / source_path).read_bytes()
        except OSError as error:
            raise GenerationError(
                f"{source_path}: unable to read source: {error}"
            ) from error
        sources[source_path] = source
        for owner, span, guard in declarations:
            try:
                resolved = resolve_span_offsets_in_source(source, span)
            except SourceError as error:
                raise GenerationError(str(error)) from error
            by_path.setdefault(source_path, []).append(
                (resolved.start, resolved.end, owner, guard)
            )

    outputs: dict[Path, bytes] = {}
    for source_path, intervals in sorted(by_path.items()):
        source = sources[source_path]
        _validate_component_source_coverage(source_path, source, intervals)
        newline = _detect_newline_bytes(source, Path(source_path))
        chunks: list[bytes] = []
        cursor = 0
        for start, end, owner, guard in sorted(intervals):
            if start < cursor:
                raise GenerationError(
                    f"{source_path}: overlapping source span at {owner}"
                )
            chunks.append(source[cursor:start])
            raw = source[start:end]
            if guard == "exclude":
                pass
            elif guard is None:
                chunks.append(raw)
            else:
                owner_bytes = owner.encode("utf-8")
                guard_bytes = guard.encode("ascii")
                chunks.extend(
                    (
                        b"// SR_CONFIG_GUARD_BEGIN " + owner_bytes + newline,
                        b"ACTION_IF (" + guard_bytes + b" = 1) BEGIN" + newline,
                        raw,
                        b"" if raw.endswith((b"\n", b"\r")) else newline,
                        b"END" + newline,
                        b"// SR_CONFIG_GUARD_END " + owner_bytes + newline,
                    )
                )
            cursor = end
        chunks.append(source[cursor:])
        relative = _component_zero_generated_path(Path(source_path))
        outputs[relative] = _rewrite_internal_source_paths(
            b"".join(chunks), by_path
        )

    entry = _render_component_zero_entry(
        root_path, catalog, infrastructure_flags, by_path
    )
    outputs[Path("spell_rev/generated/component0/entry.tpa")] = entry
    return outputs


def _component_zero_generated_path(source_path: Path) -> Path:
    parts = source_path.parts
    if not parts or parts[0].casefold() != "spell_rev":
        raise GenerationError(
            f"{source_path.as_posix()}: component-zero source must be below spell_rev"
        )
    return Path("spell_rev/generated/component0").joinpath(*parts[1:])


def _validate_component_source_coverage(
    source_path: str,
    source: bytes,
    intervals: list[tuple[int, int, str, str | None]],
) -> None:
    ordered = sorted(intervals)
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1]:
            raise GenerationError(
                f"{source_path}: overlapping source span at {current[2]}"
            )
    offset = 0
    try:
        nodes = inventory(
            source_path,
            _source=source,
            _display_path_override=source_path,
        )
    except SourceError as error:
        raise GenerationError(str(error)) from error
    for node in nodes:
        start = offset
        end = start + len(node.raw)
        offset = end
        if node.kind == "trivia":
            continue
        containing = [
            owner
            for span_start, span_end, owner, _ in ordered
            if span_start <= start and end <= span_end
        ]
        if not containing:
            partial = [
                owner
                for span_start, span_end, owner, _ in ordered
                if span_start < end and span_end > start
            ]
            if partial:
                raise GenerationError(
                    f"{source_path}:{node.line}: source span cuts through "
                    f"{node.command} ({', '.join(partial)})"
                )
            raise GenerationError(
                f"{source_path}:{node.line}: uncovered executable source "
                f"command {node.command}"
            )


def _rewrite_internal_source_paths(
    source: bytes,
    compiled_paths: Mapping[str, object],
) -> bytes:
    replacements: dict[bytes, bytes] = {}
    for original in compiled_paths:
        path = Path(original)
        generated = _component_zero_generated_path(path).as_posix()
        relative = "/".join(path.parts[1:])
        for old in {
            original.replace("\\", "/"),
            original.replace("/", "\\"),
            f"%MOD_FOLDER%/{relative}",
            f"%MOD_FOLDER%\\{relative.replace('/', chr(92))}",
        }:
            replacements[old.encode("utf-8")] = generated.encode("utf-8")
    for old, new in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        source = source.replace(old, new)
    return source


def _render_component_zero_entry(
    root: Path,
    catalog: Catalog,
    infrastructure_flags: Mapping[str, str],
    compiled_paths: Mapping[str, object],
) -> bytes:
    lines = ["// Generated from spell_rev/catalog/changes.json. Do not edit."]
    direct = {record.id: tuple(record.consumers) for record in catalog.infrastructure}
    effective = {identifier: set(consumers) for identifier, consumers in direct.items()}
    changed = True
    while changed:
        changed = False
        for record in catalog.infrastructure:
            for requirement in record.infrastructure_requires:
                before = len(effective[requirement])
                effective[requirement].update(effective[record.id])
                changed = changed or len(effective[requirement]) != before
    flags = feature_symbols(catalog)
    for record in catalog.infrastructure:
        target = infrastructure_flags[record.id]
        lines.append(f"// SR_CONFIG_INFRA_BEGIN {record.id}")
        if record.activation == "always" or not effective[record.id]:
            lines.append(f"OUTER_SET {target} = 1")
            lines.append(f"// SR_CONFIG_INFRA_END {record.id}")
            continue
        lines.append(f"OUTER_SET {target} = 0")
        for consumer in catalog.changes:
            if consumer.id not in effective[record.id]:
                continue
            lines.extend(
                (
                    f"ACTION_IF ({flags[consumer.id]} = 1) BEGIN",
                    f"  OUTER_SET {target} = 1",
                    "END",
                )
            )
        lines.append(f"// SR_CONFIG_INFRA_END {record.id}")
    main_path = _component_zero_generated_path(Path(catalog.migration.installer_source))
    if not catalog.component_zero_closure_roots:
        lines.extend(("", f"INCLUDE ~{main_path.as_posix()}~"))
    else:
        lines.append("")
    entry = ("\n".join(lines).rstrip() + "\n").encode("utf-8")

    infrastructure_by_id = {record.id: record for record in catalog.infrastructure}
    primary_include = f"INCLUDE ~{main_path.as_posix()}~".encode("utf-8")
    primary_include_count = 0
    for closure_root in catalog.component_zero_closure_roots:
        record = infrastructure_by_id[closure_root.owner]
        try:
            original = (root / closure_root.source_span.path).read_bytes()
            resolved = resolve_span_offsets_in_source(
                original, closure_root.source_span
            )
        except OSError as error:
            raise GenerationError(
                f"{closure_root.source_span.path}: unable to read source: {error}"
            ) from error
        except SourceError as error:
            raise GenerationError(str(error)) from error
        raw = _rewrite_internal_source_paths(resolved.raw, compiled_paths)
        owner = f"infrastructure:{record.id}".encode("utf-8")
        flag = (
            None
            if record.activation == "always"
            else infrastructure_flags[record.id].encode("ascii")
        )
        matches = raw.count(primary_include)
        if matches > 1:
            raise GenerationError(
                f"{closure_root.source_span.path}: closure root contains the "
                "primary component INCLUDE more than once"
            )
        if matches == 0:
            entry += _render_guarded_block(raw, owner, flag)
            continue
        primary_include_count += 1
        include_start = raw.index(primary_include)
        line_start = raw.rfind(b"\n", 0, include_start) + 1
        line_end = raw.find(b"\n", include_start)
        line_end = len(raw) if line_end < 0 else line_end + 1
        entry += _render_guarded_block(raw[:line_start], owner, flag)
        entry += raw[line_start:line_end]
        entry += _render_guarded_block(raw[line_end:], owner, flag)
    if catalog.component_zero_closure_roots and primary_include_count != 1:
        raise GenerationError(
            "component-zero closure roots must contain the primary component "
            "INCLUDE exactly once"
        )
    return entry


def _render_guarded_block(
    raw: bytes, owner: bytes, guard: bytes | None
) -> bytes:
    if not raw:
        return b""
    if guard is None:
        return raw + (b"" if raw.endswith((b"\n", b"\r")) else b"\n")
    rendered = b"// SR_CONFIG_GUARD_BEGIN " + owner + b"\n"
    rendered += b"ACTION_IF (" + guard + b" = 1) BEGIN\n"
    rendered += raw
    if not raw.endswith((b"\n", b"\r")):
        rendered += b"\n"
    return rendered + b"END\n// SR_CONFIG_GUARD_END " + owner + b"\n"


def render_config(catalog: Catalog, existing: str, *, newline: str) -> str:
    """Render settings while retaining the existing ToBEx preamble verbatim."""

    prefix = _tobex_prefix(existing)
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += newline
    if prefix and not prefix.endswith(newline * 2):
        prefix += newline

    lines = [
        "// Generated Spell Revisions selection metadata. Do not edit these two lines.",
        f"sr_config_schema = {catalog.schema_version}",
        f"SPRINT sr_catalog_fingerprint ~{catalog_fingerprint(catalog)}~",
        "",
        "// Selection values: 1 enables, 0 disables, and -1 inherits from the parent.",
        "// The untouched defaults install every applicable cataloged change.",
        "",
    ]
    for group in catalog.groups:
        inheritance = "root default" if group.parent is None else "inherits by default"
        lines.extend(
            [
                f"// {single_line(group.name)} ({inheritance}).",
                f"{group.setting} = {group.default}",
                "",
            ]
        )

    symbols = feature_symbols(catalog)
    for change in catalog.changes:
        lines.extend(
            [
                f"// {single_line(change.display_name)}; catalog ID "
                f"{single_line(change.id)}; "
                f"internal flag {symbols[change.id]}.",
                f"{change.setting} = -1",
                "",
            ]
        )
    return prefix + newline.join(lines).rstrip() + newline


def render_weidu_config_schema(catalog: Catalog) -> str:
    """Render the inert-text validator and literal tri-state value loader."""

    fingerprint = catalog_fingerprint(catalog)
    numeric_settings: list[tuple[str, tuple[int, ...]]] = [
        ("install_tobex", (1,)),
        ("sr_config_schema", (catalog.schema_version,)),
    ]
    statements: list[tuple[str, str, str, str, bool]] = [
        (
            "install_tobex",
            r"^[ %TAB%]*install_tobex[ %TAB%]*=",
            _weidu_assignment_pattern("install_tobex", r"1"),
            "install_tobex: expected exactly 1",
            False,
        ),
        (
            "sr_config_schema",
            r"^[ %TAB%]*sr_config_schema[ %TAB%]*=",
            _weidu_assignment_pattern(
                "sr_config_schema", str(catalog.schema_version)
            ),
            "stale or malformed sr_config_schema",
            False,
        ),
        (
            "sr_catalog_fingerprint",
            (
                r"^[ %TAB%]*SPRINT[ %TAB%]+sr_catalog_fingerprint"
                r"[ %TAB%]+"
            ),
            _weidu_fingerprint_pattern(fingerprint),
            "stale or malformed sr_catalog_fingerprint",
            True,
        ),
    ]
    root = next(record for record in catalog.groups if record.parent is None)
    for record in catalog.groups:
        numeric_settings.append(
            (record.setting, (0, 1) if record.id == root.id else (-1, 0, 1))
        )
        allowed = r"\(0\|1\)" if record.id == root.id else r"\(-1\|0\|1\)"
        expected = (
            f"{record.setting}: expected 0 or 1"
            if record.id == root.id
            else f"{record.setting}: expected -1, 0, or 1"
        )
        statements.append(
            (
                record.setting,
                rf"^[ %TAB%]*{record.setting}[ %TAB%]*=",
                _weidu_assignment_pattern(record.setting, allowed),
                expected,
                False,
            )
        )
    for record in catalog.changes:
        numeric_settings.append((record.setting, (-1, 0, 1)))
        statements.append(
            (
                record.setting,
                rf"^[ %TAB%]*{record.setting}[ %TAB%]*=",
                _weidu_assignment_pattern(record.setting, r"\(-1\|0\|1\)"),
                f"{record.setting}: expected -1, 0, or 1",
                False,
            )
        )

    lines = [
        "// Generated from spell_rev/catalog/changes.json. Do not edit.",
        "// The config remains inert text until every significant line is recognized.",
        "DEFINE_ACTION_MACRO sr_config_load_validate BEGIN",
        "  ACTION_IF NOT FILE_EXISTS ~%sr_config_path%~ BEGIN",
        "    FAIL ~Spell Revisions configuration file is missing: %sr_config_path%~",
        "  END",
        "  OUTER_SET sr_config_error_count = 0",
        "  OUTER_SPRINT sr_config_errors ~~",
        "  COPY ~%sr_config_path%~ ~~",
        (
            "    COUNT_REGEXP_INSTANCES CASE_SENSITIVE "
            '"^[ %TAB%]*[^ %TAB%%WNL%%MNL%%LNL%]" sr_config_nonblank_lines'
        ),
        (
            "    COUNT_REGEXP_INSTANCES CASE_SENSITIVE "
            '"^[ %TAB%]*//" sr_config_comment_lines'
        ),
        "    SET sr_config_significant_lines = "
        "sr_config_nonblank_lines - sr_config_comment_lines",
        "    SET sr_config_recognized_lines = 0",
    ]
    for index, (name, broad, exact, message, exact_case_sensitive) in enumerate(
        statements, start=1
    ):
        broad_var = f"sr_config_broad_{index:06d}"
        exact_var = f"sr_config_exact_{index:06d}"
        lines.extend(
            (
                f"    // Required statement: {name}",
                "    COUNT_REGEXP_INSTANCES CASE_INSENSITIVE "
                f'"{broad}" {broad_var}',
                "    COUNT_REGEXP_INSTANCES "
                f"{'CASE_SENSITIVE' if exact_case_sensitive else 'CASE_INSENSITIVE'} "
                f'"{exact}" {exact_var}',
                f"    SET sr_config_recognized_lines += {exact_var}",
                f"    PATCH_IF ({broad_var} = 0) BEGIN",
                "      SPRINT sr_config_errors "
                f"~%sr_config_errors%- missing setting {name}%LNL%~",
                "      SET sr_config_error_count += 1",
                f"    END ELSE PATCH_IF ({broad_var} > 1) BEGIN",
                "      SPRINT sr_config_errors "
                f"~%sr_config_errors%- duplicate setting {name}%LNL%~",
                "      SET sr_config_error_count += 1",
                f"    END ELSE PATCH_IF ({exact_var} != 1) BEGIN",
                "      SPRINT sr_config_errors "
                f"~%sr_config_errors%- {message}%LNL%~",
                "      SET sr_config_error_count += 1",
                "    END",
            )
        )
    lines.extend(
        (
            "    PATCH_IF (sr_config_recognized_lines != "
            "sr_config_significant_lines) BEGIN",
            "      SPRINT sr_config_errors ~%sr_config_errors%- unrecognized or "
            "malformed non-comment line%LNL%~",
            "      SET sr_config_error_count += 1",
            "    END",
        )
    )
    for setting_index, (setting, values) in enumerate(numeric_settings, start=1):
        for value_index, value in enumerate(values, start=1):
            count_var = (
                f"sr_config_value_{setting_index:06d}_{value_index:02d}"
            )
            literal = r"-1" if value == -1 else str(value)
            lines.extend(
                (
                    "    COUNT_REGEXP_INSTANCES CASE_INSENSITIVE "
                    f'"{_weidu_assignment_pattern(setting, literal)}" {count_var}',
                    f"    PATCH_IF ({count_var} = 1) BEGIN",
                    f"      SET {setting} = {'0 - 1' if value == -1 else value}",
                    "    END",
                )
            )
    lines.extend(
        (
            "  BUT_ONLY",
            "  ACTION_IF (sr_config_error_count > 0) BEGIN",
            "    FAIL ~Spell Revisions configuration preflight failed:%LNL%"
            "%sr_config_errors%~",
            "  END",
            "  // WeiDU 249 cannot execute the public `key = -1` syntax. The exact",
            "  // validated line counts above publish equivalent numeric variables",
            "  // without ever executing or rewriting the editable file.",
            f"  OUTER_SPRINT sr_catalog_fingerprint ~{fingerprint}~",
            "END",
            "",
        )
    )
    return "\n".join(lines)


def render_weidu_selection(catalog: Catalog) -> str:
    """Render deterministic WeiDU tri-state/dependency resolution."""

    symbols = feature_symbols(catalog)
    change_by_id = {record.id.casefold(): record for record in catalog.changes}
    groups = {record.id.casefold(): record for record in catalog.groups}
    supported_games = tuple(sorted({game for game in _catalog_games(catalog)}))
    return_values = (
        "install_tobex",
        "sr_selection_signature",
        *(symbols[record.id] for record in catalog.changes),
    )
    lines = [
        "// Generated from spell_rev/catalog/changes.json. Do not edit.",
        "DEFINE_ACTION_FUNCTION sr_config_preflight",
        "  STR_VAR",
        "    config_path = ~spell_rev/settings.ini~",
        "    game = ~~",
        "  RET",
        *(f"    {value}" for value in return_values),
        "BEGIN",
        "  OUTER_SPRINT sr_config_path EVALUATE_BUFFER ~%config_path%~",
        "  OUTER_SPRINT sr_config_game EVALUATE_BUFFER ~%game%~",
        "  LAM sr_config_load_validate",
        "  OUTER_SET sr_config_error_count = 0",
        "  OUTER_SPRINT sr_config_errors ~~",
        "  OUTER_SET sr_config_game_known = 0",
    ]
    for game in supported_games:
        lines.extend(
            (
                f"  ACTION_IF (~%sr_config_game%~ STRING_EQUAL_CASE ~{game}~) BEGIN",
                "    OUTER_SET sr_config_game_known = 1",
                "  END",
            )
        )
    _append_action_error(
        lines,
        "sr_config_game_known = 0",
        "unknown game '%sr_config_game%'",
        indent="  ",
    )

    for record in catalog.changes:
        symbol = symbols[record.id]
        lines.extend(
            (
                f"  // {record.id}",
                f"  OUTER_SET {symbol} = {record.setting}",
            )
        )
        current = groups[record.group.casefold()]
        while True:
            lines.extend(
                (
                    f"  ACTION_IF ({symbol} = (0 - 1)) BEGIN",
                    f"    OUTER_SET {symbol} = {current.setting}",
                    "  END",
                )
            )
            if current.parent is None:
                break
            current = groups[current.parent.casefold()]
        availability = _weidu_availability(record.games)
        lines.extend(
            (
                f"  ACTION_IF NOT ({availability}) BEGIN",
                f"    ACTION_IF ({record.setting} = 1) BEGIN",
                "      OUTER_SPRINT sr_config_errors "
                f"~%sr_config_errors%- {record.setting} is explicitly enabled but "
                "unavailable on game '%sr_config_game%'%LNL%~",
                "      OUTER_SET sr_config_error_count += 1",
                "    END",
                f"    OUTER_SET {symbol} = 0",
                "  END",
            )
        )

    hard_edges = [
        (record, change_by_id[target.casefold()])
        for record in catalog.changes
        for target in record.requires
    ]
    atomic_families: dict[str, list[Change]] = {}
    atomic_names: dict[str, str] = {}
    for record in catalog.changes:
        if record.atomic_group is None:
            continue
        normalized = record.atomic_group.casefold()
        atomic_families.setdefault(normalized, []).append(record)
        atomic_names.setdefault(normalized, record.atomic_group)
    atomic_edges = [
        (source, target, atomic_names[family])
        for family, members in atomic_families.items()
        for source in members
        for target in members
        if source.id.casefold() != target.id.casefold()
    ]
    error_guards: dict[tuple[str, ...], str] = {}
    for index, (source, target) in enumerate(hard_edges, start=1):
        error_guards[("hard", source.id.casefold(), target.id.casefold())] = (
            f"sr_config_hard_error_{index:06d}"
        )
    atomic_guard_keys: list[tuple[str, str]] = []
    for source, target, family_name in atomic_edges:
        key = (family_name.casefold(), target.id.casefold())
        if key not in atomic_guard_keys:
            atomic_guard_keys.append(key)
    for index, (family, target) in enumerate(atomic_guard_keys, start=1):
        error_guards[("atomic", family, target)] = (
            f"sr_config_atomic_error_{index:06d}"
        )
    for guard in error_guards.values():
        lines.append(f"  OUTER_SET {guard} = 0")

    if hard_edges or atomic_edges:
        lines.extend(
            (
                "  OUTER_SET sr_config_resolution_changed = 1",
                "  OUTER_WHILE (sr_config_resolution_changed = 1) BEGIN",
                "    OUTER_SET sr_config_resolution_changed = 0",
            )
        )
        for source, target in hard_edges:
            guard = error_guards[
                ("hard", source.id.casefold(), target.id.casefold())
            ]
            _append_closure_edge(
                lines,
                symbols[source.id],
                symbols[target.id],
                target.setting,
                _weidu_availability(target.games),
                guard,
                (
                    f"{source.setting} requires {target.setting}, but "
                    f"{target.setting} is explicitly disabled"
                ),
                (
                    f"{source.setting} requires {target.setting}, which is "
                    "unavailable on game '%sr_config_game%'"
                ),
            )
        for source, target, family_name in atomic_edges:
            guard = error_guards[
                ("atomic", family_name.casefold(), target.id.casefold())
            ]
            _append_closure_edge(
                lines,
                symbols[source.id],
                symbols[target.id],
                target.setting,
                _weidu_availability(target.games),
                guard,
                (
                    f"atomic family '{family_name}' requires {target.setting}, but "
                    f"{target.setting} is explicitly disabled"
                ),
                (
                    f"atomic family '{family_name}' requires {target.setting}, which "
                    "is unavailable on game '%sr_config_game%'"
                ),
            )
        lines.append("  END")

    seen_conflicts: set[tuple[str, str]] = set()
    for record in catalog.changes:
        for target_id in record.conflicts:
            target = change_by_id[target_id.casefold()]
            pair = tuple(sorted((record.id.casefold(), target.id.casefold())))
            if pair in seen_conflicts:
                continue
            seen_conflicts.add(pair)
            _append_action_error(
                lines,
                f"({symbols[record.id]} = 1) AND ({symbols[target.id]} = 1)",
                f"{record.setting} conflicts with {target.setting}",
                indent="  ",
            )

    lines.extend(
        (
            "  ACTION_IF (sr_config_error_count > 0) BEGIN",
            "    FAIL ~Spell Revisions configuration resolution failed:%LNL%"
            "%sr_config_errors%~",
            "  END",
            "  OUTER_SPRINT sr_selection_signature ~~",
        )
    )
    for record in catalog.changes:
        symbol = symbols[record.id]
        lines.append(
            "  OUTER_SPRINT sr_selection_signature "
            f"~%sr_selection_signature%%{symbol}%~"
        )
    lines.extend(("END", "", "DEFINE_ACTION_MACRO sr_config_preflight_component_zero BEGIN"))
    lines.extend(
        (
            "  LAF sr_config_preflight",
            "    STR_VAR",
            "      config_path = ~%sr_config_input_path%~",
            "      game = ~%sr_config_input_game%~",
            "    RET",
            *(f"      {value}" for value in return_values),
            "  END",
            "END",
            "",
        )
    )
    return "\n".join(lines)


def _weidu_assignment_pattern(setting: str, allowed: str) -> str:
    return (
        rf"^[ %TAB%]*{setting}[ %TAB%]*=[ %TAB%]*{allowed}[ %TAB%]*"
        r"\(//[^%WNL%%MNL%%LNL%]*\)?"
        r"\(%WNL%\|%MNL%\|%LNL%\|$\)"
    )


def _weidu_fingerprint_pattern(fingerprint: str) -> str:
    return (
        r"^[ %TAB%]*SPRINT[ %TAB%]+sr_catalog_fingerprint[ %TAB%]+~"
        + fingerprint
        + r"~[ %TAB%]*\(//[^%WNL%%MNL%%LNL%]*\)?"
        r"\(%WNL%\|%MNL%\|%LNL%\|$\)"
    )


def _catalog_games(catalog: Catalog) -> set[str]:
    games = set()
    for record in catalog.changes:
        games.update(game.casefold() for game in record.games if game.casefold() != "all")
    from .catalog import SUPPORTED_GAMES

    games.update(SUPPORTED_GAMES)
    return games


def _weidu_availability(games: tuple[str, ...]) -> str:
    normalized = tuple(value.casefold() for value in games)
    if "all" in normalized:
        return "1"
    return " OR ".join(
        f"(~%sr_config_game%~ STRING_EQUAL_CASE ~{game}~)" for game in normalized
    )


def _append_action_error(
    lines: list[str], condition: str, message: str, *, indent: str
) -> None:
    lines.extend(
        (
            f"{indent}ACTION_IF ({condition}) BEGIN",
            f"{indent}  OUTER_SPRINT sr_config_errors "
            f"~%sr_config_errors%- {message}%LNL%~",
            f"{indent}  OUTER_SET sr_config_error_count += 1",
            f"{indent}END",
        )
    )


def _append_closure_edge(
    lines: list[str],
    source_symbol: str,
    target_symbol: str,
    target_setting: str,
    availability: str,
    error_guard: str,
    disabled_message: str,
    unavailable_message: str,
) -> None:
    lines.extend(
        (
            f"    ACTION_IF ({source_symbol} = 1) AND ({target_symbol} = 0) BEGIN",
            f"      ACTION_IF ({target_setting} = 0) BEGIN",
            f"        ACTION_IF ({error_guard} = 0) BEGIN",
            "          OUTER_SPRINT sr_config_errors "
            f"~%sr_config_errors%- {disabled_message}%LNL%~",
            "          OUTER_SET sr_config_error_count += 1",
            f"          OUTER_SET {error_guard} = 1",
            "        END",
            f"      END ELSE ACTION_IF NOT ({availability}) BEGIN",
            f"        ACTION_IF ({error_guard} = 0) BEGIN",
            "          OUTER_SPRINT sr_config_errors "
            f"~%sr_config_errors%- {unavailable_message}%LNL%~",
            "          OUTER_SET sr_config_error_count += 1",
            f"          OUTER_SET {error_guard} = 1",
            "        END",
            "      END ELSE BEGIN",
            f"        OUTER_SET {target_symbol} = 1",
            "        OUTER_SET sr_config_resolution_changed = 1",
            "      END",
            "    END",
        )
    )


def render_markdown_catalog(catalog: Catalog, texts: Mapping[str, str]) -> str:
    """Render the complete user-facing Markdown table."""

    symbols = feature_symbols(catalog)
    change_by_id = {record.id.casefold(): record for record in catalog.changes}
    lines = [
        "# Spell Revisions change catalog",
        "",
        "This file is generated from `spell_rev/catalog/changes.json`. Edit "
        "`spell_rev/settings.ini` to select changes; `-1` inherits from the nearest "
        "parent default.",
        "",
        f"Upstream: {_markdown(catalog.upstream.tag)} "
        f"(`{catalog.upstream.commit}`)",
        "",
        "| Change | Setting | Effective default | Component | Games | Description | "
        "Atomic family | Hard dependencies | Soft edges | Upstream provenance | "
        "WeiDU flag |",
        "|---|---|---|---:|---|---|---|---|---|---|---|",
    ]
    for index, change in enumerate(catalog.changes):
        name, description = _change_text(catalog, change, index, texts)
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown(name),
                    f"`{change.setting}`",
                    _effective_default_label(catalog, change),
                    str(change.component),
                    _markdown(", ".join(change.games)),
                    _markdown(description),
                    _markdown(change.atomic_group or "None"),
                    _markdown(_relations(change.requires, change_by_id)),
                    _markdown(_relations(change.soft_requires, change_by_id)),
                    _markdown(_provenance(catalog, change)),
                    f"`{symbols[change.id]}`",
                )
            )
            + " |"
        )
    composite_changes = [
        (index, change)
        for index, change in enumerate(catalog.changes)
        if change.member_refs
    ]
    if composite_changes:
        lines.extend(
            [
                "",
                "## Atomic bundle member descriptions",
                "",
                "The members listed here are controlled together by one atomic "
                "option and are not separate options.",
            ]
        )
        for change_index, change in composite_changes:
            lines.extend(
                [
                    "",
                    f"### {_markdown(change.display_name)} (`{change.setting}`)",
                    "",
                    "| Source spell | Level / role | Current name | Current description |",
                    "|---|---|---|---|",
                ]
            )
            for member_index, member in enumerate(change.member_refs):
                name, description = _member_text(
                    change_index, member_index, member, texts
                )
                lines.append(
                    "| "
                    + " | ".join(
                        (
                            f"`{member.source_spell}`",
                            _markdown(f"{member.level} / {member.role}"),
                            _markdown(name),
                            _markdown(description),
                        )
                    )
                    + " |"
                )
    if not catalog.changes:
        lines.extend(
            [
                "",
                "No public changes have been cataloged yet. The migration gate remains "
                "closed until upstream classification is complete.",
            ]
        )
    _append_markdown_support_sections(lines, catalog)
    return "\n".join(lines) + "\n"


def render_html_catalog(
    catalog: Catalog, texts: Mapping[str, str], *, newline: str
) -> str:
    """Render an ISO-8859-1-safe HTML catalog fragment with one stable anchor."""

    symbols = feature_symbols(catalog)
    change_by_id = {record.id.casefold(): record for record in catalog.changes}
    lines = [
        '<a id="spell_changes"></a>',
        "<h3>Configurable Spell Revisions Change Catalog</h3>",
        "<p>This section is generated from the canonical catalog. Edit "
        "<code>spell_rev/settings.ini</code>; a value of <code>-1</code> inherits "
        "from its nearest parent.</p>",
        "<p>Upstream: "
        f"{_html(catalog.upstream.tag)} "
        f"(<code>{_html(catalog.upstream.commit)}</code>).</p>",
        '<table class="sr-config-catalog">',
        "  <thead>",
        "    <tr><th>Change</th><th>Setting</th><th>Default</th><th>Component</th>"
        "<th>Games</th><th>Description</th><th>Atomic family</th>"
        "<th>Hard dependencies</th><th>Soft edges</th><th>Provenance</th>"
        "<th>WeiDU flag</th></tr>",
        "  </thead>",
        "  <tbody>",
    ]
    for index, change in enumerate(catalog.changes):
        name, description = _change_text(catalog, change, index, texts)
        values = (
            name,
            change.setting,
            _effective_default_label(catalog, change),
            str(change.component),
            ", ".join(change.games),
            description,
            change.atomic_group or "None",
            _relations(change.requires, change_by_id),
            _relations(change.soft_requires, change_by_id),
            _provenance(catalog, change),
            symbols[change.id],
        )
        lines.append(
            "    <tr>" + "".join(f"<td>{_html(value)}</td>" for value in values) + "</tr>"
        )
    lines.extend(("  </tbody>", "</table>"))
    composite_changes = [
        (index, change)
        for index, change in enumerate(catalog.changes)
        if change.member_refs
    ]
    if composite_changes:
        lines.extend(
            (
                "<h4>Atomic bundle member descriptions</h4>",
                "<p>The members listed here are controlled together by one atomic "
                "option and are not separate options.</p>",
            )
        )
        for change_index, change in composite_changes:
            lines.extend(
                (
                    f"<h5>{_html(change.display_name)} "
                    f"(<code>{_html(change.setting)}</code>)</h5>",
                    '<table class="sr-config-bundle-members">',
                    "  <thead>",
                    "    <tr><th>Source spell</th><th>Level / role</th>"
                    "<th>Current name</th><th>Current description</th></tr>",
                    "  </thead>",
                    "  <tbody>",
                )
            )
            for member_index, member in enumerate(change.member_refs):
                name, description = _member_text(
                    change_index, member_index, member, texts
                )
                values = (
                    member.source_spell,
                    f"{member.level} / {member.role}",
                    name,
                    description,
                )
                lines.append(
                    "    <tr>"
                    + "".join(f"<td>{_html(value)}</td>" for value in values)
                    + "</tr>"
                )
            lines.extend(("  </tbody>", "</table>"))
    if not catalog.changes:
        lines.append(
            "<p>No public changes have been cataloged yet. The migration gate remains "
            "closed until upstream classification is complete.</p>"
        )
    _append_html_support_sections(lines, catalog)
    result = newline.join(lines) + newline
    # All dynamic Unicode is represented by ASCII numeric references because the
    # surrounding upstream document is intentionally ISO-8859-1.
    return result.encode("ascii", errors="xmlcharrefreplace").decode("ascii")


def render_html_document(document: bytes, region: str) -> bytes:
    """Replace the generated marker region, or bootstrap the known legacy overview."""

    begin = BEGIN_MARKER.encode("ascii")
    end = END_MARKER.encode("ascii")
    begin_count = document.count(begin)
    end_count = document.count(end)
    newline = _detect_newline_bytes(document, _HTML_PATH)
    try:
        region_bytes = region.encode("iso-8859-1")
    except UnicodeEncodeError as error:
        raise GenerationError(
            f"generated HTML is not ISO-8859-1 safe at character {error.start}"
        ) from error
    if not region_bytes.endswith(newline):
        region_bytes += newline
    if region_bytes.count(b'id="spell_changes"') != 1:
        raise GenerationError('generated HTML region must contain exactly one id="spell_changes"')

    if begin_count == 1 and end_count == 1:
        begin_offset = document.index(begin)
        end_offset = document.index(end)
        if begin_offset >= end_offset:
            raise GenerationError("HTML catalog markers are reversed")
        rendered = (
            document[: begin_offset + len(begin)]
            + newline
            + region_bytes
            + document[end_offset:]
        )
    elif begin_count == 0 and end_count == 0:
        starts = tuple(_LEGACY_START.finditer(document))
        ends = tuple(_LEGACY_END.finditer(document))
        if len(starts) != 1 or len(ends) != 1:
            raise GenerationError(
                "HTML catalog markers are missing and the legacy overview anchors "
                "are not unique"
            )
        start_offset = starts[0].start()
        end_offset = ends[0].start()
        if start_offset >= end_offset:
            raise GenerationError("legacy HTML overview anchors are reversed")
        stale = document[start_offset:end_offset]
        if (
            stale.count(b'id="spell_changes"') != 1
            or stale.count(b"Overview of Arcane Spell Changes") != 1
        ):
            raise GenerationError("legacy HTML spell overview is not the expected shape")
        rendered = (
            document[:start_offset]
            + begin
            + newline
            + region_bytes
            + end
            + newline
            + document[end_offset:]
        )
    else:
        raise GenerationError(
            f"HTML catalog markers must occur exactly once each; found "
            f"{begin_count} begin and {end_count} end markers"
        )

    if rendered.count(begin) != 1 or rendered.count(end) != 1:
        raise GenerationError("generated HTML must contain exactly one marker pair")
    if rendered.count(b'id="spell_changes"') != 1:
        raise GenerationError('generated HTML must contain exactly one id="spell_changes"')
    return rendered


def render_html_config_guide(document: bytes) -> bytes:
    """Keep the player-facing selection instructions synchronized with settings.ini."""

    begin = CONFIG_GUIDE_BEGIN_MARKER.encode("ascii")
    end = CONFIG_GUIDE_END_MARKER.encode("ascii")
    begin_count = document.count(begin)
    end_count = document.count(end)
    newline = _detect_newline_bytes(document, _HTML_PATH)
    lines = (
        b"  <p><strong>Choosing Which Spell Changes to Install</strong>",
        b"    <br />Before installing, edit <strong>spell_rev/settings.ini</strong>. "
        b"Each documented setting accepts <code>1</code> to enable, <code>0</code> "
        b"to disable, or <code>-1</code> to inherit its group/default. Leaving the "
        b"settings unchanged installs all applicable upstream changes.",
        b"  </p>",
        b"  <p>For example, to leave Oracle unchanged:</p>",
        b"  <pre>sr_wizard_oracle = 0</pre>",
        b"  <p>Reinstall component 0 after changing the configuration. The generated "
        b"installer sources should not be edited by hand.</p>",
    )
    guide = newline.join(lines) + newline

    if begin_count == 1 and end_count == 1:
        begin_offset = document.index(begin)
        end_offset = document.index(end)
        if begin_offset >= end_offset:
            raise GenerationError("HTML config-guide markers are reversed")
        return (
            document[: begin_offset + len(begin)]
            + newline
            + guide
            + document[end_offset:]
        )

    if begin_count == 0 and end_count == 0:
        starts = tuple(_LEGACY_CONFIG_GUIDE_START.finditer(document))
        if not starts:
            # Minimal generator fixtures predate the upstream installation guide.
            return document
        ends = tuple(_LEGACY_CONFIG_GUIDE_END.finditer(document))
        if len(starts) != 1 or len(ends) != 1:
            raise GenerationError(
                "legacy HTML config-guide anchors are not unique"
            )
        start_offset = starts[0].start()
        end_offset = ends[0].start()
        if start_offset >= end_offset:
            raise GenerationError("legacy HTML config-guide anchors are reversed")
        stale = document[start_offset:end_offset]
        if stale.count(b"setup-spell_rev.tp2") != 2 or b"Oracle" not in stale:
            raise GenerationError("legacy HTML config guide is not the expected shape")
        return (
            document[:start_offset]
            + begin
            + newline
            + guide
            + end
            + newline
            + document[end_offset:]
        )

    raise GenerationError(
        f"HTML config-guide markers must occur exactly once each; found "
        f"{begin_count} begin and {end_count} end markers"
    )


def generate(root: str | Path, *, check: bool = False) -> GenerationResult:
    """Compute and validate all artifacts, then atomically replace stale targets."""

    root_path = Path(root).resolve()
    catalog = load_catalog(root_path / _CATALOG_PATH)
    texts = load_english_tra(root_path)

    config_path = root_path / _CONFIG_PATH
    html_path = root_path / _HTML_PATH
    try:
        config_bytes = config_path.read_bytes()
    except OSError as error:
        raise GenerationError(f"{config_path}: unable to read settings: {error}") from error
    try:
        existing_config = config_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GenerationError(
            f"{config_path}: invalid UTF-8 at byte {error.start}"
        ) from error
    try:
        html_bytes = html_path.read_bytes()
    except OSError as error:
        raise GenerationError(f"{html_path}: unable to read HTML: {error}") from error

    config_newline = _detect_newline_text(existing_config, _CONFIG_PATH)
    html_newline_bytes = _detect_newline_bytes(html_bytes, _HTML_PATH)
    html_newline = html_newline_bytes.decode("ascii")
    markdown_path = root_path / _MARKDOWN_PATH
    try:
        markdown_current = markdown_path.read_bytes()
        markdown_existed = True
    except FileNotFoundError:
        markdown_current = b""
        markdown_existed = False
    except OSError as error:
        raise GenerationError(
            f"{markdown_path}: unable to read Markdown: {error}"
        ) from error
    markdown_newline = (
        _detect_newline_bytes(markdown_current, _MARKDOWN_PATH).decode("ascii")
        if markdown_current
        else "\n"
    )

    # Build every output in memory. Any catalog, TRA, encoding, or marker error
    # occurs before the first target directory or file is changed.
    rendered_config = render_config(
        catalog, existing_config, newline=config_newline
    ).encode("utf-8")
    rendered_markdown = _with_newline(
        render_markdown_catalog(catalog, texts), markdown_newline
    ).encode("utf-8")
    html_region = render_html_catalog(catalog, texts, newline=html_newline)
    rendered_html = render_html_config_guide(
        render_html_document(html_bytes, html_region)
    )
    schema_path = root_path / _WEIDU_SCHEMA_PATH
    selection_path = root_path / _WEIDU_SELECTION_PATH
    schema_existed, schema_current = _read_optional_generated(schema_path)
    selection_existed, selection_current = _read_optional_generated(selection_path)
    rendered_schema = render_weidu_config_schema(catalog).encode("utf-8")
    rendered_selection = render_weidu_selection(catalog).encode("utf-8")
    outputs = [
        (config_path, _CONFIG_PATH, True, config_bytes, rendered_config, "utf-8"),
        (
            markdown_path,
            _MARKDOWN_PATH,
            markdown_existed,
            markdown_current,
            rendered_markdown,
            "utf-8",
        ),
        (html_path, _HTML_PATH, True, html_bytes, rendered_html, "iso-8859-1"),
        (
            schema_path,
            _WEIDU_SCHEMA_PATH,
            schema_existed,
            schema_current,
            rendered_schema,
            "utf-8",
        ),
        (
            selection_path,
            _WEIDU_SELECTION_PATH,
            selection_existed,
            selection_current,
            rendered_selection,
            "utf-8",
        ),
    ]
    installer_source = root_path / catalog.migration.installer_source
    if installer_source.is_file():
        for relative, expected in render_component_zero_sources(
            root_path, catalog
        ).items():
            path = root_path / relative
            existed, current = _read_optional_generated(path)
            outputs.append(
                (path, relative, existed, current, expected, "utf-8")
            )

    changed = tuple(
        path for path, _, _, current, expected, _ in outputs if current != expected
    )
    diff = "".join(
        _unified_diff(relative, current, expected, encoding)
        for _, relative, _, current, expected, encoding in outputs
        if current != expected
    )
    if not check and changed:
        staged: list[tuple[Path, Path, Path | None]] = []
        published: list[tuple[Path, Path | None]] = []
        transaction_error: OSError | None = None
        operation = "preparing generated-file transaction"
        rollback_errors: list[str] = []
        cleanup_errors: list[str] = []
        preserved_backups: set[Path] = set()
        try:
            default_mode = _default_file_mode()
            for path, _, existed, current, expected, _ in outputs:
                if current == expected:
                    continue
                operation = f"creating parent directory {path.parent} for {path}"
                path.parent.mkdir(parents=True, exist_ok=True)
                operation = f"reading permission mode for {path}"
                mode = _publication_mode(path, existed, default_mode)
                operation = f"staging generated output for {path}"
                temporary = _stage_bytes(
                    path, expected, suffix=".tmp", mode=mode
                )
                staged.append((temporary, path, None))
                operation = f"staging rollback backup for {path}"
                backup = (
                    _stage_bytes(
                        path, current, suffix=".rollback.tmp", mode=mode
                    )
                    if existed
                    else None
                )
                staged[-1] = (temporary, path, backup)
            for temporary, path, backup in staged:
                operation = f"publishing {temporary} to {path}"
                os.replace(temporary, path)
                published.append((path, backup))
        except OSError as error:
            transaction_error = error
            cleanup_errors.extend(getattr(error, "__notes__", ()))
            for path, backup in reversed(published):
                try:
                    if backup is None:
                        path.unlink(missing_ok=True)
                    else:
                        os.replace(backup, path)
                except OSError as rollback_error:
                    if backup is not None:
                        preserved_backups.add(backup)
                        source = str(backup)
                    else:
                        source = "<new target; no backup>"
                    rollback_errors.append(
                        f"{path} from {source}: {rollback_error}"
                    )
        finally:
            for temporary, _, backup in staged:
                for candidate in (temporary, backup):
                    if candidate is None or candidate in preserved_backups:
                        continue
                    try:
                        candidate.unlink(missing_ok=True)
                    except OSError as cleanup_error:
                        cleanup_errors.append(f"{candidate}: {cleanup_error}")

        if transaction_error is not None:
            details = [
                f"generated-file transaction failed while {operation}: "
                f"{transaction_error}"
            ]
            if rollback_errors:
                details.append("rollback errors: " + "; ".join(rollback_errors))
            if preserved_backups:
                details.append(
                    "preserved rollback backups: "
                    + ", ".join(str(path) for path in sorted(preserved_backups))
                )
            if cleanup_errors:
                details.append("cleanup errors: " + "; ".join(cleanup_errors))
            raise GenerationError("; ".join(details)) from transaction_error
        if cleanup_errors:
            raise GenerationError(
                "generated-file cleanup failed; cleanup errors: "
                + "; ".join(cleanup_errors)
            )

    return GenerationResult(
        tuple(path for path, *_ in outputs),
        changed,
        diff,
    )


def _read_optional_generated(path: Path) -> tuple[bool, bytes]:
    try:
        return True, path.read_bytes()
    except FileNotFoundError:
        return False, b""
    except OSError as error:
        raise GenerationError(
            f"{path}: unable to read generated artifact: {error}"
        ) from error


def _stage_bytes(
    path: Path, payload: bytes, *, suffix: str, mode: int | None = None
) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=suffix, dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
    except BaseException as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            error.add_note(
                f"also failed to clean staging file {temporary}: {cleanup_error}"
            )
        raise
    return temporary


def _default_file_mode() -> int | None:
    if os.name == "nt":
        return None
    current_umask = os.umask(0)
    os.umask(current_umask)
    return 0o666 & ~current_umask


def _publication_mode(
    path: Path, existed: bool, default_mode: int | None
) -> int | None:
    if os.name == "nt":
        return None
    if not existed:
        return default_mode
    return stat.S_IMODE(path.stat().st_mode)


def _tobex_prefix(existing: str) -> str:
    lines = existing.splitlines(keepends=True)
    first_assignment_seen = False
    end = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            if first_assignment_seen and stripped:
                break
            if not first_assignment_seen:
                end = index + 1
            elif not stripped:
                end = index + 1
            continue
        if first_assignment_seen:
            break
        if (
            re.fullmatch(
                r"(?i)install_tobex[ \t]*=[ \t]*1(?:[ \t]*//[^\r\n]*)?",
                stripped,
            )
            is None
        ):
            raise GenerationError(
                "install_tobex = 1 must remain the first non-comment settings assignment"
            )
        first_assignment_seen = True
        end = index + 1
    if not first_assignment_seen:
        raise GenerationError(
            "settings.ini is missing its first install_tobex = 1 assignment"
        )
    # Preserve blank lines immediately following the legacy assignment, but no
    # previous generated content.
    while end < len(lines) and not lines[end].strip():
        end += 1
    return "".join(lines[:end])


def _change_text(
    catalog: Catalog,
    change: Change,
    index: int,
    texts: Mapping[str, str],
) -> tuple[str, str]:
    if change.member_refs:
        return (
            change.display_name,
            f"One atomic option controls {len(change.member_refs)} member spells "
            "listed below.",
        )
    name = (
        resolve_tra_reference(
            texts, change.name_ref, path=f"changes[{index}].name_ref"
        )
        if change.name_ref is not None
        else change.display_name
    )
    assert change.description_ref is not None
    description = resolve_tra_reference(
        texts,
        change.description_ref,
        path=f"changes[{index}].description_ref",
    )
    if change.name_fallback is not None:
        description = (
            "Name retained from installed game resource "
            f"{change.name_fallback.resource}. {description}"
        )
    return name, description


def _member_text(
    change_index: int,
    member_index: int,
    member: MemberReference,
    texts: Mapping[str, str],
) -> tuple[str, str]:
    prefix = f"changes[{change_index}].member_refs[{member_index}]"
    name = _resolved_name(
        member.name_ref,
        member.name_fallback,
        texts,
        path=prefix,
    )
    description = resolve_tra_reference(
        texts,
        member.description_ref,
        path=f"{prefix}.description_ref",
    )
    return name, description


def _resolved_name(
    reference: str | None,
    fallback: NameFallback | None,
    texts: Mapping[str, str],
    *,
    path: str,
) -> str:
    if reference is not None:
        return resolve_tra_reference(texts, reference, path=f"{path}.name_ref")
    assert fallback is not None
    return f"Game-provided name ({fallback.resource})"


def _relations(
    relation_ids: tuple[str, ...], change_by_id: Mapping[str, Change]
) -> str:
    if not relation_ids:
        return "None"
    return ", ".join(change_by_id[value.casefold()].setting for value in relation_ids)


def _provenance(catalog: Catalog, change: Change) -> str:
    base = f"{catalog.upstream.tag} {catalog.upstream.commit}"
    if not change.source_spans:
        return base
    spans = "; ".join(
        f"{span.path}: {span.start} .. "
        f"{span.end if span.end is not None else 'EOF'} [{span.sha256}]"
        for span in change.source_spans
    )
    return f"{base}; {spans}"


def _span_provenance(source_spans) -> str:
    if not source_spans:
        return "None"
    return "; ".join(
        f"{span.path}: {span.start} .. "
        f"{span.end if span.end is not None else 'EOF'} [{span.sha256}]"
        for span in source_spans
    )


def _resource_provenance(resources) -> str:
    if not resources:
        return "None"
    return ", ".join(f"{resource.path} ({resource.kind})" for resource in resources)


def _markdown_code(value: str) -> str:
    content = single_line(value).replace("|", "\\|")
    longest_run = max(
        (len(match.group(0)) for match in re.finditer(r"`+", content)),
        default=0,
    )
    delimiter = "`" * (longest_run + 1)
    padding = " " if content.startswith("`") or content.endswith("`") else ""
    return f"{delimiter}{padding}{content}{padding}{delimiter}"


def _append_markdown_support_sections(lines: list[str], catalog: Catalog) -> None:
    lines.extend(("", "## Support infrastructure", ""))
    if catalog.infrastructure:
        lines.extend(
            (
                "| ID | Category | Activation | Infrastructure requires | "
                "Consumers | Resources | Upstream provenance |",
                "|---|---|---|---|---|---|---|",
            )
        )
        for record in catalog.infrastructure:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _markdown_code(record.id),
                        _markdown_code(record.category),
                        _markdown_code(record.activation),
                        ", ".join(
                            _markdown_code(value)
                            for value in record.infrastructure_requires
                        )
                        or "None",
                        ", ".join(
                            _markdown_code(value) for value in record.consumers
                        )
                        or "None",
                        _markdown(_resource_provenance(record.resources)),
                        _markdown(_span_provenance(record.source_spans)),
                    )
                )
                + " |"
            )
    else:
        lines.append("No support infrastructure is declared.")

    lines.extend(("", "## Component-zero supplemental closure roots", ""))
    if catalog.component_zero_closure_roots:
        lines.extend(
            (
                "| Infrastructure owner | Exact entry span |",
                "|---|---|",
            )
        )
        for root in catalog.component_zero_closure_roots:
            lines.append(
                f"| {_markdown_code(root.owner)} | "
                f"{_markdown(_span_provenance((root.source_span,)))} |"
            )
    else:
        lines.append("No supplemental component-zero closure roots are declared.")

    lines.extend(("", "## Deferred source scopes", ""))
    if catalog.deferred_source_scopes:
        lines.extend(
            (
                "| ID | Reason | Exact source spans | Resources |",
                "|---|---|---|---|",
            )
        )
        for record in catalog.deferred_source_scopes:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _markdown_code(record.id),
                        _markdown(record.reason),
                        _markdown(_span_provenance(record.source_spans)),
                        _markdown(_resource_provenance(record.resources)),
                    )
                )
                + " |"
            )
    else:
        lines.append("No deferred source scopes are declared.")

    lines.extend(("", "## Dormant payloads", ""))
    if catalog.dormant_resources:
        lines.extend(("| Exact repository path | Reason |", "|---|---|"))
        for record in catalog.dormant_resources:
            lines.append(
                f"| {_markdown_code(record.path)} | {_markdown(record.reason)} |"
            )
    else:
        lines.append("No dormant payloads are declared.")

    lines.extend(("", "## Audited binary-external overrides", ""))
    if catalog.binary_edge_resolutions:
        lines.extend(
            (
                "| Source / offset | Field | Opcode | Target / expected types | "
                "Complete shadowed candidates | Classification / reason |",
                "|---|---|---:|---|---|---|",
            )
        )
        for record in catalog.binary_edge_resolutions:
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"{_markdown_code(record.source)} / {_markdown_code(hex(record.offset))}",
                        _markdown_code(record.field),
                        "null" if record.opcode is None else str(record.opcode),
                        f"{_markdown_code(record.target)} / "
                        + ", ".join(
                            _markdown_code(value) for value in record.expected_types
                        ),
                        ", ".join(
                            _markdown_code(value)
                            for value in record.shadowed_candidates
                        ),
                        f"{_markdown_code(record.classification)} / "
                        f"{_markdown(record.reason)}",
                    )
                )
                + " |"
            )
    else:
        lines.append("No binary-external overrides are declared.")


def _append_html_support_sections(lines: list[str], catalog: Catalog) -> None:
    lines.append("<h4>Support infrastructure</h4>")
    if catalog.infrastructure:
        rows = []
        for record in catalog.infrastructure:
            rows.append(
                (
                    record.id,
                    record.category,
                    record.activation,
                    ", ".join(record.infrastructure_requires) or "None",
                    ", ".join(record.consumers) or "None",
                    _resource_provenance(record.resources),
                    _span_provenance(record.source_spans),
                )
            )
        _append_html_table(
            lines,
            (
                "ID",
                "Category",
                "Activation",
                "Infrastructure requires",
                "Consumers",
                "Resources",
                "Upstream provenance",
            ),
            rows,
            "sr-config-infrastructure",
        )
    else:
        lines.append("<p>No support infrastructure is declared.</p>")

    lines.append("<h4>Component-zero supplemental closure roots</h4>")
    if catalog.component_zero_closure_roots:
        _append_html_table(
            lines,
            ("Infrastructure owner", "Exact entry span"),
            [
                (
                    root.owner,
                    _span_provenance((root.source_span,)),
                )
                for root in catalog.component_zero_closure_roots
            ],
            "sr-config-closure-roots",
        )
    else:
        lines.append(
            "<p>No supplemental component-zero closure roots are declared.</p>"
        )

    lines.append("<h4>Deferred source scopes</h4>")
    if catalog.deferred_source_scopes:
        _append_html_table(
            lines,
            ("ID", "Reason", "Exact source spans", "Resources"),
            [
                (
                    record.id,
                    record.reason,
                    _span_provenance(record.source_spans),
                    _resource_provenance(record.resources),
                )
                for record in catalog.deferred_source_scopes
            ],
            "sr-config-deferred",
        )
    else:
        lines.append("<p>No deferred source scopes are declared.</p>")

    lines.append("<h4>Dormant payloads</h4>")
    if catalog.dormant_resources:
        _append_html_table(
            lines,
            ("Exact repository path", "Reason"),
            [(record.path, record.reason) for record in catalog.dormant_resources],
            "sr-config-dormant",
        )
    else:
        lines.append("<p>No dormant payloads are declared.</p>")

    lines.append("<h4>Audited binary-external overrides</h4>")
    if catalog.binary_edge_resolutions:
        _append_html_table(
            lines,
            (
                "Source / offset",
                "Field",
                "Opcode",
                "Target / expected types",
                "Complete shadowed candidates",
                "Classification / reason",
            ),
            [
                (
                    f"{record.source} / {hex(record.offset)}",
                    record.field,
                    "null" if record.opcode is None else str(record.opcode),
                    f"{record.target} / {', '.join(record.expected_types)}",
                    ", ".join(record.shadowed_candidates),
                    f"{record.classification} / {record.reason}",
                )
                for record in catalog.binary_edge_resolutions
            ],
            "sr-config-binary-overrides",
        )
    else:
        lines.append("<p>No binary-external overrides are declared.</p>")


def _append_html_table(
    lines: list[str],
    headings: tuple[str, ...],
    rows: list[tuple[str, ...]],
    css_class: str,
) -> None:
    lines.extend(
        (
            f'<table class="{css_class}">',
            "  <thead>",
            "    <tr>"
            + "".join(f"<th>{_html(heading)}</th>" for heading in headings)
            + "</tr>",
            "  </thead>",
            "  <tbody>",
        )
    )
    for row in rows:
        lines.append(
            "    <tr>"
            + "".join(f"<td>{_html(value)}</td>" for value in row)
            + "</tr>"
        )
    lines.extend(("  </tbody>", "</table>"))


def _effective_default_label(catalog: Catalog, change: Change) -> str:
    groups = {record.id.casefold(): record for record in catalog.groups}
    current: Group = groups[change.group.casefold()]
    while current.default == -1:
        if current.parent is None:
            raise GenerationError("root group unexpectedly inherits")
        current = groups[current.parent.casefold()]
    return "Enabled (inherits)" if current.default == 1 else "Disabled (inherits)"


def _markdown(value: str) -> str:
    escaped = html.escape(single_line(value), quote=False)
    special = frozenset(r"\|`*_{}[]()#+-!")
    return "".join(
        f"\\{character}" if character in special else character
        for character in escaped
    )


def _html(value: str) -> str:
    return html.escape(single_line(value), quote=True).encode(
        "ascii", errors="xmlcharrefreplace"
    ).decode("ascii")


def single_line(value: str) -> str:
    return " ".join(value.splitlines()).strip()


def _detect_newline_text(source: str, path: Path) -> str:
    return _detect_newline_bytes(source.encode("utf-8"), path).decode("ascii")


def _detect_newline_bytes(source: bytes, path: Path) -> bytes:
    has_crlf = b"\r\n" in source
    without_crlf = source.replace(b"\r\n", b"")
    has_lone_cr = b"\r" in without_crlf
    has_lone_lf = b"\n" in without_crlf
    if has_lone_cr:
        if has_crlf or has_lone_lf:
            raise GenerationError(f"{path.as_posix()}: mixed newline conventions")
        raise GenerationError(
            f"{path.as_posix()}: unsupported lone CR newline convention"
        )
    if has_crlf:
        if has_lone_lf:
            raise GenerationError(f"{path.as_posix()}: mixed newline conventions")
        return b"\r\n"
    if has_lone_lf:
        return b"\n"
    return b"\n"


def _with_newline(source: str, newline: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)


def _unified_diff(
    path: Path, current: bytes, expected: bytes, encoding: str
) -> str:
    current_text = current.decode(encoding, errors="replace").replace("\r\n", "\n")
    expected_text = expected.decode(encoding, errors="replace").replace("\r\n", "\n")
    return "".join(
        difflib.unified_diff(
            current_text.splitlines(keepends=True),
            expected_text.splitlines(keepends=True),
            fromfile=f"{path.as_posix()} (current)",
            tofile=f"{path.as_posix()} (generated)",
        )
    )
