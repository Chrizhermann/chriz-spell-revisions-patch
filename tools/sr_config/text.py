"""Strict parsing and lookup of the current English WeiDU TRA sources."""

from __future__ import annotations

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

    def line_at(offset: int) -> int:
        return source.count("\n", 0, offset) + 1

    while index < length:
        while index < length and source[index].isspace():
            index += 1
        if index >= length:
            break
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
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
        # After a value, only horizontal whitespace and a line comment may share
        # the physical line. The next assignment begins after a newline.
        while index < length and source[index] in " \t\r":
            index += 1
        if index < length and source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
        elif index < length and source[index] != "\n":
            raise TraError(
                f"{source_name}:{line_at(index)}: unexpected content after {reference}"
            )
        elif index < length:
            index += 1

    return values


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
