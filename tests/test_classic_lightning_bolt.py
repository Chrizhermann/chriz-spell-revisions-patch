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


def _assert_classic(
    data: bytes, *, projectile: int = 40, bonus: int = 0, foreign_damage: tuple[ie_formats.SplEffect, ...] = ()
) -> None:
    spell = ie_formats.SplFile.from_bytes(data)
    # Explicit vanilla tiers, including the level-1 fallback used for levels 1-5.
    expected = {1: (5, 50), 6: (6, 60), 7: (7, 70), 8: (8, 80), 9: (9, 90), 10: (10, 100), 24: (10, 100)}
    foreign = {effect.to_bytes() for effect in foreign_damage}
    for ability in spell.abilities:
        damage = [effect for effect in ability.effects if effect.opcode == 12 and effect.to_bytes() not in foreign]
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
    assert _apply(tmp_path, patched, library) == patched


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


def _casting_after_abilities(spell: bytes) -> bytes:
    """Store the casting-feature slice after every ability slice, as some tools do."""
    source = ie_formats.SplFile.from_bytes(spell)
    data = bytearray(spell)
    effect_offset = _u32(data, 0x6A)
    casting_count = len(source.casting_effects)
    casting_size = casting_count * 0x30
    effects = data[effect_offset:]
    data[effect_offset:] = effects[casting_size:] + effects[:casting_size]
    struct.pack_into("<H", data, 0x6E, sum(len(a.effects) for a in source.abilities))
    for index in range(len(source.abilities)):
        field = _u32(data, 0x64) + index * 0x28 + 0x20
        struct.pack_into("<H", data, field, _u16(data, field) - casting_count)
    return bytes(data)


def test_casting_slice_after_ability_effects_is_relocated_and_preserved(tmp_path: Path) -> None:
    source = ie_formats.SplFile.from_bytes(_downstream_spell())
    data = _casting_after_abilities(source.to_bytes())
    patched = _apply(tmp_path, data)
    _assert_classic(patched, bonus=-2)
    result = ie_formats.SplFile.from_bytes(patched)
    assert [e.to_bytes() for e in result.casting_effects] == [e.to_bytes() for e in source.casting_effects]
    assert _u16(patched, 0x6E) == sum(len(a.effects) for a in result.abilities)
    assert _apply(tmp_path, patched) == patched


# Foreign damage riders of the kind other mods add to the bolt's ability slice.
FIRE_RIDER = ie_formats.SplEffect(
    opcode=12, target=2, power=3, parameter2=0x80000, timing=1, resist_dispel=3,
    dice_number=2, dice_size=6, save_type=MIRROR_IMAGE_BYPASS | SAVE_VS_SPELL, special=SAVE_FOR_HALF,
    resource="RIDERFX",
)
_ELECTRICAL = dict(opcode=12, target=2, parameter2=0x40000, timing=1, dice_size=6)
ELECTRICAL_RIDERS = {
    # Correct delivery, but no half or classic dice/save shape matches.
    "d4-dice": ie_formats.SplEffect(**{**_ELECTRICAL, "dice_size": 4}, dice_number=3),
    "one-die-save-for-half": ie_formats.SplEffect(**_ELECTRICAL, dice_number=1, save_type=SAVE_VS_SPELL, special=SAVE_FOR_HALF),
    "flat-damage": ie_formats.SplEffect(**{**_ELECTRICAL, "dice_size": 0}, parameter1=5),
    # Shapes of the unsaved half (3d6, no save) with a different delivery.
    "delayed": ie_formats.SplEffect(**{**_ELECTRICAL, "timing": 4}, duration=6, dice_number=3),
    "self-target": ie_formats.SplEffect(**{**_ELECTRICAL, "target": 1}, dice_number=3),
    "chance": ie_formats.SplEffect(**_ELECTRICAL, probability1=49, dice_number=3),
}
FOREIGN_NON_DAMAGE = ie_formats.SplEffect(
    opcode=146, target=2, power=7, timing=1, resist_dispel=3,
    probability1=83, probability2=17, resource="DVOTHER", parameter1=9,
)


def _assert_rejected(tmp_path: Path, data: bytes, *fragments: str) -> None:
    process, output = _run_patch(tmp_path, data)
    result = transcript(process)
    assert "NOT INSTALLED DUE TO ERRORS" in result, result
    for fragment in fragments:
        assert fragment in result, result
    assert not output.exists(), "WeiDU should roll back the failed COPY"


def _with_last_ability(effects_for, *, projectile: int | None = None) -> bytes:
    """SR source whose last tier is replaced; a failure there must still be atomic."""
    source = ie_formats.SplFile.from_bytes(SOURCE.read_bytes())
    last = source.abilities[-1]
    last = dataclasses.replace(last, effects=tuple(effects_for(*last.effects)))
    if projectile is not None:
        last = dataclasses.replace(last, projectile=projectile)
    return dataclasses.replace(source, abilities=(*source.abilities[:-1], last)).to_bytes()


@pytest.mark.parametrize(
    ("variant", "fragment"),
    [
        ("wrong-projectile", "unsupported target, projectile (99)"),
        # Formerly "different-damage-type": the record is now foreign fire damage, and
        # the remaining saved half alone is not SR's bolt.
        ("unsaved-half-not-electrical", "found 0 and 1"),
        ("missing-saved-half", "found 1 and 0"),
        ("saved-half-wrong-dice", "found 1 and 0"),
        ("halves-with-different-metadata", "different metadata"),
        ("halves-with-different-save-flags", "different save flags"),
        # A classic-shaped packet does not make an SR-projectile tier count as converted.
        ("classic-shaped-rider-without-saved-half", "found 1 and 0"),
    ],
)
def test_unrecognized_or_inconsistent_sr_bolt_fails_without_output(tmp_path: Path, variant: str, fragment: str) -> None:
    def effects_for(unsaved: ie_formats.SplEffect, saved: ie_formats.SplEffect):
        if variant == "unsaved-half-not-electrical":
            return dataclasses.replace(unsaved, parameter2=0x80000), saved
        if variant == "missing-saved-half":
            return (unsaved,)
        if variant == "saved-half-wrong-dice":
            return unsaved, dataclasses.replace(saved, dice_number=saved.dice_number + 1)
        if variant == "halves-with-different-metadata":
            return unsaved, dataclasses.replace(saved, resource="OTHERRES")
        if variant == "halves-with-different-save-flags":
            return unsaved, dataclasses.replace(saved, save_type=saved.save_type | MIRROR_IMAGE_BYPASS)
        if variant == "classic-shaped-rider-without-saved-half":
            return unsaved, _classic_shaped_rider(10)
        return unsaved, saved

    data = _with_last_ability(effects_for, projectile=99 if variant == "wrong-projectile" else None)
    _assert_rejected(tmp_path, data, "input.spl ability 6 (level 10)", fragment)


@pytest.mark.parametrize(
    ("variant", "fragment"),
    [
        # Formerly "extra-damage": a second copy of the unsaved half is ambiguous, not foreign.
        ("duplicated-unsaved-half", "2 unsaved 5d6 and 1 breath-save 5d6"),
        ("two-indistinguishable-pairs", "2 unsaved 5d6 and 2 breath-save 5d6"),
        ("duplicated-saved-half-before-pair", "1 unsaved 5d6 and 2 breath-save 5d6"),
        # A conversion is due, so a classic-shaped rider does not relax the pair checks.
        ("duplicated-saved-half-beside-classic-shaped-rider", "1 unsaved 5d6 and 2 breath-save 5d6"),
    ],
)
def test_ambiguous_sr_damage_pairs_fail_without_output(tmp_path: Path, variant: str, fragment: str) -> None:
    def effects_for(unsaved: ie_formats.SplEffect, saved: ie_formats.SplEffect):
        if variant == "duplicated-unsaved-half":
            return unsaved, saved, unsaved
        if variant == "two-indistinguishable-pairs":
            return unsaved, saved, FIRE_RIDER, unsaved, saved
        if variant == "duplicated-saved-half-beside-classic-shaped-rider":
            return unsaved, _classic_shaped_rider(10), saved, saved
        return saved, unsaved, saved

    _assert_rejected(tmp_path, _with_last_ability(effects_for), "input.spl ability 6 (level 10)", "ambiguous", fragment)


def _dice_for(level: int) -> int:
    return min(max(level, 5), 10)


def _classic_from(unsaved: ie_formats.SplEffect, saved: ie_formats.SplEffect, level: int) -> ie_formats.SplEffect:
    """The documented conversion: unsaved half's record and position, saved half's save data."""
    return dataclasses.replace(
        unsaved, dice_number=_dice_for(level),
        save_type=(saved.save_type & 0xFFFFFFE0) | MIRROR_IMAGE_BYPASS | SAVE_VS_SPELL,
        save_bonus=saved.save_bonus + 4, special=SAVE_FOR_HALF,
    )


def _layout_spell(
    layout: tuple[str, ...], riders: dict[str, ie_formats.SplEffect], *, saved_bonus: int = -6
) -> tuple[bytes, list[list[bytes]]]:
    """Downstream SR spell whose tiers follow `layout`; returns input and expected slices.

    Layout tokens: "unsaved"/"saved" are SR's halves, "foreign" a non-damage effect,
    any other token the named rider. A rider may be a builder called with the tier's
    level and SR halves. Expected slices are the exact output records.
    """
    source = ie_formats.SplFile.from_bytes(_downstream_spell())
    original = ie_formats.SplFile.from_bytes(SOURCE.read_bytes())
    abilities, expected = [], []
    for template, ability in zip((*original.abilities, original.abilities[-1]), source.abilities, strict=True):
        unsaved, saved = template.effects
        saved = dataclasses.replace(saved, save_bonus=saved_bonus)
        records = {"unsaved": unsaved, "saved": saved, "foreign": FOREIGN_NON_DAMAGE}
        for token, rider in riders.items():
            records[token] = rider(ability.required_level, unsaved, saved) if callable(rider) else rider
        abilities.append(dataclasses.replace(ability, effects=tuple(records[token] for token in layout)))
        classic = _classic_from(unsaved, saved, ability.required_level)
        expected.append([
            (classic if token == "unsaved" else records[token]).to_bytes() for token in layout if token != "saved"
        ])
    return dataclasses.replace(source, abilities=tuple(abilities)).to_bytes(), expected


def _assert_converted(source: bytes, patched: bytes, expected: list[list[bytes]], *, bonus: int, riders) -> None:
    _assert_classic(patched, bonus=bonus, foreign_damage=tuple(riders))
    _assert_layout(source, patched, expected)


def _assert_layout(source: bytes, patched: bytes, expected: list[list[bytes]], *, projectile: int = 40) -> None:
    """Exact output records per tier; everything outside the owned fields is unchanged."""
    before, after = map(ie_formats.SplFile.from_bytes, (source, patched))
    expected_range = {1: 50, 6: 60, 7: 70, 8: 80, 9: 90, 10: 100, 24: 100}
    for ability in after.abilities:
        assert ability.projectile == projectile
        assert _u16(ability.raw, 0x0E) == expected_range[ability.required_level]
    # Only the casting-feature index may move (when that slice follows the abilities).
    assert _masked(after.header_raw, (0x6E, 2)) == _masked(before.header_raw, (0x6E, 2))
    if _u16(source, 0x6E) == 0:
        assert _u16(patched, 0x6E) == 0
    else:
        assert _u16(patched, 0x6E) == sum(len(ability) for ability in expected)
    assert [e.to_bytes() for e in after.casting_effects] == [e.to_bytes() for e in before.casting_effects]
    assert [[e.to_bytes() for e in ability.effects] for ability in after.abilities] == expected
    for old, new in zip(before.abilities, after.abilities, strict=True):
        assert _masked(new.raw, (0x0E, 2), (0x1E, 4), (0x26, 2)) == _masked(old.raw, (0x0E, 2), (0x1E, 4), (0x26, 2))


@pytest.mark.parametrize("library", [LIVE_LIB, FORK_LIB], ids=["tail", "fork"])
@pytest.mark.parametrize("casting_after", [False, True], ids=["casting-first", "casting-after-abilities"])
def test_non_electrical_damage_rider_is_preserved(tmp_path: Path, library: Path, casting_after: bool) -> None:
    layout = ("foreign", "unsaved", "fire", "saved", "foreign", "fire")
    source, expected = _layout_spell(layout, {"fire": FIRE_RIDER})
    if casting_after:
        source = _casting_after_abilities(source)
    patched = _apply(tmp_path, source, library)
    _assert_converted(source, patched, expected, bonus=-2, riders=(FIRE_RIDER,))
    assert _apply(tmp_path, patched, library) == patched


@pytest.mark.parametrize("rider", list(ELECTRICAL_RIDERS), ids=list(ELECTRICAL_RIDERS))
def test_electrical_rider_matching_neither_half_is_preserved(tmp_path: Path, rider: str) -> None:
    effect = ELECTRICAL_RIDERS[rider]
    source, expected = _layout_spell(("rider", "unsaved", "rider", "saved", "rider"), {"rider": effect})
    patched = _apply(tmp_path, source)
    _assert_converted(source, patched, expected, bonus=-2, riders=(effect,))
    assert _apply(tmp_path, patched) == patched


@pytest.mark.parametrize("casting_after", [False, True], ids=["casting-first", "casting-after-abilities"])
@pytest.mark.parametrize(
    "layout",
    [("saved", "unsaved"), ("foreign", "saved", "fire", "unsaved", "foreign"), ("saved", "foreign", "fire", "unsaved")],
    ids=["adjacent", "separated", "saved-first-in-slice"],
)
def test_saved_half_before_unsaved_half(tmp_path: Path, layout: tuple[str, ...], casting_after: bool) -> None:
    source, expected = _layout_spell(layout, {"fire": FIRE_RIDER})
    if casting_after:
        source = _casting_after_abilities(source)
    patched = _apply(tmp_path, source)
    _assert_converted(source, patched, expected, bonus=-2, riders=(FIRE_RIDER,))
    assert _apply(tmp_path, patched) == patched


@pytest.mark.parametrize(("saved_bonus", "classic_bonus"), [(-4, 0), (-6, -2), (-9, -5), (-1, 3)])
def test_later_save_adjustments_survive_with_foreign_damage(tmp_path: Path, saved_bonus: int, classic_bonus: int) -> None:
    layout = ("fire", "saved", "foreign", "unsaved")
    source, expected = _layout_spell(layout, {"fire": FIRE_RIDER}, saved_bonus=saved_bonus)
    patched = _apply(tmp_path, source)
    _assert_converted(source, patched, expected, bonus=classic_bonus, riders=(FIRE_RIDER,))
    # The SCS casting hooks of the downstream spell survive unchanged.
    assert [(e.opcode, e.resource) for e in ie_formats.SplFile.from_bytes(patched).casting_effects] == [
        (146, "DW#BLHDA"), (321, "DW#HDANI"),
    ]


def test_already_classic_bolt_with_foreign_damage_is_unchanged(tmp_path: Path) -> None:
    riders = (FIRE_RIDER, ELECTRICAL_RIDERS["d4-dice"], ELECTRICAL_RIDERS["delayed"])
    classic = ie_formats.SplFile.from_bytes(_apply(tmp_path, _downstream_spell()))
    abilities = tuple(
        dataclasses.replace(a, effects=(riders[0], *a.effects, riders[1], riders[2])) for a in classic.abilities
    )
    data = dataclasses.replace(classic, abilities=abilities).to_bytes()
    _assert_classic(data, bonus=-2, foreign_damage=riders)
    once = _apply(tmp_path, data)
    assert once == data
    assert _apply(tmp_path, once) == data


def test_partly_converted_spell_converts_only_remaining_sr_tiers(tmp_path: Path) -> None:
    source, expected = _layout_spell(("foreign", "unsaved", "fire", "saved"), {"fire": FIRE_RIDER})
    converted = ie_formats.SplFile.from_bytes(_apply(tmp_path, source))
    pending = ie_formats.SplFile.from_bytes(source)
    mixed = dataclasses.replace(pending, abilities=(converted.abilities[0], *pending.abilities[1:])).to_bytes()
    patched = _apply(tmp_path, mixed)
    _assert_converted(mixed, patched, expected, bonus=-2, riders=(FIRE_RIDER,))


def test_already_classic_bolt_with_two_classic_packets_is_unchanged(tmp_path: Path) -> None:
    """Formerly rejected as ambiguous. Nothing is converted in a classic tier, so two
    byte-identical classic packets need no choice; the spell is left byte-exact."""
    classic = ie_formats.SplFile.from_bytes(_apply(tmp_path, SOURCE.read_bytes()))
    last = classic.abilities[-1]
    damage = next(e for e in last.effects if e.opcode == 12)
    data = dataclasses.replace(
        classic, abilities=(*classic.abilities[:-1], dataclasses.replace(last, effects=(*last.effects, FIRE_RIDER, damage)))
    ).to_bytes()
    once = _apply(tmp_path, data)
    assert once == data
    assert _apply(tmp_path, once) == data


def test_already_classic_projectile_without_classic_packet_fails(tmp_path: Path) -> None:
    data = _with_last_ability(lambda unsaved, saved: (unsaved, saved, FIRE_RIDER), projectile=40)
    _assert_rejected(tmp_path, data, "input.spl ability 6 (level 10)", "without a recognizable classic bolt")


def _classic_shaped_rider(level: int, *_halves: ie_formats.SplEffect) -> ie_formats.SplEffect:
    """A foreign electrical packet that already has the converted classic packet's shape."""
    return ie_formats.SplEffect(**_ELECTRICAL, dice_number=_dice_for(level),
                                save_type=MIRROR_IMAGE_BYPASS | SAVE_VS_SPELL, special=SAVE_FOR_HALF)


@pytest.mark.parametrize("library", [LIVE_LIB, FORK_LIB], ids=["tail", "fork"])
def test_classic_shaped_electrical_rider_on_sr_bolt_survives_and_repeat_is_byte_exact(tmp_path: Path, library: Path) -> None:
    """Review finding: the rider is foreign on SR input, so the first run keeps it and the
    tier then holds two classic-shaped packets. The repeat must be a byte-exact no-op."""
    source = ie_formats.SplFile.from_bytes(SOURCE.read_bytes())
    data = dataclasses.replace(source, abilities=tuple(
        dataclasses.replace(a, effects=(*a.effects, _classic_shaped_rider(a.required_level))) for a in source.abilities
    )).to_bytes()
    once = _apply(tmp_path, data, library)
    for old, new in zip(source.abilities, ie_formats.SplFile.from_bytes(once).abilities, strict=True):
        assert [e.to_bytes() for e in new.effects] == [
            _classic_from(*old.effects, old.required_level).to_bytes(),
            _classic_shaped_rider(old.required_level).to_bytes(),
        ]
    assert _apply(tmp_path, once, library) == once


def _same_as_result(level: int, unsaved: ie_formats.SplEffect, saved: ie_formats.SplEffect) -> ie_formats.SplEffect:
    """A foreign packet byte-identical to the one the conversion produces."""
    return _classic_from(unsaved, saved, level)


@pytest.mark.parametrize("casting_after", [False, True], ids=["casting-first", "casting-after-abilities"])
@pytest.mark.parametrize(
    "layout",
    [
        ("foreign", "unsaved", "fire", "saved", "foreign"),
        ("classic", "foreign", "unsaved", "fire", "saved"),
        ("foreign", "saved", "classic", "unsaved", "fire"),
        ("unsaved", "foreign", "saved", "fire", "classic"),
        ("same", "foreign", "saved", "fire", "unsaved"),
        ("unsaved", "classic", "saved", "same", "foreign", "fire"),
    ],
    ids=["without-rider", "rider-first", "rider-between-saved-first", "rider-last", "rider-identical-to-result", "two-riders"],
)
def test_classic_shaped_rider_variations_convert_once_then_repeat_byte_exact(
    tmp_path: Path, layout: tuple[str, ...], casting_after: bool
) -> None:
    riders = {"fire": FIRE_RIDER, "classic": _classic_shaped_rider, "same": _same_as_result}
    source, expected = _layout_spell(layout, riders)
    if casting_after:
        source = _casting_after_abilities(source)
    patched = _apply(tmp_path, source)
    # Exact records per tier: the pair becomes one packet in the unsaved half's place,
    # and every rider and unrelated effect is retained byte-identically in order.
    _assert_layout(source, patched, expected)
    if "same" not in layout:  # a byte-identical rider cannot be told apart by bytes
        levels = [a.required_level for a in ie_formats.SplFile.from_bytes(source).abilities]
        foreign = (FIRE_RIDER, *(_classic_shaped_rider(level) for level in levels))
        _assert_classic(patched, bonus=-2, foreign_damage=foreign)
    assert _apply(tmp_path, patched) == patched


def test_partly_converted_tier_with_two_classic_packets_still_converts_remaining_sr_tiers(tmp_path: Path) -> None:
    layout = ("foreign", "unsaved", "classic", "fire", "saved")
    source, expected = _layout_spell(layout, {"fire": FIRE_RIDER, "classic": _classic_shaped_rider})
    converted = _apply(tmp_path, source)
    pending = ie_formats.SplFile.from_bytes(source)
    first = ie_formats.SplFile.from_bytes(converted).abilities[0]
    mixed = dataclasses.replace(pending, abilities=(first, *pending.abilities[1:])).to_bytes()
    patched = _apply(tmp_path, mixed)
    _assert_layout(mixed, patched, expected)
    assert patched == converted
    assert _apply(tmp_path, patched) == patched


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
