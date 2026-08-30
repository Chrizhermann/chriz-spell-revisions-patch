"""Deterministic, format-aware dependency edges for shipped IE resources."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


class ResourceError(ValueError):
    """Raised when an Infinity Engine resource is malformed or unreadable."""


@dataclass(frozen=True)
class ResourceEdge:
    """One resource reference with exact binary provenance."""

    source: str
    format: str
    field: str
    target: str
    offset: int
    opcode: int | None
    classification: str
    local_candidates: tuple[str, ...]


@dataclass(frozen=True)
class ScannedResource:
    """One scanned package resource, including files with no outgoing edges."""

    path: str
    format: str
    edges: tuple[ResourceEdge, ...]


ResourceIndex = Mapping[str, tuple[str, ...]]

_FORMATS = {
    ".spl": "SPL V1",
    ".itm": "ITM V1",
    ".eff": "EFF V2",
    ".cre": "CRE V1",
}
_HEADER_SIZE = {"SPL V1": 0x72, "ITM V1": 0x72, "CRE V1": 0x2D4}


def build_resource_index(root: str | Path) -> ResourceIndex:
    """Index package files by case-insensitive resref, preserving path spelling."""

    root_path = Path(root)
    if not root_path.is_dir():
        raise ResourceError(f"{root_path}: package root is not a directory")
    try:
        files = tuple(path for path in root_path.rglob("*") if path.is_file())
    except OSError as error:
        raise ResourceError(f"{root_path}: unable to index package: {error}") from error
    candidates: dict[str, list[str]] = {}
    for path in files:
        relative = path.relative_to(root_path).as_posix()
        candidates.setdefault(path.stem.casefold(), []).append(relative)
    frozen = {
        key: tuple(sorted(values, key=lambda value: (value.casefold(), value)))
        for key, values in candidates.items()
    }
    return MappingProxyType(frozen)


def scan_resource_edges(
    path: str | Path,
    *,
    package_root: str | Path | None = None,
    resource_index: ResourceIndex | None = None,
) -> tuple[ResourceEdge, ...]:
    """Scan one SPL/ITM/EFF/CRE resource without heuristic string hunting."""

    source_path = Path(path)
    suffix = source_path.suffix.casefold()
    format_name = _FORMATS.get(suffix)
    if format_name is None:
        raise ResourceError(
            f"{source_path}: unsupported resource path {source_path.suffix!r}; "
            "expected .spl, .itm, .eff, or .cre"
        )
    try:
        data = source_path.read_bytes()
    except OSError as error:
        raise ResourceError(f"{source_path}: unable to read resource: {error}") from error

    display_path = _display_path(source_path, package_root)
    if resource_index is None:
        resource_index = (
            build_resource_index(package_root) if package_root is not None else {}
        )
    builder = _EdgeBuilder(display_path, format_name, data, resource_index)
    if suffix == ".spl":
        _scan_spl(builder)
    elif suffix == ".itm":
        _scan_itm(builder)
    elif suffix == ".eff":
        _scan_eff(builder)
    else:
        _scan_cre(builder)
    return builder.finish()


def scan_package_resources(root: str | Path) -> tuple[ScannedResource, ...]:
    """Scan every supported resource below *root* in stable path order."""

    root_path = Path(root)
    index = build_resource_index(root_path)
    try:
        paths = sorted(
            (
                path
                for path in root_path.rglob("*")
                if path.is_file() and path.suffix.casefold() in _FORMATS
            ),
            key=lambda path: (
                path.relative_to(root_path).as_posix().casefold(),
                path.relative_to(root_path).as_posix(),
            ),
        )
    except OSError as error:
        raise ResourceError(f"{root_path}: unable to enumerate package: {error}") from error

    resources: list[ScannedResource] = []
    for path in paths:
        relative = path.relative_to(root_path).as_posix()
        edges = scan_resource_edges(
            path, package_root=root_path, resource_index=index
        )
        resources.append(
            ScannedResource(
                path=relative,
                format=_FORMATS[path.suffix.casefold()],
                edges=edges,
            )
        )
    return tuple(resources)


def scan_package_edges(root: str | Path) -> tuple[ResourceEdge, ...]:
    """Flatten :func:`scan_package_resources` without dropping duplicates."""

    return tuple(
        edge for resource in scan_package_resources(root) for edge in resource.edges
    )


class _EdgeBuilder:
    def __init__(
        self,
        source: str,
        format_name: str,
        data: bytes,
        resource_index: ResourceIndex,
    ) -> None:
        self.source = source
        self.format = format_name
        self.data = data
        self.resource_index = resource_index
        self._edges: list[tuple[int, ResourceEdge]] = []
        self._serial = 0

    def error(self, message: str) -> ResourceError:
        return ResourceError(f"{self.source}: {message}")

    def add(self, field: str, offset: int, opcode: int | None = None) -> None:
        target = _resref(self, field, offset)
        if not target or target.casefold() == "none":
            return
        candidates = self.resource_index.get(target.casefold(), ())
        edge = ResourceEdge(
            source=self.source,
            format=self.format,
            field=field,
            target=target,
            offset=offset,
            opcode=opcode,
            classification="local" if candidates else "external",
            local_candidates=tuple(candidates),
        )
        self._edges.append((self._serial, edge))
        self._serial += 1

    def finish(self) -> tuple[ResourceEdge, ...]:
        return tuple(
            edge
            for _, edge in sorted(
                self._edges, key=lambda item: (item[1].offset, item[0])
            )
        )


def _scan_spl(builder: _EdgeBuilder) -> None:
    data = builder.data
    _signature(builder, b"SPL V1  ", _HEADER_SIZE[builder.format])
    builder.add("header.completion_sound", 0x10)
    builder.add("header.spellbook_icon", 0x3A)
    builder.add("header.ground_icon", 0x44)
    builder.add("header.description_icon", 0x58)

    ability_offset = _u32(builder, 0x64, "ability table offset field 0x64")
    ability_count = _u16(builder, 0x68, "ability table count field 0x68")
    effect_offset = _u32(builder, 0x6A, "effect table offset field 0x6a")
    casting_first = _u16(builder, 0x6E, "casting effect index field 0x6e")
    casting_count = _u16(builder, 0x70, "casting effect count field 0x70")
    ability_range = _table_range(
        builder,
        name="ability table",
        offset=ability_offset,
        count=ability_count,
        stride=0x28,
        field_offset=0x64,
        header_size=0x72,
    )

    slices: list[tuple[str, int, int]] = [("casting_effect", casting_first, casting_count)]
    for ability_index in range(ability_count):
        offset = ability_offset + ability_index * 0x28
        builder.add(f"ability[{ability_index}].icon", offset + 0x04)
        count = _u16(
            builder,
            offset + 0x1E,
            f"ability[{ability_index}] effect count at 0x{offset + 0x1E:x}",
        )
        first = _u16(
            builder,
            offset + 0x20,
            f"ability[{ability_index}] effect index at 0x{offset + 0x20:x}",
        )
        slices.append((f"ability[{ability_index}].effect", first, count))

    effect_count, effect_range = _effect_table(
        builder,
        effect_offset,
        field_offset=0x6A,
        header_size=0x72,
        stride=0x30,
        required=max((first + count for _, first, count in slices), default=0),
    )
    _reject_overlap(builder, ability_range, effect_range)
    referenced: set[int] = set()
    for scope, first, count in slices:
        _check_effect_slice(builder, scope, first, count, effect_count)
        for relative_index in range(count):
            index = first + relative_index
            referenced.add(index)
            effect = effect_offset + index * 0x30
            opcode = _u16(builder, effect, f"{scope}[{relative_index}] opcode")
            builder.add(
                f"{scope}[{relative_index}].resource", effect + 0x14, opcode
            )
    for index in range(effect_count):
        if index not in referenced:
            effect = effect_offset + index * 0x30
            opcode = _u16(builder, effect, f"effect[{index}] opcode")
            builder.add(f"effect[{index}].resource", effect + 0x14, opcode)


def _scan_itm(builder: _EdgeBuilder) -> None:
    data = builder.data
    _signature(builder, b"ITM V1  ", _HEADER_SIZE[builder.format])
    builder.add("header.replacement_item", 0x10)
    builder.add("header.inventory_icon", 0x3A)
    builder.add("header.ground_icon", 0x44)
    builder.add("header.description_icon", 0x58)

    ability_offset = _u32(builder, 0x64, "ability table offset field 0x64")
    ability_count = _u16(builder, 0x68, "ability table count field 0x68")
    effect_offset = _u32(builder, 0x6A, "effect table offset field 0x6a")
    equipped_first = _u16(builder, 0x6E, "equipped effect index field 0x6e")
    equipped_count = _u16(builder, 0x70, "equipped effect count field 0x70")
    ability_range = _table_range(
        builder,
        name="ability table",
        offset=ability_offset,
        count=ability_count,
        stride=0x38,
        field_offset=0x64,
        header_size=0x72,
    )

    slices: list[tuple[str, int, int]] = [
        ("equipped_effect", equipped_first, equipped_count)
    ]
    for ability_index in range(ability_count):
        offset = ability_offset + ability_index * 0x38
        builder.add(f"ability[{ability_index}].icon", offset + 0x04)
        count = _u16(
            builder,
            offset + 0x1E,
            f"ability[{ability_index}] effect count at 0x{offset + 0x1E:x}",
        )
        first = _u16(
            builder,
            offset + 0x20,
            f"ability[{ability_index}] effect index at 0x{offset + 0x20:x}",
        )
        slices.insert(-1, (f"ability[{ability_index}].effect", first, count))

    effect_count, effect_range = _effect_table(
        builder,
        effect_offset,
        field_offset=0x6A,
        header_size=0x72,
        stride=0x30,
        required=max((first + count for _, first, count in slices), default=0),
    )
    _reject_overlap(builder, ability_range, effect_range)
    referenced: set[int] = set()
    for scope, first, count in slices:
        _check_effect_slice(builder, scope, first, count, effect_count)
        for relative_index in range(count):
            index = first + relative_index
            referenced.add(index)
            effect = effect_offset + index * 0x30
            opcode = _u16(builder, effect, f"{scope}[{relative_index}] opcode")
            builder.add(
                f"{scope}[{relative_index}].resource", effect + 0x14, opcode
            )
    for index in range(effect_count):
        if index not in referenced:
            effect = effect_offset + index * 0x30
            opcode = _u16(builder, effect, f"effect[{index}] opcode")
            builder.add(f"effect[{index}].resource", effect + 0x14, opcode)


def _scan_eff(builder: _EdgeBuilder) -> None:
    data = builder.data
    if len(data) != 0x110:
        raise builder.error(
            f"EFF V2 size is 0x{len(data):x}; expected exactly 0x110 bytes"
        )
    if data[:8] != b"EFF V2.0":
        raise builder.error(
            f"EFF V2 signature/version at 0x0 is {data[:8]!r}; expected b'EFF V2.0'"
        )
    secondary_preamble = data[8:16]
    if secondary_preamble not in (b"\0" * 8, b" " * 8, b"EFF V2.0"):
        raise builder.error(
            "EFF V2 secondary preamble at 0x8 is "
            f"{secondary_preamble!r}; expected 8 NUL bytes, 8 space bytes, "
            "or b'EFF V2.0'"
        )
    opcode = _u32(builder, 0x10, "effect opcode at 0x10")
    builder.add("effect.resource", 0x30, opcode)
    builder.add("effect.resource2", 0x70, opcode)
    builder.add("effect.resource3", 0x78, opcode)
    builder.add("effect.parent_resource", 0x94, opcode)


def _scan_cre(builder: _EdgeBuilder) -> None:
    data = builder.data
    _signature(builder, b"CRE V1.0", _HEADER_SIZE[builder.format])
    effect_version = data[0x33]
    if effect_version not in (0, 1):
        raise builder.error(
            f"effect version field 0x33 is {effect_version}; expected 0 or 1"
        )

    for field, offset in (
        ("header.small_portrait", 0x34),
        ("header.large_portrait", 0x3C),
        ("header.override_script", 0x248),
        ("header.class_script", 0x250),
        ("header.race_script", 0x258),
        ("header.general_script", 0x260),
        ("header.default_script", 0x268),
        ("header.dialog", 0x2CC),
    ):
        builder.add(field, offset)

    known_offset = _u32(builder, 0x2A0, "known spells offset field 0x2a0")
    known_count = _u32(builder, 0x2A4, "known spells count field 0x2a4")
    info_offset = _u32(builder, 0x2A8, "memorization info offset field 0x2a8")
    info_count = _u32(builder, 0x2AC, "memorization info count field 0x2ac")
    memorized_offset = _u32(
        builder, 0x2B0, "memorized spells offset field 0x2b0"
    )
    memorized_count = _u32(
        builder, 0x2B4, "memorized spells count field 0x2b4"
    )
    slots_offset = _u32(builder, 0x2B8, "item slots offset field 0x2b8")
    items_offset = _u32(builder, 0x2BC, "items offset field 0x2bc")
    items_count = _u32(builder, 0x2C0, "items count field 0x2c0")
    effects_offset = _u32(builder, 0x2C4, "effects offset field 0x2c4")
    effects_count = _u32(builder, 0x2C8, "effects count field 0x2c8")
    effect_stride = 0x30 if effect_version == 0 else 0x108

    ranges = [
        _table_range(builder, "known spells", known_offset, known_count, 0x0C, 0x2A0, 0x2D4),
        _table_range(builder, "memorization info", info_offset, info_count, 0x10, 0x2A8, 0x2D4),
        _table_range(
            builder,
            "memorized spells",
            memorized_offset,
            memorized_count,
            0x0C,
            0x2B0,
            0x2D4,
        ),
        _table_range(builder, "item slots", slots_offset, 1, 0x50, 0x2B8, 0x2D4),
        _table_range(builder, "items", items_offset, items_count, 0x14, 0x2BC, 0x2D4),
        _table_range(
            builder,
            "effects",
            effects_offset,
            effects_count,
            effect_stride,
            0x2C4,
            0x2D4,
        ),
    ]
    for index, left in enumerate(ranges):
        for right in ranges[index + 1 :]:
            _reject_overlap(builder, left, right)

    for index in range(info_count):
        entry = info_offset + index * 0x10
        first = _u32(
            builder, entry + 0x08, f"memorization info[{index}] first index"
        )
        count = _u32(
            builder, entry + 0x0C, f"memorization info[{index}] spell count"
        )
        if first + count > memorized_count:
            raise builder.error(
                f"memorization info[{index}] slice {first}+{count} exceeds "
                f"memorized spell count {memorized_count} (fields at "
                f"0x{entry + 0x08:x}/0x{entry + 0x0C:x})"
            )

    for index in range(known_count):
        builder.add(f"known_spell[{index}]", known_offset + index * 0x0C)
    for index in range(memorized_count):
        builder.add(
            f"memorized_spell[{index}]", memorized_offset + index * 0x0C
        )
    for index in range(items_count):
        builder.add(f"item[{index}]", items_offset + index * 0x14)
    for index in range(effects_count):
        effect = effects_offset + index * effect_stride
        if effect_version == 0:
            opcode = _u16(builder, effect, f"effect[{index}] opcode")
            builder.add(f"effect[{index}].resource", effect + 0x14, opcode)
        else:
            opcode = _u32(builder, effect + 0x08, f"effect[{index}] opcode")
            builder.add(f"effect[{index}].resource", effect + 0x28, opcode)
            builder.add(f"effect[{index}].resource2", effect + 0x68, opcode)
            builder.add(f"effect[{index}].resource3", effect + 0x70, opcode)
            builder.add(
                f"effect[{index}].parent_resource", effect + 0x8C, opcode
            )


def _signature(builder: _EdgeBuilder, expected: bytes, header_size: int) -> None:
    data = builder.data
    if len(data) < header_size:
        raise builder.error(
            f"{builder.format} header is truncated at 0x{len(data):x}; "
            f"expected at least 0x{header_size:x} bytes"
        )
    if data[:8] != expected:
        raise builder.error(
            f"{builder.format} signature/version at 0x0 is {data[:8]!r}; "
            f"expected {expected!r}"
        )


def _u16(builder: _EdgeBuilder, offset: int, field: str) -> int:
    if offset < 0 or offset + 2 > len(builder.data):
        raise builder.error(f"{field} at 0x{offset:x} is out of bounds")
    return struct.unpack_from("<H", builder.data, offset)[0]


def _u32(builder: _EdgeBuilder, offset: int, field: str) -> int:
    if offset < 0 or offset + 4 > len(builder.data):
        raise builder.error(f"{field} at 0x{offset:x} is out of bounds")
    return struct.unpack_from("<I", builder.data, offset)[0]


def _resref(builder: _EdgeBuilder, field: str, offset: int) -> str:
    if offset < 0 or offset + 8 > len(builder.data):
        raise builder.error(f"{field} resref at 0x{offset:x} is out of bounds")
    raw = builder.data[offset : offset + 8].split(b"\0", 1)[0].rstrip(b" ")
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise builder.error(
            f"{field} resref at 0x{offset:x} is not ASCII: {raw!r}"
        ) from error


def _table_range(
    builder: _EdgeBuilder,
    name: str,
    offset: int,
    count: int,
    stride: int,
    field_offset: int,
    header_size: int,
) -> tuple[str, int, int] | None:
    if count == 0:
        if offset > len(builder.data):
            raise builder.error(
                f"{name} offset field 0x{field_offset:x} points to 0x{offset:x}, "
                f"past file size 0x{len(builder.data):x}"
            )
        return None
    end = offset + count * stride
    if offset < header_size:
        raise builder.error(
            f"{name} offset field 0x{field_offset:x} points inside header at "
            f"0x{offset:x}"
        )
    if end > len(builder.data):
        raise builder.error(
            f"{name} offset/count from field 0x{field_offset:x} spans "
            f"0x{offset:x}..0x{end:x}, past file size 0x{len(builder.data):x}"
        )
    return name, offset, end


def _effect_table(
    builder: _EdgeBuilder,
    offset: int,
    *,
    field_offset: int,
    header_size: int,
    stride: int,
    required: int,
) -> tuple[int, tuple[str, int, int] | None]:
    if offset > len(builder.data):
        raise builder.error(
            f"effect table offset field 0x{field_offset:x} points to 0x{offset:x}, "
            f"past file size 0x{len(builder.data):x}"
        )
    available = len(builder.data) - offset
    if available == 0:
        if required:
            raise builder.error(
                f"effect table offset field 0x{field_offset:x} is EOF but "
                f"{required} effects are referenced"
            )
        return 0, None
    if offset < header_size:
        raise builder.error(
            f"effect table offset field 0x{field_offset:x} points inside header "
            f"at 0x{offset:x}"
        )
    if available % stride:
        raise builder.error(
            f"effect table at 0x{offset:x} has a partial effect: "
            f"0x{available:x} bytes is not divisible by 0x{stride:x}"
        )
    count = available // stride
    if required > count:
        raise builder.error(
            f"effect slices require {required} effects but table at 0x{offset:x} "
            f"contains {count}"
        )
    return count, ("effect table", offset, len(builder.data))


def _check_effect_slice(
    builder: _EdgeBuilder, scope: str, first: int, count: int, effect_count: int
) -> None:
    if first + count > effect_count:
        raise builder.error(
            f"{scope} slice {first}+{count} exceeds effect count {effect_count}"
        )


def _reject_overlap(
    builder: _EdgeBuilder,
    left: tuple[str, int, int] | None,
    right: tuple[str, int, int] | None,
) -> None:
    if left is None or right is None:
        return
    left_name, left_start, left_end = left
    right_name, right_start, right_end = right
    if max(left_start, right_start) < min(left_end, right_end):
        raise builder.error(
            f"{left_name} 0x{left_start:x}..0x{left_end:x} overlaps "
            f"{right_name} 0x{right_start:x}..0x{right_end:x}"
        )


def _display_path(path: Path, root: str | Path | None) -> str:
    if root is None:
        return path.as_posix()
    root_path = Path(root).resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(root_path).as_posix()
    except ValueError as error:
        raise ResourceError(f"{path}: resource is outside package root {root_path}") from error


__all__ = [
    "ResourceEdge",
    "ResourceError",
    "ResourceIndex",
    "ScannedResource",
    "build_resource_index",
    "scan_package_edges",
    "scan_package_resources",
    "scan_resource_edges",
]
