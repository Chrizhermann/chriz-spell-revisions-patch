"""Chaos back at wizard level 5, Confusion's rounds, and the Waves of Fatigue scroll.

Christopher's decisions (2026-10-26/27): Chaos returns to SPWI508 as SR's Confusion with its
saving throw at -4; Confusion and Chaos last 4 rounds, 5 from caster level 15 and 6 from caster
level 20; Waves of Fatigue moves to its own spell (ADD_SPELL) and its scroll turns up wherever
the Chaos scroll does.

Coverage:
* `--nogame` harness on SR's real Confusion (spell_rev/spwi4##/spwi401.spl) and on synthetic
  spells: the three abilities, their durations, what stays byte-identical, other table layouts,
  and the inputs the functions refuse.
* synthetic fake game: Chaos takes the game's icons when they exist; the scroll lands next to
  the Chaos scroll in stores, area containers and creature inventories, once.
* the shipped resources: which spell each scroll teaches, and Waves of Fatigue's registration.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import struct
from pathlib import Path

import pytest

from tests import ie_formats
from tests.weidu_env import (
    ROOT,
    FakeGame,
    assert_installed,
    nogame_harness,
    parse_check,
    transcript,
)

LIBRARY = ROOT / "spell_rev" / "lib" / "chaos_confusion.tpa"
PLACEMENT = ROOT / "spell_rev" / "lib" / "item_beside.tpa"
HARNESS = ROOT / "tests" / "weidu" / "chaos_confusion_harness.tp2"
FAKE_GAME_TP2 = ROOT / "tests" / "weidu" / "fake_game_chaos.tp2"
COMPONENT = ROOT / "spell_rev" / "components" / "main_component.tpa"
ADD_SPELL_REFERENCES = ROOT / "spell_rev" / "lib" / "manage_add_spell_references.tpa"
CONFUSION_FILE = ROOT / "spell_rev" / "spwi4##" / "spwi401.spl"
LEVEL5 = ROOT / "spell_rev" / "spwi5##"

STEPS = [(1, 24), (15, 30), (20, 36)]  # (minimum caster level, duration in seconds)


# --------------------------------------------------------------------------- spell helpers


def run_harness(tmp_path: Path, data: bytes, mode: str) -> tuple[bytes | None, str]:
    run_dir = tmp_path / f"run-{len(list(tmp_path.iterdir()))}"
    run_dir.mkdir()
    (run_dir / "in.spl").write_bytes(data)
    out = run_dir / "out.spl"
    process = nogame_harness(
        HARNESS, 0, run_dir, [(run_dir / "in.spl").as_posix(), out.as_posix(), mode, LIBRARY.as_posix()]
    )
    return (out.read_bytes() if out.exists() else None), transcript(process)


def converted(tmp_path: Path, data: bytes, mode: str) -> bytes:
    out, text = run_harness(tmp_path, data, mode)
    assert out is not None and "SUCCESSFULLY INSTALLED" in text, text
    return out


def durations(spell: ie_formats.SplFile) -> list[list[tuple[int, int]]]:
    return [[(e.opcode, e.duration) for e in a.effects] for a in spell.abilities]


def without(effect: ie_formats.SplEffect, **fields: object) -> tuple[object, ...]:
    """An effect's fields with the named ones blanked, for 'nothing else changed' checks."""
    return dataclasses.astuple(dataclasses.replace(effect, raw=b"", **fields))


CONFUSION = CONFUSION_FILE.read_bytes()


# --------------------------------------------------------------------------- environment


@pytest.mark.parametrize(
    ("kind", "path"),
    [("TPA", LIBRARY), ("TPA", PLACEMENT), ("TPA", COMPONENT), ("TPA", ADD_SPELL_REFERENCES),
     ("TP2", HARNESS), ("TP2", FAKE_GAME_TP2)],
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_parse_check(kind: str, path: Path) -> None:
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


# --------------------------------------------------------------------------- Confusion's rounds


def test_confusion_gets_three_abilities_with_its_rounds(tmp_path: Path) -> None:
    before = ie_formats.SplFile.from_bytes(CONFUSION)
    after = ie_formats.SplFile.from_bytes(converted(tmp_path, CONFUSION, "rounds"))

    assert [a.required_level for a in after.abilities] == [level for level, _ in STEPS]
    (original,) = before.abilities
    timed = {e.opcode for e in original.effects if e.duration == 30}
    assert timed == {128, 142, 174, 215}  # the confusion, its icon, its end sound, its visual
    for ability, (_, seconds) in zip(after.abilities, STEPS):
        assert [(op, d) for op, d in durations_of(ability)] == [
            (e.opcode, seconds if e.opcode in timed else e.duration) for e in original.effects
        ]
        # everything but the duration and the minimum level is the original's
        assert [without(e, duration=0) for e in ability.effects] == [without(e, duration=0) for e in original.effects]
        assert strip_ability(ability.raw) == strip_ability(original.raw)
    assert after.casting_effects == before.casting_effects
    assert header_without_tables(after.header_raw) == header_without_tables(before.header_raw)


def durations_of(ability: ie_formats.SplAbility) -> list[tuple[int, int]]:
    return [(e.opcode, e.duration) for e in ability.effects]


def strip_ability(raw: bytes) -> bytes:
    """Ability bytes without minimum level (0x10) and first-effect index (0x20)."""
    data = bytearray(raw)
    data[0x10:0x12] = b"\0\0"
    data[0x20:0x22] = b"\0\0"
    return bytes(data)


def header_without_tables(raw: bytes) -> bytes:
    """Header bytes without the ability count (0x68) and the effect offset (0x6a)."""
    data = bytearray(raw)
    data[0x68:0x6E] = bytes(6)
    return bytes(data)


def test_rounds_keep_casting_effects_that_sit_before_the_ability_effects(tmp_path: Path) -> None:
    base = ie_formats.SplFile.from_bytes(CONFUSION)
    cast = (ie_formats.SplEffect(opcode=321, target=1, timing=1, resource="SPWI401"),)
    spell = dataclasses.replace(base, casting_effects=cast).to_bytes()  # casting effects first
    after = ie_formats.SplFile.from_bytes(converted(tmp_path, spell, "rounds"))
    assert after.casting_effects == cast
    assert [a.required_level for a in after.abilities] == [1, 15, 20]
    assert [d for op, d in durations_of(after.abilities[2]) if op == 128] == [36]


def test_rounds_handle_an_effect_table_before_the_abilities(tmp_path: Path) -> None:
    # Same spell, tables swapped: header, effects, then the ability.
    ability_off = struct.unpack_from("<I", CONFUSION, 0x64)[0]
    effect_off = struct.unpack_from("<I", CONFUSION, 0x6A)[0]
    ability = CONFUSION[ability_off:ability_off + 0x28]
    effects = CONFUSION[effect_off:]
    header = bytearray(CONFUSION[:0x72])
    struct.pack_into("<I", header, 0x6A, 0x72)
    struct.pack_into("<I", header, 0x64, 0x72 + len(effects))
    out = converted(tmp_path, bytes(header) + effects + ability, "rounds")

    ab_off, ab_num, fx_off = struct.unpack_from("<IHI", out, 0x64)
    assert (fx_off, ab_num) == (0x72, 3)
    assert ab_off == 0x72 + 3 * len(effects)  # all three effect sets come first
    assert ab_off + 3 * 0x28 == len(out)
    for step, (level, seconds) in enumerate(STEPS):
        raw = out[ab_off + step * 0x28: ab_off + (step + 1) * 0x28]
        count, first = struct.unpack_from("<HH", raw, 0x1E)
        assert struct.unpack_from("<H", raw, 0x10)[0] == level
        ops = [struct.unpack_from("<HxxiiBxI", out, fx_off + (first + j) * 0x30) for j in range(count)]
        assert [(op, dur) for op, _, _, _, dur in ops if op == 128] == [(128, seconds)]


def test_rounds_refuse_a_spell_with_more_than_one_ability(tmp_path: Path) -> None:
    base = ie_formats.SplFile.from_bytes(CONFUSION)
    twice = dataclasses.replace(base, abilities=base.abilities * 2).to_bytes()
    out, text = run_harness(tmp_path, twice, "rounds")
    assert out is None and "has 2 abilities" in text, text


def test_rounds_refuse_a_spell_without_a_timed_confusion(tmp_path: Path) -> None:
    base = ie_formats.SplFile.from_bytes(CONFUSION)
    (ability,) = base.abilities
    effects = tuple(e for e in ability.effects if e.opcode != 128)
    spell = dataclasses.replace(base, abilities=(dataclasses.replace(ability, effects=effects),)).to_bytes()
    out, text = run_harness(tmp_path, spell, "rounds")
    assert out is None and "no timed confusion effect" in text, text


# --------------------------------------------------------------------------- Chaos


def test_chaos_is_confusion_at_level_5_with_a_save_at_minus_4(tmp_path: Path) -> None:
    before = ie_formats.SplFile.from_bytes(CONFUSION)
    data = converted(tmp_path, CONFUSION, "chaos")
    after = ie_formats.SplFile.from_bytes(data)

    assert struct.unpack_from("<I", data, 0x34)[0] == 5
    (old,), (new,) = before.abilities, after.abilities
    assert all(e.save_type == 1 for e in old.effects)
    assert [(e.power, e.save_bonus) for e in new.effects] == [(5, -4)] * len(old.effects)
    assert [without(e, power=0, save_bonus=0) for e in new.effects] == [
        without(e, power=0, save_bonus=0) for e in old.effects]
    # no Chaos icons in a --nogame run, so Confusion's stay
    assert (after.spell_icon, new.icon) == (before.spell_icon, old.icon)
    head = bytearray(data[:0x72])
    head[0x34:0x38] = CONFUSION[0x34:0x38]
    assert bytes(head) == CONFUSION[:0x72]


def test_chaos_lasts_four_to_six_rounds_like_confusion(tmp_path: Path) -> None:
    rounds_only = ie_formats.SplFile.from_bytes(converted(tmp_path, CONFUSION, "rounds"))
    chaos = ie_formats.SplFile.from_bytes(converted(tmp_path, CONFUSION, "both"))
    assert durations(chaos) == durations(rounds_only)
    assert all(e.save_bonus == -4 and e.power == 5 for a in chaos.abilities for e in a.effects)


def test_effects_without_a_save_or_with_another_power_keep_them(tmp_path: Path) -> None:
    base = ie_formats.SplFile.from_bytes(CONFUSION)
    (ability,) = base.abilities
    extra = ie_formats.SplEffect(opcode=139, target=2, power=0, parameter1=1, timing=1)
    spell = dataclasses.replace(
        base, abilities=(dataclasses.replace(ability, effects=ability.effects + (extra,)),)).to_bytes()
    (new,) = ie_formats.SplFile.from_bytes(converted(tmp_path, spell, "chaos")).abilities
    assert (new.effects[-1].power, new.effects[-1].save_type, new.effects[-1].save_bonus) == (0, 0, 0)


# --------------------------------------------------------------------------- fake game


def sto(entries: list[tuple[str, int, int, int, int, int, int, int]]) -> bytes:
    """STOR V1.0 with sale entries (resref, expiry, charge x3, flags, stock, infinite), one bought
    item type, one drink and one cure after them."""
    sale = b"".join(struct.pack("<8sHHHHIII", r.encode(), *rest) for r, *rest in entries)
    bought = struct.pack("<I", 11)
    drink = struct.pack("<8sIII", b"", 7777, 5, 20)
    cure = struct.pack("<8sI", b"SPPR103", 100)
    head = bytearray(0x9C)
    head[0:8] = b"STORV1.0"
    sale_off = 0x9C
    bought_off = sale_off + len(sale)
    drink_off = bought_off + len(bought)
    cure_off = drink_off + len(drink)
    struct.pack_into("<II", head, 0x2C, bought_off, 1)
    struct.pack_into("<II", head, 0x34, sale_off, len(entries))
    struct.pack_into("<II", head, 0x4C, drink_off, 1)
    struct.pack_into("<II", head, 0x70, cure_off, 1)
    return bytes(head) + sale + bought + drink + cure


def sto_entries(data: bytes) -> list[tuple[object, ...]]:
    off, count = struct.unpack_from("<II", data, 0x34)
    return [
        (data[off + i * 0x1C: off + i * 0x1C + 8].rstrip(b"\0").decode().upper(),)
        + struct.unpack_from("<HHHHIII", data, off + i * 0x1C + 8)
        for i in range(count)
    ]


def sto_tail(data: bytes) -> tuple[bytes, bytes, bytes]:
    bought_off, bought = struct.unpack_from("<II", data, 0x2C)
    drink_off, drinks = struct.unpack_from("<II", data, 0x4C)
    cure_off, cures = struct.unpack_from("<II", data, 0x70)
    return (data[bought_off:bought_off + 4 * bought], data[drink_off:drink_off + 0x14 * drinks],
            data[cure_off:cure_off + 0x0C * cures])


SONG = bytes(range(0x90))
REST = bytes((i * 7) & 0xFF for i in range(0xE4))


def are(containers: list[list[tuple[str, int, int, int, int, int]]]) -> bytes:
    """AREAV1.0 with containers of items (resref, expiry, charge x3, flags), song and rest
    sections after them, and every other section empty."""
    head = bytearray(0x11C)
    head[0:8] = b"AREAV1.0"
    head[8:16] = b"AR9999\0\0"
    con_off = 0x11C
    con = bytearray()
    items = bytearray()
    for index, contents in enumerate(containers):
        record = bytearray(0xC0)
        record[0:32] = f"Container {index}".encode().ljust(32, b"\0")
        struct.pack_into("<II", record, 0x40, len(items) // 0x14, len(contents))
        con += record
        for resref, *rest in contents:
            items += struct.pack("<8sHHHHI", resref.encode(), *rest)
    items_off = con_off + len(con)
    end = items_off + len(items)
    song_off, rest_off = end, end + len(SONG)
    struct.pack_into("<IH", head, 0x54, end, 0)
    struct.pack_into("<HI", head, 0x5A, 0, end)
    struct.pack_into("<IIII", head, 0x60, end, 0, end, 0)
    struct.pack_into("<IHHI", head, 0x70, con_off, len(containers), len(items) // 0x14, items_off)
    struct.pack_into("<IHHIII", head, 0x7C, end, 0, 0, end, end, 0)
    struct.pack_into("<II", head, 0x9C, 0, end)
    struct.pack_into("<IIIIIIII", head, 0xA4, 0, end, 0, end, 0, end, song_off, rest_off)
    struct.pack_into("<IIII", head, 0xC4, end, 0, end, 0)
    return bytes(head) + con + items + SONG + REST


def are_containers(data: bytes) -> list[list[tuple[object, ...]]]:
    con_off, con_num, _, items_off = struct.unpack_from("<IHHI", data, 0x70)
    out = []
    for c in range(con_num):
        first, count = struct.unpack_from("<II", data, con_off + c * 0xC0 + 0x40)
        out.append([
            (data[items_off + i * 0x14: items_off + i * 0x14 + 8].rstrip(b"\0").decode().upper(),)
            + struct.unpack_from("<HHHHI", data, items_off + i * 0x14 + 8)
            for i in range(first, first + count)
        ])
    return out


def are_tail(data: bytes) -> tuple[bytes, bytes]:
    song_off, rest_off = struct.unpack_from("<II", data, 0xBC)
    return data[song_off:song_off + 0x90], data[rest_off:rest_off + 0xE4]


def cre(items: list[tuple[str, int, int, int, int, int]], slots: dict[int, int]) -> bytes:
    """CRE V1.0 with items (resref, expiry, charge x3, flags) and slots {slot: item index}."""
    head = bytearray(0x2D4)
    head[0:8] = b"CRE V1.0"
    head[0x33] = 1  # EFF V2 effects
    off = 0x2D4
    item_bytes = b"".join(struct.pack("<8sHHHHI", r.encode(), *rest) for r, *rest in items)
    table = [-1] * 38 + [1000, 0]
    for slot, index in slots.items():
        table[slot] = index
    struct.pack_into("<IIIIII", head, 0x2A0, off, 0, off, 0, off, 0)
    struct.pack_into("<IIIII", head, 0x2B8, off + len(item_bytes), off, len(items), off, 0)
    return bytes(head) + item_bytes + struct.pack("<40h", *table)


def cre_inventory(data: bytes) -> dict[int, tuple[object, ...]]:
    slots_off, items_off, _ = struct.unpack_from("<III", data, 0x2B8)
    table = struct.unpack_from("<40h", data, slots_off)
    return {
        slot: (data[items_off + i * 0x14: items_off + i * 0x14 + 8].rstrip(b"\0").decode().upper(),)
        + struct.unpack_from("<HHHHI", data, items_off + i * 0x14 + 8)
        for slot, i in enumerate(table[:38]) if i >= 0
    }


def item_variant(data: bytes, item_type: int | None = None, teaches: str | None = None) -> bytes:
    """A copy of a scroll with another item type and/or every op147/148 pointed elsewhere."""
    out = bytearray(data)
    if item_type is not None:
        struct.pack_into("<H", out, 0x1C, item_type)
    if teaches is not None:
        ab_off, ab_num, fx_off = struct.unpack_from("<IHI", out, 0x64)
        for a in range(ab_num):
            count, first = struct.unpack_from("<HH", out, ab_off + a * 0x38 + 0x1E)
            for j in range(count):
                at = fx_off + (first + j) * 0x30
                out[at + 0x14:at + 0x1C] = teaches.encode().ljust(8, b"\0")
    return bytes(out)


CHAOS_SCROLL = (ROOT / "spell_rev" / "spwi5##" / "scrl5p.itm").read_bytes()  # teaches SPWI508
SCROLLS = (
    ("SCRL5P", "ITM", CHAOS_SCROLL),
    ("SCCHAO", "ITM", CHAOS_SCROLL),  # Icewind Dale's name for it
    ("SCRL1U", "ITM", item_variant(CHAOS_SCROLL, teaches="SPWI401")),  # teaches another spell
    ("RING95", "ITM", item_variant(CHAOS_SCROLL, item_type=10)),  # names SPWI508 but is no scroll
)
CHAOS_ENTRY = ("SCRL5P", 0, 1, 0, 0, 1, 3, 0)  # charges 1, identified, 3 in stock
STORE = sto([("SCRL1U", 0, 1, 0, 0, 1, 2, 0), CHAOS_ENTRY, ("POTN08", 0, 5, 0, 0, 1, 1, 1)])
STORE_WITH_ITEM = sto([CHAOS_ENTRY, ("srcbwofs", 0, 1, 0, 0, 1, 9, 0)])  # lower case, as another tool may write it
STORE_WITHOUT = sto([("SCRL1U", 0, 1, 0, 0, 1, 2, 0), ("RING95", 0, 0, 0, 0, 1, 1, 0)])
STORE_IWD = sto([("SCCHAO", 0, 1, 0, 0, 1, 1, 1)])  # unlimited supply
AREA = are([
    [("MISC01", 0, 0, 0, 0, 0), ("scrl5p", 0, 2, 0, 0, 3)],  # two Chaos scrolls, identified + unstealable
    [("SCRL1U", 0, 1, 0, 0, 0)],
    [("SCRL5P", 4, 1, 0, 0, 0), ("SRCBWOFS", 0, 1, 0, 0, 0)],  # already has one
])
MAGE = cre([("SCRL7C", 0, 0, 0, 0, 0), ("SCRL5P", 0, 0, 0, 0, 8), ("SCRL1Y", 0, 0, 0, 0, 0)],
           {18: 0, 19: 1, 21: 2})  # Chaos in quick item 2, something in INV1
FULL_MAGE = cre([("SCRL5P", 0, 0, 0, 0, 0)] + [("MISC01", 0, 0, 0, 0, 0)] * 16,
                {19: 0, **{21 + i: 1 + i for i in range(16)}})


@pytest.fixture
def chaos_game(tmp_path: Path) -> tuple[FakeGame, str]:
    game = FakeGame(
        tmp_path / "game",
        (
            ("SPWI508B", "BAM", b"BAM V1  "),
            ("SPWI508C", "BAM", b"BAM V1  "),
            ("STORE1", "STO", STORE),
            ("STORE2", "STO", STORE_WITH_ITEM),
            ("STORE3", "STO", STORE_WITHOUT),
            ("STORE4", "STO", STORE_IWD),
            *SCROLLS,
            ("AR9999", "ARE", AREA),
            ("MAGE", "CRE", MAGE),
            ("FULLMAGE", "CRE", FULL_MAGE),
        ),
    )
    for source in (LIBRARY, PLACEMENT, CONFUSION_FILE):
        target = game.root / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(FAKE_GAME_TP2, game.root / "setup-srcb_test_chaos.tp2")
    text = ""
    for component in (0, 1):
        process = game.install("setup-srcb_test_chaos.tp2", component)
        assert_installed(process)
        text += transcript(process)
    return game, text


def test_chaos_takes_the_games_chaos_icons(chaos_game: tuple[FakeGame, str]) -> None:
    game, _ = chaos_game
    chaos = ie_formats.SplFile.from_bytes(game.override_file("SPWI508.SPL").read_bytes())
    assert chaos.spell_icon.upper() == "SPWI508C"
    assert [a.icon.upper() for a in chaos.abilities] == ["SPWI508B"] * 3
    assert [a.required_level for a in chaos.abilities] == [1, 15, 20]


def test_scroll_sits_after_the_chaos_scroll_with_its_stock(chaos_game: tuple[FakeGame, str]) -> None:
    game, _ = chaos_game
    data = game.override_file("STORE1.STO").read_bytes()
    assert sto_entries(data) == [
        ("SCRL1U", 0, 1, 0, 0, 1, 2, 0), CHAOS_ENTRY, ("SRCBWOFS",) + CHAOS_ENTRY[1:], ("POTN08", 0, 5, 0, 0, 1, 1, 1)]
    assert sto_tail(data) == sto_tail(STORE)


def test_stores_with_the_scroll_or_without_chaos_stay_untouched(chaos_game: tuple[FakeGame, str]) -> None:
    game, _ = chaos_game
    assert game.override_file("STORE2.STO") is None
    assert game.override_file("STORE3.STO") is None  # sells a ring that names Chaos, no scroll
    game.assert_inputs_unchanged()


def test_only_scrolls_that_teach_chaos_count(chaos_game: tuple[FakeGame, str]) -> None:
    game, text = chaos_game
    assert sorted(set(re.findall(r"srcb_test anchor=(\w+)", text))) == ["SCCHAO", "SCRL5P"]
    assert sto_entries(game.override_file("STORE4.STO").read_bytes()) == [
        ("SCCHAO", 0, 1, 0, 0, 1, 1, 1), ("SRCBWOFS", 0, 1, 0, 0, 1, 1, 1)]


def test_area_container_gets_the_scroll_once(chaos_game: tuple[FakeGame, str]) -> None:
    game, _ = chaos_game
    data = game.override_file("AR9999.ARE").read_bytes()
    assert are_containers(data) == [
        [("MISC01", 0, 0, 0, 0, 0), ("SCRL5P", 0, 2, 0, 0, 3), ("SRCBWOFS", 0, 2, 0, 0, 3)],
        [("SCRL1U", 0, 1, 0, 0, 0)],
        [("SCRL5P", 4, 1, 0, 0, 0), ("SRCBWOFS", 0, 1, 0, 0, 0)],
    ]
    assert are_tail(data) == (SONG, REST)


def test_creature_gets_the_scroll_in_its_first_free_inventory_slot(chaos_game: tuple[FakeGame, str]) -> None:
    game, _ = chaos_game
    inventory = cre_inventory(game.override_file("MAGE.CRE").read_bytes())
    assert inventory == {
        18: ("SCRL7C", 0, 0, 0, 0, 0), 19: ("SCRL5P", 0, 0, 0, 0, 8), 21: ("SCRL1Y", 0, 0, 0, 0, 0),
        22: ("SRCBWOFS", 0, 0, 0, 0, 8),
    }


def test_creature_without_room_keeps_its_items_and_warns(chaos_game: tuple[FakeGame, str]) -> None:
    game, text = chaos_game
    assert game.override_file("FULLMAGE.CRE") is None
    assert re.search(r"FULLMAGE\.CRE carries scrl5p but has no free inventory slot for srcbwofs", text, re.I), text


# --------------------------------------------------------------------------- shipped resources


def item_effects(path: Path) -> list[tuple[int, str]]:
    data = path.read_bytes()
    ab_off, ab_num, fx_off = struct.unpack_from("<IHI", data, 0x64)
    found = []
    for a in range(ab_num):
        count, first = struct.unpack_from("<HH", data, ab_off + a * 0x38 + 0x1E)
        for j in range(count):
            at = fx_off + (first + j) * 0x30
            found.append((struct.unpack_from("<H", data, at)[0], data[at + 0x14:at + 0x1C].rstrip(b"\0").decode().upper()))
    return found


def item_icons(path: Path) -> set[str]:
    data = path.read_bytes()
    ab_off, ab_num = struct.unpack_from("<IH", data, 0x64)
    icons = {data[0x3A:0x42].rstrip(b"\0").decode().upper()}
    icons |= {data[ab_off + a * 0x38 + 4: ab_off + a * 0x38 + 12].rstrip(b"\0").decode().upper() for a in range(ab_num)}
    return icons


def test_chaos_scroll_teaches_chaos_with_the_chaos_scroll_icon() -> None:
    scroll = LEVEL5 / "scrl5p.itm"
    assert sorted(item_effects(scroll)) == [(147, "SPWI508"), (148, "SPWI508")]
    assert item_icons(scroll) == {"ISCRL5P"}


def test_waves_of_fatigue_ships_under_its_own_names() -> None:
    scroll = LEVEL5 / "srcbwofs.itm"
    assert sorted(item_effects(scroll)) == [(147, "SPWIWOF"), (148, "SPWIWOF")]
    assert item_icons(scroll) == {"SRCBWOFA"}
    spell = ie_formats.SplFile.from_bytes((LEVEL5 / "spwiwof.spl").read_bytes())
    assert spell.spell_icon.upper() == "SRCBWOFC" and [a.icon.upper() for a in spell.abilities] == ["SRCBWOFB"]
    for icon in ("srcbwofa", "srcbwofb", "srcbwofc"):
        assert (LEVEL5 / f"{icon}.bam").is_file()
    assert not (LEVEL5 / "spwi508.spl").exists()
    # the scroll's reference is resolved through ADD_SPELL's registry
    registry = ADD_SPELL_REFERENCES.read_text(encoding="utf-8")
    assert re.search(r"^\s*spwiwof\s*=>\s*WIZARD_WAVES_OF_FATIGUE\s*$", registry, re.MULTILINE)


def test_component_installs_chaos_and_waves_of_fatigue_as_designed() -> None:
    text = COMPONENT.read_text(encoding="latin-1")
    assert "2508 WIZARD_WAVES_OF_FATIGUE" not in text  # no SPELL.IDS rename any more
    assert "2711 WIZARD_CHAOS" not in text
    assert re.search(r"ADD_SPELL ~spell_rev\\spwi5##\\spwiwof\.spl~ 2 5 ~WIZARD_WAVES_OF_FATIGUE~", text)
    assert re.search(r"COPY ~spell_rev\\spwi4##\\spwi401\.spl~\s+~override\\spwi508\.spl~", text)
    # every Chaos scroll, after the Tutu block has made SR's copies of them
    placement = text.index("LAF srcb_scrolls_teaching STR_VAR spell = ~spwi508~")
    assert text.index("/*---------------------Tutu Scrolls") < placement
    assert re.search(r"LAF srcb_add_item_beside STR_VAR anchor = EVAL ~%srcb_chaos_scroll%~ item = ~srcbwofs~ END",
                     text[placement:])
