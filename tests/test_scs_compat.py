"""Hermetic real-WeiDU tests for the SCS / SR compatibility component.

Christopher's decisions: Chaos is a level-5 wizard spell again from v4.21-chriz.8
(2026-10-27), and SCS's own Chaos tactic should run with it (2026-10-28). SCS leaves that
tactic out whenever Spell Revisions is installed: its block in
``mage/ssl/combatblocks/l5_enchantment.ssl`` carries ``IgnoreBlock(Demivrgvs)``. The
component removes that gate from SCS's source before SCS compiles its mage scripts.

Coverage: a synthetic fake game with a synthetic SCS-shaped source file (not SCS's own
text): which gates go and which stay, line endings and spacing, gate lists with other
entries, a second pass, uninstall, and every refusal. The real SCS file is checked in a
disposable lab, recorded in ``docs/plans/2026-10-28-chaos-level-5-design.md``.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

import pytest

from tests import ie_formats
from tests.weidu_env import ROOT, FakeGame, assert_installed, parse_check, transcript

LIVE_ROOT = ROOT / "live-patch" / "SRCB_SCS_COMPAT"
SETUP_TP2 = LIVE_ROOT / "setup-SRCB_SCS_COMPAT.tp2"
LIBRARY = LIVE_ROOT / "lib" / "scs_chaos_tactic.tpa"
TP2 = "SRCB_SCS_COMPAT/setup-SRCB_SCS_COMPAT.tp2"
SSL_PATH = Path("stratagems/mage/ssl/combatblocks/l5_enchantment.ssl")
ALWAYS_PATH = Path("stratagems/lib/always.tph")

LEVEL5_SPELL_IDS = """IDS V1.0
2401 WIZARD_CONFUSION
2506 WIZARD_DOMINATION
2508 WIZARD_CHAOS
2525 WIZARD_WAVES_OF_FATIGUE
2711 WIZARD_SPHERE_OF_CHAOS
"""
# SR up to v4.21-chriz.7: Waves of Fatigue holds the level-5 slot, Chaos is the sphere.
LEVEL7_SPELL_IDS = """IDS V1.0
2401 WIZARD_CONFUSION
2506 WIZARD_DOMINATION
2508 WIZARD_WAVES_OF_FATIGUE
2711 WIZARD_CHAOS
2711 WIZARD_SPHERE_OF_CHAOS
"""
ALWAYS_TPH = (
    "   ACTION_IF demivrgvs BEGIN\n"
    "           OUTER_SPRINT ~sslvariables~ ~%sslvariables%~^~&~^~Demivrgvs=True~\n"
    "   END\n"
)
SR_LOG = "~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #0 // Spell Revisions"

GATE = "\tIgnoreBlock(Demivrgvs)\n"


def block(*lines: str, actions: tuple[str, ...] = (), opener: str = "IF TRIGGER", then: str = "THEN DO",
          end: str = "END") -> str:
    """One SSL block; trigger and action lines come with their own indentation."""
    return f"{opener}\n" + "".join(lines) + f"{then}\n" + "".join(actions) + f"{end}\n\n"


CONTROL_UNDEAD = block(
    "\tTargetBlock(EnemiesInOrder)\n",
    "\tGeneral(scstarget,UNDEAD)\n",
    actions=("\tAction(Spell,WIZARD_CONTROL_UNDEAD|100|100)\n",),
)
CHAOS_TRIGGERS = (
    "\tTargetBlock(PCsInReverseOrder)\n",
    "\tTargetBlock(EnemiesInOrderShort)\n",
    "\tTriggerBlock(AoEDisabled|Confused|ConfuseProof|MR|Enemy)\n",
    "\tCheckStatGT(scstarget,0,SAVEVSSPELL)\n",
)
CHAOS_ACTION = ("\tAction(SpellArea,WIZARD_CHAOS|200|100)\n",)
WAVES = block(
    "\tRequireBlock(Demivrgvs)\n",
    "\tTargetBlock(PCsInReverseOrder)\n",
    "\tTriggerBlock(AoEDisabled|MR|Enemy)\n",
    actions=("\tAction(SpellArea,WIZARD_WAVES_OF_FATIGUE|100|100)\n",),
)
DOMINATION = block(
    "\tIgnoreBlock(Demivrgvs)\n",
    "\tTargetBlock(PCsPreferringStrong)\n",
    actions=("\tAction(Spell,WIZARD_DOMINATION|200|100)\n",),
)


def scs_source(chaos_gate: str = GATE, *, chaos_block: str | None = None, extra: str = "") -> str:
    """SCS-shaped source: the Chaos tactic between blocks that must stay as they are."""
    if chaos_block is None:
        chaos_block = block(chaos_gate, *CHAOS_TRIGGERS, actions=CHAOS_ACTION)
    return (
        "// Synthetic SCS-shaped combat blocks for SRCB_SCS_COMPAT tests.\n\n"
        + CONTROL_UNDEAD + chaos_block + WAVES + DOMINATION + extra
    )


EXPECTED = scs_source(chaos_gate="")


def _wizard_spell(level: int) -> bytes:
    data = bytearray(ie_formats.make_spl(()).to_bytes())
    struct.pack_into("<H", data, 0x1C, 1)
    struct.pack_into("<I", data, 0x34, level)
    return bytes(data)


def _make_game(
    tmp_path: Path,
    source: str | bytes | None = None,
    *,
    spell_ids: str = LEVEL5_SPELL_IDS,
    chaos_level: int = 5,
    always: str | None = ALWAYS_TPH,
    log_lines: tuple[str, ...] = (SR_LOG,),
) -> FakeGame:
    """``source`` None is the default SCS-shaped file; ``always`` None leaves SCS's library out."""
    resources = (
        ("SPELL", "IDS", spell_ids.encode("ascii")),
        ("SPWI508", "SPL", _wizard_spell(chaos_level)),
        ("SPWI711", "SPL", _wizard_spell(7)),
    )
    game = FakeGame(tmp_path / "game", resources)
    if source is None:
        source = scs_source()
    path = game.root / SSL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.encode("ascii") if isinstance(source, str) else source)
    if always is not None:
        path = game.root / ALWAYS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(always, encoding="ascii", newline="\n")
    shutil.copytree(LIVE_ROOT, game.root / "SRCB_SCS_COMPAT")
    for line in log_lines:
        game.append_weidu_log(line)
    return game


def _without_scs_source(tmp_path: Path) -> FakeGame:
    game = _make_game(tmp_path)
    (game.root / SSL_PATH).unlink()
    return game


def _ssl(game: FakeGame) -> bytes:
    return (game.root / SSL_PATH).read_bytes()


def _assert_refused(game: FakeGame, message: str) -> None:
    before = _ssl(game) if (game.root / SSL_PATH).exists() else None
    overrides = game.override_tree()
    text = transcript(game.install(TP2, 0))
    assert "SUCCESSFULLY INSTALLED" not in text, text
    assert "INSTALLED WITH WARNINGS" not in text, text
    assert message in text, text
    assert "SRCB_SCS_COMPAT" not in game.active_weidu_log()
    if before is not None:
        assert _ssl(game) == before
    assert game.override_tree() == overrides
    game.assert_inputs_unchanged()


# --------------------------------------------------------------------------- environment


@pytest.mark.parametrize(
    ("kind", "path"),
    [("TP2", SETUP_TP2), ("TPA", LIBRARY)],
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_parse_check(kind: str, path: Path) -> None:
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


# --------------------------------------------------------------------------- the gate goes


def test_only_the_chaos_tactic_loses_its_gate(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    original = _ssl(game)
    overrides = game.override_tree()
    process = game.install(TP2, 0)
    assert_installed(process)
    text = transcript(process)
    assert "INSTALLED WITH WARNINGS" not in text, text
    assert "Chaos is the level-5 spell SPWI508" in text, text
    assert "(1 of 1 Chaos blocks were gated)" in text, text
    # Control Undead, Waves of Fatigue (RequireBlock) and Domination keep their lines.
    assert _ssl(game) == EXPECTED.encode("ascii")
    assert game.override_tree() == overrides

    process = game.uninstall(TP2, 0)
    assert "SRCB_SCS_COMPAT" not in game.active_weidu_log(), transcript(process)
    assert _ssl(game) == original
    game.assert_inputs_unchanged()


def test_windows_line_endings_stay(tmp_path: Path) -> None:
    game = _make_game(tmp_path, scs_source().replace("\n", "\r\n").encode("ascii"))
    assert_installed(game.install(TP2, 0))
    assert _ssl(game) == EXPECTED.replace("\n", "\r\n").encode("ascii")


@pytest.mark.parametrize(
    ("gate", "kept"),
    [
        ("\tIgnoreBlock(Demivrgvs) // SR has no level-5 Chaos\n", ""),
        ("  IgnoreBlock(Demivrgvs)  \n", ""),
        ("\tIgnoreBlock(Demivrgvs|Demivrgvs)\n", ""),
        ("\tIgnoreBlock(IsIWDArcane|Demivrgvs)\n", "\tIgnoreBlock(IsIWDArcane)\n"),
        ("\tIgnoreBlock(Demivrgvs|IsIWDArcane)\n", "\tIgnoreBlock(IsIWDArcane)\n"),
        ("\tIgnoreBlock(IsLich|Demivrgvs|IsIWDArcane)\n", "\tIgnoreBlock(IsLich|IsIWDArcane)\n"),
        ("\tIgnoreBlock(Demivrgvs|Demivrgvs|IsLich)\n", "\tIgnoreBlock(IsLich)\n"),
        ("\tIgnoreBlock(IsLich|Demivrgvs|Demivrgvs)\n", "\tIgnoreBlock(IsLich)\n"),
        ("\tIgnoreBlock(IsLich|Demivrgvs) // note\n", "\tIgnoreBlock(IsLich) // note\n"),
    ],
    ids=["comment", "spaces", "twice", "last", "first", "middle", "leading-run", "trailing-run", "kept-comment"],
)
def test_gate_lists(tmp_path: Path, gate: str, kept: str) -> None:
    game = _make_game(tmp_path, scs_source(gate))
    assert_installed(game.install(TP2, 0))
    assert _ssl(game) == scs_source(kept).encode("ascii")


def test_block_spelling_follows_scs(tmp_path: Path) -> None:
    # SCS collapses blank runs and strips // comments; a blank around an action argument
    # still names the same spell in the compiled script.
    chaos = block(
        GATE, *CHAOS_TRIGGERS,
        actions=("\tAction(SpellArea, WIZARD_CHAOS |200|100) // the tactic\n",),
        opener="IF \t TRIGGER // Chaos", then="THEN\t DO", end="  END // Chaos",
    )
    game = _make_game(tmp_path, scs_source(chaos_block=chaos))
    assert_installed(game.install(TP2, 0))
    assert _ssl(game) == scs_source(chaos_block=chaos.replace(GATE, "")).encode("ascii")


def test_every_chaos_tactic_loses_its_gate(tmp_path: Path) -> None:
    second = block(
        "\tIgnoreBlock(Demivrgvs)\n", "\tTargetBlock(EnemiesInOrder)\n",
        actions=("\tAction(SpellReplace,WIZARD_CONFUSION,WIZARD_CHAOS|150|50)\n",),
    )
    game = _make_game(tmp_path, scs_source(extra=second))
    process = game.install(TP2, 0)
    assert_installed(process)
    assert "(2 of 2 Chaos blocks were gated)" in transcript(process)
    assert _ssl(game) == scs_source("", extra=second.replace(GATE, "")).encode("ascii")


def test_other_gates_stay(tmp_path: Path) -> None:
    lookalikes = (
        # Chaos Shield is another spell.
        block(GATE, actions=("\tAction(Spell,WIZARD_CHAOS_SHIELD|100|100)\n",))
        # SCS compares entries exactly, so a padded entry or another name is no SR gate.
        + block("\tIgnoreBlock( Demivrgvs)\n", actions=CHAOS_ACTION)
        + block("\tIgnoreBlock(NotDemivrgvs)\n", actions=CHAOS_ACTION)
        # Comments are not code.
        + block("\t// IgnoreBlock(Demivrgvs)\n", actions=CHAOS_ACTION)
        # A plain BAF block is not an SSL tactic.
        + "IF\n\tIgnoreBlock(Demivrgvs)\n\tHaveSpell(WIZARD_CHAOS)\nTHEN\n\tRESPONSE #100\n"
          "\t\tSpell(NearestEnemyOf(Myself),WIZARD_CHAOS)\nEND\n\n"
        # A gate belongs before THEN DO; after it, the line is no gate of the block.
        + block(actions=("\tIgnoreBlock(Demivrgvs)\n", *CHAOS_ACTION))
    )
    game = _make_game(tmp_path, scs_source(extra=lookalikes))
    process = game.install(TP2, 0)
    assert_installed(process)
    assert "(1 of 5 Chaos blocks were gated)" in transcript(process)
    assert _ssl(game) == scs_source("", extra=lookalikes).encode("ascii")


def test_a_second_pass_changes_nothing(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    original = _ssl(game)
    assert_installed(game.install(TP2, 0))
    # A reinstall restores the file first and patches it again.
    process = game.install(TP2, 0)
    assert_installed(process)
    assert _ssl(game) == EXPECTED.encode("ascii")
    assert game.active_weidu_log().count("SETUP-SRCB_SCS_COMPAT.TP2") == 1, game.weidu_log()
    game.uninstall(TP2, 0)
    assert _ssl(game) == original


def test_an_open_tactic_is_left_alone(tmp_path: Path) -> None:
    game = _make_game(tmp_path, EXPECTED)
    process = game.install(TP2, 0)
    assert_installed(process)
    assert "already runs with Spell Revisions; nothing to change" in transcript(process)
    assert _ssl(game) == EXPECTED.encode("ascii")
    game.uninstall(TP2, 0)
    assert _ssl(game) == EXPECTED.encode("ascii")


# --------------------------------------------------------------------------- SCS installed first


def test_scs_ai_installed_first_is_warned(tmp_path: Path) -> None:
    game = _make_game(
        tmp_path, log_lines=(SR_LOG, "~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #6030 // Smarter Mages: 35.21"))
    process = game.install(TP2, 0)
    text = transcript(process)
    assert "INSTALLED WITH WARNINGS" in text, text
    assert "SCS component 6030 is already installed" in text, text
    assert _ssl(game) == EXPECTED.encode("ascii")


def test_scs_components_below_6000_compile_no_mage_scripts(tmp_path: Path) -> None:
    game = _make_game(
        tmp_path,
        log_lines=(
            SR_LOG,
            "~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #2000 // Install all spell tweaks: 35.21",
            "~STRATAGEMS/SETUP-STRATAGEMS.TP2~ #0 #5900 // Initialise AI components: 35.21",
        ),
    )
    process = game.install(TP2, 0)
    assert_installed(process)
    assert "INSTALLED WITH WARNINGS" not in transcript(process)
    assert _ssl(game) == EXPECTED.encode("ascii")


# --------------------------------------------------------------------------- refusals


def test_chaos_at_level_seven_is_refused(tmp_path: Path) -> None:
    game = _make_game(tmp_path, spell_ids=LEVEL7_SPELL_IDS)
    _assert_refused(game, "does not map WIZARD_CHAOS to a level-5 wizard spell")


def test_chaos_spell_must_be_a_level_five_wizard_spell(tmp_path: Path) -> None:
    game = _make_game(tmp_path, chaos_level=7)
    _assert_refused(game, "SPWI508.SPL is not the expected level-5 wizard spell")


def test_spell_revisions_is_required(tmp_path: Path) -> None:
    game = _make_game(tmp_path, log_lines=())
    _assert_refused(game, "requires Spell Revisions (main component)")


def test_scs_files_are_required(tmp_path: Path) -> None:
    _assert_refused(_without_scs_source(tmp_path), "requires Sword Coast Stratagems' files")


def test_a_source_without_chaos_tactic_is_refused(tmp_path: Path) -> None:
    game = _make_game(tmp_path, CONTROL_UNDEAD + WAVES + DOMINATION)
    _assert_refused(game, "has no block that casts WIZARD_CHAOS")


@pytest.mark.parametrize("always", [None, "OUTER_SPRINT ~sslvariables~ ~%sslvariables%&SpellRevisions=True~\n"])
def test_scs_must_call_spell_revisions_demivrgvs(tmp_path: Path, always: str | None) -> None:
    game = _make_game(tmp_path, always=always)
    _assert_refused(game, "always.tph is missing or does not set Demivrgvs")
