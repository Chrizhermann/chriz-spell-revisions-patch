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

from .catalog import Catalog, Change, Group, load_catalog
from .resolve import feature_symbols
from .text import TraError, load_english_tra, resolve_tra_reference


BEGIN_MARKER = "<!-- SR_CONFIG_CATALOG_BEGIN -->"
END_MARKER = "<!-- SR_CONFIG_CATALOG_END -->"

_CATALOG_PATH = Path("spell_rev/catalog/changes.json")
_CONFIG_PATH = Path("spell_rev/settings.ini")
_MARKDOWN_PATH = Path("docs/spell-revisions-change-catalog.md")
_HTML_PATH = Path("spell_rev/readme-spell_rev.html")
_LEGACY_START = re.compile(
    rb'(?m)^  <p>\r?\n    <a id="spell_changes"></a>'
    rb"<strong>Overview of Divine Spell Changes</strong>"
)
_LEGACY_END = re.compile(
    rb'(?m)^</div>\r?\n\r?\n<h2>Contact Information</h2>'
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
    if not catalog.changes:
        lines.extend(
            [
                "",
                "No public changes have been cataloged yet. The migration gate remains "
                "closed until upstream classification is complete.",
            ]
        )
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
    if not catalog.changes:
        lines.append(
            "<p>No public changes have been cataloged yet. The migration gate remains "
            "closed until upstream classification is complete.</p>"
        )
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
    rendered_html = render_html_document(html_bytes, html_region)
    outputs = (
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
    name = (
        resolve_tra_reference(texts, change.name_ref, path=f"changes[{index}].name_ref")
        if change.name_ref is not None
        else change.display_name
    )
    description = (
        resolve_tra_reference(
            texts,
            change.description_ref,
            path=f"changes[{index}].description_ref",
        )
        if change.description_ref is not None
        else change.documentation_only_reason or "No description supplied."
    )
    return name, description


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
        f"{span.path}: {span.start} .. {span.end} [{span.sha256}]"
        for span in change.source_spans
    )
    return f"{base}; {spans}"


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
