"""Component 60 migrates SR's hidden elemental choices to their public parent.

The legacy SR_SUBSPELL_FIX hard-coded four resrefs. These tests instead exercise the
maintained component against effective SPELL.IDS, container opcode 214, selector 2DA,
and HIDESPL data in a disposable synthetic BG2:EE-shaped game.
"""

from __future__ import annotations

import shutil
import struct
from dataclasses import dataclass, replace
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


HARNESS = ROOT / "tests" / "weidu" / "fake_game_npc_spellbooks.tp2"
CRE_HARNESS = ROOT / "tests" / "weidu" / "hidden_elemental_cre_harness.tp2"
SETUP_TP2 = ROOT / "spell_rev" / "setup-spell_rev.tp2"
JOINABLE_LIB = ROOT / "spell_rev" / "lib" / "joinable_npcs.tpa"
ARCANE_FIX = ROOT / "spell_rev" / "components" / "fix_arcane_spellbooks.tpa"
CLEANUP_LIB = ROOT / "spell_rev" / "lib" / "hidden_elemental_subspells.tpa"
CLEANUP_PATCH = ROOT / "spell_rev" / "lib" / "hidden_elemental_subspells_patch.tph"
NEERA_SCRIPT = ROOT / "tests" / "weidu" / "NEERASCR.BAF"
CONTROL_SCRIPT = ROOT / "tests" / "weidu" / "CTRLBCS.BAF"

PARENT_SYMBOL = "WIZARD_PROTECTION_FROM_ELEMENTAL_ENERGY"
CHILD_SYMBOLS = (
    "WIZARD_PROTECTION_FROM_FIRE",
    "WIZARD_PROTECTION_FROM_COLD",
    "WIZARD_PROTECTION_FROM_ELECTRICITY",
    "WIZARD_PROTECTION_FROM_ACID",
)
LEGACY_CHILDREN = ("SPWI319", "SPWI320", "SPWI512", "SPWI517")
LEGITIMATE = ("ZZLEGIT", "ZZHIDDN", "ZZVISIB")


@dataclass(frozen=True)
class Layout:
    parent_value: int
    parent: str
    selector: str
    child_values: tuple[int, ...]
    children: tuple[str, ...]
    hidden: tuple[bool, ...]
    selector_text: bytes
    hidespl_text: bytes


CURRENT = Layout(
    parent_value=2426,
    parent="SPWI426",
    selector="DVWI426",
    child_values=(2319, 2320, 2512, 2517),
    children=LEGACY_CHILDREN,
    hidden=(True, True, True, True),
    selector_text=(
        "2DA V1.0\n"
        "0\n"
        "ResRef Type\n"
        "ProFire SPWI319 3\n"
        "ProCold SPWI320 3\n"
        "ProElec SPWI512 3\n"
        "ProAcid SPWI517 3\n"
        "Foreign ZZHIDDN 3\n"
        "Visible ZZVISIB 3\n"
    ).encode("ascii"),
    hidespl_text=(
        "2DA V1.0\n"
        "0\n"
        "IS_HIDDEN IS_FINAL IS_REMOVED\n"
        "SPWI319 1 0 0\n"
        "SPWI320 1 0 0\n"
        "SPWI512 1 0 0\n"
        "SPWI517 1 0 0\n"
        "ZZHIDDN 1 0 0\n"
        "ZZVISIB 0 0 0\n"
        "ZZOTHER 1 0 0\n"
    ).encode("ascii"),
)

DRIFTED = Layout(
    parent_value=2899,
    parent="SPWI899",
    selector="ELMCHO2",
    child_values=(2881, 2882, 2883, 2884),
    children=("SPWI881", "SPWI882", "SPWI883", "SPWI884"),
    hidden=(True, True, True, False),
    selector_text=(
        "2DA V1.0\n"
        "0\n"
        "Type Label ResRef\n"
        "Fire 3 fire SPWI881\n"
        "Cold 3 cold SPWI882\n"
        "Elec 3 elec SPWI883\n"
        "Acid 3 acid SPWI884\n"
        "Foreign 3 foreign ZZHIDDN\n"
        "Visible 3 visible ZZVISIB\n"
    ).encode("ascii"),
    hidespl_text=(
        "2DA V1.0\n"
        "0\n"
        "IS_FINAL IS_REMOVED IS_HIDDEN\n"
        "SPWI881 0 0 1\n"
        "SPWI882 0 0 1\n"
        "SPWI883 0 0 1\n"
        "SPWI884 0 0 0\n"
        "ZZHIDDN 0 0 1\n"
        "ZZVISIB 0 0 0\n"
        "ZZOTHER 0 0 1\n"
    ).encode("ascii"),
)


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<H", data, offset, value & 0xFFFF)


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value & 0xFFFFFFFF)


def _put_resref(data: bytearray, offset: int, value: str) -> None:
    encoded = value.encode("ascii")
    assert len(encoded) <= 8, value
    data[offset : offset + 8] = encoded.ljust(8, b"\0")


def _resref(data: bytes, offset: int) -> str:
    return data[offset : offset + 8].split(b"\0", 1)[0].decode("ascii").upper()


def _make_cre(
    death_variable: str,
    known: tuple[str, ...],
    memorized: tuple[str, ...],
    *,
    class_id: int = 1,
    override_script: str = "OVERRIDE",
    script_slots: tuple[str, str, str, str, str] | None = None,
) -> bytes:
    known_offset = 0x2D4
    info_offset = known_offset + len(known) * 0x0C
    memorized_offset = info_offset + 0x10
    slots_offset = memorized_offset + len(memorized) * 0x0C
    end_offset = slots_offset + 0x50
    data = bytearray(end_offset)
    data[:8] = b"CRE V1.0"
    data[0x273] = class_id
    scripts = script_slots or (override_script, "", "", "", "DEFAULT")
    for offset, script in zip(range(0x248, 0x270, 0x08), scripts):
        _put_resref(data, offset, script)
    encoded_dv = death_variable.encode("ascii")
    assert len(encoded_dv) <= 32
    data[0x280 : 0x2A0] = encoded_dv.ljust(32, b"\0")

    for field_offset, value in (
        (0x2A0, known_offset),
        (0x2A4, len(known)),
        (0x2A8, info_offset),
        (0x2AC, 1),
        (0x2B0, memorized_offset),
        (0x2B4, len(memorized)),
        (0x2B8, slots_offset),
        (0x2BC, end_offset),
        (0x2C0, 0),
        (0x2C4, end_offset),
        (0x2C8, 0),
    ):
        _put_u32(data, field_offset, value)

    for index, spell in enumerate(known):
        offset = known_offset + index * 0x0C
        _put_resref(data, offset, spell)
        _put_u16(data, offset + 0x08, 7)  # deliberately irrelevant to identity
        _put_u16(data, offset + 0x0A, 1)  # wizard

    _put_u16(data, info_offset + 0x00, 7)
    _put_u16(data, info_offset + 0x02, max(1, len(memorized)))
    _put_u16(data, info_offset + 0x06, 0)  # wizard memorization table
    _put_u32(data, info_offset + 0x08, 0)
    _put_u32(data, info_offset + 0x0C, len(memorized))
    for index, spell in enumerate(memorized):
        offset = memorized_offset + index * 0x0C
        _put_resref(data, offset, spell)
        _put_u32(data, offset + 0x08, 1)

    for offset in range(slots_offset, end_offset, 2):
        _put_u16(data, offset, 0xFFFF)
    return bytes(data)


def _spellbook(data: bytes) -> tuple[tuple[str, ...], tuple[str, ...]]:
    known_offset, known_count = struct.unpack_from("<II", data, 0x2A0)
    memorized_offset, memorized_count = struct.unpack_from("<II", data, 0x2B0)
    known = tuple(_resref(data, known_offset + index * 0x0C) for index in range(known_count))
    memorized = tuple(
        _resref(data, memorized_offset + index * 0x0C) for index in range(memorized_count)
    )
    return known, memorized


def _spell_ids(layout: Layout, omitted_child_symbol: str | None = None) -> bytes:
    lines = ["IDS V1.0", f"{layout.parent_value} {PARENT_SYMBOL}"]
    lines.extend(
        f"{value} {symbol}"
        for value, symbol in zip(layout.child_values, CHILD_SYMBOLS)
        if symbol != omitted_child_symbol
    )
    return ("\n".join(lines) + "\n").encode("ascii")


def _empty_spell() -> bytes:
    return ie_formats.make_spl(()).to_bytes()


def _container_spell(selector: str) -> bytes:
    data = bytearray(ie_formats.make_spl(
        (
            ie_formats.SplAbility(
                required_level=1,
                target=5,
                projectile=0,
                effects=(ie_formats.SplEffect(opcode=214, target=1, resource=selector),),
            ),
        )
    ).to_bytes())
    _put_u16(data, 0x1C, 1)
    _put_u16(data, 0x1E, 0x0040)
    _put_u32(data, 0x34, 4)
    return bytes(data)


def _casting_only_container(selector: str) -> bytes:
    """Build an invalid container whose selector appears outside any ability."""
    return replace(
        ie_formats.make_spl(()),
        casting_effects=(ie_formats.SplEffect(opcode=214, target=1, resource=selector),),
    ).to_bytes()


def _pdialog() -> bytes:
    return (
        "2DA V1.0\n"
        "0\n"
        "POST_DIALOG_FILE JOIN_DIALOG_FILE\n"
        # JOINABLE_NPC_ARRAYS intentionally starts at row 1.
        "DUMMY DUMMYP DUMMYJ\n"
        "NEERA NEERAP NEERAJ\n"
        "SAFEJOIN SAFEP SAFEJ\n"
        "FIGHTER FIGHTP FIGHTJ\n"
    ).encode("ascii")


def _copy_harness_sources(game: FakeGame) -> None:
    (game.root / "spell_rev" / "lib").mkdir(parents=True)
    (game.root / "spell_rev" / "components").mkdir(parents=True)
    shutil.copy2(JOINABLE_LIB, game.root / "spell_rev" / "lib" / JOINABLE_LIB.name)
    shutil.copy2(ARCANE_FIX, game.root / "spell_rev" / "components" / ARCANE_FIX.name)
    if CLEANUP_LIB.is_file():
        shutil.copy2(CLEANUP_LIB, game.root / "spell_rev" / "lib" / CLEANUP_LIB.name)
        shutil.copy2(CLEANUP_PATCH, game.root / "spell_rev" / "lib" / CLEANUP_PATCH.name)
    (game.root / "spell_rev" / "tests").mkdir(parents=True)
    shutil.copy2(NEERA_SCRIPT, game.root / "spell_rev" / "tests" / NEERA_SCRIPT.name)
    shutil.copy2(CONTROL_SCRIPT, game.root / "spell_rev" / "tests" / CONTROL_SCRIPT.name)
    shutil.copy2(HARNESS, game.root / "setup-srcb_test_npc_spellbooks.tp2")


def make_game(
    tmp_path: Path,
    layout: Layout,
    *,
    include_hidespl: bool = True,
    include_selector: bool = True,
    include_container: bool = True,
    container_data: bytes | None = None,
    omitted_child_symbol: str | None = None,
    neera_script_slot: int = 0,
) -> tuple[FakeGame, dict[str, bytes]]:
    target_known = (
        *layout.children,
        layout.parent,
        *LEGITIMATE,
        *(LEGACY_CHILDREN if layout is DRIFTED else ()),
    )
    target_memorized = (*layout.children, layout.children[0], layout.parent, "ZZLEGIT")
    neera_scripts = ["", "", "", "", ""]
    neera_scripts[neera_script_slot] = "NEERASCR"
    creatures = {
        "NEERA6": _make_cre(
            "NEERA", target_known, target_memorized, script_slots=tuple(neera_scripts)
        ),
        "NEERA7": _make_cre(
            "NEERA", target_known, target_memorized, script_slots=tuple(neera_scripts)
        ),
        "SAFEJOIN": _make_cre("SAFEJOIN", (layout.parent, "ZZLEGIT"), ("ZZLEGIT",)),
        "FIGHTER": _make_cre("FIGHTER", layout.children, layout.children, class_id=2),
        "STRANGER": _make_cre(
            "STRANGER", layout.children, layout.children, override_script="CTRLBCS"
        ),
    }
    resources: list[tuple[str, str, bytes]] = [
        ("OH6000", "ARE", b"synthetic BG2EE marker"),
        ("SPELL", "IDS", _spell_ids(layout, omitted_child_symbol)),
        (
            "ACTION",
            "IDS",
            b"IDS V1.0\n30 SetGlobal(S:Name*,S:Area*,I:Value*)\n279 AddSpecialAbility(S:ResRef*)\n",
        ),
        (
            "TRIGGER",
            "IDS",
            b"IDS V1.0\n0x400F Global(S:Name*,S:Area*,I:Value*)\n",
        ),
        ("PDIALOG", "2DA", _pdialog()),
    ]
    if include_container:
        resources.append(
            (layout.parent, "SPL", container_data or _container_spell(layout.selector))
        )
    if include_selector:
        resources.append((layout.selector, "2DA", layout.selector_text))
    if include_hidespl:
        resources.append(("HIDESPL", "2DA", layout.hidespl_text))
    for resref in {*layout.children, *LEGACY_CHILDREN, *LEGITIMATE, "ZZOTHER"}:
        resources.append((resref, "SPL", _empty_spell()))
    resources.extend((resref, "CRE", data) for resref, data in creatures.items())

    game = FakeGame(tmp_path / "game", tuple(resources))
    # Exercise uninstall restoration of a pre-existing override as well as removal of
    # a BIFF-only publication (NEERA6).
    (game.override / "NEERA7.CRE").write_bytes(creatures["NEERA7"])
    _copy_harness_sources(game)
    return game, creatures


def _install(game: FakeGame, component: int = 0):
    process = game.install("setup-srcb_test_npc_spellbooks.tp2", component)
    assert_installed(process)
    return process


def _override_cre(game: FakeGame, name: str) -> bytes:
    path = game.override_file(f"{name}.CRE")
    assert path is not None, (name, sorted(game.override_tree()))
    return path.read_bytes()


def _override_bcs(game: FakeGame, name: str) -> bytes:
    path = game.override_file(f"{name}.BCS")
    assert path is not None, (name, sorted(game.override_tree()))
    return path.read_bytes().upper()


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("TP2", HARNESS),
        ("TP2", CRE_HARNESS),
        ("TP2", SETUP_TP2),
        ("TPA", JOINABLE_LIB),
        ("TPA", ARCANE_FIX),
        ("TPA", CLEANUP_LIB),
        ("TPA", CLEANUP_PATCH),
    ],
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_parse_check(kind: str, path: Path) -> None:
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


def test_component_60_runs_migration_after_spellbook_assignments() -> None:
    source = SETUP_TP2.read_text(encoding="utf-8")
    divine = source.index("fix_divine_spellbooks.tpa")
    arcane = source.index("fix_arcane_spellbooks.tpa")
    migration = source.index("hidden_elemental_subspells.tpa")
    assert divine < arcane < migration


def _run_cre_harness(tmp_path: Path, component: int, source: bytes) -> bytes:
    run_dir = tmp_path / f"cre-pass-{component}-{len(list(tmp_path.iterdir()))}"
    run_dir.mkdir()
    source_path = run_dir / "input.cre"
    output_path = run_dir / "output.cre"
    source_path.write_bytes(source)
    process = nogame_harness(
        CRE_HARNESS,
        component,
        run_dir,
        [
            source_path.as_posix(),
            output_path.as_posix(),
            CLEANUP_PATCH.as_posix(),
            *CURRENT.children,
            CURRENT.parent,
            "4",
        ],
    )
    assert_installed(process)
    return output_path.read_bytes()


def test_nogame_cre_transform_is_surgical_and_idempotent(tmp_path: Path) -> None:
    source = _make_cre(
        "NEERA",
        (*CURRENT.children, "ZZLEGIT"),
        (*CURRENT.children, CURRENT.children[0], "ZZLEGIT"),
    )
    once = _run_cre_harness(tmp_path, 0, source)
    twice = _run_cre_harness(tmp_path, 1, source)
    known, memorized = _spellbook(once)
    assert all(child not in known for child in CURRENT.children)
    assert all(child not in memorized for child in CURRENT.children)
    assert known.count(CURRENT.parent) == 1
    assert memorized.count(CURRENT.parent) == 5
    assert known.count("ZZLEGIT") == 1
    assert memorized.count("ZZLEGIT") == 1
    assert twice == once
    assert _resref(once, 0x248) == "OVERRIDE"
    assert _resref(once, 0x268) == "DEFAULT"

    already_clean = _make_cre("SAFEJOIN", (CURRENT.parent, "ZZLEGIT"), ("ZZLEGIT",))
    assert _run_cre_harness(tmp_path, 0, already_clean) == already_clean


def test_nogame_malformed_non_cre_fails_closed(tmp_path: Path) -> None:
    malformed = bytearray(
        _make_cre("NEERA", (*CURRENT.children, "ZZLEGIT"), (*CURRENT.children,))
    )
    malformed[:8] = b"NOTCRE!!"
    assert _run_cre_harness(tmp_path, 0, bytes(malformed)) == bytes(malformed)


def test_current_layout_migration_and_public_uninstall_round_trip(tmp_path: Path) -> None:
    game, originals = make_game(tmp_path, CURRENT)
    process = _install(game)
    assert "hidden elemental-protection subspell" in transcript(process).lower()
    game.assert_inputs_unchanged()

    expected_known = (CURRENT.parent, *LEGITIMATE)
    for name in ("NEERA6", "NEERA7"):
        known, memorized = _spellbook(_override_cre(game, name))
        assert known == expected_known
        assert all(child not in memorized for child in CURRENT.children)
        assert memorized.count(CURRENT.parent) == 6
        assert memorized.count("ZZLEGIT") == 1

    fighter_known, fighter_memorized = _spellbook(_override_cre(game, "FIGHTER"))
    assert fighter_known == (CURRENT.parent,)
    assert fighter_memorized == (CURRENT.parent,) * 4
    assert set(game.override_tree()) == {
        "CTRLBCS.BCS",
        "FIGHTER.CRE",
        "NEERA6.CRE",
        "NEERA7.CRE",
        "NEERASCR.BCS",
    }
    for untouched in ("SAFEJOIN.CRE", "STRANGER.CRE"):
        assert game.override_file(untouched) is None
    assert "#0 #0" in game.active_weidu_log()

    process = game.uninstall("setup-srcb_test_npc_spellbooks.tp2", 0)
    text = transcript(process)
    assert "SUCCESSFULLY REMOVED" in text or "Uninstalled" in text, text
    assert game.override_file("NEERA6.CRE") is None
    assert _override_cre(game, "NEERA7") == originals["NEERA7"]
    assert set(game.override_tree()) == {"NEERA7.CRE"}
    assert "SRCB_TEST_NPC_SPELLBOOKS" not in game.active_weidu_log().upper()
    game.assert_inputs_unchanged()


@pytest.mark.parametrize("script_slot", range(5), ids=("override", "class", "race", "general", "default"))
def test_only_joinable_npc_script_grants_migrate_to_parent(
    tmp_path: Path, script_slot: int
) -> None:
    game, _ = make_game(tmp_path, CURRENT, neera_script_slot=script_slot)
    _install(game)

    joinable_script = _override_bcs(game, "NEERASCR")
    control_script = _override_bcs(game, "CTRLBCS")
    for child in CURRENT.children:
        assert child.encode("ascii") not in joinable_script
        assert child.encode("ascii") in control_script
    assert joinable_script.count(CURRENT.parent.encode("ascii")) == 4
    assert CURRENT.parent.encode("ascii") not in control_script
    assert b"ZZLEGIT" in joinable_script
    assert b"ZZHIDDN" in joinable_script
    assert b"SRCB_NEERA_GRANT" in joinable_script
    assert b"SRCB_CONTROL_GRANT" in control_script


def test_effective_container_hidespl_and_semantic_drift(tmp_path: Path) -> None:
    game, _ = make_game(tmp_path, DRIFTED)
    _install(game)
    known, memorized = _spellbook(_override_cre(game, "NEERA6"))

    for removed in DRIFTED.children[:3]:
        assert removed not in known
        assert removed not in memorized
    # Each guard is independently meaningful: semantic but visible, selector+hidden
    # but foreign, hidden but not selected, and the old hard-coded slots all survive.
    for preserved in (
        DRIFTED.children[3],
        "ZZHIDDN",
        "ZZVISIB",
        "ZZLEGIT",
        DRIFTED.parent,
        *LEGACY_CHILDREN,
    ):
        assert preserved in known
    assert DRIFTED.children[3] in memorized
    assert memorized.count(DRIFTED.parent) == 5


def test_repeated_component_pass_is_byte_exact(tmp_path: Path) -> None:
    game, _ = make_game(tmp_path, CURRENT)
    _install(game, 0)
    once = game.override_tree()
    _install(game, 1)
    assert game.override_tree() == once
    game.assert_inputs_unchanged()


def test_production_discovery_is_same_process_idempotent(tmp_path: Path) -> None:
    once_game, _ = make_game(tmp_path / "once", CURRENT)
    _install(once_game, 0)
    once = once_game.override_tree()

    twice_game, _ = make_game(tmp_path / "twice", CURRENT)
    _install(twice_game, 2)
    assert twice_game.override_tree() == once
    twice_game.assert_inputs_unchanged()


@pytest.mark.parametrize("missing", ("hidespl", "selector"))
def test_missing_semantic_layer_fails_closed(tmp_path: Path, missing: str) -> None:
    game, originals = make_game(
        tmp_path,
        CURRENT,
        include_hidespl=missing != "hidespl",
        include_selector=missing != "selector",
    )
    _install(game)
    assert _override_cre(game, "NEERA7") == originals["NEERA7"]
    assert game.override_file("NEERA6.CRE") is None
    assert set(game.override_tree()) == {"CTRLBCS.BCS", "NEERA7.CRE", "NEERASCR.BCS"}
    for child in CURRENT.children:
        assert child.encode("ascii") in _override_bcs(game, "NEERASCR")
    game.assert_inputs_unchanged()


@pytest.mark.parametrize(
    "container",
    (None, _casting_only_container(CURRENT.selector)),
    ids=("missing", "selector-in-casting-feature-only"),
)
def test_missing_or_malformed_parent_container_fails_closed(
    tmp_path: Path, container: bytes | None
) -> None:
    game, originals = make_game(
        tmp_path,
        CURRENT,
        include_container=container is not None,
        container_data=container,
    )
    process = _install(game)
    assert "skipped" in transcript(process).lower()
    assert _override_cre(game, "NEERA7") == originals["NEERA7"]
    assert game.override_file("NEERA6.CRE") is None
    assert set(game.override_tree()) == {"CTRLBCS.BCS", "NEERA7.CRE", "NEERASCR.BCS"}
    for child in CURRENT.children:
        assert child.encode("ascii") in _override_bcs(game, "NEERASCR")
    game.assert_inputs_unchanged()


@pytest.mark.parametrize(
    "layout",
    (
        replace(
            CURRENT,
            selector_text=CURRENT.selector_text.replace(b"SPWI319 3", b"SPWI319 nope"),
        ),
        replace(
            CURRENT,
            hidespl_text=CURRENT.hidespl_text.replace(b"SPWI319 1 0 0", b"SPWI319 nope 0 0"),
        ),
        replace(
            CURRENT,
            hidespl_text=(
                b"2DA V1.0\n0\nUNUSED\nSPWI319 1\nSPWI320 1\n"
                b"SPWI512 1\nSPWI517 1\n"
            ),
        ),
    ),
    ids=("nonnumeric-selector-type", "nonnumeric-hidden-flag", "ee-two-column-hidespl"),
)
def test_malformed_semantic_table_fails_closed(tmp_path: Path, layout: Layout) -> None:
    game, originals = make_game(tmp_path, layout)
    process = _install(game)
    assert "skipped" in transcript(process).lower()
    assert _override_cre(game, "NEERA7") == originals["NEERA7"]
    assert game.override_file("NEERA6.CRE") is None
    assert set(game.override_tree()) == {"CTRLBCS.BCS", "NEERA7.CRE", "NEERASCR.BCS"}
    for child in layout.children:
        assert child.encode("ascii") in _override_bcs(game, "NEERASCR")
    game.assert_inputs_unchanged()


def test_partial_semantic_resolution_warns_and_excludes_only_missing_child(tmp_path: Path) -> None:
    game, _ = make_game(
        tmp_path,
        CURRENT,
        omitted_child_symbol="WIZARD_PROTECTION_FROM_ACID",
    )
    process = _install(game)
    assert "resolved only 3 of 4" in transcript(process).lower()
    known, memorized = _spellbook(_override_cre(game, "NEERA6"))
    for removed in CURRENT.children[:3]:
        assert removed not in known
        assert removed not in memorized
    assert CURRENT.children[3] in known
    assert CURRENT.children[3] in memorized
    assert memorized.count(CURRENT.parent) == 5
