"""Hermetic real-WeiDU tests for the RR / SR tail compatibility component."""

from __future__ import annotations

import re
import shutil
import struct
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from tests import ie_formats
from tests.weidu_env import (
    ROOT,
    FakeGame,
    WEIDU,
    assert_installed,
    parse_check,
    run_weidu,
    transcript,
)


LIVE_ROOT = ROOT / "live-patch" / "SRCB_RR_COMPAT"
SETUP_TP2 = LIVE_ROOT / "setup-SRCB_RR_COMPAT.tp2"
LIBRARY = LIVE_ROOT / "lib" / "rr_spell_semantics.tpa"
HARNESS = ROOT / "tests" / "weidu" / "rr_compat_harness.tp2"

OLD_RESREF = "SPWI508"
CHAOS_RESREF = "SPWI711"
SORCERER = 19
COUNTS = {
    "RR#SELI": 6,
    "RR#ZAER": 0,
    "RR#ARAN2": 4,
    "RR#SAW09": 0,
    "RR#SFL04": 2,
}
SORCERERS = {"RR#SELI"}
# Christopher's decision, 2026-10-23: Chaos stays SR's level-7 spell. These
# level-5 spells take the prepared Chaos copies, and the scripts cast them.
# RR#ZAER and RR#SAW09 only know the old slot and are not changed.
REPLACEMENTS = {"RR#SELI": "SPWI506", "RR#ARAN2": "SPWI507", "RR#SFL04": "SPWI509"}
SCRIPT_COUNTS = {"RR#SELI": 17, "RR#ARAN2": 13, "RR#STM01": 12}
CASTING_BLOCKS = {"RR#SELI": 8, "RR#ARAN2": 6, "RR#STM01": 6}
SCRIPT_REPLACEMENTS = {
    "RR#SELI": "WIZARD_DOMINATION",
    "RR#ARAN2": "WIZARD_HOLD_MONSTER",
    "RR#STM01": "WIZARD_FEEBLEMIND",
}
# RR#STM01 casts Feeblemind already in a block of its own.
NATIVE_REFERENCES = {"RR#STM01": 2}

TARGET = "LastSeenBy(Myself)"
# Filters of RR's Chaos blocks; they stay for the replacement.
CHAOS_FILTERS = (
    "!General({t},UNDEAD)",
    "!CheckStatGT({t},0,CLERIC_CHAOTIC_COMMANDS)",
    '!HasItemEquiped("SHLD25",{t})',
)
# What each replacement needs that Chaos did not (rr_spell_semantics.tpa).
SINGLE_TARGET_FILTERS = (
    "!CheckStatGT({t},0,WIZARD_SPELL_TURNING)",
    "!CheckStatGT({t},0,WIZARD_SPELL_DEFLECTION)",
    "!CheckStatGT({t},0,WIZARD_SPELL_TRAP)",
    "!CheckStat({t},1,CLERIC_SHIELD_OF_THE_ARCHONS)",
)
DOMINATION_FILTERS = SINGLE_TARGET_FILTERS + (
    '!HasItemEquiped("HELM06",{t})',
    '!HasItemEquiped("SHLD25",{t})',
    '!HasItemEquipedReal("SPER07",{t})',
    '!HasItemEquipedReal("SW1H35",{t})',
    '!HasItemEquipedReal("SW2H14",{t})',
)
HOLD_FILTERS = (
    "!General({t},UNDEAD)",
    "!CheckStatGT({t},0,CLERIC_FREE_ACTION)",
    "!Kit({t},INQUISITOR)",
    "!Kit({t},UNDEADHUNTER)",
    '!HasItem("MORSWORD",{t})',
    '!HasItemEquiped("RING09",{t})',
    '!HasItemEquiped("SHLD25",{t})',
    '!HasItemEquipedReal("NPSW01",{t})',
    '!HasItemEquipedReal("SPER07",{t})',
    '!HasItemEquipedReal("SW1H27",{t})',
    '!HasItemEquipedReal("SW2H06",{t})',
)
SCRIPT_FILTERS = {
    "RR#SELI": DOMINATION_FILTERS,
    "RR#ARAN2": HOLD_FILTERS,
    "RR#STM01": SINGLE_TARGET_FILTERS,
}

CURRENT_SPELL_IDS = """IDS V1.0
2506 WIZARD_DOMINATION
2507 WIZARD_HOLD_MONSTER
2508 WIZARD_WAVES_OF_FATIGUE
2509 WIZARD_FEEBLEMIND
2701 WIZARD_SPELL_TURNING
2711 WIZARD_CHAOS
2711 WIZARD_SPHERE_OF_CHAOS
"""
CURRENT_SPELL_IDS_CHAOS_LAST = """IDS V1.0
2506 WIZARD_DOMINATION
2507 WIZARD_HOLD_MONSTER
2508 WIZARD_WAVES_OF_FATIGUE
2509 WIZARD_FEEBLEMIND
2701 WIZARD_SPELL_TURNING
2711 WIZARD_SPHERE_OF_CHAOS
2711 WIZARD_CHAOS
"""
VANILLA_SPELL_IDS = """IDS V1.0
2506 WIZARD_DOMINATION
2507 WIZARD_HOLD_MONSTER
2508 WIZARD_CHAOS
2509 WIZARD_FEEBLEMIND
2701 WIZARD_SPELL_TURNING
2711 WIZARD_SPHERE_OF_CHAOS
"""


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<H", data, offset, value)


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value)


def _put_resref(data: bytearray, offset: int, value: str) -> None:
    data[offset : offset + 8] = value.encode("ascii").ljust(8, b"\0")


def _resref(data: bytes, offset: int) -> str:
    return data[offset : offset + 8].split(b"\0", 1)[0].decode("ascii").upper()


def _make_rr_cre(old_copies: int, *, mixed: bool = False, sorcerer: bool = False) -> bytes:
    """Build RR's relevant spellbook shape plus unrelated level-five/seven spells."""
    known = (("ZZFIVE", 4), (OLD_RESREF, 4), ("ZZSEVEN", 6))
    if mixed:
        known += ((CHAOS_RESREF, 6),)
    level_five = ["ZZMEMA", *([OLD_RESREF] * old_copies)]
    level_seven = ["ZZMEMB"]
    memorized = level_five + level_seven

    known_offset = 0x2D4
    info_offset = known_offset + len(known) * 0x0C
    memorized_offset = info_offset + 0x20
    slots_offset = memorized_offset + len(memorized) * 0x0C
    end_offset = slots_offset + 0x50
    data = bytearray(end_offset)
    data[:8] = b"CRE V1.0"
    data[0x33] = 0
    if sorcerer:
        data[0x273] = SORCERER
    for field_offset, value in (
        (0x2A0, known_offset),
        (0x2A4, len(known)),
        (0x2A8, info_offset),
        (0x2AC, 2),
        (0x2B0, memorized_offset),
        (0x2B4, len(memorized)),
        (0x2B8, slots_offset),
        (0x2BC, end_offset),
        (0x2C0, 0),
        (0x2C4, end_offset),
        (0x2C8, 0),
    ):
        _put_u32(data, field_offset, value)

    for index, (spell, level) in enumerate(known):
        offset = known_offset + index * 0x0C
        _put_resref(data, offset, spell)
        _put_u16(data, offset + 8, level)
        _put_u16(data, offset + 10, 1)

    for index, (level, first, count) in enumerate(
        ((4, 0, len(level_five)), (6, len(level_five), len(level_seven)))
    ):
        offset = info_offset + index * 0x10
        _put_u16(data, offset, level)
        _put_u16(data, offset + 2, max(1, count))
        _put_u16(data, offset + 6, 1)
        _put_u32(data, offset + 8, first)
        _put_u32(data, offset + 12, count)

    for index, spell in enumerate(memorized):
        offset = memorized_offset + index * 0x0C
        _put_resref(data, offset, spell)
        _put_u32(data, offset + 8, 1)
    for offset in range(slots_offset, end_offset, 2):
        _put_u16(data, offset, 0xFFFF)
    return bytes(data)


def _wizard_spell(level: int) -> bytes:
    data = bytearray(ie_formats.make_spl(()).to_bytes())
    _put_u16(data, 0x1C, 1)
    _put_u32(data, 0x34, level)
    return bytes(data)


def _known_spells(data: bytes) -> list[tuple[str, int, int]]:
    offset, count = struct.unpack_from("<II", data, 0x2A0)
    return [
        (
            _resref(data, offset + index * 0x0C),
            struct.unpack_from("<H", data, offset + index * 0x0C + 8)[0],
            struct.unpack_from("<H", data, offset + index * 0x0C + 10)[0],
        )
        for index in range(count)
    ]


def _memorized_by_level(data: bytes) -> dict[int, list[tuple[str, int]]]:
    info_offset, info_count = struct.unpack_from("<II", data, 0x2A8)
    memorized_offset, memorized_count = struct.unpack_from("<II", data, 0x2B0)
    result: dict[int, list[tuple[str, int]]] = {}
    for index in range(info_count):
        entry = info_offset + index * 0x10
        level, _, _, kind = struct.unpack_from("<HHHH", data, entry)
        first, count = struct.unpack_from("<II", data, entry + 8)
        assert kind == 1
        assert first + count <= memorized_count
        result[level] = [
            (
                _resref(data, memorized_offset + (first + item) * 0x0C),
                struct.unpack_from(
                    "<I", data, memorized_offset + (first + item) * 0x0C + 8
                )[0],
            )
            for item in range(count)
        ]
    return result


def _memorization_caps(data: bytes) -> dict[int, tuple[int, int]]:
    info_offset, info_count = struct.unpack_from("<II", data, 0x2A8)
    result: dict[int, tuple[int, int]] = {}
    for index in range(info_count):
        entry = info_offset + index * 0x10
        level, maximum, current, kind = struct.unpack_from("<HHHH", data, entry)
        assert kind == 1
        result[level] = (maximum, current)
    return result


def _script_ids(spell_ids: str) -> dict[str, str]:
    return {
        "ACTION.IDS": """90
0 NoAction()
31 Spell(O:Target*,I:Spell*Spell)
181 ReallyForceSpell(O:Target,I:Spell*Spell)
191 SpellNoDec(O:Target*,I:Spell*Spell)
""",
        "TRIGGER.IDS": """IDS V1.0
0x4000 True()
0x400E General(O:Object*,I:General*General)
0x4031 HaveSpell(I:Spell*Spell)
0x4044 CheckStat(O:Object*,I:Value*,I:StatNum*Stats)
0x4045 CheckStatGT(O:Object*,I:Value*,I:StatNum*Stats)
0x4061 HasItem(S:ResRef*,O:Object*)
0x407F HasItemEquiped(S:ResRef*,O:Object*)
0x40BB Kit(O:Object*,I:Kit*KIT)
0x40C2 HasItemEquipedReal(S:ResRef*,O:Object*)
""",
        "OBJECT.IDS": "IDS V1.0\n0 Nothing\n1 Myself\n12 NearestEnemyOf\n18 LastSeenBy\n21 Player1\n",
        "STATS.IDS": """IDS V1.0
116 WIZARD_SPELL_DEFLECTION
119 CLERIC_CHAOTIC_COMMANDS
123 CLERIC_SHIELD_OF_THE_ARCHONS
129 WIZARD_SPELL_TURNING
131 CLERIC_FREE_ACTION
164 WIZARD_SPELL_TRAP
""",
        "KIT.IDS": "IDS V1.0\n0x4005 INQUISITOR\n0x4006 UNDEADHUNTER\n",
        "SPELL.IDS": spell_ids,
        "GENERAL.IDS": "IDS V1.0\n0 GENERAL_NONE\n4 UNDEAD\n",
        "RACE.IDS": "IDS V1.0\n0 NO_RACE\n",
        "CLASS.IDS": "IDS V1.0\n0 NO_CLASS\n",
        "SPECIFIC.IDS": "IDS V1.0\n0 SPECIFIC_NONE\n",
        "GENDER.IDS": "IDS V1.0\n0 GENDER_NONE\n",
        "ALIGN.IDS": "IDS V1.0\n0 NO_ALIGNMENT\n",
    }


GAME_IDS = ("SPELL", "ACTION", "TRIGGER", "OBJECT", "STATS", "KIT", "GENERAL")


def _write_script_ids(root: Path, spell_ids: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in _script_ids(spell_ids).items():
        (root / name).write_text(text, encoding="ascii", newline="\n")


def _chaos_block(target: str = TARGET, action: str = "Spell", extra: tuple[str, ...] = ()) -> str:
    """One of RR's Chaos casting blocks: availability, target filters, cast."""
    triggers = ("HaveSpell(WIZARD_CHAOS)", *(f.format(t=target) for f in CHAOS_FILTERS), *extra)
    return (
        "IF\n"
        + "".join(f"  {trigger}\n" for trigger in triggers)
        + f"THEN\n  RESPONSE #100\n    {action}({target},WIZARD_CHAOS)\nEND\n"
    )


def _chaos_blocks(count: int) -> str:
    return "\n".join(_chaos_block() for _ in range(count))


FEEBLEMIND_TRIGGERS = [
    "HaveSpell(WIZARD_FEEBLEMIND)",
    *(f.format(t=TARGET) for f in SINGLE_TARGET_FILTERS),
]
FEEBLEMIND_BLOCK = (
    "IF\n"
    + "".join(f"  {trigger}\n" for trigger in FEEBLEMIND_TRIGGERS)
    + f"THEN\n  RESPONSE #100\n    Spell({TARGET},WIZARD_FEEBLEMIND)\nEND\n"
)


def _script_source(name: str) -> str:
    if name == "RR#SELI":
        # Her opening Spell Trigger forces Chaos as its third spell.
        return (
            """IF
  True()
THEN
  RESPONSE #100
    ReallyForceSpell(Player1,WIZARD_CHAOS)
END

"""
            + _chaos_blocks(8)
            + """
IF
  HaveSpell(WIZARD_SPELL_TURNING)
  !CheckStatGT(Myself,0,WIZARD_SPELL_TURNING)
THEN
  RESPONSE #100
    Spell(Myself,WIZARD_SPELL_TURNING)
END

IF
  CheckStatGT(Myself,1,WIZARD_SPELL_TURNING)
THEN
  RESPONSE #100
    ReallyForceSpell(Myself,WIZARD_SPELL_TURNING)
END
"""
        )
    if name == "RR#ARAN2":
        # Another of his blocks asks whether he still has Chaos.
        return """IF
  !HaveSpell(WIZARD_CHAOS)
THEN
  RESPONSE #100
    NoAction()
END

""" + _chaos_blocks(6)
    if name == "RR#STM01":
        return _chaos_blocks(6) + "\n" + FEEBLEMIND_BLOCK
    raise AssertionError(name)


def _compile_baf(source: str, ids_root: Path, stem: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="srcb-rr-compile-") as temporary:
        scratch = Path(temporary)
        baf = scratch / f"{stem}.baf"
        baf.write_text(source, encoding="ascii", newline="\n")
        process = run_weidu(
            ["--nogame", "--search-ids", str(ids_root), str(baf), "--no-exit-pause"],
            cwd=scratch,
        )
        assert process.returncode == 0, transcript(process)
        assert "ERROR" not in transcript(process), transcript(process)
        return (scratch / f"{stem}.bcs").read_bytes()


def _decompile_bcs(source: Path, ids_root: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="srcb-rr-decompile-") as temporary:
        scratch = Path(temporary)
        process = run_weidu(
            ["--nogame", "--search-ids", str(ids_root), str(source), "--no-exit-pause"],
            cwd=scratch,
        )
        assert process.returncode == 0, transcript(process)
        return (scratch / f"{source.stem}.baf").read_text(
            encoding="utf-8", errors="replace"
        )


def _make_game(
    tmp_path: Path,
    *,
    rr_after_sr: bool,
    mixed_cre: bool = False,
    current_spell_ids: str = CURRENT_SPELL_IDS,
    compile_spell_ids: str | None = None,
    cres: dict[str, bytes | None] | None = None,
    scripts: dict[str, str | None] | None = None,
    game_ids: dict[str, str] | None = None,
    spells: dict[str, bytes] | None = None,
) -> tuple[FakeGame, Path]:
    """``cres``/``scripts`` replace a resource; ``None`` leaves it out of the game.

    ``game_ids`` replaces an IDS file in the game only; ``spells`` replaces an SPL.
    """
    compile_ids_root = tmp_path / ("compile-current" if rr_after_sr else "compile-vanilla")
    verify_ids_root = tmp_path / "verify-current"
    if compile_spell_ids is None:
        compile_spell_ids = current_spell_ids if rr_after_sr else VANILLA_SPELL_IDS
    _write_script_ids(compile_ids_root, compile_spell_ids)
    _write_script_ids(verify_ids_root, current_spell_ids)
    game_ids = game_ids or {}
    resources: list[tuple[str, str, bytes]] = [("OH6000", "ARE", b"synthetic BG2EE marker")]
    for name in GAME_IDS:
        text = game_ids.get(f"{name}.IDS")
        data = (verify_ids_root / f"{name}.IDS").read_bytes() if text is None else text.encode("ascii")
        resources.append((name, "IDS", data))
    game_spells = {
        OLD_RESREF: _wizard_spell(5),
        CHAOS_RESREF: _wizard_spell(7),
        **{resref: _wizard_spell(5) for resref in REPLACEMENTS.values()},
        **(spells or {}),
    }
    resources.extend((resref, "SPL", data) for resref, data in game_spells.items())
    cres = cres or {}
    scripts = scripts or {}
    for name, count in COUNTS.items():
        data = cres.get(
            name,
            _make_rr_cre(count, mixed=mixed_cre and name == "RR#SELI", sorcerer=name in SORCERERS),
        )
        if data is not None:
            resources.append((name, "CRE", data))
    game = FakeGame(tmp_path / "game", tuple(resources))
    for name in SCRIPT_COUNTS:
        source = scripts.get(name, _script_source(name))
        if source is None:
            continue
        (game.override / f"{name}.BCS").write_bytes(
            _compile_baf(source, compile_ids_root, name)
        )
    game.stable_hashes = game._input_hashes()

    (game.root / "SRCB_RR_COMPAT").mkdir()
    if LIVE_ROOT.exists():
        shutil.copytree(LIVE_ROOT, game.root / "SRCB_RR_COMPAT", dirs_exist_ok=True)
    return game, verify_ids_root


def _mark_dependencies(
    game: FakeGame, *, sr: bool = True, rr_components: tuple[int, ...] = (11, 12)
) -> None:
    if sr:
        game.append_weidu_log(
            "~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #0 // Spell Revisions"
        )
    for component in rr_components:
        game.append_weidu_log(
            f"~RR/SETUP-RR.TP2~ #0 #{component} // synthetic RR prerequisite"
        )


def _install_public(game: FakeGame):
    _mark_dependencies(game)
    return game.install("SRCB_RR_COMPAT/setup-SRCB_RR_COMPAT.tp2", 0)


def _decompiled(game: FakeGame, ids_root: Path, name: str) -> str:
    path = game.override_file(f"{name}.BCS")
    assert path is not None
    return _decompile_bcs(path, ids_root)


def _chaos_count(text: str) -> int:
    return text.count("WIZARD_CHAOS)") + text.count("WIZARD_SPHERE_OF_CHAOS)")


def _references(text: str, symbol: str) -> int:
    return len(re.findall(rf"[(,]{re.escape(symbol)}[),]", text))


def _blocks(text: str) -> list[tuple[list[str], str]]:
    """(trigger lines without the decompiler's comments, response text) of each block."""
    return [
        (
            [line.split("//", 1)[0].strip() for line in match.group(1).splitlines()
             if line.split("//", 1)[0].strip()],
            match.group(2),
        )
        for match in re.finditer(r"^IF\s*$(.*?)^THEN\s*$(.*?)^END\s*$", text, flags=re.S | re.M)
    ]


def _casts(actions: str, symbol: str, target: str = TARGET) -> bool:
    return re.search(rf"\b(Spell|SpellNoDec)\({re.escape(target)},{symbol}\)", actions) is not None


def _expected_triggers(name: str, target: str = TARGET, extra: tuple[str, ...] = ()) -> list[str]:
    """A retargeted Chaos block: its own triggers, then the missing filters in order."""
    kept = [*(f.format(t=target) for f in CHAOS_FILTERS), *extra]
    added = [f.format(t=target) for f in SCRIPT_FILTERS[name] if f.format(t=target) not in kept]
    return [f"HaveSpell({SCRIPT_REPLACEMENTS[name]})", *kept, *added]


def _assert_retargeted(text: str, name: str, chaos_references: int) -> int:
    """No Chaos is left; each retargeted cast block has exactly its expected triggers."""
    replacement = SCRIPT_REPLACEMENTS[name]
    assert "WIZARD_WAVES_OF_FATIGUE" not in text, text
    assert _chaos_count(text) == 0, text
    assert _references(text, replacement) == chaos_references + NATIVE_REFERENCES.get(name, 0), text
    filters = {f.format(t=TARGET) for f in SCRIPT_FILTERS[name]}
    retargeted = 0
    for triggers, actions in _blocks(text):
        if not _casts(actions, replacement):
            # Forced casts and other references gain no target filters.
            assert not filters & set(triggers), text
            continue
        if triggers == FEEBLEMIND_TRIGGERS:
            continue  # RR#STM01's own Feeblemind block, unchanged
        assert triggers == _expected_triggers(name), text
        retargeted += 1
    return retargeted


def _assert_final_resources(game: FakeGame, ids_root: Path) -> None:
    for name, old_count in COUNTS.items():
        path = game.override_file(f"{name}.CRE")
        replacement = REPLACEMENTS.get(name)
        if replacement is None:
            assert path is None, name
            continue
        assert path is not None
        data = path.read_bytes()
        known_five = replacement if name in SORCERERS else OLD_RESREF
        assert _known_spells(data) == [("ZZFIVE", 4, 1), (known_five, 4, 1), ("ZZSEVEN", 6, 1)]
        memorized = _memorized_by_level(data)
        assert memorized[4] == [("ZZMEMA", 1), *((replacement, 1),) * old_count]
        assert memorized[6] == [("ZZMEMB", 1)]
        assert _memorization_caps(data) == {
            4: (max(1, old_count + 1), 0),
            6: (1, 0),
        }

    for name, chaos_references in SCRIPT_COUNTS.items():
        text = _decompiled(game, ids_root, name)
        assert _assert_retargeted(text, name, chaos_references) == CASTING_BLOCKS[name]
    selina = _decompiled(game, ids_root, "RR#SELI")
    assert selina.count("!CheckStatGT(Myself,0,WIZARD_SPELL_DEFLECTION)") == 1
    assert "!CheckStatGT(Myself,0,WIZARD_SPELL_TURNING)" not in selina
    turning_filter = f"!CheckStatGT({TARGET},0,WIZARD_SPELL_TURNING)"
    assert selina.count("WIZARD_SPELL_TURNING") - selina.count(turning_filter) == 4
    assert "CheckStatGT(Myself,1,WIZARD_SPELL_TURNING)" in selina
    opening = _blocks(selina)[0]
    assert opening == (["True()"], opening[1])
    assert "ReallyForceSpell(Player1,WIZARD_DOMINATION)" in opening[1]
    aran = _blocks(_decompiled(game, ids_root, "RR#ARAN2"))[0]
    assert aran[0] == ["!HaveSpell(WIZARD_HOLD_MONSTER)"]


@pytest.mark.parametrize(
    ("kind", "path"),
    (("TP2", SETUP_TP2), ("TPA", LIBRARY), ("TP2", HARNESS)),
)
def test_rr_compat_parse_check(kind: str, path: Path) -> None:
    assert path.is_file(), path
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


def test_both_install_orders_converge_and_public_uninstall_restores(tmp_path: Path) -> None:
    outputs: list[dict[str, bytes]] = []
    for rr_after_sr in (False, True):
        game, ids_root = _make_game(tmp_path / str(rr_after_sr), rr_after_sr=rr_after_sr)
        before = game.override_tree()
        process = _install_public(game)
        assert_installed(process)
        _assert_final_resources(game, ids_root)
        outputs.append(game.override_tree())

        process = game.uninstall("SRCB_RR_COMPAT/setup-SRCB_RR_COMPAT.tp2", 0)
        text = transcript(process)
        assert "SUCCESSFULLY REMOVED" in text or "Uninstalled" in text, text
        assert game.override_tree() == before
        game.assert_inputs_unchanged()
    assert outputs[0] == outputs[1]


def test_repeated_production_action_is_byte_exact(tmp_path: Path) -> None:
    once_game, _ = _make_game(tmp_path / "once", rr_after_sr=False)
    assert_installed(_install_public(once_game))
    once = once_game.override_tree()

    game, ids_root = _make_game(tmp_path / "twice", rr_after_sr=False)
    process = _install_twice(game)
    assert_installed(process)
    assert "INSTALLED WITH WARNINGS" not in transcript(process), transcript(process)
    _assert_final_resources(game, ids_root)
    assert game.override_tree() == once


@pytest.mark.parametrize(
    "spell_ids", (CURRENT_SPELL_IDS, CURRENT_SPELL_IDS_CHAOS_LAST)
)
def test_final_chaos_alias_order_is_irrelevant(tmp_path: Path, spell_ids: str) -> None:
    game, ids_root = _make_game(
        tmp_path, rr_after_sr=True, current_spell_ids=spell_ids
    )
    assert_installed(_install_public(game))
    _assert_final_resources(game, ids_root)


@pytest.mark.parametrize(
    ("component", "patched_creatures", "patched_scripts"),
    (
        (11, {"RR#SELI"}, {"RR#SELI"}),
        (12, {"RR#ARAN2", "RR#SFL04"}, {"RR#ARAN2", "RR#STM01"}),
    ),
)
def test_each_rr_component_patches_only_its_own_resources(
    tmp_path: Path,
    component: int,
    patched_creatures: set[str],
    patched_scripts: set[str],
) -> None:
    game, ids_root = _make_game(tmp_path, rr_after_sr=False)
    before = game.override_tree()
    _mark_dependencies(game, rr_components=(component,))
    process = game.install("SRCB_RR_COMPAT/setup-SRCB_RR_COMPAT.tp2", 0)
    assert_installed(process)

    for name in COUNTS:
        assert (game.override_file(f"{name}.CRE") is not None) == (name in patched_creatures)
    for name in SCRIPT_COUNTS:
        path = game.override_file(f"{name}.BCS")
        assert path is not None
        if name in patched_scripts:
            assert path.read_bytes() != before[f"{name}.BCS"]
            _assert_retargeted(_decompile_bcs(path, ids_root), name, SCRIPT_COUNTS[name])
        else:
            assert path.read_bytes() == before[f"{name}.BCS"]


@pytest.mark.parametrize(
    ("sr", "rr_components"),
    ((False, (11,)), (True, ()), (True, (10,))),
)
def test_public_component_requires_both_mods(
    tmp_path: Path, sr: bool, rr_components: tuple[int, ...]
) -> None:
    game, _ = _make_game(tmp_path, rr_after_sr=True)
    _mark_dependencies(game, sr=sr, rr_components=rr_components)
    process = game.install("SRCB_RR_COMPAT/setup-SRCB_RR_COMPAT.tp2", 0)
    text = transcript(process)
    assert "SUCCESSFULLY INSTALLED" not in text, text
    assert "requires" in text.lower(), text


def test_mixed_cre_shape_fails_closed(tmp_path: Path) -> None:
    game, _ = _make_game(tmp_path, rr_after_sr=False, mixed_cre=True)
    before = game.override_tree()
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert f"RR#SELI.CRE names both {OLD_RESREF}" in text, text
    assert game.override_tree() == before


# Valid alternate layouts (compatibility policy, 2026-10-17): RR's records are
# recognized by the spell they name, not by the reference installation's counts.

Row = tuple[int, int, int, int, list[tuple[str, int]]]


def _build_cre(
    known: list[tuple[str, int, int]],
    rows: list[Row],
    layout: list[int] | None = None,
    *,
    class_id: int = 0,
    items: int = 0,
) -> bytes:
    """CRE V1.0 with known spells and memorization rows.

    ``rows`` are (level, type, maximum, current, [(resref, flags), ...]) in
    table order; ``layout`` is the physical order of their prepared records.
    ``items`` patterned item records follow the item slots.
    """
    layout = list(range(len(rows))) if layout is None else layout
    assert sorted(layout) == list(range(len(rows)))
    known_offset = 0x2D4
    info_offset = known_offset + len(known) * 0x0C
    memorized_offset = info_offset + len(rows) * 0x10
    memorized: list[tuple[str, int]] = []
    firsts: dict[int, int] = {}
    for index in layout:
        firsts[index] = len(memorized)
        memorized.extend(rows[index][4])
    slots_offset = memorized_offset + len(memorized) * 0x0C
    items_offset = slots_offset + 0x50
    end_offset = items_offset + items * 0x14
    data = bytearray(end_offset)
    data[:8] = b"CRE V1.0"
    data[0x273] = class_id
    for field_offset, value in (
        (0x2A0, known_offset),
        (0x2A4, len(known)),
        (0x2A8, info_offset),
        (0x2AC, len(rows)),
        (0x2B0, memorized_offset),
        (0x2B4, len(memorized)),
        (0x2B8, slots_offset),
        (0x2BC, items_offset),
        (0x2C0, items),
        (0x2C4, end_offset),
        (0x2C8, 0),
    ):
        _put_u32(data, field_offset, value)
    for index, (spell, level, kind) in enumerate(known):
        offset = known_offset + index * 0x0C
        _put_resref(data, offset, spell)
        _put_u16(data, offset + 8, level)
        _put_u16(data, offset + 10, kind)
    for index, (level, kind, maximum, current, entries) in enumerate(rows):
        offset = info_offset + index * 0x10
        _put_u16(data, offset, level)
        _put_u16(data, offset + 2, maximum)
        _put_u16(data, offset + 4, current)
        _put_u16(data, offset + 6, kind)
        _put_u32(data, offset + 8, firsts[index])
        _put_u32(data, offset + 12, len(entries))
    for index, (spell, flags) in enumerate(memorized):
        offset = memorized_offset + index * 0x0C
        _put_resref(data, offset, spell)
        _put_u32(data, offset + 8, flags)
    for offset in range(slots_offset, items_offset, 2):
        _put_u16(data, offset, 0xFFFF)
    for offset in range(items_offset, end_offset):
        data[offset] = (offset * 7 + 3) & 0xFF
    return bytes(data)


def _rows(data: bytes) -> list[Row]:
    info_offset, info_count = struct.unpack_from("<II", data, 0x2A8)
    memorized_offset, memorized_count = struct.unpack_from("<II", data, 0x2B0)
    result: list[Row] = []
    for index in range(info_count):
        entry = info_offset + index * 0x10
        level, maximum, current, kind = struct.unpack_from("<HHHH", data, entry)
        first, count = struct.unpack_from("<II", data, entry + 8)
        assert first + count <= memorized_count
        records = []
        for item in range(count):
            offset = memorized_offset + (first + item) * 0x0C
            records.append((_resref(data, offset), struct.unpack_from("<I", data, offset + 8)[0]))
        result.append((level, kind, maximum, current, records))
    return result


def _cre_after(game: FakeGame, name: str) -> bytes | None:
    path = game.override_file(f"{name}.CRE")
    return None if path is None else path.read_bytes()


def _assert_only_spellbook_changed(before: bytes, after: bytes) -> None:
    """Same size, header and everything after the prepared-spell table."""
    assert len(after) == len(before)
    assert after[:0x2D4] == before[:0x2D4]
    slots_offset = struct.unpack_from("<I", before, 0x2B8)[0]
    assert after[slots_offset:] == before[slots_offset:]


def _assert_known_record_removed(before: bytes, after: bytes) -> None:
    """One known record less; every later table moved with its contents."""
    assert len(after) == len(before) - 0x0C
    assert after[:0x2A0] == before[:0x2A0]
    assert after[0x2CC:0x2D4] == before[0x2CC:0x2D4]
    assert struct.unpack_from("<I", after, 0x2A4)[0] == struct.unpack_from("<I", before, 0x2A4)[0] - 1
    for field in (0x2A8, 0x2B0, 0x2B8, 0x2BC, 0x2C4):
        assert struct.unpack_from("<I", after, field)[0] == struct.unpack_from("<I", before, field)[0] - 0x0C
    for field in (0x2AC, 0x2B4, 0x2C0, 0x2C8):
        assert struct.unpack_from("<I", after, field)[0] == struct.unpack_from("<I", before, field)[0]
    old_slots = struct.unpack_from("<I", before, 0x2B8)[0]
    assert after[old_slots - 0x0C :] == before[old_slots:]


def _replaced_rows(rows: list[Row], replacement: str) -> list[Row]:
    """Expected rows: old-slot copies at level 5 become the replacement, flags kept."""
    return [
        (level, kind, maximum, current,
         [(replacement if (level, kind) == (4, 1) and spell == OLD_RESREF else spell, flags)
          for spell, flags in entries])
        for level, kind, maximum, current, entries in rows
    ]


def _full_book(flags: tuple[int, ...]) -> tuple[list[tuple[str, int, int]], list[Row]]:
    """Priest, wizard and innate rows, with old-slot copies among other records."""
    known = [("ZZPRIEST", 0, 0), (OLD_RESREF, 4, 1), ("ZZSEVEN", 6, 1), ("ZZINNATE", 0, 2)]
    rows: list[Row] = [(level, 0, 2, 1, [(f"ZZP{level}", 1)]) for level in range(7)]
    for level in range(9):
        entries = [(f"ZZW{level}", 1)]
        if level == 4:
            entries = [("ZZW4", 1), (OLD_RESREF, flags[0]), ("ZZW4B", 0)]
            entries += [(OLD_RESREF, f) for f in flags[1:]]
        rows.append((level, 1, 3, 2, entries))
    rows.append((0, 2, 1, 1, [("ZZINN", 1)]))
    return known, rows


@pytest.mark.parametrize("caster", ("wizard", "sorcerer"))
@pytest.mark.parametrize("layout", ("table-order", "level-7-first"))
def test_full_spellbook_renames_only_old_slot_copies_with_flags(
    tmp_path: Path, layout: str, caster: str
) -> None:
    known, rows = _full_book((1, 0, 3))
    order = list(range(len(rows)))
    if layout == "level-7-first":
        order = list(reversed(order))
    before = _build_cre(known, rows, order, class_id=SORCERER if caster == "sorcerer" else 1, items=2)
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": before})
    assert_installed(_install_public(game))
    after = _cre_after(game, "RR#SELI")
    assert after is not None
    _assert_only_spellbook_changed(before, after)
    assert _rows(after) == _replaced_rows(rows, "SPWI506")
    known_five = "SPWI506" if caster == "sorcerer" else OLD_RESREF
    assert _known_spells(after) == [
        ("ZZPRIEST", 0, 0), (known_five, 4, 1), ("ZZSEVEN", 6, 1), ("ZZINNATE", 0, 2)
    ]


def _selina_book(*, knows_domination: bool = False, class_id: int = SORCERER) -> tuple[bytes, list[Row]]:
    """RR v4.92's Selina: a sorcerer with four level-5 spells, six slots each."""
    known = [("SPWI401", 3, 1), ("SPWI513", 4, 1), (OLD_RESREF, 4, 1), ("SPWI505", 4, 1),
             ("SPWI514", 4, 1), ("SPWI607", 5, 1)]
    level_five = ([("SPWI513", 1)] * 6 + [(OLD_RESREF, 1)] * 6
                  + [("SPWI514", 1)] * 6 + [("SPWI505", 1)] * 6)
    if knows_domination:
        known.insert(2, ("SPWI506", 4, 1))
        level_five += [("SPWI506", 1)] * 6
    rows: list[Row] = [
        (3, 1, 6, 6, [("SPWI401", 1)] * 6),
        (4, 1, 6, 6, level_five),
        (5, 1, 5, 4, [("SPWI607", 1)] * 4 + [("SPWI607", 0)]),
    ]
    return _build_cre(known, rows, class_id=class_id, items=3), rows


def _level_five_known(data: bytes) -> list[str]:
    return [spell for spell, level, kind in _known_spells(data) if (level, kind) == (4, 1)]


def test_sorcerer_known_record_changes_with_its_prepared_copies(tmp_path: Path) -> None:
    before, rows = _selina_book()
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": before})
    assert_installed(_install_public(game))
    after = _cre_after(game, "RR#SELI")
    assert after is not None
    _assert_only_spellbook_changed(before, after)
    assert _level_five_known(after) == ["SPWI513", "SPWI506", "SPWI505", "SPWI514"]
    level_five = _rows(after)[1]
    assert level_five[:4] == (4, 1, 6, 6)
    assert [spell for spell, _ in level_five[4]] == (
        ["SPWI513"] * 6 + ["SPWI506"] * 6 + ["SPWI514"] * 6 + ["SPWI505"] * 6
    )
    # Known and memorized agree: each known spell has the level's six copies.
    assert Counter(spell for spell, _ in level_five[4]) == {
        spell: 6 for spell in _level_five_known(after)
    }
    assert _rows(after) == _replaced_rows(rows, "SPWI506")


def test_sorcerer_who_knows_the_replacement_loses_the_old_record(tmp_path: Path) -> None:
    before, rows = _selina_book(knows_domination=True)
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": before})
    assert_installed(_install_public(game))
    after = _cre_after(game, "RR#SELI")
    assert after is not None
    _assert_known_record_removed(before, after)
    assert _level_five_known(after) == ["SPWI513", "SPWI506", "SPWI505", "SPWI514"]
    assert [spell for spell, _, _ in _known_spells(after)].count("SPWI506") == 1
    assert _rows(after) == _replaced_rows(rows, "SPWI506")


def test_wizard_with_a_sorcerer_shaped_book_keeps_its_known_records(tmp_path: Path) -> None:
    before, rows = _selina_book(class_id=1)
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": before})
    assert_installed(_install_public(game))
    after = _cre_after(game, "RR#SELI")
    assert after is not None
    _assert_only_spellbook_changed(before, after)
    assert _known_spells(after) == _known_spells(before)
    assert _rows(after) == _replaced_rows(rows, "SPWI506")


def test_wizard_books_keep_their_known_records(tmp_path: Path) -> None:
    # RR v4.92's Aran (mage/thief) and RR#SFL04 (mage), level-5 rows as shipped.
    aran_rows: list[Row] = [
        (3, 1, 5, 5, [("SPWI401", 1)] * 5),
        (4, 1, 5, 5, [(OLD_RESREF, 1)] * 4 + [("SPWI505", 1)]),
    ]
    aran = _build_cre(
        [("SPWI401", 3, 1), ("SPWI505", 4, 1), (OLD_RESREF, 4, 1), ("SPWI509", 4, 1)],
        aran_rows, class_id=13,
    )
    stim_rows: list[Row] = [
        (4, 1, 5, 5, [(OLD_RESREF, 1), (OLD_RESREF, 0), ("SPWI509", 1), ("SPWI509", 1), ("SPWI505", 1)]),
    ]
    stim = _build_cre([(OLD_RESREF, 4, 1), ("SPWI505", 4, 1), ("SPWI509", 4, 1)], stim_rows, class_id=1)
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#ARAN2": aran, "RR#SFL04": stim})
    assert_installed(_install_public(game))
    for name, before, rows, replacement in (
        ("RR#ARAN2", aran, aran_rows, "SPWI507"),
        ("RR#SFL04", stim, stim_rows, "SPWI509"),
    ):
        after = _cre_after(game, name)
        assert after is not None
        _assert_only_spellbook_changed(before, after)
        assert _known_spells(after) == _known_spells(before)
        assert _rows(after) == _replaced_rows(rows, replacement)
    assert [spell for spell, _ in _rows(_cre_after(game, "RR#SFL04"))[0][4]] == (  # type: ignore[arg-type]
        ["SPWI509"] * 4 + ["SPWI505"]
    )


def test_other_copy_counts_are_replaced(tmp_path: Path) -> None:
    counts = {"RR#SELI": 5, "RR#ARAN2": 1, "RR#SFL04": 3}
    game, _ = _make_game(
        tmp_path, rr_after_sr=False,
        cres={name: _make_rr_cre(count, sorcerer=name in SORCERERS) for name, count in counts.items()},
    )
    assert_installed(_install_public(game))
    for name, count in counts.items():
        after = _cre_after(game, name)
        assert after is not None
        replacement = REPLACEMENTS[name]
        known_five = replacement if name in SORCERERS else OLD_RESREF
        assert _known_spells(after) == [("ZZFIVE", 4, 1), (known_five, 4, 1), ("ZZSEVEN", 6, 1)]
        memorized = _memorized_by_level(after)
        assert memorized[4] == [("ZZMEMA", 1), *((replacement, 1),) * count]
        assert memorized[6] == [("ZZMEMB", 1)]
        assert _memorization_caps(after) == {4: (max(1, count + 1), 0), 6: (1, 0)}


def test_prepared_without_known_and_duplicate_known_records(tmp_path: Path) -> None:
    prepared_only = _build_cre(
        [("ZZFIVE", 4, 1)], [(4, 1, 2, 2, [(OLD_RESREF, 1), (OLD_RESREF, 0)])], class_id=SORCERER
    )
    known_twice = _build_cre(
        [(OLD_RESREF, 4, 1), ("ZZFIVE", 4, 1), (OLD_RESREF, 4, 1)],
        [(4, 1, 1, 1, [(OLD_RESREF, 1)])], class_id=SORCERER,
    )
    game, _ = _make_game(
        tmp_path, rr_after_sr=False,
        cres={"RR#SFL04": prepared_only, "RR#SELI": known_twice},
    )
    assert_installed(_install_public(game))
    stim = _cre_after(game, "RR#SFL04")
    assert stim is not None
    assert _known_spells(stim) == [("ZZFIVE", 4, 1)]
    assert _rows(stim) == [(4, 1, 2, 2, [("SPWI509", 1), ("SPWI509", 0)])]
    selina = _cre_after(game, "RR#SELI")
    assert selina is not None
    _assert_known_record_removed(known_twice, selina)
    assert _known_spells(selina) == [("SPWI506", 4, 1), ("ZZFIVE", 4, 1)]
    assert _rows(selina) == [(4, 1, 1, 1, [("SPWI506", 1)])]


def test_known_only_replaced_and_unrelated_creatures_are_left_alone(tmp_path: Path) -> None:
    # Known-only old-slot records are not RR's prepared Chaos, even for a sorcerer.
    known_only = _build_cre([(OLD_RESREF, 4, 1)], [(4, 1, 1, 1, [("ZZMEMA", 1)])], class_id=SORCERER)
    # Already changed: prepares the replacement, still knows the old slot (wizard).
    replaced = _build_cre(
        [("ZZFIVE", 4, 1), (OLD_RESREF, 4, 1)],
        [(4, 1, 5, 5, [("SPWI507", 1)] * 4 + [("ZZMEMA", 1)])], class_id=13,
    )
    unrelated = _build_cre([("ZZFIVE", 4, 1)], [(4, 1, 1, 0, [("ZZMEMA", 1)]), (6, 1, 1, 0, [])])
    game, _ = _make_game(
        tmp_path, rr_after_sr=False,
        cres={"RR#SELI": known_only, "RR#ARAN2": replaced, "RR#SFL04": unrelated},
    )
    process = _install_public(game)
    assert_installed(process)
    text = transcript(process)
    assert "INSTALLED WITH WARNINGS" in text, text
    assert f"RR#SELI.CRE prepares neither {OLD_RESREF}" in text, text
    assert f"RR#SFL04.CRE prepares neither {OLD_RESREF}" in text, text
    assert "RR#ARAN2.CRE" not in text
    for name in ("RR#SELI", "RR#ARAN2", "RR#SFL04", "RR#ZAER", "RR#SAW09"):
        assert _cre_after(game, name) is None, name


def test_missing_rr_resources_are_reported(tmp_path: Path) -> None:
    game, _ = _make_game(
        tmp_path, rr_after_sr=False,
        cres={"RR#SFL04": None, "RR#ZAER": None}, scripts={"RR#STM01": None},
    )
    process = _install_public(game)
    assert_installed(process)
    text = transcript(process)
    assert "RR#SFL04.CRE is not in the game" in text, text
    assert "RR#STM01.BCS is not in the game" in text, text
    assert "RR#ZAER" not in text, text
    assert _cre_after(game, "RR#SELI") is not None


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("innate-copy", f"RR#SELI.CRE has {OLD_RESREF} prepared outside its level-5 wizard row (1 of 2 copies there)"),
        ("sorcerer-knows-it-at-level-7", f"RR#SELI.CRE knows {OLD_RESREF} outside its level-5 wizard book (1 of 2 known records there)"),
        ("copy-shared-with-level-7", "RR#SELI.CRE memorization rows 0 and 1 share prepared records"),
    ),
)
def test_unattributable_spellbooks_fail_without_changes(tmp_path: Path, case: str, message: str) -> None:
    known = [(OLD_RESREF, 4, 1)]
    rows: list[Row] = [(4, 1, 1, 1, [(OLD_RESREF, 1)]), (6, 1, 1, 1, [("ZZMEMB", 1)])]
    class_id = 1
    if case == "innate-copy":
        rows.append((0, 2, 1, 1, [(OLD_RESREF, 1)]))
    elif case == "sorcerer-knows-it-at-level-7":
        known.append((OLD_RESREF, 6, 1))
        class_id = SORCERER
    data = _build_cre(known, rows, class_id=class_id)
    if case == "copy-shared-with-level-7":
        data = _set_row_first(data, 1, 0)  # level-7 row reuses record 0
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": data})
    before = game.override_tree()
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert message in text, text
    assert game.override_tree() == before


@pytest.mark.parametrize("case", ("wizard-knows-it-at-level-7", "no-level-7-row", "rows-sharing-other-records"))
def test_layouts_the_rename_does_not_depend_on(tmp_path: Path, case: str) -> None:
    known = [(OLD_RESREF, 4, 1)]
    rows: list[Row] = [(4, 1, 2, 2, [(OLD_RESREF, 1), ("ZZW4", 1)]), (6, 1, 1, 1, [("ZZMEMB", 1)])]
    if case == "wizard-knows-it-at-level-7":
        known.append((OLD_RESREF, 6, 1))
    elif case == "no-level-7-row":
        rows = rows[:1]
    data = _build_cre(known, rows, class_id=1)
    if case == "rows-sharing-other-records":
        data = _set_row_first(data, 1, 1)  # level 7 shares ZZW4, not the copy
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": data})
    assert_installed(_install_public(game))
    after = _cre_after(game, "RR#SELI")
    assert after is not None
    assert after == _renamed_records(data, "SPWI506")


def _set_row_first(data: bytes, row: int, first: int) -> bytes:
    info_offset = struct.unpack_from("<I", data, 0x2A8)[0]
    patched = bytearray(data)
    _put_u32(patched, info_offset + row * 0x10 + 8, first)
    return bytes(patched)


def _records(data: bytes) -> list[tuple[str, int]]:
    offset, count = struct.unpack_from("<II", data, 0x2B0)
    return [(_resref(data, offset + i * 0x0C), struct.unpack_from("<I", data, offset + i * 0x0C + 8)[0])
            for i in range(count)]


def _renamed_records(data: bytes, replacement: str) -> bytes:
    """``data`` with every prepared old-slot record renamed, nothing else changed."""
    offset, count = struct.unpack_from("<II", data, 0x2B0)
    renamed = bytearray(data)
    for index in range(count):
        if _resref(data, offset + index * 0x0C) == OLD_RESREF:
            _put_resref(renamed, offset + index * 0x0C, replacement)
    return bytes(renamed)


def _install_twice(game: FakeGame):
    """The production action applied twice in one transaction (see the harness)."""
    _mark_dependencies(game)
    shutil.copy2(HARNESS, game.root / HARNESS.name)
    (game.root / "SRCB_RR_COMPAT" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(LIBRARY, game.root / "SRCB_RR_COMPAT" / "lib" / LIBRARY.name)
    return run_weidu(
        [HARNESS.name, "--game", str(game.root), "--force-install-list", "0",
         "--args", "SRCB_RR_COMPAT/lib/rr_spell_semantics.tpa", "--language", "0",
         "--use-lang", "en_US", "--no-exit-pause", "--quick-log"],
        cwd=game.root,
    )


@pytest.mark.parametrize(
    ("case", "rows", "row_first"),
    (
        # Layouts from the 2026-10-17 review: an empty level-7 row whose first
        # index points between another row's records. Renaming in place leaves
        # every row index as it was.
        ("inside-level-5", [(4, 1, 3, 3, [("ZZW4", 1), (OLD_RESREF, 1), ("ZZW4B", 1)]), (6, 1, 1, 0, [])], 1),
        ("inside-level-5-old-last", [(4, 1, 3, 3, [("ZZW4", 1), ("ZZW4B", 1), (OLD_RESREF, 0)]), (6, 1, 1, 0, [])], 1),
        ("inside-another-level", [(2, 1, 3, 3, [("ZZW2", 1), ("ZZW2B", 1), ("ZZW2C", 1)]),
                                  (4, 1, 1, 1, [(OLD_RESREF, 1)]), (6, 1, 1, 0, [])], 1),
        ("at-level-5-start", [(4, 1, 2, 2, [(OLD_RESREF, 1), ("ZZW4", 1)]), (6, 1, 1, 0, [])], 0),
    ),
)
def test_unusual_row_layouts_change_only_the_renamed_records(
    tmp_path: Path, case: str, rows: list[Row], row_first: int
) -> None:
    target_row = next(index for index, row in enumerate(rows) if row[:2] == (6, 1))
    before = _set_row_first(_build_cre([(OLD_RESREF, 4, 1)], rows), target_row, row_first)
    expected = _renamed_records(before, "SPWI506")
    for name, install in (("once", _install_public), ("twice", _install_twice)):
        game, _ = _make_game(tmp_path / name, rr_after_sr=False, cres={"RR#SELI": before})
        assert_installed(install(game))
        assert _cre_after(game, "RR#SELI") == expected, name


def test_extra_and_fewer_chaos_branches_are_retargeted(tmp_path: Path) -> None:
    scripts = {
        "RR#SELI": _script_source("RR#SELI") + "\n" + _chaos_blocks(2),
        "RR#ARAN2": _chaos_blocks(3),
    }
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, scripts=scripts)
    assert_installed(_install_public(game))
    for name, references, blocks in (("RR#SELI", 21, 10), ("RR#ARAN2", 6, 3), ("RR#STM01", 12, 6)):
        text = _decompiled(game, ids_root, name)
        assert _assert_retargeted(text, name, references) == blocks


def test_filters_a_block_has_are_kept_once_and_other_targets_get_their_own(tmp_path: Path) -> None:
    # The decompiler comments a HasItem line; it still counts as present.
    already = (
        f"!CheckStatGT({TARGET},0,CLERIC_FREE_ACTION)",
        f"!Kit({TARGET},INQUISITOR)",
        f'!HasItem("MORSWORD",{TARGET})',
    )
    nearest = "NearestEnemyOf(Myself)"
    script = "\n".join((
        _chaos_block(extra=already),
        _chaos_block(target=nearest, action="SpellNoDec"),
    ))
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, scripts={"RR#ARAN2": script})
    assert_installed(_install_public(game))
    blocks = _blocks(_decompiled(game, ids_root, "RR#ARAN2"))
    assert len(blocks) == 2
    assert blocks[0][0] == _expected_triggers("RR#ARAN2", extra=already)
    assert blocks[1][0] == _expected_triggers("RR#ARAN2", target=nearest)
    assert f"SpellNoDec({nearest},WIZARD_HOLD_MONSTER)" in blocks[1][1]
    assert TARGET not in "".join(blocks[1][0])


def test_scripts_already_pointing_at_the_replacements_are_left_alone(tmp_path: Path) -> None:
    retargeted = {
        name: _script_source(name).replace("WIZARD_CHAOS", SCRIPT_REPLACEMENTS[name])
        for name in SCRIPT_COUNTS
    }
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, scripts=retargeted)
    before = game.override_tree()
    process = _install_public(game)
    assert_installed(process)
    text = transcript(process)
    assert ".BCS names" not in text, text
    after = game.override_tree()
    assert after["RR#ARAN2.BCS"] == before["RR#ARAN2.BCS"]
    assert after["RR#STM01.BCS"] == before["RR#STM01.BCS"]
    # Selina's script changes only by her Spell Deflection guard.
    selina = _decompiled(game, ids_root, "RR#SELI")
    assert selina.count("!CheckStatGT(Myself,0,WIZARD_SPELL_DEFLECTION)") == 1
    assert f"!CheckStatGT({TARGET},0,WIZARD_SPELL_TURNING)" not in selina


def test_script_naming_both_slots_fails_without_changes(tmp_path: Path) -> None:
    sphere = "IF\n  HaveSpell(WIZARD_SPHERE_OF_CHAOS)\nTHEN\n  RESPONSE #100\n    Spell(Myself,WIZARD_SPHERE_OF_CHAOS)\nEND\n"
    game, _ = _make_game(
        tmp_path, rr_after_sr=False, scripts={"RR#STM01": _chaos_blocks(6) + "\n" + sphere}
    )
    before = game.override_tree()
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert "RR#STM01.BCS names both Waves of Fatigue (12 references) and Chaos (2)" in text, text
    assert game.override_tree() == before


def test_script_without_chaos_references_is_reported(tmp_path: Path) -> None:
    turning = "IF\n  True()\nTHEN\n  RESPONSE #100\n    Spell(Myself,WIZARD_SPELL_TURNING)\nEND\n"
    game, _ = _make_game(tmp_path, rr_after_sr=False, scripts={"RR#STM01": turning})
    before = game.override_tree()
    process = _install_public(game)
    assert_installed(process)
    text = transcript(process)
    assert "RR#STM01.BCS names neither Waves of Fatigue nor Chaos" in text, text
    assert game.override_tree()["RR#STM01.BCS"] == before["RR#STM01.BCS"]


def test_chaos_shield_is_not_mistaken_for_chaos(tmp_path: Path) -> None:
    shield = "2109 WIZARD_CHAOS_SHIELD\n"
    block = "IF\n  HaveSpell(WIZARD_CHAOS_SHIELD)\nTHEN\n  RESPONSE #100\n    Spell(Myself,WIZARD_CHAOS_SHIELD)\nEND\n"
    game, ids_root = _make_game(
        tmp_path, rr_after_sr=False,
        current_spell_ids=CURRENT_SPELL_IDS + shield,
        compile_spell_ids=VANILLA_SPELL_IDS + shield,
        scripts={"RR#STM01": _script_source("RR#STM01") + "\n" + block},
    )
    assert_installed(_install_public(game))
    text = _decompiled(game, ids_root, "RR#STM01")
    assert _assert_retargeted(text, "RR#STM01", 12) == 6
    assert text.count("WIZARD_CHAOS_SHIELD") == 2, text
    assert _blocks(text)[-1][0] == ["HaveSpell(WIZARD_CHAOS_SHIELD)"]


def test_old_slot_alias_printed_by_the_decompiler_is_recognized(tmp_path: Path) -> None:
    aliased = CURRENT_SPELL_IDS.replace(
        "2508 WIZARD_WAVES_OF_FATIGUE\n",
        "2508 WIZARD_WAVES_OF_FATIGUE\n2508 WIZARD_FATIGUE_WAVES\n",
    )
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, current_spell_ids=aliased)
    assert_installed(_install_public(game))
    for name, references in SCRIPT_COUNTS.items():
        text = _decompiled(game, ids_root, name)
        assert _assert_retargeted(text, name, references) == CASTING_BLOCKS[name]
        assert "FATIGUE" not in text


def _turning_block(guard: str, action: str) -> str:
    return f"IF\n  True()\n  {guard}\nTHEN\n  RESPONSE #100\n    {action}\nEND\n"


def test_selina_guard_is_found_by_its_self_recast_block(tmp_path: Path) -> None:
    extra = "2213 WIZARD_MIRROR_IMAGE\n"
    old_guard = "!CheckStatGT(Myself,0,WIZARD_SPELL_TURNING)"
    new_guard = "!CheckStatGT(Myself,0,WIZARD_SPELL_DEFLECTION)"
    selina = "\n".join((
        _chaos_blocks(2),
        _turning_block(old_guard, "Spell(Myself,WIZARD_SPELL_TURNING)"),
        _turning_block(old_guard, "ReallyForceSpell(Myself,WIZARD_SPELL_TURNING)"),
        _turning_block(old_guard, "Spell(Myself,WIZARD_MIRROR_IMAGE)"),
        _turning_block(new_guard, "Spell(Myself,WIZARD_SPELL_TURNING)"),
    ))
    game, ids_root = _make_game(
        tmp_path, rr_after_sr=False,
        current_spell_ids=CURRENT_SPELL_IDS + extra,
        compile_spell_ids=VANILLA_SPELL_IDS + extra,
        scripts={"RR#SELI": selina},
    )
    assert_installed(_install_public(game))
    text = _decompiled(game, ids_root, "RR#SELI")
    assert text.count(new_guard) == 3, text
    assert text.count(old_guard) == 1, text
    mirror = text.index("Spell(Myself,WIZARD_MIRROR_IMAGE)")
    assert text.rindex(old_guard, 0, mirror) > text.rindex("IF", 0, mirror)


def test_selina_without_self_recast_guard_is_reported(tmp_path: Path) -> None:
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, scripts={"RR#SELI": _chaos_blocks(3)})
    process = _install_public(game)
    assert_installed(process)
    text = transcript(process)
    assert "RR#SELI.BCS has no self-recast of Spell Turning" in text, text
    assert _assert_retargeted(_decompiled(game, ids_root, "RR#SELI"), "RR#SELI", 6) == 3


def test_spell_turning_alias_printed_by_the_decompiler_is_recognized(tmp_path: Path) -> None:
    aliased = CURRENT_SPELL_IDS.replace(
        "2701 WIZARD_SPELL_TURNING\n",
        "2701 WIZARD_SPELL_TURNING\n2701 WIZARD_GREATER_DEFLECTION\n",
    )
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, current_spell_ids=aliased)
    assert_installed(_install_public(game))
    text = _decompiled(game, ids_root, "RR#SELI")
    assert "Spell(Myself,WIZARD_GREATER_DEFLECTION)" in text, text
    assert text.count("!CheckStatGT(Myself,0,WIZARD_SPELL_DEFLECTION)") == 1, text
    assert "!CheckStatGT(Myself,0,WIZARD_SPELL_TURNING)" not in text


@pytest.mark.parametrize(
    ("ids_name", "line", "message"),
    (
        ("STATS.IDS", "164 WIZARD_SPELL_TRAP\n", "STATS.IDS has no WIZARD_SPELL_TRAP"),
        ("KIT.IDS", "0x4006 UNDEADHUNTER\n", "KIT.IDS has no UNDEADHUNTER"),
        ("GENERAL.IDS", "4 UNDEAD\n", "GENERAL.IDS has no UNDEAD"),
    ),
)
def test_missing_filter_symbol_fails_without_changes(
    tmp_path: Path, ids_name: str, line: str, message: str
) -> None:
    ids_text = _script_ids(CURRENT_SPELL_IDS)[ids_name]
    assert line in ids_text
    game, _ = _make_game(
        tmp_path, rr_after_sr=False, game_ids={ids_name: ids_text.replace(line, "")}
    )
    before = game.override_tree()
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert message in text, text
    assert game.override_tree() == before


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("symbol-at-level-6", "final SPELL.IDS must map WIZARD_HOLD_MONSTER to a level-5 wizard spell"),
        ("symbol-on-the-old-slot", "final SPELL.IDS must map WIZARD_FEEBLEMIND to a level-5 wizard spell other than Waves of Fatigue"),
        ("spell-file-at-level-6", "SPWI506.SPL is not the expected level-5 wizard spell"),
    ),
)
def test_replacement_must_be_a_level_five_wizard_spell(tmp_path: Path, case: str, message: str) -> None:
    spell_ids = CURRENT_SPELL_IDS
    spells: dict[str, bytes] = {}
    if case == "symbol-at-level-6":
        spell_ids = spell_ids.replace("2507 WIZARD_HOLD_MONSTER", "2607 WIZARD_HOLD_MONSTER")
    elif case == "symbol-on-the-old-slot":
        spell_ids = spell_ids.replace("2509 WIZARD_FEEBLEMIND", "2508 WIZARD_FEEBLEMIND")
    else:
        spells = {"SPWI506": _wizard_spell(6)}
    game, _ = _make_game(tmp_path, rr_after_sr=False, game_ids={"SPELL.IDS": spell_ids}, spells=spells)
    before = game.override_tree()
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert message in text, text
    assert game.override_tree() == before


HEX_SPELL_IDS = """IDS V1.0
0x9ca WIZARD_DOMINATION
0x9CB WIZARD_HOLD_MONSTER
0x9cc WIZARD_WAVES_OF_FATIGUE
0x9cd WIZARD_FEEBLEMIND
0xA8D WIZARD_SPELL_TURNING
0xa97 WIZARD_CHAOS
0xa97 WIZARD_SPHERE_OF_CHAOS
"""


@pytest.mark.parametrize("rr_after_sr", (False, True))
def test_hexadecimal_spell_ids_are_read(tmp_path: Path, rr_after_sr: bool) -> None:
    # Review finding 2026-10-17: the engine reads hexadecimal IDS values too.
    game, ids_root = _make_game(
        tmp_path, rr_after_sr=rr_after_sr, current_spell_ids=HEX_SPELL_IDS,
        compile_spell_ids=HEX_SPELL_IDS if rr_after_sr else VANILLA_SPELL_IDS,
    )
    assert_installed(_install_public(game))
    _assert_final_resources(game, ids_root)
