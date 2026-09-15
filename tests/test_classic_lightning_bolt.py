"""Exercise the optional classic Lightning Bolt through real WeiDU transformations.

The shipped SR SPL is the principal fixture. Synthetic variants represent downstream
save penalties, SCS casting hooks, relocated IDS slots, and incompatible spell shapes.
The public tail installer runs only in throwaway KEY/BIFF/TLK games; none of these
checks claim to simulate projectile movement or the engine's Mirror Image behavior.
"""

from __future__ import annotations

import dataclasses
import shutil
import struct
from pathlib import Path

import pytest

from tests import ie_formats, weidu_env
from tests.weidu_env import ROOT, FakeGame, assert_installed, nogame_harness, parse_check, transcript

HARNESS = ROOT / "tests" / "weidu" / "classic_lightning_harness.tp2"
FORK_LIB = ROOT / "spell_rev" / "lib" / "classic_lightning_bolt.tpa"
LIVE_DIR = ROOT / "live-patch" / "SRCB_CLASSIC_LIGHTNING"
LIVE_LIB = LIVE_DIR / "lib" / "classic_lightning_bolt.tpa"
LIVE_TP2 = LIVE_DIR / "setup-SRCB_CLASSIC_LIGHTNING.tp2"
LIVE_RELATIVE = "SRCB_CLASSIC_LIGHTNING/setup-SRCB_CLASSIC_LIGHTNING.tp2"
SOURCE = ROOT / "spell_rev" / "spwi3##" / "spwi308.spl"
SCROLL = ROOT / "spell_rev" / "spwi3##" / "scrl1k.itm"
SR_LOG = "~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #0 // Spell Revisions: v4.19"
MIRROR_IMAGE_BYPASS = 1 << 24
SAVE_VS_SPELL = 1
SAVE_FOR_HALF = 0x100


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _masked(data: bytes, *spans: tuple[int, int]) -> bytes:
    result = bytearray(data)
    for start, length in spans:
        result[start : start + length] = bytes(length)
    return bytes(result)


def _run_patch(tmp_path: Path, data: bytes, library: Path = LIVE_LIB, *, classic: int = 40, sr: int = 241):
    run_dir = tmp_path / f"run-{len(list(tmp_path.iterdir()))}"
    run_dir.mkdir()
    source, output = run_dir / "input.spl", run_dir / "output.spl"
    source.write_bytes(data)
    process = nogame_harness(
        HARNESS, 0, run_dir,
        [source.as_posix(), output.as_posix(), library.as_posix(), str(classic), str(sr)],
    )
    return process, output


def _apply(tmp_path: Path, data: bytes, library: Path = LIVE_LIB, **kwargs) -> bytes:
    process, output = _run_patch(tmp_path, data, library, **kwargs)
    assert_installed(process)
    assert output.is_file(), transcript(process)
    return output.read_bytes()


def _assert_classic(data: bytes, *, projectile: int = 40, bonus: int = 0) -> None:
    spell = ie_formats.SplFile.from_bytes(data)
    # Explicit vanilla tiers, including the level-1 fallback used for levels 1-5.
    expected = {1: (5, 50), 6: (6, 60), 7: (7, 70), 8: (8, 80), 9: (9, 90), 10: (10, 100), 24: (10, 100)}
    for ability in spell.abilities:
        damage = [effect for effect in ability.effects if effect.opcode == 12]
        assert len(damage) == 1, "a single full damage roll is required for true save-for-half"
        effect = damage[0]
        dice, distance = expected[ability.required_level]
        assert ability.projectile == projectile
        assert _u16(ability.raw, 0x0E) == distance
        assert effect.parameter2 == 0x40000  # electrical damage
        assert (effect.dice_number, effect.dice_size, effect.parameter1) == (dice, 6, 0)
        assert effect.save_type == MIRROR_IMAGE_BYPASS | SAVE_VS_SPELL
        assert effect.save_bonus == bonus
        assert effect.special == SAVE_FOR_HALF


def _downstream_spell() -> bytes:
    source = ie_formats.SplFile.from_bytes(SOURCE.read_bytes())
    foreign = ie_formats.SplEffect(
        opcode=146, target=2, power=7, timing=1, resist_dispel=3,
        probability1=83, probability2=17, resource="DVOTHER", parameter1=9,
    )
    hooks = (
        ie_formats.SplEffect(opcode=146, target=1, timing=1, resource="DW#BLHDA"),
        ie_formats.SplEffect(opcode=321, target=1, timing=1, resource="DW#HDANI"),
    )
    abilities = []
    for ability in (*source.abilities, dataclasses.replace(source.abilities[-1], required_level=24)):
        first, saved = ability.effects
        saved = dataclasses.replace(saved, save_bonus=-6)
        abilities.append(dataclasses.replace(ability, effects=(foreign, first, foreign, saved, foreign)))
    return dataclasses.replace(source, abilities=tuple(abilities), casting_effects=hooks).to_bytes()


@pytest.mark.parametrize(("kind", "path"), [("TP2", HARNESS), ("TP2", LIVE_TP2), ("TPA", LIVE_LIB), ("TPA", FORK_LIB)])
def test_parse_check(kind: str, path: Path) -> None:
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


def test_fork_and_tail_ship_identical_library() -> None:
    assert FORK_LIB.read_bytes() == LIVE_LIB.read_bytes()


def test_source_control_exhibits_sr_single_target_split_damage() -> None:
    source = ie_formats.SplFile.from_bytes(SOURCE.read_bytes())
    assert [a.required_level for a in source.abilities] == [1, 6, 7, 8, 9, 10]
    assert all(a.projectile == 241 and a.target == 1 and _u16(a.raw, 0x0E) == 30 for a in source.abilities)
    first, saved = source.abilities[0].effects
    assert (first.dice_number, saved.dice_number) == (3, 2)
    assert first.save_type == 0 and saved.save_type == 2 and saved.save_bonus == -4
    assert not any(e.save_type & MIRROR_IMAGE_BYPASS for a in source.abilities for e in a.effects)


@pytest.mark.parametrize("library", [LIVE_LIB, FORK_LIB], ids=["tail", "fork"])
def test_real_sr_source_becomes_classic_bolt(tmp_path: Path, library: Path) -> None:
    before = ie_formats.SplFile.from_bytes(SOURCE.read_bytes())
    patched = _apply(tmp_path, SOURCE.read_bytes(), library)
    _assert_classic(patched)
    after = ie_formats.SplFile.from_bytes(patched)
    assert after.header_raw == before.header_raw
    for old, new in zip(before.abilities, after.abilities, strict=True):
        assert _masked(new.raw, (0x0E, 2), (0x1E, 4), (0x26, 2)) == _masked(old.raw, (0x0E, 2), (0x1E, 4), (0x26, 2))
        assert new.effects[0].delivery_key() == old.effects[0].delivery_key()


def test_preserves_downstream_penalties_foreign_effects_and_casting_hooks(tmp_path: Path) -> None:
    source = _downstream_spell()
    patched = _apply(tmp_path, source)
    _assert_classic(patched, bonus=-2)
    before, after = map(ie_formats.SplFile.from_bytes, (source, patched))
    assert after.header_raw == before.header_raw
    assert [e.to_bytes() for e in after.casting_effects] == [e.to_bytes() for e in before.casting_effects]
    for old, new in zip(before.abilities, after.abilities, strict=True):
        assert [e.to_bytes() for e in new.effects if e.opcode != 12] == [e.to_bytes() for e in old.effects if e.opcode != 12]
        assert [e.opcode for e in new.effects] == [146, 12, 146, 146]
        assert _masked(new.raw, (0x0E, 2), (0x1E, 4), (0x26, 2)) == _masked(old.raw, (0x0E, 2), (0x1E, 4), (0x26, 2))


def test_second_application_is_byte_exact(tmp_path: Path) -> None:
    once = _apply(tmp_path, _downstream_spell())
    assert _apply(tmp_path, once) == once


def test_casting_slice_after_ability_effects_is_relocated_and_preserved(tmp_path: Path) -> None:
    source = ie_formats.SplFile.from_bytes(_downstream_spell())
    data = bytearray(source.to_bytes())
    effect_offset = _u32(data, 0x6A)
    casting_count = len(source.casting_effects)
    casting_size = casting_count * 0x30
    effects = data[effect_offset:]
    data[effect_offset:] = effects[casting_size:] + effects[:casting_size]
    struct.pack_into("<H", data, 0x6E, sum(len(a.effects) for a in source.abilities))
    for index in range(len(source.abilities)):
        field = _u32(data, 0x64) + index * 0x28 + 0x20
        struct.pack_into("<H", data, field, _u16(data, field) - casting_count)
    patched = _apply(tmp_path, bytes(data))
    _assert_classic(patched, bonus=-2)
    result = ie_formats.SplFile.from_bytes(patched)
    assert [e.to_bytes() for e in result.casting_effects] == [e.to_bytes() for e in source.casting_effects]
    assert _u16(patched, 0x6E) == sum(len(a.effects) for a in result.abilities)
    assert _apply(tmp_path, patched) == patched


@pytest.mark.parametrize("variant", ["wrong-projectile", "extra-damage", "different-damage-type", "missing-saved-half"])
def test_unknown_spell_shapes_fail_without_output(tmp_path: Path, variant: str) -> None:
    source = ie_formats.SplFile.from_bytes(SOURCE.read_bytes())
    last = source.abilities[-1]  # Failure after earlier valid tiers must still be atomic.
    if variant == "wrong-projectile":
        last = dataclasses.replace(last, projectile=99)
    elif variant == "extra-damage":
        last = dataclasses.replace(last, effects=(*last.effects, last.effects[0]))
    elif variant == "different-damage-type":
        last = dataclasses.replace(last, effects=(dataclasses.replace(last.effects[0], parameter2=0x80000), last.effects[1]))
    else:
        last = dataclasses.replace(last, effects=(last.effects[0],))
    data = dataclasses.replace(source, abilities=(*source.abilities[:-1], last)).to_bytes()
    process, output = _run_patch(tmp_path, data)
    result = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in result, result
    assert not output.exists(), "WeiDU should roll back the failed COPY"


def _scroll_for(resref: str, *, item_type: int = 11, learn: bool = True) -> bytes:
    data = bytearray(SCROLL.read_bytes())
    struct.pack_into("<H", data, 0x1C, item_type)
    struct.pack_into("<II", data, 0x50, 0, 0)
    effect_offset = _u32(data, 0x6A)
    for offset in range(effect_offset, len(data), 0x30):
        data[offset + 0x14 : offset + 0x1C] = resref.encode("ascii").ljust(8, b"\0")
        if not learn and _u16(data, offset) == 147:
            struct.pack_into("<H", data, offset, 146)
    return bytes(data)


def _malformed_scroll(offset_field: int) -> bytes:
    data = bytearray(_scroll_for("SPWI301"))
    struct.pack_into("<I", data, offset_field, len(data) + 0x100)
    return bytes(data)


def _fake_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, relocated: bool = False) -> tuple[FakeGame, str, int]:
    # Local extension of the shared fixture builder; restore the mapping after this test.
    monkeypatch.setitem(weidu_env.RESOURCE_TYPE, "ITM", 1005)
    resref, spell_id, classic, sr = ("SPWI399", 2399, 812, 901) if relocated else ("SPWI308", 2308, 40, 241)
    source = ie_formats.SplFile.from_bytes(_downstream_spell())
    header = bytearray(source.header_raw)
    struct.pack_into("<I", header, 0x50, 0)
    source = dataclasses.replace(source, header_raw=bytes(header), abilities=tuple(dataclasses.replace(a, projectile=sr) for a in source.abilities)).to_bytes()
    resources = [
        ("OH6000", "ARE", b"synthetic BG2EE marker"),
        ("SPELL", "IDS", f"IDS V1.0\n{spell_id} WIZARD_LIGHTNING_BOLT\n".encode("ascii")),
        ("PROJECTL", "IDS", f"IDS V1.0\n{classic - 1} LIGHTB\n{sr - 1} NEWBOLT1\n".encode("ascii")),
        (resref, "SPL", source),
        ("SCRL1K", "ITM", _scroll_for(resref)),
        ("CUSTSCRL", "ITM", _scroll_for(resref)),
        ("OTHER", "ITM", _scroll_for("SPWI301")),
        ("NONSCROL", "ITM", _scroll_for(resref, item_type=5)),
        ("CASTONLY", "ITM", _scroll_for(resref, learn=False)),
        ("BADABILI", "ITM", _malformed_scroll(0x64)),
        ("BADEFFEC", "ITM", _malformed_scroll(0x6A)),
        ("TOOSHORT", "ITM", _scroll_for("SPWI301")[:0x40]),
    ]
    if relocated:
        resources.append(("SPWI308", "SPL", SOURCE.read_bytes()))
    game = FakeGame(tmp_path / "game", tuple(resources))
    # Exercise existing override backups as well as resources initially only in the BIFF.
    (game.override / f"{resref}.spl").write_bytes(source)
    (game.override / "scrl1k.itm").write_bytes(_scroll_for(resref))
    (game.override / "unrelated.bin").write_bytes(b"preserve this foreign override")
    shutil.copytree(LIVE_DIR, game.root / LIVE_DIR.name)
    return game, resref, classic


def _tlk_text(tlk: bytes, strref: int) -> str:
    count, strings = struct.unpack_from("<II", tlk, 0x0A)
    assert 0 <= strref < count
    offset, length = struct.unpack_from("<II", tlk, 0x12 + strref * 26 + 18)
    return tlk[strings + offset : strings + offset + length].decode("utf-8", errors="replace")


@pytest.mark.parametrize("relocated", [False, True], ids=["vanilla-ids", "relocated-spell-and-projectiles"])
def test_public_tail_install_descriptions_and_byte_exact_uninstall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relocated: bool) -> None:
    game, resref, classic = _fake_game(tmp_path, monkeypatch, relocated=relocated)
    before = game.override_tree()
    key_before = (game.root / "chitin.key").read_bytes()
    bif_before = game.bif_path.read_bytes()
    game.append_weidu_log(SR_LOG)
    process = game.install(LIVE_RELATIVE, 0)
    assert_installed(process)
    after = game.override_tree()
    assert set(after) == set(before) | {"CUSTSCRL.ITM"}
    _assert_classic(after[f"{resref}.SPL"], projectile=classic, bonus=-2)
    assert after["UNRELATED.BIN"] == before["UNRELATED.BIN"]
    description = _u32(after[f"{resref}.SPL"], 0x50)
    assert description > 0
    text = _tlk_text(game.lang_tlk.read_bytes(), description).lower()
    assert "lightning" in text and "bounc" in text and "spell" in text
    for name in ("SCRL1K.ITM", "CUSTSCRL.ITM"):
        assert _u32(after[name], 0x54) == description
        assert _masked(after[name], (0x54, 4)) == _masked(_scroll_for(resref), (0x54, 4))
    assert (game.root / "chitin.key").read_bytes() == key_before
    assert game.bif_path.read_bytes() == bif_before
    assert "SRCB_CLASSIC_LIGHTNING" in game.active_weidu_log().upper()

    process = game.uninstall(LIVE_RELATIVE, 0)
    result = transcript(process)
    assert "SUCCESSFULLY REMOVED" in result or "Uninstalled" in result, result
    assert game.override_tree() == before
    assert (game.root / "chitin.key").read_bytes() == key_before
    assert game.bif_path.read_bytes() == bif_before
    assert "SRCB_CLASSIC_LIGHTNING" not in game.active_weidu_log().upper()


def test_public_tail_requires_spell_revisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    game, _, _ = _fake_game(tmp_path, monkeypatch)
    before = game.override_tree()
    process = game.install(LIVE_RELATIVE, 0)
    result = transcript(process)
    assert "SKIPPING" in result and "requires Spell Revisions" in result, result
    assert game.override_tree() == before
    game.assert_inputs_unchanged()


def test_fork_component_80_runs_real_setup_and_restores_on_uninstall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    game, resref, classic = _fake_game(tmp_path, monkeypatch, relocated=True)
    before = game.override_tree()
    fork = game.root / "spell_rev"
    (fork / "lib").mkdir(parents=True)
    for name in ("setup-spell_rev.tp2", "settings.ini"):
        shutil.copy2(ROOT / "spell_rev" / name, fork / name)
    shutil.copy2(FORK_LIB, fork / "lib" / FORK_LIB.name)
    shutil.copytree(ROOT / "spell_rev" / "languages", fork / "languages")
    game.append_weidu_log(SR_LOG)
    process = game.install("spell_rev/setup-spell_rev.tp2", 80)
    assert_installed(process)
    after = game.override_tree()
    assert set(after) == set(before) | {"CUSTSCRL.ITM"}
    _assert_classic(after[f"{resref}.SPL"], projectile=classic, bonus=-2)
    assert "#0 #80" in game.active_weidu_log()
    process = game.uninstall("spell_rev/setup-spell_rev.tp2", 80)
    result = transcript(process)
    assert "SUCCESSFULLY REMOVED" in result or "Uninstalled" in result, result
    assert game.override_tree() == before
