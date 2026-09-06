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
    script_drift: bool = False,
    current_spell_ids: str = CURRENT_SPELL_IDS,
) -> tuple[FakeGame, Path]:
    compile_ids_root = tmp_path / ("compile-current" if rr_after_sr else "compile-vanilla")
    verify_ids_root = tmp_path / "verify-current"
    _write_script_ids(
        compile_ids_root, current_spell_ids if rr_after_sr else VANILLA_SPELL_IDS
    )
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
    resources.extend(
        (name, "CRE", _make_rr_cre(count, mixed=mixed_cre and name == "RR#SELI"))
        for name, count in COUNTS.items()
    )
    game = FakeGame(tmp_path / "game", tuple(resources))
    for name in SCRIPT_COUNTS:
        source = _script_source(name)
        if script_drift and name == "RR#SELI":
            source += _chaos_blocks(1)
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


def test_script_shape_drift_fails_closed(tmp_path: Path) -> None:
    game, _ = _make_game(tmp_path, rr_after_sr=False, script_drift=True)
    process = _install_public(game)
    text = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert "RR#SELI.BCS has an unexpected Chaos reference shape" in text
