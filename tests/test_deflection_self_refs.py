"""Spell Deflection blocks AoE spells (component 55): guards and refreshes inside the copy.

Component 55 copies each listed area spell X into a secondary spell (X plus the first free
letter d..m) that X casts on every creature it reaches. Creatures receive the copy's effects
under the copy's name (lab-verified on BG2:EE 2.7.3.0, 2026-10-27). So a protection (opcode
206/318/324) that names X and precedes other effects of its ability never blocked them — for
example Chaotic Commands' check in both Chaos spheres — and a removal (opcode 321) of X never
found an earlier copy's effects. srcb_deflection_copy_self_refs points both at the copy. A
protection that is its ability's last effect only stops later castings; naming X already does
that, so it stays.

Coverage:
* `--nogame` harness on synthetic SPLs: byte-exact renames, kept references, casting
  features, case-insensitive matching, idempotency.
* synthetic fake game running the REAL nwn_spell_deflection.tpa: the wrapper, the copy's
  letter when X+d is taken, and the references in each copy.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
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

HARNESS = ROOT / "tests" / "weidu" / "deflection_self_refs_harness.tp2"
FAKE_GAME_TP2 = ROOT / "tests" / "weidu" / "fake_game_deflection.tp2"
LIBRARY = ROOT / "spell_rev" / "lib" / "deflection_self_refs.tpa"
COMPONENT = ROOT / "spell_rev" / "components" / "nwn_spell_deflection.tpa"
ADD_SPELL_REFERENCES = ROOT / "spell_rev" / "lib" / "manage_add_spell_references.tpa"
MAIN_COMPONENT = ROOT / "spell_rev" / "components" / "main_component.tpa"

CHAOTIC_COMMANDS_STATE = 41
SPLPROT_SPLSTATE_ROW = 110


# --------------------------------------------------------------------------- builders


def effect(opcode: int, resource: str = "", **fields: int) -> ie_formats.SplEffect:
    return ie_formats.SplEffect(opcode=opcode, target=2, resource=resource, **fields)


def guard(resource: str) -> ie_formats.SplEffect:
    """kreso's Chaotic Commands check, as main component 0 inserts it first in every ability."""
    return effect(324, resource, parameter1=CHAOTIC_COMMANDS_STATE, parameter2=SPLPROT_SPLSTATE_ROW, duration=1)


def ability(level: int, effects: list[ie_formats.SplEffect], target: int = 1, projectile: int = 1) -> ie_formats.SplAbility:
    return ie_formats.SplAbility(required_level=level, target=target, projectile=projectile, effects=tuple(effects))


def spell(abilities: list[ie_formats.SplAbility], casting: tuple[ie_formats.SplEffect, ...] = (), level: int = 4) -> bytes:
    base = ie_formats.make_spl(abilities)
    header = bytearray(base.header_raw)
    header[0x34:0x38] = level.to_bytes(4, "little")
    return dataclasses.replace(base, casting_effects=casting, header_raw=bytes(header)).to_bytes()


def resources(data: bytes) -> list[list[str]]:
    """Ability effects' resources, upper case (ie_formats reads resrefs case-insensitively)."""
    return [[e.resource for e in a.effects] for a in ie_formats.SplFile.from_bytes(data).abilities]


def with_resource(data: bytes, positions: list[tuple[int, int]], name: str) -> bytes:
    """The same bytes with the resource of each (ability, effect) position set to name."""
    out = bytearray(data)
    abilities, effects = int.from_bytes(data[0x64:0x68], "little"), int.from_bytes(data[0x6A:0x6E], "little")
    for ability_, index in positions:
        first = int.from_bytes(data[abilities + ability_ * 0x28 + 0x20 : abilities + ability_ * 0x28 + 0x22], "little")
        at = effects + (first + index) * 0x30 + 0x14
        out[at : at + 8] = name.encode("ascii").ljust(8, b"\0")
    return bytes(out)


def apply_fix(tmp_path: Path, data: bytes, original: str, copy: str) -> tuple[bytes, str]:
    run_dir = tmp_path / f"run-{len(list(tmp_path.iterdir()))}"
    run_dir.mkdir()
    (run_dir / "in.spl").write_bytes(data)
    process = nogame_harness(
        HARNESS, 0, run_dir,
        [(run_dir / "in.spl").as_posix(), (run_dir / "out.spl").as_posix(), original, copy, LIBRARY.as_posix()],
    )
    assert_installed(process)
    return (run_dir / "out.spl").read_bytes(), transcript(process)


def renamed_count(text: str) -> int:
    found = re.findall(r"srcb_test renamed=(\d+)", text)
    assert len(found) == 1, text
    return int(found[0])


# --------------------------------------------------------------------------- fixtures

# Confusion as main component 0 leaves it: a guard first in every ability, the effects, and an
# anti-restack protection last (shape of SR's sppr250).
CONFUSION = spell([
    ability(1, [guard("spwi401"), effect(128, duration=30), effect(142, parameter2=3, duration=30),
                effect(206, "SPWI401", duration=5)], target=4, projectile=170),
    ability(10, [guard("spwi401"), effect(128, duration=36), effect(206, "SPWI401", duration=5)],
            target=4, projectile=170),
])

# A refreshing spell: removal of itself first and last, a guard, a foreign guard, a foreign
# removal, and a self-protection that ends its ability. A casting feature names the spell too.
SPHERE = spell(
    [
        ability(1, [effect(321, "SPWI711", timing=1), guard("spwi711"), effect(24, duration=6),
                    guard("SPPR709"), effect(321, "SPWI205", timing=1), effect(318, "SPWI711", duration=6)]),
        ability(14, [effect(24, duration=6), effect(321, "spwi711", timing=1)]),
    ],
    casting=(effect(321, "SPWI711", timing=1),),
    level=7,
)

PRIEST_SPHERE = spell([ability(1, [guard("sppr709"), effect(76, duration=6)])], level=7)
UNRELATED_SPWI711D = spell([ability(1, [effect(0, parameter1=1, duration=60)])], level=1)


# --------------------------------------------------------------------------- environment


@pytest.mark.parametrize(
    ("kind", "path"),
    [("TPA", LIBRARY), ("TPA", COMPONENT), ("TP2", HARNESS), ("TP2", FAKE_GAME_TP2)],
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_parse_check(kind: str, path: Path) -> None:
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


# --------------------------------------------------------------------------- library (--nogame)


def test_guards_name_the_copy_in_every_ability(tmp_path: Path) -> None:
    out, text = apply_fix(tmp_path, CONFUSION, "spwi401", "spwi401d")
    assert resources(out) == [["SPWI401D", "", "", "SPWI401"], ["SPWI401D", "", "SPWI401"]]
    assert out == with_resource(CONFUSION, [(0, 0), (1, 0)], "spwi401d")  # nothing else changed
    assert renamed_count(text) == 2


def test_refreshes_rename_anywhere_but_closing_protections_and_foreign_names_stay(tmp_path: Path) -> None:
    out, text = apply_fix(tmp_path, SPHERE, "SPWI711", "spwi711e")
    assert resources(out) == [["SPWI711E", "SPWI711E", "", "SPPR709", "SPWI205", "SPWI711"], ["", "SPWI711E"]]
    assert out == with_resource(SPHERE, [(0, 0), (0, 1), (1, 1)], "spwi711e")
    assert renamed_count(text) == 3
    # the casting feature still names the original
    assert ie_formats.SplFile.from_bytes(out).casting_effects[0].resource == "SPWI711"


def test_name_matching_ignores_case(tmp_path: Path) -> None:
    out, _ = apply_fix(tmp_path, PRIEST_SPHERE, "SPPR709", "SPPR709D")
    assert resources(out) == [["SPPR709D", ""]]


def test_spell_without_self_references_is_byte_identical(tmp_path: Path) -> None:
    out, text = apply_fix(tmp_path, UNRELATED_SPWI711D, "SPWI711", "SPWI711E")
    assert out == UNRELATED_SPWI711D
    assert renamed_count(text) == 0


def test_second_pass_changes_nothing(tmp_path: Path) -> None:
    once, _ = apply_fix(tmp_path, SPHERE, "SPWI711", "spwi711e")
    twice, text = apply_fix(tmp_path, once, "SPWI711", "spwi711e")
    assert twice == once
    assert renamed_count(text) == 0


# --------------------------------------------------------------------------- component 55 (fake game)


def _spell_ids_text() -> bytes:
    """SPELL.IDS entries for every ADD_SPELL spell the component resolves (no warnings).

    A numbered registry name (spwi427) stands for its own slot. A named one (spwiwof) gets a
    stand-in slot at the level its ADD_SPELL line in main component 0 gives it; the real slot is
    whichever ADD_SPELL finds free."""
    text = ADD_SPELL_REFERENCES.read_text(encoding="utf-8")
    block = text.split("ACTION_DEFINE_ASSOCIATIVE_ARRAY new_spells BEGIN", 1)[1].split("END", 1)[0]
    levels = {
        name.lower(): int(level)
        for name, level in re.findall(
            r"^ADD_SPELL ~[^~]*\\(\w+)\.spl~ \d (\d)", MAIN_COMPONENT.read_text(encoding="latin-1"), re.MULTILINE)
    }
    lines = ["IDS V1.0"]
    for index, (resref, symbol) in enumerate(re.findall(r"^\s*(sp(?:pr|wi)\w+)\s*=>\s*(\w+)", block, re.MULTILINE)):
        kind = 1 if resref.startswith("sppr") else 2
        number = int(resref[4:]) if resref[4:].isdigit() else levels[resref] * 100 + 50 + index
        lines.append(f"{kind * 1000 + number} {symbol}")
    return ("\n".join(lines) + "\n").encode("ascii")


@pytest.fixture
def deflection_game(tmp_path: Path) -> FakeGame:
    game = FakeGame(
        tmp_path / "game",
        (
            ("SPELL", "IDS", _spell_ids_text()),
            ("SPWI401", "SPL", CONFUSION),
            ("SPWI711", "SPL", SPHERE),
            ("SPWI711D", "SPL", UNRELATED_SPWI711D),
            ("SPPR709", "SPL", PRIEST_SPHERE),
        ),
    )
    for source in (COMPONENT, LIBRARY, ADD_SPELL_REFERENCES):
        target = game.root / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(FAKE_GAME_TP2, game.root / "setup-srcb_test_deflection.tp2")
    process = game.install("setup-srcb_test_deflection.tp2", 0)
    assert "SUCCESSFULLY INSTALLED" in transcript(process), transcript(process)
    assert "Could not find" not in transcript(process), transcript(process)  # every ADD_SPELL symbol resolved
    return game


def _override(game: FakeGame, resref: str) -> bytes:
    path = game.override_file(f"{resref}.SPL")
    assert path is not None, f"{resref}.SPL missing: {sorted(game.override_tree())}"
    return path.read_bytes()


def test_component_wraps_and_points_guards_at_the_copy(deflection_game: FakeGame) -> None:
    wrapper = ie_formats.SplFile.from_bytes(_override(deflection_game, "SPWI401"))
    assert len(wrapper.abilities) == 1 and wrapper.casting_effects == ()
    (cast,) = wrapper.abilities[0].effects
    assert (cast.opcode, cast.target, cast.parameter2, cast.timing, cast.resource.upper()) == (146, 2, 1, 1, "SPWI401D")

    copy = _override(deflection_game, "SPWI401D")
    assert resources(copy) == [
        ["SPWI401D", "", "", "SPWI401"], ["SPWI401D", "", "SPWI401"]]
    assert all((a.target, a.projectile) == (1, 1) for a in ie_formats.SplFile.from_bytes(copy).abilities)


def test_component_uses_the_copy_letter_it_chose(deflection_game: FakeGame) -> None:
    # SPWI711D exists already (in the game's BIF), so the component leaves it alone and writes
    # the copy to SPWI711E
    assert deflection_game.override_file("SPWI711D.SPL") is None
    deflection_game.assert_inputs_unchanged()
    (cast,) = ie_formats.SplFile.from_bytes(_override(deflection_game, "SPWI711")).abilities[0].effects
    assert cast.resource.upper() == "SPWI711E"
    assert resources(_override(deflection_game, "SPWI711E")) == [
        ["SPWI711E", "SPWI711E", "", "SPPR709", "SPWI205", "SPWI711"], ["", "SPWI711E"]]


def test_component_fixes_the_priest_sphere_guard(deflection_game: FakeGame) -> None:
    assert resources(_override(deflection_game, "SPPR709D")) == [["SPPR709D", ""]]
    deflection_game.assert_inputs_unchanged()
