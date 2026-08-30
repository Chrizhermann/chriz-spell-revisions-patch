"""Lossless, conservative inventory helpers for WeiDU source files."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .catalog import SourceSpan


class SourceError(ValueError):
    """Raised when WeiDU source cannot be inventoried or anchored safely."""


@dataclass(frozen=True)
class ResourceOperand:
    """A resource-like quoted operand attached to a WeiDU statement."""

    role: str
    value: str


@dataclass(frozen=True)
class SourceNode:
    """One lossless slice of a WeiDU source file."""

    path: str
    line: int
    kind: str
    command: str | None
    section_comments: tuple[str, ...]
    resource_operands: tuple[ResourceOperand, ...]
    raw: bytes


# Action-level commands are deliberately explicit. Unfamiliar statements are still
# emitted as ``unknown``; the list is used only to separate action statements from
# the patch-language body owned by COPY-family commands.
_COPY_COMMANDS = frozenset(
    {
        "COPY",
        "COPY_ALL_GAM_FILES",
        "COPY_EXISTING",
        "COPY_EXISTING_REGEXP",
        "COPY_LARGE",
        "COPY_RANDOM",
    }
)
_BLOCK_COMMANDS = frozenset(
    {
        "ACTION_BASH_FOR",
        "ACTION_DEFINE_ARRAY",
        "ACTION_DEFINE_ASSOCIATIVE_ARRAY",
        "ACTION_FOR_EACH",
        "ACTION_IF",
        "ACTION_MATCH",
        "ACTION_PHP_EACH",
        "WITH_SCOPE",
        "DEFINE_ACTION_FUNCTION",
        "DEFINE_ACTION_MACRO",
        "DEFINE_PATCH_FUNCTION",
        "DEFINE_PATCH_MACRO",
        "OUTER_FOR",
        "OUTER_INNER_PATCH",
        "OUTER_PATCH",
        "OUTER_WHILE",
    }
)
_CALL_COMMANDS = frozenset(
    {
        "ACTION_TRY",
        "LAF",
        "LAUNCH_ACTION_FUNCTION",
    }
)
_END_DELIMITED_COMMANDS = frozenset(
    {
        "ACTION_TRY",
        "LAF",
        "LAUNCH_ACTION_FUNCTION",
        "LAUNCH_PATCH_FUNCTION",
        "LPF",
        "PATCH_MATCH",
    }
)
_SIMPLE_COMMANDS = frozenset(
    {
        "ADD_AREA_TYPE",
        "ADD_GAM_NPC",
        "ADD_JOURNAL",
        "ADD_KIT",
        "ADD_KIT_EX",
        "ADD_MUSIC",
        "ADD_PROJECTILE",
        "ADD_SECTYPE",
        "ADD_SPELL",
        "ABORT",
        "APPEND",
        "APPEND_COL",
        "APPEND_FILE",
        "APPEND_OUTER",
        "AT_EXIT",
        "AT_INTERACTIVE_EXIT",
        "AT_NOW",
        "AUTO_EVAL_STRINGS",
        "AUTO_TRA",
        "COMPILE",
        "DELETE",
        "DESIGNATED",
        "DISABLE_FROM_KEY",
        "EXTEND_BOTTOM",
        "EXTEND_TOP",
        "FAIL",
        "FORBID_COMPONENT",
        "GET_DIRECTORY_ARRAY",
        "INCLUDE",
        "INSTALL_BY_DEFAULT",
        "LAM",
        "LAUNCH_ACTION_MACRO",
        "LANGUAGE",
        "LOAD_TRA",
        "MKDIR",
        "MOVE",
        "OUTER_SET",
        "OUTER_SNPRINT",
        "OUTER_SPRINT",
        "OUTER_TEXT_SPRINT",
        "PRINT",
        "README",
        "REINCLUDE",
        "REQUIRE_COMPONENT",
        "REQUIRE_PREDICATE",
        "SILENT",
        "STRING_SET",
        "STRING_SET_RANGE",
        "SUBCOMPONENT",
        "UNINSTALL",
        "UNINSTALL_NOW",
        "VERBOSE",
        "WARN",
    }
)
_ACTION_COMMANDS = _COPY_COMMANDS | _BLOCK_COMMANDS | _CALL_COMMANDS | _SIMPLE_COMMANDS
_NESTED_ACTION_BLOCK_COMMANDS = frozenset(
    {
        "ACTION_BASH_FOR",
        "ACTION_FOR_EACH",
        "ACTION_IF",
        "ACTION_MATCH",
        "ACTION_PHP_EACH",
        "ACTION_TRY",
        "DEFINE_ACTION_FUNCTION",
        "DEFINE_ACTION_MACRO",
        "OUTER_FOR",
        "OUTER_WHILE",
        "WITH_SCOPE",
    }
)
_PIPELINE_COMMANDS = _COPY_COMMANDS | {"ADD_SPELL", "APPEND"}
_PIPELINE_TERMINATORS = frozenset(
    {"BUT_ONLY", "BUT_ONLY_IF_IT_CHANGES", "UNLESS"}
)

# These commands/modifiers can legally occur at BEGIN-depth zero while remaining
# part of a COPY-family patch body. The set need not classify them semantically;
# it prevents false action boundaries.
_PATCH_OR_COPY_CONTINUATIONS = frozenset(
    {
        "ADD_CRE_EFFECT",
        "ADD_CRE_ITEM",
        "ADD_MAP_NOTE",
        "ADD_MEMORIZED_SPELL",
        "ADD_SPELL_EFFECT",
        "ADD_KNOWN_SPELL",
        "ALTER_EFFECT",
        "ALTER_ITEM_HEADER",
        "ALTER_SPELL_HEADER",
        "BUT_ONLY",
        "BUT_ONLY_IF_IT_CHANGES",
        "CASE_SENSITIVE",
        "CLEAR_ARRAY",
        "CLONE_EFFECT",
        "COMPILE_BAF_TO_BCS",
        "COUNT_2DA_COLS",
        "COUNT_2DA_ROWS",
        "DECOMPILE_AND_PATCH",
        "DECOMPILE_BCS_TO_BAF",
        "DELETE_BYTES",
        "DELETE_EFFECT",
        "DELETE_ITEM_HEADER",
        "EVALUATE_BUFFER",
        "FOR",
        "FOR_EACH",
        "GET_OFFSET_ARRAY",
        "GLOB",
        "IF_EXISTS",
        "INSERT_BYTES",
        "INNER_ACTION",
        "INNER_PATCH",
        "INSERT_FILE",
        "INT_VAR",
        "LPM",
        "LAUNCH_PATCH_FUNCTION",
        "LAUNCH_PATCH_MACRO",
        "LPF",
        "PATCH_FOR_EACH",
        "PATCH_IF",
        "PATCH_INCLUDE",
        "PATCH_MATCH",
        "PHP_EACH",
        "PATCH_PHP_EACH",
        "PATCH_PRINT",
        "PATCH_READLN",
        "PATCH_WARN",
        "PRETTY_PRINT_2DA",
        "READ_ASCII",
        "READ_BYTE",
        "READ_2DA_ENTRIES_NOW",
        "READ_LONG",
        "READ_SHORT",
        "READ_STRREF",
        "REGEXP",
        "REMOVE_CRE_ITEM",
        "REPLACE",
        "REPLACE_EVALUATE",
        "REPLACE_TEXTUALLY",
        "RET",
        "RET_ARRAY",
        "SAY",
        "SET",
        "SET_2DA_ENTRY",
        "SOURCE_BIFF",
        "SOURCE_FILE",
        "SOURCE_RES",
        "SPRINT",
        "STR_VAR",
        "TEXT_SPRINT",
        "TO_LOWER",
        "TO_UPPER",
        "WHILE",
        "WRITE_ASCII",
        "WRITE_ASCIIE",
        "WRITE_BYTE",
        "WRITE_LONG",
        "WRITE_SHORT",
        "WRITE_STRREF",
    }
)
_COPY_PREFIX_MODIFIERS = frozenset(
    {"CASE_SENSITIVE", "EVALUATE_BUFFER", "GLOB", "IF_EXISTS", "REGEXP"}
)
_IDENTIFIER_RE = re.compile(rb"[A-Za-z_][A-Za-z0-9_#]*")
_PATCH_ASSIGNMENT_RE = re.compile(
    rb"^[ \t]*[A-Za-z_][A-Za-z0-9_#]*[ \t]*(?:[+\-*/]?=)"
)
_DECORATIVE_COMMENT_RE = re.compile(r"[-=_*~. ]+\Z")


@dataclass
class _LexState:
    block_comment: bool = False
    block_comment_line: int | None = None
    quote: int | None = None
    quote_line: int | None = None
    inline_file: bool = False
    inline_file_line: int | None = None


@dataclass(frozen=True)
class _Frame:
    kind: str
    line: int


@dataclass(frozen=True)
class _LexedLine:
    tokens: tuple[str, ...]
    has_code: bool


@dataclass
class _OpenNode:
    start: int
    end: int
    line: int
    command: str
    kind: str
    mode: str
    base_depth: int
    root_opened: bool = False
    pending_close: bool = False
    pipeline_terminated: bool = False


def inventory(
    path: str | Path,
    *,
    root: str | Path | None = None,
    _source: bytes | None = None,
    _display_path_override: str | None = None,
) -> tuple[SourceNode, ...]:
    """Split *path* into lossless trivia and top-level WeiDU statement nodes."""

    source_path = Path(path)
    if _source is None:
        try:
            source = source_path.read_bytes()
        except OSError as error:
            raise SourceError(f"{source_path}: unable to read source: {error}") from error
    else:
        source = _source

    display_path = (
        _display_path_override
        if _display_path_override is not None
        else _display_path(source_path, root)
    )
    lines = tuple(_lines_with_offsets(source))
    lex_state = _LexState()
    frames: list[_Frame] = []
    open_node: _OpenNode | None = None
    emitted: list[tuple[int, int, int, str, str]] = []
    cursor = 0

    def finish(node: _OpenNode) -> None:
        nonlocal cursor
        if cursor < node.start:
            emitted.append((cursor, node.start, _line_at_offset(lines, cursor), "trivia", ""))
        emitted.append((node.start, node.end, node.line, node.kind, node.command))
        cursor = node.end

    for line_number, start, end in lines:
        raw_line = source[start:end]
        depth_before = len(frames)
        lexed = _lex_line(raw_line, lex_state, line_number=line_number)
        tokens = lexed.tokens
        first = tokens[0] if tokens else None
        candidate = _statement_candidate(first)

        if open_node is not None and open_node.pending_close and depth_before == 0:
            if first == "ELSE":
                open_node.end = end
                open_node.pending_close = False
                open_node.root_opened = "BEGIN" in tokens
            elif lexed.has_code:
                finish(open_node)
                open_node = None
            else:
                continue

        if open_node is not None and open_node.mode == "copy" and depth_before == 0:
            if open_node.pipeline_terminated and lexed.has_code:
                finish(open_node)
                open_node = None
            elif candidate is not None:
                complete_operands = _pipeline_operands_complete(
                    open_node.command,
                    source[open_node.start : open_node.end],
                )
                if open_node.command == "ADD_SPELL" and not complete_operands:
                    raise SourceError(
                        f"{display_path}: incomplete ADD_SPELL operands opened "
                        f"at line {open_node.line} before {first} at line "
                        f"{line_number}; expected source, type, level, and IDS name"
                    )
                if _starts_after_pipeline(
                    first,
                    complete_operands=complete_operands,
                    raw_line=raw_line,
                ):
                    finish(open_node)
                    open_node = None

        if open_node is not None and open_node.mode == "include" and depth_before == 0:
            if candidate is not None:
                finish(open_node)
                open_node = None

        if open_node is None and candidate is not None and depth_before == 0:
            command, kind = candidate
            mode = _statement_mode(command, kind, tokens)
            open_node = _OpenNode(
                start=start,
                end=end,
                line=line_number,
                command=command,
                kind=kind,
                mode=mode,
                base_depth=depth_before,
                root_opened="BEGIN" in tokens,
            )
        elif open_node is not None:
            if (
                open_node.mode not in {"copy", "include"}
                or lexed.has_code
                or depth_before > 0
            ):
                open_node.end = end

        for token in tokens:
            if token in _END_DELIMITED_COMMANDS:
                frames.append(_Frame(token, line_number))
                if open_node is not None and open_node.mode == "call":
                    open_node.root_opened = True
            elif token == "BEGIN":
                frames.append(_Frame("BEGIN", line_number))
                if open_node is not None and open_node.mode == "block":
                    open_node.root_opened = True
            elif token == "END":
                if not frames:
                    raise SourceError(
                        f"{display_path}: unmatched END at line {line_number}"
                    )
                frames.pop()

        if (
            open_node is not None
            and open_node.mode == "copy"
            and len(frames) == open_node.base_depth
            and any(token in _PIPELINE_TERMINATORS for token in tokens)
        ):
            open_node.pipeline_terminated = True

        if open_node is None:
            continue
        complete = False
        if open_node.mode == "simple":
            complete = True
        elif open_node.mode == "call":
            complete = (
                open_node.root_opened
                and "END" in tokens
                and len(frames) == open_node.base_depth
            )
        elif open_node.mode == "block":
            complete = (
                open_node.root_opened
                and "END" in tokens
                and len(frames) == open_node.base_depth
            )
        if complete:
            if open_node.mode == "block":
                if _else_awaits_begin(tokens):
                    open_node.root_opened = False
                else:
                    open_node.pending_close = True
            else:
                finish(open_node)
                open_node = None

    if lex_state.quote is not None:
        raise SourceError(
            f"{display_path}: unterminated quote opened at line "
            f"{lex_state.quote_line}"
        )
    if lex_state.block_comment:
        raise SourceError(
            f"{display_path}: unterminated block comment opened at line "
            f"{lex_state.block_comment_line}"
        )
    if lex_state.inline_file:
        raise SourceError(
            f"{display_path}: unterminated inline-file opened at line "
            f"{lex_state.inline_file_line}"
        )
    if (
        open_node is not None
        and open_node.mode in {"block", "call"}
        and not open_node.pending_close
    ):
        raise SourceError(
            f"{display_path}: unterminated {open_node.command} {open_node.mode} "
            f"opened at line {open_node.line}"
        )
    if frames:
        frame = frames[-1]
        raise SourceError(
            f"{display_path}: unterminated {frame.kind} delimiter opened at "
            f"line {frame.line}"
        )
    if open_node is not None:
        finish(open_node)
    if cursor < len(source):
        emitted.append((cursor, len(source), _line_at_offset(lines, cursor), "trivia", ""))
    if not emitted and source == b"":
        return ()

    nodes: list[SourceNode] = []
    last_section: tuple[str, ...] = ()
    for start, end, line_number, kind, command in emitted:
        raw = source[start:end]
        if kind == "trivia":
            comments = _nearest_comment_group(raw)
            if comments:
                last_section = comments
            operands: tuple[ResourceOperand, ...] = ()
            node_command: str | None = None
        else:
            operands = _resource_operands(command, raw)
            node_command = command
        nodes.append(
            SourceNode(
                path=display_path,
                line=line_number,
                kind=kind,
                command=node_command,
                section_comments=last_section if kind != "trivia" else (),
                resource_operands=operands,
                raw=raw,
            )
        )
    return tuple(nodes)


def inventory_nested(node: SourceNode) -> tuple[SourceNode, ...]:
    """Inventory executable action streams nested inside an action block.

    A top-level block remains one lossless node, while dependency-bearing
    commands in its action-language bodies are returned as contextual child
    nodes. Patch-language bodies are intentionally excluded.
    """

    if node.command not in _NESTED_ACTION_BLOCK_COMMANDS:
        return ()

    result: list[SourceNode] = []
    body_ranges = (
        _action_try_bodies(node.raw)
        if node.command == "ACTION_TRY"
        else _top_level_block_bodies(node.raw)
    )
    for start, end in body_ranges:
        line_prefix = node.line - 1 + node.raw[:start].count(b"\n")
        body = b"\n" * line_prefix + node.raw[start:end]
        children = inventory(
            node.path,
            _source=body,
            _display_path_override=node.path,
        )
        for child in children:
            if child.kind == "trivia":
                continue
            result.append(child)
            result.extend(inventory_nested(child))
    return tuple(result)


def _action_try_bodies(source: bytes) -> tuple[tuple[int, int], ...]:
    """Return ACTION_TRY's try stream and executable handler bodies."""

    frames: list[str] = []
    bodies: list[tuple[int, int]] = []
    try_start: int | None = None
    handler_start: int | None = None
    default_start: int | None = None
    for token, start, end in _structural_tokens(source):
        if token in _END_DELIMITED_COMMANDS:
            frames.append(token)
            if len(frames) == 1 and token == "ACTION_TRY":
                try_start = end
        elif token == "WITH" and frames == ["ACTION_TRY"]:
            if try_start is not None:
                bodies.append((try_start, start))
                try_start = None
        elif token == "DEFAULT" and frames == ["ACTION_TRY"]:
            default_start = end
        elif token == "BEGIN":
            if frames == ["ACTION_TRY"]:
                handler_start = end
                default_start = None
            frames.append(token)
        elif token == "END" and frames:
            frame = frames.pop()
            if (
                frame == "BEGIN"
                and frames == ["ACTION_TRY"]
                and handler_start is not None
            ):
                bodies.append((handler_start, start))
                handler_start = None
            elif frame == "ACTION_TRY" and not frames:
                if default_start is not None:
                    bodies.append((default_start, start))
                break
    return tuple(bodies)


def _top_level_block_bodies(source: bytes) -> tuple[tuple[int, int], ...]:
    tokens = _structural_tokens(source)
    bodies: list[tuple[int, int]] = []
    frames: list[str] = []
    body_start: int | None = None
    for token, start, end in tokens:
        if token in _END_DELIMITED_COMMANDS:
            frames.append(token)
        elif token == "BEGIN":
            if not frames:
                body_start = end
            frames.append(token)
        elif token == "END" and frames:
            frame = frames.pop()
            if not frames and frame == "BEGIN" and body_start is not None:
                bodies.append((body_start, start))
                body_start = None
    return tuple(bodies)


def _structural_tokens(source: bytes) -> tuple[tuple[str, int, int], ...]:
    """Return identifiers while masking WeiDU literal regions."""

    tokens: list[tuple[str, int, int]] = []
    index = 0
    line_start = True
    block_comment = False
    inline_file = False
    while index < len(source):
        if line_start:
            line_end = source.find(b"\n", index)
            if line_end < 0:
                line_end = len(source)
            stripped = source[index:line_end].lstrip(b" \t\r")
            if inline_file:
                if stripped.startswith(b">>>>>>>>"):
                    inline_file = False
                index = line_end + (line_end < len(source))
                line_start = True
                continue
            if not block_comment and stripped.startswith(b"<<<<<<<<"):
                inline_file = True
                index = line_end + (line_end < len(source))
                line_start = True
                continue
            line_start = False

        if block_comment:
            close = source.find(b"*/", index)
            if close < 0:
                break
            block_comment = False
            index = close + 2
            continue
        if source.startswith(b"//", index):
            newline = source.find(b"\n", index)
            if newline < 0:
                break
            index = newline + 1
            line_start = True
            continue
        if source.startswith(b"/*", index):
            block_comment = True
            index += 2
            continue
        byte = source[index]
        if byte in (ord("~"), ord('"')):
            close = source.find(bytes((byte,)), index + 1)
            if close < 0:
                break
            line_start = b"\n" in source[index:close]
            index = close + 1
            continue
        match = _IDENTIFIER_RE.match(source, index)
        if match is not None:
            token = match.group().decode("ascii").upper()
            tokens.append((token, match.start(), match.end()))
            index = match.end()
            continue
        if byte == ord("\n"):
            line_start = True
        index += 1
    return tuple(tokens)


@dataclass(frozen=True)
class ResolvedSourceSpan:
    """A validated source span with offsets into its original byte stream."""

    source: bytes
    start: int
    end: int

    @property
    def raw(self) -> bytes:
        return self.source[self.start : self.end]


def resolve_span_offsets(root: str | Path, span: SourceSpan) -> ResolvedSourceSpan:
    """Resolve anchors after newline normalization, preserving original offsets."""

    root_path = Path(root).resolve()
    source_path = (root_path / Path(span.path)).resolve()
    try:
        source_path.relative_to(root_path)
    except ValueError as error:
        raise SourceError(
            f"{span.path}: source span path escapes root {root_path}"
        ) from error
    try:
        source = source_path.read_bytes()
    except OSError as error:
        raise SourceError(f"{span.path}: unable to read source: {error}") from error

    normalized_source, boundaries = _normalize_newlines_with_boundaries(source)
    start_anchor = _normalize_newlines(span.start.encode("utf-8"))
    start_matches = _occurrences(normalized_source, start_anchor)
    if len(start_matches) != 1:
        raise SourceError(
            f"{span.path}: start anchor {span.start!r} has {len(start_matches)} matches; "
            "expected exactly 1"
        )
    start = boundaries[start_matches[0]]
    if span.end is None:
        end = len(source)
    else:
        end_anchor = _normalize_newlines(span.end.encode("utf-8"))
        end_matches = _occurrences(normalized_source, end_anchor)
        if len(end_matches) != 1:
            raise SourceError(
                f"{span.path}: end anchor {span.end!r} has {len(end_matches)} "
                "matches; expected exactly 1"
            )
        end = boundaries[end_matches[0]]
        if end <= start:
            raise SourceError(
                f"{span.path}: end anchor {span.end!r} occurs before start anchor "
                f"{span.start!r}"
            )
    resolved = source[start:end]
    normalized = _normalize_newlines(resolved)
    actual = hashlib.sha256(normalized).hexdigest()
    if actual.casefold() != span.sha256.casefold():
        raise SourceError(
            f"{span.path}: anchor hash changed for {span.start!r} .. "
            f"{span.end if span.end is not None else 'EOF'!r}: "
            f"expected {span.sha256.lower()}, got {actual}"
        )
    return ResolvedSourceSpan(source, start, end)


def resolve_span(root: str | Path, span: SourceSpan) -> bytes:
    """Resolve and hash-check an inclusive-start/exclusive-end source span."""

    return resolve_span_offsets(root, span).raw


def _normalize_newlines(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _normalize_newlines_with_boundaries(
    value: bytes,
) -> tuple[bytes, tuple[int, ...]]:
    normalized = bytearray()
    boundaries = [0]
    index = 0
    while index < len(value):
        if value[index : index + 2] == b"\r\n":
            normalized.append(ord("\n"))
            index += 2
        elif value[index] == ord("\r"):
            normalized.append(ord("\n"))
            index += 1
        else:
            normalized.append(value[index])
            index += 1
        boundaries.append(index)
    return bytes(normalized), tuple(boundaries)


def _display_path(path: Path, root: str | Path | None) -> str:
    if root is None:
        return path.name
    root_path = Path(root).resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(root_path).as_posix()
    except ValueError as error:
        raise SourceError(f"{path}: source is outside inventory root {root_path}") from error


def _lines_with_offsets(source: bytes):
    offset = 0
    for line_number, raw in enumerate(source.splitlines(keepends=True), start=1):
        end = offset + len(raw)
        yield line_number, offset, end
        offset = end
    if source and offset < len(source):
        yield source.count(b"\n") + 1, offset, len(source)


def _line_at_offset(lines: tuple[tuple[int, int, int], ...], offset: int) -> int:
    for line_number, start, end in lines:
        if start <= offset < end:
            return line_number
    return lines[-1][0] if lines else 1


def _lex_line(
    raw: bytes, state: _LexState, *, line_number: int = 1
) -> _LexedLine:
    stripped = raw.lstrip(b" \t\r\n")
    if state.inline_file:
        if stripped.startswith(b">>>>>>>>"):
            state.inline_file = False
            state.inline_file_line = None
        return _LexedLine((), True)
    if not state.block_comment and state.quote is None and stripped.startswith(b"<<<<<<<<"):
        state.inline_file = True
        state.inline_file_line = line_number
        return _LexedLine((), True)

    tokens: list[str] = []
    has_code = False
    index = 0
    while index < len(raw):
        if state.block_comment:
            close = raw.find(b"*/", index)
            if close < 0:
                return _LexedLine(tuple(tokens), has_code)
            state.block_comment = False
            state.block_comment_line = None
            index = close + 2
            continue
        if state.quote is not None:
            close = raw.find(bytes((state.quote,)), index)
            has_code = True
            if close < 0:
                return _LexedLine(tuple(tokens), has_code)
            state.quote = None
            state.quote_line = None
            index = close + 1
            continue
        if raw.startswith(b"//", index):
            break
        if raw.startswith(b"/*", index):
            state.block_comment = True
            state.block_comment_line = line_number
            index += 2
            continue
        byte = raw[index]
        if byte in (ord("~"), ord('"')):
            state.quote = byte
            state.quote_line = line_number
            has_code = True
            index += 1
            continue
        match = _IDENTIFIER_RE.match(raw, index)
        if match is not None:
            tokens.append(match.group().decode("ascii").upper())
            has_code = True
            index = match.end()
            continue
        if byte not in b" \t\r\n":
            has_code = True
        index += 1
    return _LexedLine(tuple(tokens), has_code)


def _statement_candidate(first: str | None) -> tuple[str, str] | None:
    if first is None or first in {"BEGIN", "END", "ELSE"}:
        return None
    if first in _ACTION_COMMANDS:
        return first, "executable"
    return first, "unknown"


def _starts_after_pipeline(
    first: str | None,
    *,
    complete_operands: bool = False,
    raw_line: bytes = b"",
) -> bool:
    if (
        first is None
        or first in _PATCH_OR_COPY_CONTINUATIONS
        or first in _PIPELINE_TERMINATORS
        or _PATCH_ASSIGNMENT_RE.match(raw_line) is not None
    ):
        return False
    return (
        complete_operands
        or first in _ACTION_COMMANDS
        or first.startswith(("ACTION_", "AT_"))
    )


def _pipeline_operands_complete(command: str, raw: bytes) -> bool:
    if command in _COPY_COMMANDS:
        values = _copy_operand_values(raw)
        return len(values) >= 2 and len(values) % 2 == 0
    required = {"ADD_SPELL": 4, "APPEND": 2}.get(command)
    if required is None:
        return False
    atoms = _source_atoms(_copy_prefix(raw))
    command_index = next(
        (
            index
            for index, (value, quoted) in enumerate(atoms)
            if not quoted and value.upper() == command
        ),
        None,
    )
    return (
        command_index is not None
        and len(atoms[command_index + 1 :]) >= required
    )


def _else_awaits_begin(tokens: tuple[str, ...]) -> bool:
    if "ELSE" not in tokens:
        return False
    last_else = len(tokens) - 1 - tokens[::-1].index("ELSE")
    # Patch reads also use ELSE for a fallback value. A branch continuation is
    # instead attached to the END that closed the preceding branch.
    if last_else == 0 or tokens[last_else - 1] != "END":
        return False
    branch_head = tokens[last_else + 1 :]
    if "BEGIN" in branch_head:
        return False
    return not branch_head or branch_head[0] in {"ACTION_IF", "PATCH_IF"}


def _statement_mode(command: str, kind: str, tokens: tuple[str, ...]) -> str:
    if command in _PIPELINE_COMMANDS:
        return "copy"
    if command == "INCLUDE":
        return "include"
    if command in _BLOCK_COMMANDS:
        return "block"
    if command in _CALL_COMMANDS:
        return "call"
    if kind == "unknown" and "BEGIN" in tokens:
        return "block"
    return "simple"


def _nearest_comment_group(raw: bytes) -> tuple[str, ...]:
    text = raw.decode("utf-8-sig", errors="replace")
    groups: list[list[str]] = []
    current: list[str] = []
    in_block = False
    for source_line in text.splitlines():
        stripped = source_line.strip()
        comment: str | None = None
        if in_block:
            before, marker, _ = stripped.partition("*/")
            comment = before.lstrip("*").strip()
            in_block = not bool(marker)
        elif stripped.startswith("//"):
            comment = stripped[2:].strip()
        elif stripped.startswith("/*"):
            body = stripped[2:]
            before, marker, _ = body.partition("*/")
            comment = before.lstrip("*").strip()
            in_block = not bool(marker)
        elif not stripped:
            if current:
                groups.append(current)
                current = []
            continue
        else:
            if current:
                groups.append(current)
                current = []
            continue
        if comment and not _DECORATIVE_COMMENT_RE.fullmatch(comment):
            current.append(comment)
    if current:
        groups.append(current)
    return tuple(groups[-1]) if groups else ()


def _resource_operands(command: str, raw: bytes) -> tuple[ResourceOperand, ...]:
    quoted = _quoted_values(raw)
    if not quoted:
        if command not in _COPY_COMMANDS:
            return ()
    if command in _COPY_COMMANDS:
        values = _copy_operand_values(raw)
        return tuple(
            ResourceOperand("source" if index % 2 == 0 else "destination", value)
            for index, value in enumerate(values)
        )
    if command in {"INCLUDE", "REINCLUDE"}:
        return tuple(ResourceOperand("include", value) for value in quoted)
    if command == "ADD_SPELL":
        values = _quoted_values(_copy_prefix(raw))
        operands = [ResourceOperand("source", values[0])]
        operands.extend(ResourceOperand("symbol", value) for value in values[1:])
        return tuple(operands)
    if command in {"APPEND", "APPEND_OUTER"}:
        prefix = _copy_prefix(raw) if command == "APPEND" else raw
        atoms = _source_atoms(prefix)
        command_index = next(
            (
                index
                for index, (value, quoted) in enumerate(atoms)
                if not quoted and value.upper() == command
            ),
            None,
        )
        if command_index is None or command_index + 1 >= len(atoms):
            return ()
        return (ResourceOperand("target", atoms[command_index + 1][0]),)
    if command in _CALL_COMMANDS:
        return tuple(ResourceOperand("argument", value) for value in quoted)
    if command in _BLOCK_COMMANDS:
        # Nested command strings are owned by the outer block. Only the block head
        # is source-level dependency evidence for this conservative inventory.
        head = raw.splitlines(keepends=True)[0] if raw.splitlines() else raw
        return tuple(ResourceOperand("condition", value) for value in _quoted_values(head))
    if command == "LAM":
        # The quoted macro name is executable identity, not a resource dependency.
        return ()
    return tuple(ResourceOperand("argument", value) for value in quoted)


def _copy_prefix(raw: bytes) -> bytes:
    state = _LexState()
    offset = 0
    first_line = True
    for line in raw.splitlines(keepends=True):
        lexed = _lex_line(line, state)
        first = lexed.tokens[0] if lexed.tokens else None
        if not first_line and first is not None:
            if first in _PATCH_OR_COPY_CONTINUATIONS - _COPY_PREFIX_MODIFIERS:
                return raw[:offset]
        first_line = False
        offset += len(line)
    return raw


def _copy_operand_values(raw: bytes) -> tuple[str, ...]:
    atoms = _source_atoms(_copy_prefix(raw))
    command_index = next(
        (
            index
            for index, (value, quoted) in enumerate(atoms)
            if not quoted and value.upper() in _COPY_COMMANDS
        ),
        None,
    )
    if command_index is None:
        return ()
    values: list[str] = []
    for value, quoted in atoms[command_index + 1 :]:
        if not quoted and value.upper() in _COPY_PREFIX_MODIFIERS:
            continue
        values.append(value)
    return tuple(values)


def _source_atoms(raw: bytes) -> tuple[tuple[str, bool], ...]:
    """Return ordered quoted/bare atoms while masking WeiDU opaque regions."""

    atoms: list[tuple[str, bool]] = []
    index = 0
    block_comment = False
    inline_file = False
    line_start = True
    while index < len(raw):
        if line_start:
            line_end = raw.find(b"\n", index)
            if line_end < 0:
                line_end = len(raw)
            stripped = raw[index:line_end].lstrip(b" \t\r")
            if inline_file:
                if stripped.startswith(b">>>>>>>>"):
                    inline_file = False
                index = line_end + (line_end < len(raw))
                line_start = True
                continue
            if not block_comment and stripped.startswith(b"<<<<<<<<"):
                inline_file = True
                index = line_end + (line_end < len(raw))
                line_start = True
                continue
            line_start = False
        if block_comment:
            close = raw.find(b"*/", index)
            if close < 0:
                break
            block_comment = False
            index = close + 2
            continue
        if raw.startswith(b"//", index):
            newline = raw.find(b"\n", index)
            if newline < 0:
                break
            index = newline + 1
            line_start = True
            continue
        if raw.startswith(b"/*", index):
            block_comment = True
            index += 2
            continue
        byte = raw[index]
        if byte in (ord("~"), ord('"')):
            close = raw.find(bytes((byte,)), index + 1)
            if close < 0:
                break
            atoms.append(
                (
                    raw[index + 1 : close].decode("utf-8", errors="replace"),
                    True,
                )
            )
            index = close + 1
            continue
        if byte in b" \t\r\n":
            if byte == ord("\n"):
                line_start = True
            index += 1
            continue
        start = index
        while index < len(raw):
            if raw[index] in b" \t\r\n~\"":
                break
            if raw.startswith(b"//", index) or raw.startswith(b"/*", index):
                break
            index += 1
        if index == start:
            index += 1
            continue
        atoms.append(
            (raw[start:index].decode("utf-8", errors="replace"), False)
        )
    return tuple(atoms)


def _quoted_values(raw: bytes) -> tuple[str, ...]:
    values: list[str] = []
    index = 0
    block_comment = False
    inline_file = False
    line_start = True
    while index < len(raw):
        if line_start:
            line_end = raw.find(b"\n", index)
            if line_end < 0:
                line_end = len(raw)
            stripped = raw[index:line_end].lstrip(b" \t\r")
            if inline_file:
                if stripped.startswith(b">>>>>>>>"):
                    inline_file = False
                index = line_end + (line_end < len(raw))
                line_start = True
                continue
            if not block_comment and stripped.startswith(b"<<<<<<<<"):
                inline_file = True
                index = line_end + (line_end < len(raw))
                line_start = True
                continue
            line_start = False
        if block_comment:
            close = raw.find(b"*/", index)
            if close < 0:
                break
            block_comment = False
            index = close + 2
            continue
        if raw.startswith(b"//", index):
            newline = raw.find(b"\n", index)
            if newline < 0:
                break
            index = newline + 1
            line_start = True
            continue
        if raw.startswith(b"/*", index):
            block_comment = True
            index += 2
            continue
        byte = raw[index]
        if byte in (ord("~"), ord('"')):
            close = raw.find(bytes((byte,)), index + 1)
            if close < 0:
                break
            values.append(raw[index + 1 : close].decode("utf-8", errors="replace"))
            index = close + 1
            continue
        if byte == ord("\n"):
            line_start = True
        index += 1
    return tuple(values)


def _occurrences(haystack: bytes, needle: bytes) -> tuple[int, ...]:
    if not needle:
        return ()
    positions: list[int] = []
    start = 0
    while True:
        position = haystack.find(needle, start)
        if position < 0:
            return tuple(positions)
        positions.append(position)
        start = position + 1
