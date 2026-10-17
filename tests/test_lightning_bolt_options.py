"""Real WeiDU checks for selectable, selectively non-bouncing Lightning Bolt.

All game files are synthetic or repository-owned inputs in disposable directories.
These tests prove resource routing, data compatibility, and uninstall behavior;
projectile movement and friendly fire still require engine acceptance testing.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import struct
from pathlib import Path

import pytest

from tests import ie_formats, weidu_env
from tests.test_classic_lightning_bolt import (
    ELECTRICAL_RIDERS,
    FIRE_RIDER,
    FORK_LIB,
    LIVE_DIR,
    LIVE_LIB,
    LIVE_RELATIVE,
    LIVE_TP2,
    ROOT,
    SOURCE,
    SR_LOG,
    _assert_classic,
    _downstream_spell,
    _masked,
    _scroll_for,
    _tlk_text,
    _u16,
    _u32,
)
from tests.weidu_env import FakeGame, assert_installed, nogame_harness, parse_check, transcript


HARNESS = ROOT / "tests" / "weidu" / "nonbounce_harness.tp2"
FORK_RELATIVE = "spell_rev/setup-spell_rev.tp2"


def _projectile(*, modern: bool = True) -> bytes:
    """Area projectile with distinct unrelated fields and both bounce layouts.

    The modern count at 0x21a is the discriminator used by CDTweaks 2530.
    Legacy projectiles use rebound flags and a secondary projectile instead.
    """
    data = bytearray(0x300)
    data[:8] = b"PRO V1.0"
    struct.pack_into("<HH", data, 0x08, 3, 500)
    struct.pack_into("<I", data, 0x2C, 0x04000001)
    data[0x100:0x108] = b"LIGHTB\0\0"
    struct.pack_into("<HHH", data, 0x200, 0x1111, 17, 23)
    struct.pack_into("<H", data, 0x214, 40)
    struct.pack_into("<H", data, 0x21A, 5 if modern else 0)
    data[0x220:0x228] = b"LITBOOM\0"
    return bytes(data)


def _run_projectile_patch(tmp_path: Path, data: bytes, library: Path = LIVE_LIB):
    run = tmp_path / f"pro-run-{len(list(tmp_path.iterdir()))}"
    run.mkdir()
    source, output = run / "input.pro", run / "output.pro"
    source.write_bytes(data)
    process = nogame_harness(
        HARNESS, 0, run, [source.as_posix(), output.as_posix(), library.as_posix()]
    )
    return process, output


def _nonbouncing(data: bytes) -> bytes:
    expected = bytearray(data)
    if _u16(data, 0x21A):
        struct.pack_into("<H", expected, 0x21A, 0)
    else:
        struct.pack_into("<I", expected, 0x2C, _u32(data, 0x2C) & ~1)
        struct.pack_into("<H", expected, 0x200, _u16(data, 0x200) & ~0x10)
        struct.pack_into("<H", expected, 0x214, 0)
    return bytes(expected)


def test_nonbounce_harness_parses() -> None:
    process = parse_check("TP2", HARNESS)
    assert process.returncode == 0, transcript(process)


@pytest.mark.parametrize("library", [LIVE_LIB, FORK_LIB], ids=["tail", "fork"])
@pytest.mark.parametrize("modern", [True, False], ids=["ee26-bounce-count", "legacy-rebound"])
def test_private_projectile_changes_only_the_bounce_fields(
    tmp_path: Path, library: Path, modern: bool
) -> None:
    source = _projectile(modern=modern)
    process, output = _run_projectile_patch(tmp_path, source, library)
    assert_installed(process)
    assert output.read_bytes() == _nonbouncing(source)


@pytest.mark.parametrize("variant", ["truncated", "wrong-signature", "not-area"])
def test_malformed_projectile_fails_without_publishing(tmp_path: Path, variant: str) -> None:
    source = bytearray(_projectile())
    if variant == "truncated":
        source = source[:0x21B]
    elif variant == "wrong-signature":
        source[:8] = b"PRO V0.0"
    else:
        struct.pack_into("<H", source, 8, 2)
    process, output = _run_projectile_patch(tmp_path, bytes(source))
    result = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in result, result
    assert not output.exists()


def _item(
    *, projectile: int = 40, item_type: int = 35, electrical: bool = True,
    equip_effects: tuple[ie_formats.SplEffect, ...] = (),
) -> bytes:
    """Vanilla-shaped six-target Wand of Lightning, plus a foreign ability."""
    header = bytearray(0x72)
    header[:8] = b"ITM V1  "
    struct.pack_into("<H", header, 0x1C, item_type)
    struct.pack_into("<I", header, 0x64, 0x72)
    struct.pack_into("<H", header, 0x68, 2)
    struct.pack_into("<I", header, 0x6A, 0x72 + 2 * 0x38)
    struct.pack_into("<HH", header, 0x6E, 0, len(equip_effects))
    bolt = bytearray(0x38)
    bolt[0] = 3
    bolt[2] = 3
    bolt[0xC:0xE] = bytes((1, 6))
    struct.pack_into("<H", bolt, 0xE, 45)
    struct.pack_into("<HHHH", bolt, 0x1E, 1, len(equip_effects), 50, 0)
    struct.pack_into("<H", bolt, 0x2A, projectile)
    other = bytearray(bolt)
    struct.pack_into("<H", other, 0x20, len(equip_effects) + 1)
    struct.pack_into("<H", other, 0x2A, 99)
    effects = (
        *equip_effects,
        ie_formats.SplEffect(
            opcode=12, target=2, power=3, parameter2=0x40000 if electrical else 0x80000,
            timing=1, resist_dispel=3, dice_number=3, dice_size=6,
            save_type=0x01000008, special=0x100,
        ),
        ie_formats.SplEffect(opcode=17, target=2, timing=1, parameter1=7),
    )
    return bytes(header + bolt + other) + b"".join(e.to_bytes() for e in effects)


def _item_abilities(data: bytes) -> list[tuple[bytes, tuple[ie_formats.SplEffect, ...]]]:
    result = []
    abilities, effects = _u32(data, 0x64), _u32(data, 0x6A)
    for index in range(_u16(data, 0x68)):
        raw = data[abilities + index * 0x38 : abilities + (index + 1) * 0x38]
        first, count = _u16(raw, 0x20), _u16(raw, 0x1E)
        records = tuple(
            ie_formats.SplEffect.from_bytes(data[effects + j * 0x30 : effects + (j + 1) * 0x30])
            for j in range(first, first + count)
        )
        result.append((raw, records))
    return result


def _item_equipped_effects(data: bytes) -> tuple[ie_formats.SplEffect, ...]:
    offset, first, count = _u32(data, 0x6A), _u16(data, 0x6E), _u16(data, 0x70)
    return tuple(ie_formats.SplEffect.from_bytes(data[offset + i * 0x30 : offset + (i + 1) * 0x30])
                 for i in range(first, first + count))


def _tlk(strings: tuple[str, ...]) -> bytes:
    encoded = [text.encode("utf-8") for text in strings]
    entries = bytearray()
    payload = bytearray()
    for text in encoded:
        entries.extend(struct.pack("<H8siiII", 1, b"\0" * 8, 0, 0, len(payload), len(text)))
        payload.extend(text)
    return struct.pack("<8sHII", b"TLK V1  ", 0, len(strings), 0x12 + 26 * len(strings)) + entries + payload


def _protective_spell(classic: int) -> bytes:
    effects = tuple(
        ie_formats.SplEffect(
            opcode=opcode, target=2, power=5, parameter1=7, parameter2=classic - 1,
            timing=0, duration=36, probability1=73, probability2=11,
            resource="OTHERFX", save_type=2, save_bonus=-2,
        )
        for opcode in (83, 197)
    )
    ability = ie_formats.SplAbility(required_level=1, target=1, projectile=1, effects=effects)
    source = ie_formats.make_spl((ability,))
    return dataclasses.replace(
        source,
        casting_effects=(ie_formats.SplEffect(opcode=83, target=1, parameter2=classic - 1, duration=12),),
    ).to_bytes()


def _protected_creature(classic: int, *, extended: bool) -> bytes:
    header = bytearray(0x324)
    header[:8] = b"CRE V1.0"
    header[0x33] = int(extended)
    for offset in (0x2A0, 0x2A8, 0x2B0, 0x2B8):
        struct.pack_into("<I", header, offset, 0x2D4)
    struct.pack_into("<I", header, 0x2BC, len(header))
    struct.pack_into("<II", header, 0x2C4, len(header), 2)
    header[0x2D4:] = b"\xff" * 0x50
    effect_class = ie_formats.EffV2 if extended else ie_formats.SplEffect
    effects = [effect_class(opcode=opcode, target=1, parameter2=classic - 1, timing=9,
                            parameter1=17, power=5, probability1=100)
               for opcode in (83, 197)]
    return bytes(header) + b"".join(
        e.to_bytes()[8:] if extended else e.to_bytes() for e in effects
    )


def _creature_effects(data: bytes) -> tuple[ie_formats.SplEffect | ie_formats.EffV2, ...]:
    offset, count = struct.unpack_from("<II", data, 0x2C4)
    stride = 0x108 if data[0x33] else 0x30
    blocks = (data[offset + index * stride : offset + (index + 1) * stride]
              for index in range(count))
    if data[0x33]:
        return tuple(ie_formats.EffV2.from_bytes(b"EFF V2.0" + block) for block in blocks)
    return tuple(ie_formats.SplEffect.from_bytes(block) for block in blocks)


def _fake_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, relocated: bool = False,
    modern: bool = True,
) -> tuple[FakeGame, str, int, dict[str, bytes]]:
    for extension, value in (("ITM", 1005), ("PRO", 1021), ("EFF", 1016)):
        monkeypatch.setitem(weidu_env.RESOURCE_TYPE, extension, value)
    resref, spell_id, classic, sr = ("SPWI399", 2399, 812, 901) if relocated else ("SPWI308", 2308, 40, 241)
    source = ie_formats.SplFile.from_bytes(_downstream_spell())
    header = bytearray(source.header_raw)
    struct.pack_into("<I", header, 0x50, 0)
    source = dataclasses.replace(
        source, header_raw=bytes(header),
        abilities=tuple(dataclasses.replace(a, projectile=sr) for a in source.abilities),
    ).to_bytes()
    trap = ie_formats.make_spl((ie_formats.SplAbility(
        required_level=1, target=1, projectile=classic,
        effects=(ie_formats.SplEffect(opcode=12, target=2, parameter2=0x40000, timing=1,
                                     dice_number=8, dice_size=6, save_type=1, special=0x100),),
    ),)).to_bytes()
    resources = {
        "OH6000.ARE": b"synthetic BG2EE marker",
        "SPELL.IDS": f"IDS V1.0\n{spell_id} WIZARD_LIGHTNING_BOLT\n".encode("ascii"),
        "PROJECTL.IDS": f"IDS V1.0\n{classic - 1} LIGHTB\n{sr - 1} NEWBOLT1\n".encode("ascii"),
        "MISSILE.IDS": b"IDS V1.0\n0 NONE\n",
        f"{resref}.SPL": source,
        "LIGHTB.PRO": _projectile(modern=modern),
        "WAND07.ITM": _item(projectile=classic),
        "CUSTOMWD.ITM": _item(projectile=classic),
        "NONWAND.ITM": _item(projectile=classic, item_type=5),
        "OTHERWND.ITM": _item(projectile=99),
        "FIREWAND.ITM": _item(projectile=classic, electrical=False),
        "TRAPBOLT.SPL": trap,
        "OTHERLB.SPL": trap,
        "BOLTPROT.SPL": _protective_spell(classic),
        "CREPROT.CRE": _protected_creature(classic, extended=False),
        "CREPROT2.CRE": _protected_creature(classic, extended=True),
        "CLCK24.ITM": _item(projectile=99, item_type=32, equip_effects=tuple(
            ie_formats.SplEffect(opcode=opcode, target=1, parameter2=classic - 1,
                                timing=2, power=5, parameter1=7)
            for opcode in (83, 197)
        )),
        "SCRL1K.ITM": _scroll_for(resref),
        "CUSTSCRL.ITM": _scroll_for(resref),
    }
    if relocated:
        resources["SPWI308.SPL"] = SOURCE.read_bytes()
    game = FakeGame(tmp_path / "game", tuple(
        (*name.rsplit(".", 1), data) for name, data in resources.items()
    ))
    for name in (f"{resref}.SPL", "LIGHTB.PRO", "WAND07.ITM", "TRAPBOLT.SPL", "BOLTPROT.SPL"):
        (game.override / name).write_bytes(resources[name])
    (game.override / "unrelated.bin").write_bytes(b"preserve this foreign override")
    shutil.copytree(LIVE_DIR, game.root / LIVE_DIR.name)
    fork = game.root / "spell_rev"
    (fork / "lib").mkdir(parents=True)
    for name in ("setup-spell_rev.tp2", "settings.ini"):
        shutil.copy2(ROOT / "spell_rev" / name, fork / name)
    shutil.copy2(FORK_LIB, fork / "lib" / FORK_LIB.name)
    shutil.copytree(ROOT / "spell_rev" / "languages", fork / "languages")
    return game, resref, classic, resources


@pytest.mark.parametrize(
    ("installer", "component", "relocated", "modern"),
    [(LIVE_RELATIVE, 1, False, True), (LIVE_RELATIVE, 1, True, False),
     (FORK_RELATIVE, 81, True, True)],
    ids=["tail-modern", "tail-relocated-legacy", "fork-relocated-modern"],
)
def test_nonbounce_option_routes_spell_and_wands_but_preserves_traps_and_uninstalls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installer: str,
    component: int, relocated: bool, modern: bool,
) -> None:
    game, resref, classic, resources = _fake_game(tmp_path, monkeypatch, relocated=relocated, modern=modern)
    before = game.override_tree()
    key, bif = (game.root / "chitin.key").read_bytes(), game.bif_path.read_bytes()
    game.append_weidu_log(SR_LOG)
    process = game.install(installer, component)
    assert_installed(process)
    after = game.override_tree()
    projectiles = ie_formats.IdsFile.from_text(after["PROJECTL.IDS"].decode("ascii"))
    private = projectiles.value("SRCBLBN") + 1
    assert private != classic
    assert projectiles.value("LIGHTB") == classic - 1
    assert after["SRCBLBN.PRO"] == _nonbouncing(resources["LIGHTB.PRO"])
    assert after["LIGHTB.PRO"] == before["LIGHTB.PRO"]
    _assert_classic(after[f"{resref}.SPL"], projectile=private, bonus=-2)
    for name in ("TRAPBOLT.SPL", "OTHERLB.SPL", "NONWAND.ITM", "OTHERWND.ITM", "FIREWAND.ITM"):
        assert after.get(name, resources[name]) == resources[name], name
    assert after["UNRELATED.BIN"] == before["UNRELATED.BIN"]
    if relocated:
        assert after.get("SPWI308.SPL", resources["SPWI308.SPL"]) == resources["SPWI308.SPL"]
    for name in ("WAND07.ITM", "CUSTOMWD.ITM"):
        old_abilities, new_abilities = map(_item_abilities, (resources[name], after[name]))
        assert _u16(new_abilities[0][0], 0x2A) == private
        assert _masked(new_abilities[0][0], (0x1E, 4), (0x2A, 2)) == _masked(old_abilities[0][0], (0x1E, 4), (0x2A, 2))
        assert _masked(new_abilities[1][0], (0x20, 2)) == _masked(old_abilities[1][0], (0x20, 2))
        assert new_abilities[1][1] == old_abilities[1][1]
        assert [e.to_bytes() for e in new_abilities[0][1] if e.opcode != 83] == [e.to_bytes() for e in old_abilities[0][1]]
        protections = [e for e in new_abilities[0][1] if e.opcode == 83]
        assert len(protections) == 1
        assert (protections[0].target, protections[0].parameter2, protections[0].duration) == (1, private - 1, 2)
    spell = ie_formats.SplFile.from_bytes(after[f"{resref}.SPL"])
    assert any(e.opcode == 83 and e.target == 1 and e.parameter2 == private - 1 for e in spell.casting_effects)
    old_protection = ie_formats.SplFile.from_bytes(resources["BOLTPROT.SPL"])
    new_protection = ie_formats.SplFile.from_bytes(after["BOLTPROT.SPL"])
    for old_effects, new_effects in (
        (old_protection.casting_effects, new_protection.casting_effects),
        (old_protection.abilities[0].effects, new_protection.abilities[0].effects),
        *[(_creature_effects(resources[name]), _creature_effects(after[name]))
          for name in ("CREPROT.CRE", "CREPROT2.CRE")],
        (_item_equipped_effects(resources["CLCK24.ITM"]), _item_equipped_effects(after["CLCK24.ITM"])),
    ):
        assert len(new_effects) == 2 * len(old_effects)
        for effect in old_effects:
            assert sum(e.to_bytes() == effect.to_bytes() for e in new_effects) == 1
            clone = dataclasses.replace(effect, parameter2=private - 1)
            assert sum(e.to_bytes() == clone.to_bytes() for e in new_effects) == 1
    description = _u32(after[f"{resref}.SPL"], 0x50)
    text = _tlk_text(game.lang_tlk.read_bytes(), description).lower()
    assert "lightning" in text and ("not bounce" in text or "without bouncing" in text)
    for name in ("SCRL1K.ITM", "CUSTSCRL.ITM"):
        assert _u32(after[name], 0x54) == description
    assert (game.root / "chitin.key").read_bytes() == key
    assert game.bif_path.read_bytes() == bif
    process = game.uninstall(installer, component)
    result = transcript(process)
    assert "SUCCESSFULLY REMOVED" in result or "Uninstalled" in result, result
    assert game.override_tree() == before
    assert (game.root / "chitin.key").read_bytes() == key
    assert game.bif_path.read_bytes() == bif


@pytest.mark.parametrize(("installer", "component"), [(LIVE_RELATIVE, 0), (LIVE_RELATIVE, 1), (FORK_RELATIVE, 81)])
def test_public_install_preserves_foreign_damage_riders_and_uninstalls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installer: str, component: int
) -> None:
    game, resref, classic, _ = _fake_game(tmp_path, monkeypatch)
    riders = (FIRE_RIDER, ELECTRICAL_RIDERS["delayed"])
    spell = ie_formats.SplFile.from_bytes((game.override / f"{resref}.SPL").read_bytes())
    abilities = []
    for ability in spell.abilities:
        damage = [e for e in ability.effects if e.opcode == 12]
        others = [e for e in ability.effects if e.opcode != 12]
        # Saved half first, foreign damage between the halves and at the end.
        abilities.append(dataclasses.replace(ability, effects=(
            others[0], damage[1], riders[0], damage[0], *others[1:], riders[1],
        )))
    source = dataclasses.replace(spell, abilities=tuple(abilities)).to_bytes()
    (game.override / f"{resref}.SPL").write_bytes(source)
    before = game.override_tree()
    game.append_weidu_log(SR_LOG)
    assert_installed(game.install(installer, component))
    after = game.override_tree()
    projectile = classic
    if component != 0:
        projectile = ie_formats.IdsFile.from_text(after["PROJECTL.IDS"].decode("ascii")).value("SRCBLBN") + 1
    _assert_classic(after[f"{resref}.SPL"], projectile=projectile, bonus=-2, foreign_damage=riders)
    patched = ie_formats.SplFile.from_bytes(after[f"{resref}.SPL"])
    foreign = {rider.to_bytes() for rider in riders}

    def not_owned(effects: tuple[ie_formats.SplEffect, ...]) -> list[bytes]:
        return [e.to_bytes() for e in effects if e.opcode != 12 or e.to_bytes() in foreign]

    for old, new in zip(abilities, patched.abilities, strict=True):
        assert not_owned(new.effects) == not_owned(old.effects)
        assert len(new.effects) == len(old.effects) - 1
    process = game.uninstall(installer, component)
    assert "SUCCESSFULLY REMOVED" in transcript(process) or "Uninstalled" in transcript(process)
    assert game.override_tree() == before


@pytest.mark.parametrize(("installer", "component"), [(LIVE_RELATIVE, 1), (FORK_RELATIVE, 81)])
def test_nonbounce_option_requires_sr_and_rejects_global_no_bounce_tweak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installer: str, component: int
) -> None:
    game, _, _, _ = _fake_game(tmp_path, monkeypatch)
    before = game.override_tree()
    process = game.install(installer, component)
    result = transcript(process)
    assert "SKIPPING" in result and "Spell Revisions" in result, result
    assert game.override_tree() == before
    game.assert_inputs_unchanged()
    game.append_weidu_log(SR_LOG)
    game.append_weidu_log("~CDTWEAKS/SETUP-CDTWEAKS.TP2~ #0 #2530 // Lightning Bolts Don't Bounce")
    process = game.install(installer, component)
    result = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in result and "2530" in result, result
    assert game.override_tree() == before
    game.assert_inputs_unchanged()


@pytest.mark.parametrize("opcode", [83, 197], ids=["external-immunity", "external-reflection"])
def test_unknown_external_projectile_protection_rejects_before_any_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, opcode: int
) -> None:
    game, _, classic, _ = _fake_game(tmp_path, monkeypatch)
    (game.override / "EXTPROT.EFF").write_bytes(ie_formats.EffV2(
        opcode=opcode, target=1, parameter2=classic - 1, timing=9,
    ).to_bytes())
    before = game.override_tree()
    game.append_weidu_log(SR_LOG)
    process = game.install(LIVE_RELATIVE, 1)
    result = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in result and "external projectile protection" in result, result
    assert game.override_tree() == before
    game.assert_inputs_unchanged()


def test_existing_private_projectile_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game, _, _, _ = _fake_game(tmp_path, monkeypatch)
    (game.override / "SRCBLBN.PRO").write_bytes(b"an existing foreign resource")
    before = game.override_tree()
    game.append_weidu_log(SR_LOG)
    process = game.install(LIVE_RELATIVE, 1)
    result = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in result and "already in use" in result, result
    assert game.override_tree() == before
    game.assert_inputs_unchanged()


def test_wand_descriptions_explain_nonbounce_and_preserve_existing_statistics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game, _, _, resources = _fake_game(tmp_path, monkeypatch)
    rebound_sentence = 'Each bolt will continue through its target and proceed to "rebound" until expended.'
    introduction = "This wand releases six bolts of lightning with each charge."
    statistics = "STATISTICS:\nDamage: 3d6 electrical\nSaving Throw: Wand for half\nCharges: 50"
    other_ability = "Other ability: Restores 7 Hit Points."
    vanilla_description = f"{introduction}\n\n{rebound_sentence}\n\n{statistics}\n\n{other_ability}"
    custom_description = "A stormglass wand bearing an unfamiliar maker's sigil.\n\n" + statistics + "\n\n" + other_ability
    unrelated_description = "This unrelated wand casts a separate spell. Its description must remain unchanged."
    descriptions = ("", vanilla_description, custom_description, unrelated_description)
    tlk = _tlk(descriptions)
    game.lang_tlk.write_bytes(tlk)
    game.root_tlk.write_bytes(tlk)
    for strref, name in enumerate(("WAND07.ITM", "CUSTOMWD.ITM", "OTHERWND.ITM"), start=1):
        data = bytearray(resources[name])
        struct.pack_into("<I", data, 0x54, strref)
        (game.override / name).write_bytes(data)
    before = game.override_tree()
    game.append_weidu_log(SR_LOG)
    assert_installed(game.install(LIVE_RELATIVE, 1))
    after = game.override_tree()
    updated = {}
    for name in ("WAND07.ITM", "CUSTOMWD.ITM"):
        updated[name] = _tlk_text(game.lang_tlk.read_bytes(), _u32(after[name], 0x54))
        text = updated[name].lower()
        assert re.search(r"(?:do(?:es)? not|never) bounce|without bouncing|non-bouncing", text), text
        assert "allies" in text or "friendly fire" in text, text
        assert any(word in text for word in ("caster", "wielder", "user")), text
        assert any(word in text for word in ("protected", "immune", "cannot harm", "cannot hit")), text
        assert statistics in updated[name]
        assert other_ability in updated[name]
    assert introduction in updated["WAND07.ITM"]
    assert "rebound" not in updated["WAND07.ITM"].lower()
    assert updated["CUSTOMWD.ITM"].startswith(custom_description)
    assert after["OTHERWND.ITM"] == before["OTHERWND.ITM"]
    assert _tlk_text(game.lang_tlk.read_bytes(), 3) == unrelated_description
    process = game.uninstall(LIVE_RELATIVE, 1)
    assert "SUCCESSFULLY REMOVED" in transcript(process) or "Uninstalled" in transcript(process)
    assert game.override_tree() == before
    for strref, name in enumerate(("WAND07.ITM", "CUSTOMWD.ITM", "OTHERWND.ITM"), start=1):
        assert _tlk_text(game.lang_tlk.read_bytes(), _u32(before[name], 0x54)) == descriptions[strref]


def test_tail_variants_replace_each_other_and_can_return_to_sr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game, resref, classic, resources = _fake_game(tmp_path, monkeypatch)
    before = game.override_tree()
    game.append_weidu_log(SR_LOG)
    assert_installed(game.install(LIVE_RELATIVE, 0))
    _assert_classic(game.override_tree()[f"{resref}.SPL"], projectile=classic, bonus=-2)
    assert game.override_tree()["WAND07.ITM"] == resources["WAND07.ITM"]

    process = game.install(LIVE_RELATIVE, 1)
    assert "ANOTHER SUBCOMPONENT" in transcript(process).upper(), transcript(process)
    assert "SRCBLBN.PRO" not in game.override_tree()
    process = game.uninstall(LIVE_RELATIVE, 0)
    assert "SUCCESSFULLY REMOVED" in transcript(process) or "Uninstalled" in transcript(process)
    assert_installed(game.install(LIVE_RELATIVE, 1))
    active = game.active_weidu_log().upper()
    component_lines = [line for line in active.splitlines() if "SRCB_CLASSIC_LIGHTNING" in line]
    assert len(component_lines) == 1 and "#0 #1" in component_lines[0]
    assert "SRCBLBN.PRO" in game.override_tree()

    process = game.install(LIVE_RELATIVE, 0)
    assert "ANOTHER SUBCOMPONENT" in transcript(process).upper(), transcript(process)
    assert "SRCBLBN.PRO" in game.override_tree()
    process = game.uninstall(LIVE_RELATIVE, 1)
    assert "SUCCESSFULLY REMOVED" in transcript(process) or "Uninstalled" in transcript(process)
    assert_installed(game.install(LIVE_RELATIVE, 0))
    after = game.override_tree()
    _assert_classic(after[f"{resref}.SPL"], projectile=classic, bonus=-2)
    assert "SRCBLBN.PRO" not in after
    assert after["WAND07.ITM"] == resources["WAND07.ITM"]
    assert after["BOLTPROT.SPL"] == resources["BOLTPROT.SPL"]
    active = game.active_weidu_log().upper()
    component_lines = [line for line in active.splitlines() if "SRCB_CLASSIC_LIGHTNING" in line]
    assert len(component_lines) == 1 and "#0 #0" in component_lines[0]
    process = game.uninstall(LIVE_RELATIVE, 0)
    assert "SUCCESSFULLY REMOVED" in transcript(process) or "Uninstalled" in transcript(process)
    assert game.override_tree() == before


@pytest.mark.parametrize(("path", "components"), [(LIVE_TP2, (0, 1)), (ROOT / FORK_RELATIVE, (80, 81))])
def test_lightning_variants_share_one_optional_subcomponent(path: Path, components: tuple[int, int]) -> None:
    content = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^BEGIN\s", content)
    groups = []
    for component in components:
        block = next(block for block in blocks if re.search(rf"\bDESIGNATED\s+{component}\b", block))
        group = re.search(r"\bSUBCOMPONENT\s+~([^~]+)~", block)
        assert group, f"component {component} must be mutually exclusive with the other bolt variant"
        assert "FORCED_SUBCOMPONENT" not in block
        groups.append(group.group(1))
    assert groups[0] == groups[1]
