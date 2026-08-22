"""Minimal Infinity Engine formats used by this repository's tests.

Copied from chriz-bg-rebalance/tests/ie_formats.py (MIT, same author).  This is
intentionally not a general IE file-format library: it implements only the SPL V1,
EFF V2, 2DA, and IDS fields the test suites assert on.
"""

from __future__ import annotations

import dataclasses
import struct
from pathlib import Path
from typing import Iterable


SPL_HEADER_SIZE = 0x72
SPL_ABILITY_SIZE = 0x28
SPL_EFFECT_SIZE = 0x30
EFF_V2_SIZE = 0x110


def _u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _i32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<H", data, offset, value & 0xFFFF)


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value & 0xFFFFFFFF)


def _resref(data: bytes | bytearray, offset: int) -> str:
    return bytes(data[offset : offset + 8]).split(b"\0", 1)[0].decode("ascii").upper()


def _put_resref(data: bytearray, offset: int, value: str) -> None:
    encoded = value.encode("ascii")
    if len(encoded) > 8:
        raise ValueError(f"resref exceeds eight bytes: {value!r}")
    data[offset : offset + 8] = encoded.ljust(8, b"\0")


@dataclasses.dataclass(frozen=True)
class SplEffect:
    opcode: int = 0
    target: int = 0
    power: int = 0
    parameter1: int = 0
    parameter2: int = 0
    timing: int = 0
    resist_dispel: int = 0
    duration: int = 0
    probability1: int = 100
    probability2: int = 0
    resource: str = ""
    dice_number: int = 0
    dice_size: int = 0
    save_type: int = 0
    save_bonus: int = 0
    special: int = 0
    raw: bytes = dataclasses.field(default=b"", repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes) -> "SplEffect":
        if len(data) != SPL_EFFECT_SIZE:
            raise ValueError(f"SPL effect must be {SPL_EFFECT_SIZE} bytes, got {len(data)}")
        return cls(
            opcode=_u16(data, 0x00),
            target=data[0x02],
            power=data[0x03],
            parameter1=_i32(data, 0x04),
            parameter2=_i32(data, 0x08),
            timing=data[0x0C],
            resist_dispel=data[0x0D],
            duration=_u32(data, 0x0E),
            probability1=data[0x12],
            probability2=data[0x13],
            resource=_resref(data, 0x14),
            dice_number=_i32(data, 0x1C),
            dice_size=_i32(data, 0x20),
            save_type=_u32(data, 0x24),
            save_bonus=_i32(data, 0x28),
            special=_u32(data, 0x2C),
            raw=data,
        )

    def to_bytes(self) -> bytes:
        data = bytearray(self.raw if len(self.raw) == SPL_EFFECT_SIZE else bytes(SPL_EFFECT_SIZE))
        _put_u16(data, 0x00, self.opcode)
        data[0x02] = self.target & 0xFF
        data[0x03] = self.power & 0xFF
        _put_u32(data, 0x04, self.parameter1)
        _put_u32(data, 0x08, self.parameter2)
        data[0x0C] = self.timing & 0xFF
        data[0x0D] = self.resist_dispel & 0xFF
        _put_u32(data, 0x0E, self.duration)
        data[0x12] = self.probability1 & 0xFF
        data[0x13] = self.probability2 & 0xFF
        _put_resref(data, 0x14, self.resource)
        _put_u32(data, 0x1C, self.dice_number)
        _put_u32(data, 0x20, self.dice_size)
        _put_u32(data, 0x24, self.save_type)
        _put_u32(data, 0x28, self.save_bonus)
        _put_u32(data, 0x2C, self.special)
        return bytes(data)

    def delivery_key(self) -> tuple[object, ...]:
        """Delivery fields an additive IH marker must clone from its APR donor."""
        return (
            self.target,
            self.power,
            self.timing,
            self.resist_dispel,
            self.duration,
            self.probability1,
            self.probability2,
        )

    def preservation_key(self) -> tuple[object, ...]:
        """Identity fields for foreign effects; duration may be tier-normalized."""
        return (
            self.opcode,
            self.target,
            self.power,
            self.parameter1,
            self.parameter2,
            self.resist_dispel,
            self.probability1,
            self.probability2,
            self.resource.upper(),
            self.dice_number,
            self.dice_size,
            self.save_type,
            self.save_bonus,
            self.special,
        )

    def canonical(self) -> tuple[object, ...]:
        return (
            self.opcode,
            self.target,
            self.power,
            self.parameter1,
            self.parameter2,
            self.timing,
            self.resist_dispel,
            self.duration,
            self.probability1,
            self.probability2,
            self.resource.upper(),
            self.dice_number,
            self.dice_size,
            self.save_type,
            self.save_bonus,
            self.special,
        )


@dataclasses.dataclass(frozen=True)
class SplAbility:
    required_level: int
    target: int
    projectile: int
    effects: tuple[SplEffect, ...]
    icon: str = ""
    raw: bytes = dataclasses.field(default=b"", repr=False, compare=False)

    @classmethod
    def from_bytes(cls, raw: bytes, effects: tuple[SplEffect, ...]) -> "SplAbility":
        if len(raw) != SPL_ABILITY_SIZE:
            raise ValueError(f"SPL ability must be {SPL_ABILITY_SIZE} bytes, got {len(raw)}")
        return cls(
            required_level=_u16(raw, 0x10),
            target=raw[0x0C],
            projectile=_u16(raw, 0x26),
            effects=effects,
            icon=_resref(raw, 0x04),
            raw=raw,
        )

    def to_bytes(self, first_effect: int) -> bytes:
        raw = bytearray(self.raw if len(self.raw) == SPL_ABILITY_SIZE else bytes(SPL_ABILITY_SIZE))
        _put_resref(raw, 0x04, self.icon)
        raw[0x0C] = self.target & 0xFF
        _put_u16(raw, 0x10, self.required_level)
        _put_u16(raw, 0x1E, len(self.effects))
        _put_u16(raw, 0x20, first_effect)
        _put_u16(raw, 0x26, self.projectile)
        return bytes(raw)

    def canonical(self) -> tuple[object, ...]:
        return (
            self.required_level,
            self.target,
            self.projectile,
            self.icon.upper(),
            tuple(effect.canonical() for effect in self.effects),
        )


@dataclasses.dataclass(frozen=True)
class SplFile:
    abilities: tuple[SplAbility, ...]
    casting_effects: tuple[SplEffect, ...] = ()
    header_raw: bytes = dataclasses.field(default=b"", repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes) -> "SplFile":
        if len(data) < SPL_HEADER_SIZE:
            raise ValueError(f"truncated SPL V1 header: {len(data)} bytes")
        if data[:8] != b"SPL V1  ":
            raise ValueError(f"not SPL V1: {data[:8]!r}")
        ability_offset = _u32(data, 0x64)
        ability_count = _u16(data, 0x68)
        effect_offset = _u32(data, 0x6A)
        casting_first = _u16(data, 0x6E)
        casting_count = _u16(data, 0x70)
        ability_end = ability_offset + ability_count * SPL_ABILITY_SIZE
        if ability_offset < SPL_HEADER_SIZE or ability_end > len(data):
            raise ValueError("SPL ability table is out of bounds")
        if effect_offset < ability_end or effect_offset > len(data):
            raise ValueError("SPL effect table overlaps or is out of bounds")
        effect_bytes = len(data) - effect_offset
        if effect_bytes % SPL_EFFECT_SIZE:
            raise ValueError("SPL effect table has a partial effect")
        effect_count = effect_bytes // SPL_EFFECT_SIZE
        effects = tuple(
            SplEffect.from_bytes(data[effect_offset + i * SPL_EFFECT_SIZE : effect_offset + (i + 1) * SPL_EFFECT_SIZE])
            for i in range(effect_count)
        )
        if casting_first + casting_count > effect_count:
            raise ValueError("SPL casting-feature slice is out of bounds")
        abilities = []
        for index in range(ability_count):
            offset = ability_offset + index * SPL_ABILITY_SIZE
            raw = data[offset : offset + SPL_ABILITY_SIZE]
            count = _u16(raw, 0x1E)  # empirical engine/WeiDU layout
            first = _u16(raw, 0x20)
            if first + count > effect_count:
                raise ValueError(
                    f"SPL ability {index} effect slice {first}+{count} exceeds {effect_count}"
                )
            abilities.append(SplAbility.from_bytes(raw, effects[first : first + count]))
        return cls(
            abilities=tuple(abilities),
            casting_effects=effects[casting_first : casting_first + casting_count],
            header_raw=data[:SPL_HEADER_SIZE],
        )

    def to_bytes(self) -> bytes:
        header = bytearray(
            self.header_raw if len(self.header_raw) == SPL_HEADER_SIZE else bytes(SPL_HEADER_SIZE)
        )
        header[:8] = b"SPL V1  "
        ability_offset = SPL_HEADER_SIZE
        effect_offset = ability_offset + len(self.abilities) * SPL_ABILITY_SIZE
        _put_u32(header, 0x64, ability_offset)
        _put_u16(header, 0x68, len(self.abilities))
        _put_u32(header, 0x6A, effect_offset)
        _put_u16(header, 0x6E, 0)
        _put_u16(header, 0x70, len(self.casting_effects))

        effect_index = len(self.casting_effects)
        ability_bytes = []
        effects = list(self.casting_effects)
        for ability in self.abilities:
            ability_bytes.append(ability.to_bytes(effect_index))
            effects.extend(ability.effects)
            effect_index += len(ability.effects)
        return bytes(header) + b"".join(ability_bytes) + b"".join(effect.to_bytes() for effect in effects)

    @property
    def spell_icon(self) -> str:
        if len(self.header_raw) < 0x42:
            return ""
        return _resref(self.header_raw, 0x3A)

    def ability_for_level(self, level: int) -> SplAbility:
        candidates = [ability for ability in self.abilities if ability.required_level <= level]
        if not candidates:
            raise LookupError(f"no SPL ability serves level {level}")
        return max(candidates, key=lambda ability: ability.required_level)

    def canonical(self) -> tuple[object, ...]:
        return (
            self.spell_icon.upper(),
            tuple(effect.canonical() for effect in self.casting_effects),
            tuple(ability.canonical() for ability in self.abilities),
        )


def make_spl(abilities: Iterable[SplAbility]) -> SplFile:
    header = bytearray(SPL_HEADER_SIZE)
    header[:8] = b"SPL V1  "
    _put_u32(header, 0x64, SPL_HEADER_SIZE)
    _put_u32(header, 0x6A, SPL_HEADER_SIZE)
    return SplFile(abilities=tuple(abilities), header_raw=bytes(header))


@dataclasses.dataclass(frozen=True)
class EffV2:
    opcode: int = 0
    target: int = 0
    power: int = 0
    parameter1: int = 0
    parameter2: int = 0
    timing: int = 0
    duration: int = 0
    probability1: int = 100
    probability2: int = 0
    resource: str = ""
    dice_number: int = 0
    dice_size: int = 0
    save_type: int = 0
    save_bonus: int = 0
    special: int = 0
    flags: int = 0
    raw: bytes = dataclasses.field(default=b"", repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes) -> "EffV2":
        if len(data) != EFF_V2_SIZE:
            raise ValueError(f"EFF V2 must be exactly {EFF_V2_SIZE} bytes, got {len(data)}")
        if data[:8] != b"EFF V2.0" or data[8:16] != b"EFF V2.0":
            raise ValueError("not standalone EFF V2")
        return cls(
            opcode=_u32(data, 0x10),
            target=_u32(data, 0x14),
            power=_u32(data, 0x18),
            parameter1=_i32(data, 0x1C),
            parameter2=_i32(data, 0x20),
            timing=_u16(data, 0x24),
            duration=_u32(data, 0x28),
            probability1=_u16(data, 0x2C),
            probability2=_u16(data, 0x2E),
            resource=_resref(data, 0x30),
            dice_number=_i32(data, 0x38),
            dice_size=_i32(data, 0x3C),
            save_type=_u32(data, 0x40),
            save_bonus=_i32(data, 0x44),
            special=_u32(data, 0x48),
            flags=_u32(data, 0x5C),
            raw=data,
        )

    def to_bytes(self) -> bytes:
        data = bytearray(self.raw if len(self.raw) == EFF_V2_SIZE else bytes(EFF_V2_SIZE))
        data[:8] = b"EFF V2.0"
        data[8:16] = b"EFF V2.0"
        for offset, value in (
            (0x10, self.opcode),
            (0x14, self.target),
            (0x18, self.power),
            (0x1C, self.parameter1),
            (0x20, self.parameter2),
            (0x28, self.duration),
            (0x38, self.dice_number),
            (0x3C, self.dice_size),
            (0x40, self.save_type),
            (0x44, self.save_bonus),
            (0x48, self.special),
            (0x5C, self.flags),
        ):
            _put_u32(data, offset, value)
        _put_u16(data, 0x24, self.timing)
        _put_u16(data, 0x2C, self.probability1)
        _put_u16(data, 0x2E, self.probability2)
        _put_resref(data, 0x30, self.resource)
        return bytes(data)

    def canonical(self) -> tuple[object, ...]:
        return (
            self.opcode,
            self.target,
            self.power,
            self.parameter1,
            self.parameter2,
            self.timing,
            self.duration,
            self.probability1,
            self.probability2,
            self.resource.upper(),
            self.dice_number,
            self.dice_size,
            self.save_type,
            self.save_bonus,
            self.special,
            self.flags,
        )


@dataclasses.dataclass(frozen=True)
class TwoDA:
    default: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, tuple[str, ...]], ...]

    @classmethod
    def from_text(cls, text: str) -> "TwoDA":
        lines = []
        for raw in text.lstrip("\ufeff").splitlines():
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            lines.append(line)
        if len(lines) < 3 or lines[0].upper().split()[:2] != ["2DA", "V1.0"]:
            raise ValueError("not 2DA V1.0")
        default = lines[1].split()[0]
        columns = tuple(lines[2].split())
        rows = []
        for index, line in enumerate(lines[3:]):
            tokens = line.split()
            if len(tokens) != len(columns) + 1:
                raise ValueError(
                    f"2DA row {index} has {len(tokens) - 1} cells, expected {len(columns)}"
                )
            rows.append((tokens[0], tuple(tokens[1:])))
        return cls(default=default, columns=columns, rows=tuple(rows))

    def to_text(self) -> str:
        lines = ["2DA V1.0", self.default, "\t".join(self.columns)]
        lines.extend(f"{name}\t" + "\t".join(values) for name, values in self.rows)
        return "\n".join(lines) + "\n"

    def cell(self, row_name: str, column: str) -> str:
        try:
            column_index = next(i for i, name in enumerate(self.columns) if name.upper() == column.upper())
        except StopIteration as exc:
            raise KeyError(f"2DA column not found: {column}") from exc
        matches = [values for name, values in self.rows if name.upper() == row_name.upper()]
        if len(matches) != 1:
            raise KeyError(f"2DA row {row_name!r} matched {len(matches)} rows")
        return matches[0][column_index]

    def canonical(self) -> tuple[object, ...]:
        return (self.default.upper(), tuple(name.upper() for name in self.columns), self.rows)


@dataclasses.dataclass(frozen=True)
class IdsFile:
    entries: tuple[tuple[int, str], ...]

    @classmethod
    def from_text(cls, text: str) -> "IdsFile":
        entries = []
        for raw in text.lstrip("\ufeff").splitlines():
            line = raw.split("//", 1)[0].strip()
            if not line:
                continue
            tokens = line.split()
            if tokens[0].upper() == "IDS" or (len(tokens) == 1 and not entries):
                continue
            if len(tokens) < 2:
                raise ValueError(f"malformed IDS line: {raw!r}")
            entries.append((int(tokens[0], 0), tokens[1]))
        return cls(entries=tuple(entries))

    def to_text(self) -> str:
        return "\n".join(f"{value} {symbol}" for value, symbol in self.entries) + "\n"

    def value(self, symbol: str) -> int:
        matches = [value for value, candidate in self.entries if candidate.upper() == symbol.upper()]
        if len(matches) != 1:
            raise KeyError(f"IDS symbol {symbol!r} matched {len(matches)} values: {matches}")
        return matches[0]

    def values(self) -> set[int]:
        return {value for value, _ in self.entries}

    def canonical(self) -> tuple[tuple[int, str], ...]:
        return tuple((value, symbol.upper()) for value, symbol in self.entries)


def spell_resref(value: int, symbol: str) -> str:
    symbol = symbol.upper()
    slot = value % 1000
    if symbol.startswith("CLERIC_") and 1000 <= value < 2000:
        return f"SPPR{slot:03d}"
    if symbol.startswith("WIZARD_") and 2000 <= value < 3000:
        return f"SPWI{slot:03d}"
    raise ValueError(f"unsupported fixture SPELL.IDS mapping: {value} {symbol}")


def read_spl(path: Path | str) -> SplFile:
    return SplFile.from_bytes(Path(path).read_bytes())


def write_spl(path: Path | str, spell: SplFile) -> None:
    Path(path).write_bytes(spell.to_bytes())


def read_eff_v2(path: Path | str) -> EffV2:
    return EffV2.from_bytes(Path(path).read_bytes())


def read_2da(path: Path | str) -> TwoDA:
    return TwoDA.from_text(Path(path).read_text(encoding="utf-8-sig"))


def write_2da(path: Path | str, table: TwoDA) -> None:
    Path(path).write_text(table.to_text(), encoding="ascii", newline="\n")


def read_ids(path: Path | str) -> IdsFile:
    return IdsFile.from_text(Path(path).read_text(encoding="utf-8-sig"))


def write_ids(path: Path | str, ids: IdsFile) -> None:
    Path(path).write_text(ids.to_text(), encoding="ascii", newline="\n")


def canonical_resource_tree(root: Path | str) -> tuple[tuple[str, object], ...]:
    root = Path(root)
    result = []
    for path in sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(root).as_posix().upper()):
        relative = path.relative_to(root).as_posix().upper()
        suffix = path.suffix.upper()
        if suffix == ".SPL":
            value: object = ("SPL", read_spl(path).canonical())
        elif suffix == ".EFF":
            value = ("EFF", read_eff_v2(path).canonical())
        elif suffix == ".2DA":
            value = ("2DA", read_2da(path).canonical())
        elif suffix == ".IDS":
            value = ("IDS", read_ids(path).canonical())
        else:
            value = ("BYTES", path.read_bytes())
        result.append((relative, value))
    return tuple(result)
