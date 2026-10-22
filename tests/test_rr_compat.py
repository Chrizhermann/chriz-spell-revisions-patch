"""Hermetic real-WeiDU tests for the RR / SR tail compatibility component."""

from __future__ import annotations

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
FINAL_RESREF = "SPWI711"
COUNTS = {
    "RR#SELI": 6,
    "RR#ZAER": 0,
    "RR#ARAN2": 4,
    "RR#SAW09": 0,
    "RR#SFL04": 2,
}
SCRIPT_COUNTS = {"RR#SELI": 17, "RR#ARAN2": 13, "RR#STM01": 12}

CURRENT_SPELL_IDS = """IDS V1.0
2508 WIZARD_WAVES_OF_FATIGUE
2701 WIZARD_SPELL_TURNING
2711 WIZARD_CHAOS
2711 WIZARD_SPHERE_OF_CHAOS
"""
CURRENT_SPELL_IDS_CHAOS_LAST = """IDS V1.0
2508 WIZARD_WAVES_OF_FATIGUE
2701 WIZARD_SPELL_TURNING
2711 WIZARD_SPHERE_OF_CHAOS
2711 WIZARD_CHAOS
"""
VANILLA_SPELL_IDS = """IDS V1.0
2508 WIZARD_CHAOS
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


def _make_rr_cre(old_copies: int, *, mixed: bool = False) -> bytes:
    """Build RR's relevant spellbook shape plus unrelated level-five/seven spells."""
    known = (("ZZFIVE", 4), (OLD_RESREF, 4), ("ZZSEVEN", 6))
    if mixed:
        known += ((FINAL_RESREF, 6),)
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


def _write_script_ids(root: Path, spell_ids: str) -> None:
    files = {
        "ACTION.IDS": """90
31 Spell(O:Target*,I:Spell*Spell)
181 ReallyForceSpell(O:Target,I:Spell*Spell)
""",
        "TRIGGER.IDS": """IDS V1.0
0x4000 True()
0x4031 HaveSpell(I:Spell*Spell)
0x4045 CheckStatGT(O:Object*,I:Value*,I:StatNum*Stats)
""",
        "OBJECT.IDS": "IDS V1.0\n0 Nothing\n1 Myself\n",
        "STATS.IDS": """IDS V1.0
116 WIZARD_SPELL_DEFLECTION
129 WIZARD_SPELL_TURNING
""",
        "SPELL.IDS": spell_ids,
        "GENERAL.IDS": "IDS V1.0\n0 GENERAL_NONE\n",
        "RACE.IDS": "IDS V1.0\n0 NO_RACE\n",
        "CLASS.IDS": "IDS V1.0\n0 NO_CLASS\n",
        "SPECIFIC.IDS": "IDS V1.0\n0 SPECIFIC_NONE\n",
        "GENDER.IDS": "IDS V1.0\n0 GENDER_NONE\n",
        "ALIGN.IDS": "IDS V1.0\n0 NO_ALIGNMENT\n",
    }
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).write_text(text, encoding="ascii", newline="\n")


def _chaos_blocks(pair_count: int) -> str:
    blocks = []
    for _ in range(pair_count):
        blocks.append(
            """IF
  HaveSpell(WIZARD_CHAOS)
THEN
  RESPONSE #100
    Spell(Myself,WIZARD_CHAOS)
END
"""
        )
    return "\n".join(blocks)


def _script_source(name: str) -> str:
    if name == "RR#SELI":
        return (
            """IF
  True()
THEN
  RESPONSE #100
    ReallyForceSpell(Myself,WIZARD_CHAOS)
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
        return """IF
  True()
THEN
  RESPONSE #100
    ReallyForceSpell(Myself,WIZARD_CHAOS)
END

""" + _chaos_blocks(6)
    if name == "RR#STM01":
        return _chaos_blocks(6)
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
) -> tuple[FakeGame, Path]:
    """``cres``/``scripts`` replace a resource; ``None`` leaves it out of the game."""
    compile_ids_root = tmp_path / ("compile-current" if rr_after_sr else "compile-vanilla")
    verify_ids_root = tmp_path / "verify-current"
    if compile_spell_ids is None:
        compile_spell_ids = current_spell_ids if rr_after_sr else VANILLA_SPELL_IDS
    _write_script_ids(compile_ids_root, compile_spell_ids)
    _write_script_ids(verify_ids_root, current_spell_ids)
    resources: list[tuple[str, str, bytes]] = [
        ("OH6000", "ARE", b"synthetic BG2EE marker"),
        ("SPELL", "IDS", current_spell_ids.encode("ascii")),
        ("ACTION", "IDS", (verify_ids_root / "ACTION.IDS").read_bytes()),
        ("TRIGGER", "IDS", (verify_ids_root / "TRIGGER.IDS").read_bytes()),
        ("OBJECT", "IDS", (verify_ids_root / "OBJECT.IDS").read_bytes()),
        ("STATS", "IDS", (verify_ids_root / "STATS.IDS").read_bytes()),
        (OLD_RESREF, "SPL", _wizard_spell(5)),
        (FINAL_RESREF, "SPL", _wizard_spell(7)),
    ]
    cres = cres or {}
    scripts = scripts or {}
    for name, count in COUNTS.items():
        data = cres.get(name, _make_rr_cre(count, mixed=mixed_cre and name == "RR#SELI"))
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


def _assert_final_resources(game: FakeGame, ids_root: Path) -> None:
    for name, old_count in COUNTS.items():
        path = game.override_file(f"{name}.CRE")
        assert path is not None
        data = path.read_bytes()
        known = _known_spells(data)
        assert Counter(known) == Counter(
            (("ZZFIVE", 4, 1), (FINAL_RESREF, 6, 1), ("ZZSEVEN", 6, 1))
        )
        memorized = _memorized_by_level(data)
        assert memorized[4] == [("ZZMEMA", 1)]
        assert Counter(memorized[6]) == Counter(
            [("ZZMEMB", 1), *((FINAL_RESREF, 1),) * old_count]
        )
        assert _memorization_caps(data) == {
            4: (max(1, old_count + 1), 0),
            6: (1, 0),
        }

    for name, expected_count in SCRIPT_COUNTS.items():
        path = game.override_file(f"{name}.BCS")
        assert path is not None
        text = _decompile_bcs(path, ids_root)
        assert (
            text.count("WIZARD_CHAOS") + text.count("WIZARD_SPHERE_OF_CHAOS")
            == expected_count
        )
        assert "WIZARD_WAVES_OF_FATIGUE" not in text
    selina = _decompile_bcs(game.override_file("RR#SELI.BCS"), ids_root)  # type: ignore[arg-type]
    assert selina.count("!CheckStatGT(Myself,0,WIZARD_SPELL_DEFLECTION)") == 1
    assert "!CheckStatGT(Myself,0,WIZARD_SPELL_TURNING)" not in selina
    assert selina.count("WIZARD_SPELL_TURNING") == 4
    assert "CheckStatGT(Myself,1,WIZARD_SPELL_TURNING)" in selina


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
    _mark_dependencies(game)
    shutil.copy2(HARNESS, game.root / HARNESS.name)
    (game.root / "SRCB_RR_COMPAT" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(LIBRARY, game.root / "SRCB_RR_COMPAT" / "lib" / LIBRARY.name)
    process = run_weidu(
        [
            HARNESS.name,
            "--game",
            str(game.root),
            "--force-install-list",
            "0",
            "--args",
            "SRCB_RR_COMPAT/lib/rr_spell_semantics.tpa",
            "--language",
            "0",
            "--use-lang",
            "en_US",
            "--no-exit-pause",
            "--quick-log",
        ],
        cwd=game.root,
    )
    assert_installed(process)
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
        (11, {"RR#SELI", "RR#ZAER"}, {"RR#SELI"}),
        (12, {"RR#ARAN2", "RR#SAW09", "RR#SFL04"}, {"RR#ARAN2", "RR#STM01"}),
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
            text = _decompile_bcs(path, ids_root)
            assert "WIZARD_WAVES_OF_FATIGUE" not in text
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
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert "RR#SELI" in text


# Valid alternate layouts (compatibility policy, 2026-10-17): RR's records are
# recognized by the spell they name, not by the reference installation's counts.

Row = tuple[int, int, int, int, list[tuple[str, int]]]


def _build_cre(
    known: list[tuple[str, int, int]],
    rows: list[Row],
    layout: list[int] | None = None,
) -> bytes:
    """CRE V1.0 with known spells and memorization rows.

    ``rows`` are (level, type, maximum, current, [(resref, flags), ...]) in
    table order; ``layout`` is the physical order of their prepared records.
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
    end_offset = slots_offset + 0x50
    data = bytearray(end_offset)
    data[:8] = b"CRE V1.0"
    for field_offset, value in (
        (0x2A0, known_offset),
        (0x2A4, len(known)),
        (0x2A8, info_offset),
        (0x2AC, len(rows)),
        (0x2B0, memorized_offset),
        (0x2B4, len(memorized)),
        (0x2B8, slots_offset),
        (0x2BC, end_offset),
        (0x2C0, 0),
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
    for offset in range(slots_offset, end_offset, 2):
        _put_u16(data, offset, 0xFFFF)
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


def _migrated_rows(rows: list[Row]) -> list[Row]:
    """Expected rows: old-slot copies leave level 5 and join level 7, flags kept."""
    moved = [(FINAL_RESREF, flags) for spell, flags in
             next(r for r in rows if r[:2] == (4, 1))[4] if spell == OLD_RESREF]
    result = []
    for level, kind, maximum, current, entries in rows:
        if (level, kind) == (4, 1):
            entries = [e for e in entries if e[0] != OLD_RESREF]
        if (level, kind) == (6, 1):
            entries = entries + moved
        result.append((level, kind, maximum, current, entries))
    return result


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


@pytest.mark.parametrize("layout", ("table-order", "level-7-first"))
def test_full_spellbook_moves_only_old_slot_copies_with_flags(tmp_path: Path, layout: str) -> None:
    known, rows = _full_book((1, 0, 3))
    order = list(range(len(rows)))
    if layout == "level-7-first":
        order = list(reversed(order))
    before = _build_cre(known, rows, order)
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": before})
    assert_installed(_install_public(game))
    after = _cre_after(game, "RR#SELI")
    assert after is not None
    _assert_only_spellbook_changed(before, after)
    assert _rows(after) == _migrated_rows(rows)
    assert _known_spells(after) == [
        ("ZZPRIEST", 0, 0), (FINAL_RESREF, 6, 1), ("ZZSEVEN", 6, 1), ("ZZINNATE", 0, 2)
    ]


def test_other_copy_counts_are_migrated(tmp_path: Path) -> None:
    counts = {"RR#SELI": 5, "RR#ZAER": 0, "RR#ARAN2": 1, "RR#SAW09": 3, "RR#SFL04": 0}
    game, _ = _make_game(
        tmp_path, rr_after_sr=False,
        cres={name: _make_rr_cre(count) for name, count in counts.items()},
    )
    assert_installed(_install_public(game))
    for name, count in counts.items():
        after = _cre_after(game, name)
        assert after is not None
        assert Counter(_known_spells(after)) == Counter(
            (("ZZFIVE", 4, 1), (FINAL_RESREF, 6, 1), ("ZZSEVEN", 6, 1))
        )
        memorized = _memorized_by_level(after)
        assert memorized[4] == [("ZZMEMA", 1)]
        assert memorized[6] == [("ZZMEMB", 1), *((FINAL_RESREF, 1),) * count]
        assert _memorization_caps(after) == {4: (max(1, count + 1), 0), 6: (1, 0)}


def test_prepared_without_known_and_duplicate_known_records(tmp_path: Path) -> None:
    rows: list[Row] = [
        (4, 1, 2, 2, [(OLD_RESREF, 1), (OLD_RESREF, 1)]),
        (6, 1, 1, 1, []),
    ]
    prepared_only = _build_cre([("ZZFIVE", 4, 1)], rows)
    known_twice = _build_cre([(OLD_RESREF, 4, 1), (OLD_RESREF, 4, 1)], [(4, 1, 1, 1, []), (6, 1, 1, 1, [])])
    game, _ = _make_game(
        tmp_path, rr_after_sr=False,
        cres={"RR#SAW09": prepared_only, "RR#ZAER": known_twice},
    )
    assert_installed(_install_public(game))
    saw = _cre_after(game, "RR#SAW09")
    assert saw is not None
    assert _known_spells(saw) == [("ZZFIVE", 4, 1)]
    assert _rows(saw) == [(4, 1, 2, 2, []), (6, 1, 1, 1, [(FINAL_RESREF, 1), (FINAL_RESREF, 1)])]
    zaer = _cre_after(game, "RR#ZAER")
    assert zaer is not None
    assert _known_spells(zaer) == [(FINAL_RESREF, 6, 1), (FINAL_RESREF, 6, 1)]
    assert _rows(zaer) == [(4, 1, 1, 1, []), (6, 1, 1, 1, [])]


def test_migrated_and_unrelated_creatures_are_left_alone(tmp_path: Path) -> None:
    migrated = _build_cre(
        [("ZZFIVE", 4, 1), (FINAL_RESREF, 6, 1)],
        [(4, 1, 1, 0, [("ZZMEMA", 1)]), (6, 1, 1, 0, [("ZZMEMB", 1), (FINAL_RESREF, 0)])],
    )
    unrelated = _build_cre([("ZZFIVE", 4, 1)], [(4, 1, 1, 0, [("ZZMEMA", 1)]), (6, 1, 1, 0, [])])
    game, _ = _make_game(
        tmp_path, rr_after_sr=False, cres={"RR#ARAN2": migrated, "RR#SFL04": unrelated}
    )
    process = _install_public(game)
    assert_installed(process)
    text = transcript(process)
    assert "INSTALLED WITH WARNINGS" in text, text
    assert f"RR#SFL04.CRE names neither {OLD_RESREF} nor {FINAL_RESREF}" in text
    assert "RR#ARAN2.CRE names" not in text
    assert _cre_after(game, "RR#ARAN2") is None
    assert _cre_after(game, "RR#SFL04") is None


def test_missing_rr_resources_are_reported(tmp_path: Path) -> None:
    game, _ = _make_game(
        tmp_path, rr_after_sr=False, cres={"RR#ZAER": None}, scripts={"RR#STM01": None}
    )
    process = _install_public(game)
    assert_installed(process)
    text = transcript(process)
    assert "RR#ZAER.CRE is not in the game" in text, text
    assert "RR#STM01.BCS is not in the game" in text, text
    assert _cre_after(game, "RR#SELI") is not None


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("innate-copy", f"RR#SELI.CRE has {OLD_RESREF} prepared outside its level-5 wizard row (1 of 2 copies there)"),
        ("known-at-level-7", f"RR#SELI.CRE knows {OLD_RESREF} outside its level-5 wizard book (1 of 2 known records there)"),
        ("no-level-7-row", "RR#SELI.CRE needs one level-5 and one level-7 wizard memorization row to move its 1 prepared Chaos copies; it has 1 and 0"),
        ("overlapping-rows", "RR#SELI.CRE memorization rows 0 and 1 share prepared records"),
    ),
)
def test_unattributable_spellbooks_fail_without_changes(tmp_path: Path, case: str, message: str) -> None:
    known = [(OLD_RESREF, 4, 1)]
    rows: list[Row] = [(4, 1, 1, 1, [(OLD_RESREF, 1)]), (6, 1, 1, 1, [("ZZMEMB", 1)])]
    if case == "innate-copy":
        rows.append((0, 2, 1, 1, [(OLD_RESREF, 1)]))
    elif case == "known-at-level-7":
        known.append((OLD_RESREF, 6, 1))
    elif case == "no-level-7-row":
        rows = rows[:1]
    data = _build_cre(known, rows)
    if case == "overlapping-rows":
        info_offset = struct.unpack_from("<I", data, 0x2A8)[0]
        patched = bytearray(data)
        _put_u32(patched, info_offset + 0x10 + 8, 0)  # level-7 row reuses record 0
        data = bytes(patched)
    game, _ = _make_game(tmp_path, rr_after_sr=False, cres={"RR#SELI": data})
    before = game.override_tree()
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert message in text, text
    assert game.override_tree() == before


def _decompiled(game: FakeGame, ids_root: Path, name: str) -> str:
    path = game.override_file(f"{name}.BCS")
    assert path is not None
    return _decompile_bcs(path, ids_root)


def _chaos_count(text: str) -> int:
    return text.count("WIZARD_CHAOS)") + text.count("WIZARD_SPHERE_OF_CHAOS)")


def test_extra_and_fewer_chaos_branches_are_migrated(tmp_path: Path) -> None:
    scripts = {
        "RR#SELI": _script_source("RR#SELI") + "\n" + _chaos_blocks(2),
        "RR#ARAN2": _chaos_blocks(3),
    }
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, scripts=scripts)
    assert_installed(_install_public(game))
    for name, expected in (("RR#SELI", 21), ("RR#ARAN2", 6), ("RR#STM01", 12)):
        text = _decompiled(game, ids_root, name)
        assert _chaos_count(text) == expected, text
        assert "WIZARD_WAVES_OF_FATIGUE" not in text


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
        scripts={"RR#STM01": _chaos_blocks(6) + "\n" + block},
    )
    assert_installed(_install_public(game))
    text = _decompiled(game, ids_root, "RR#STM01")
    assert _chaos_count(text) == 12, text
    assert text.count("WIZARD_CHAOS_SHIELD") == 2, text
    assert "WIZARD_WAVES_OF_FATIGUE" not in text


def test_old_slot_alias_printed_by_the_decompiler_is_recognized(tmp_path: Path) -> None:
    aliased = CURRENT_SPELL_IDS.replace(
        "2508 WIZARD_WAVES_OF_FATIGUE\n",
        "2508 WIZARD_WAVES_OF_FATIGUE\n2508 WIZARD_FATIGUE_WAVES\n",
    )
    game, ids_root = _make_game(tmp_path, rr_after_sr=False, current_spell_ids=aliased)
    assert_installed(_install_public(game))
    for name, expected in SCRIPT_COUNTS.items():
        text = _decompiled(game, ids_root, name)
        assert _chaos_count(text) == expected, text
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
    assert _chaos_count(_decompiled(game, ids_root, "RR#SELI")) == 6


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


def _set_row_first(data: bytes, row: int, first: int) -> bytes:
    info_offset = struct.unpack_from("<I", data, 0x2A8)[0]
    patched = bytearray(data)
    _put_u32(patched, info_offset + row * 0x10 + 8, first)
    return bytes(patched)


def _records(data: bytes) -> list[tuple[str, int]]:
    offset, count = struct.unpack_from("<II", data, 0x2B0)
    return [(_resref(data, offset + i * 0x0C), struct.unpack_from("<I", data, offset + i * 0x0C + 8)[0])
            for i in range(count)]


def _assert_rows_disjoint(data: bytes) -> None:
    info_offset, info_count = struct.unpack_from("<II", data, 0x2A8)
    used: list[int] = []
    for index in range(info_count):
        first, count = struct.unpack_from("<II", data, info_offset + index * 0x10 + 8)
        used.extend(range(first, first + count))
    assert len(used) == len(set(used))


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
    ("case", "rows", "target_first"),
    (
        # Review finding 2026-10-17: an empty level-7 row whose first index points
        # between level 5's records.
        ("inside-level-5", [(4, 1, 3, 3, [("ZZW4", 1), (OLD_RESREF, 1), ("ZZW4B", 1)]), (6, 1, 1, 0, [])], 1),
        ("inside-level-5-old-last", [(4, 1, 3, 3, [("ZZW4", 1), ("ZZW4B", 1), (OLD_RESREF, 0)]), (6, 1, 1, 0, [])], 1),
        ("inside-another-level", [(2, 1, 3, 3, [("ZZW2", 1), ("ZZW2B", 1), ("ZZW2C", 1)]),
                                  (4, 1, 1, 1, [(OLD_RESREF, 1)]), (6, 1, 1, 0, [])], 1),
        ("at-level-5-start", [(4, 1, 2, 2, [(OLD_RESREF, 1), ("ZZW4", 1)]), (6, 1, 1, 0, [])], 0),
    ),
)
def test_empty_level_seven_row_pointing_into_another_row(
    tmp_path: Path, case: str, rows: list[Row], target_first: int
) -> None:
    target_row = next(index for index, row in enumerate(rows) if row[:2] == (6, 1))
    before = _set_row_first(_build_cre([(OLD_RESREF, 4, 1)], rows), target_row, target_first)
    results = []
    for name, install in (("once", _install_public), ("twice", _install_twice)):
        game, _ = _make_game(tmp_path / name, rr_after_sr=False, cres={"RR#SELI": before})
        assert_installed(install(game))
        after = _cre_after(game, "RR#SELI")
        assert after is not None
        _assert_only_spellbook_changed(before, after)
        _assert_rows_disjoint(after)
        assert _rows(after) == _migrated_rows(rows)
        assert Counter(_records(after)) == Counter(
            (FINAL_RESREF if spell == OLD_RESREF else spell, flags) for spell, flags in _records(before)
        )
        results.append(after)
    assert results[0] == results[1]


HEX_SPELL_IDS = """IDS V1.0
0x9cc WIZARD_WAVES_OF_FATIGUE
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
