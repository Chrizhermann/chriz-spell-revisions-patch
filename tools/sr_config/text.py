"""Strict parsing and lookup of the current English WeiDU TRA sources."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from pathlib import Path


class TraError(ValueError):
    """Raised when a TRA file cannot be parsed or a reference is unresolved."""


def parse_tra(source: str, *, source_name: str = "<TRA>") -> dict[str, str]:
    """Parse WeiDU ``@number = delimiter...delimiter`` assignments losslessly."""

    values: dict[str, str] = {}
    locations: dict[str, int] = {}
    length = len(source)
    index = 0
    line_starts = _line_starts(source)

    def line_at(offset: int) -> int:
        return bisect_right(line_starts, offset)

    while index < length:
        while index < length and source[index].isspace():
            index += 1
        if index >= length:
            break
        if source.startswith("//", index):
            index = _after_line_end(source, index + 2)
            continue
        if source.startswith("/*", index):
            end_comment = source.find("*/", index + 2)
            if end_comment < 0:
                raise TraError(
                    f"{source_name}:{line_at(index)}: unterminated block comment"
                )
            index = end_comment + 2
            continue
        assignment_line = line_at(index)
        if source[index] != "@":
            raise TraError(
                f"{source_name}:{assignment_line}: unexpected content outside an assignment"
            )
        reference_start = index
        index += 1
        digits_start = index
        while index < length and source[index].isdigit():
            index += 1
        if index == digits_start:
            raise TraError(f"{source_name}:{assignment_line}: malformed assignment")
        raw_reference = source[reference_start:index]
        reference = f"@{int(raw_reference[1:])}"
        while index < length and source[index] in " \t\r\n":
            index += 1
        if index >= length or source[index] != "=":
            raise TraError(f"{source_name}:{assignment_line}: malformed assignment")
        index += 1
        while index < length and source[index] in " \t":
            index += 1
        if index >= length or source[index] not in '~"%':
            raise TraError(f"{source_name}:{assignment_line}: malformed assignment")
        delimiter = source[index]
        value_start = index + 1
        value_end = source.find(delimiter, value_start)
        if value_end < 0:
            raise TraError(
                f"{source_name}:{assignment_line}: unterminated {delimiter!r} value "
                f"for {reference}"
            )
        if reference in values:
            raise TraError(
                f"{source_name}:{assignment_line}: duplicate reference {reference}; "
                f"first assigned on line {locations[reference]}"
            )
        values[reference] = source[value_start:value_end]
        locations[reference] = assignment_line
        index = value_end + 1

        # WeiDU permits one optional bracketed sound reference after the text.
        # Block comments are ignored tokens and may appear on either side of it;
        # arbitrary suffix tokens remain an error so syntax is never truncated.
        sound_seen = False
        while index < length:
            while index < length and source[index].isspace():
                index += 1
            if index >= length:
                break
            if source.startswith("/*", index):
                comment_line = line_at(index)
                end_comment = source.find("*/", index + 2)
                if end_comment < 0:
                    raise TraError(
                        f"{source_name}:{comment_line}: unterminated block comment "
                        f"after {reference}"
                    )
                index = end_comment + 2
                while index < length and source[index] in " \t":
                    index += 1
                continue
            if source[index] == "[" and not sound_seen:
                sound_line = line_at(index)
                sound_end = source.find("]", index + 1)
                newline_positions = tuple(
                    position
                    for position in (
                        source.find("\r", index + 1),
                        source.find("\n", index + 1),
                    )
                    if position >= 0
                )
                first_newline = min(newline_positions, default=length)
                if sound_end < 0 or sound_end > first_newline:
                    raise TraError(
                        f"{source_name}:{sound_line}: unterminated sound reference "
                        f"after {reference}"
                    )
                sound_seen = True
                index = sound_end + 1
                continue
            if source.startswith("//", index):
                index = _after_line_end(source, index + 2)
                continue
            if source[index] == "@":
                break
            raise TraError(
                f"{source_name}:{line_at(index)}: unexpected content after {reference}"
            )

    return values


def _line_starts(source: str) -> tuple[int, ...]:
    """Return offsets for physical lines under CRLF, LF, and CR conventions."""

    starts = [0]
    index = 0
    while index < len(source):
        if source[index] == "\r":
            has_line_feed = (
                index + 1 < len(source) and source[index + 1] == "\n"
            )
            index += 2 if has_line_feed else 1
            starts.append(index)
        elif source[index] == "\n":
            index += 1
            starts.append(index)
        else:
            index += 1
    return tuple(starts)


def _after_line_end(source: str, start: int) -> int:
    """Return the offset after the next CRLF, LF, or CR line ending."""

    carriage_return = source.find("\r", start)
    line_feed = source.find("\n", start)
    positions = tuple(
        position for position in (carriage_return, line_feed) if position >= 0
    )
    if not positions:
        return len(source)
    end = min(positions)
    if source[end] == "\r" and end + 1 < len(source) and source[end + 1] == "\n":
        return end + 2
    return end + 1


def load_english_tra(root: str | Path) -> dict[str, str]:
    """Load and merge the authoritative English arcane/divine/setup TRA files."""

    root_path = Path(root)
    directory = root_path / "spell_rev" / "languages" / "english"
    merged: dict[str, str] = {}
    locations: dict[str, str] = {}
    for filename in ("arcane.tra", "divine.tra", "setup.tra"):
        path = directory / filename
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise TraError(f"{path}: invalid UTF-8 at byte {error.start}") from error
        except OSError as error:
            raise TraError(f"{path}: unable to read TRA file: {error}") from error
        parsed = parse_tra(source, source_name=path.as_posix())
        for reference, value in parsed.items():
            if reference in merged:
                raise TraError(
                    f"{path.as_posix()}: duplicate reference {reference}; first "
                    f"declared in {locations[reference]}"
                )
            merged[reference] = value
            locations[reference] = path.as_posix()
    return merged


def resolve_tra_reference(
    texts: Mapping[str, str], reference: str, *, path: str
) -> str:
    canonical_reference = f"@{int(reference[1:])}"
    try:
        return texts[canonical_reference]
    except KeyError as error:
        raise TraError(f"{path}: missing TRA reference {reference}") from error
