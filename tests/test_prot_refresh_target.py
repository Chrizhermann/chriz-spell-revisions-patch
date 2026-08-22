"""Protection from Magic Energy / the Elements / Energy: refresh must target the recipient.

Upstream Spell Revisions (EE games) inserts `opcode 321: remove effects by resource = itself`
as the first effect of these spells so a new cast replaces the old one.  It inserts it with
effect target 1 ("Self" = the CASTER); for creature-targeted spells that strips the caster's
own buff whenever the spell is cast on an ally and never refreshes the recipient's.  Correct
is target 2 ("Projectile target" = the recipient); caster-only spells (ability target 5/7)
keep target 1.

Coverage:
* `--nogame` harness against the live-patch library (byte-exact vs an expected build,
  idempotency, caster-only and foreign-321 guards).
* synthetic fake game running the REAL fork `refresh_non_stacking.tpa`, plus the upstream
  v4.21 copy as a control that must still show the bug (proves the assertions detect it).
* public install / uninstall of the live-patch tp2 in the fake game (byte-exact restore,
  untouched KEY/BIF/TLK, REQUIRE_PREDICATE gate).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests import ie_formats
from tests.weidu_env import (
    MIN_WEIDU_VERSION,
    ROOT,
    FakeGame,
    assert_installed,
    nogame_harness,
    parse_check,
    transcript,
    weidu_version,
)

HARNESS = ROOT / "tests" / "weidu" / "prot_refresh_harness.tp2"
FAKE_GAME_TP2 = ROOT / "tests" / "weidu" / "fake_game_refresh.tp2"
LIVE_PATCH_DIR = ROOT / "live-patch" / "SRCB_PROT_REFRESH"
LIVE_PATCH_TP2 = LIVE_PATCH_DIR / "setup-SRCB_PROT_REFRESH.tp2"
LIVE_PATCH_LIB = LIVE_PATCH_DIR / "lib" / "prot_refresh_target.tpa"
FORK_REFRESH = ROOT / "spell_rev" / "lib" / "refresh_non_stacking.tpa"
UPSTREAM_REFRESH = ROOT / "tests" / "fixtures" / "upstream_v4.21_refresh_non_stacking.tpa"

# Spell Revisions source SPLs (the mod's own shipped files, pre-install).
SOURCE_SPELLS: dict[str, Path] = {
    # creature-targeted (ability target 1) — the affected spells
    "SPWI606": ROOT / "spell_rev" / "spwi6##" / "spwi606.spl",  # Protection from Magic Energy
    "SPWI702": ROOT / "spell_rev" / "spwi7##" / "spwi702.spl",  # Protection from the Elements
    "SPWI803": ROOT / "spell_rev" / "spwi8##" / "spwi803.spl",  # Protection from Energy
    # caster-only (ability target 5) — same upstream code path, must stay on target 1
    "SPWI212": ROOT / "spell_rev" / "spwi2##" / "spwi212.spl",  # Mirror Image
    # (Wraith Form spwi315 is a vanilla file SR patches in place — not shipped in spell_rev/,
    #  so it is not a fixture here; it takes the same caster-only path as the three above.)
    "SPWI406": ROOT / "spell_rev" / "spwi4##" / "spwi406.spl",  # Minor Globe of Invulnerability
    "SPWI602": ROOT / "spell_rev" / "spwi6##" / "spwi602.spl",  # Globe of Invulnerability
}
TARGETED = ("SPWI606", "SPWI702", "SPWI803")
CASTER_ONLY = ("SPWI212", "SPWI406", "SPWI602")

# spell.ids symbols the refresh code resolves (values = vanilla BG2:EE slots, which SR keeps
# for these spells; the fixture SPELL.IDS below is the only place they matter).
SPELL_IDS = {
    "CLERIC_ANIMAL_GROWTH": 1525,
    "WIZARD_MIRROR_IMAGE": 2212,
    "WIZARD_MINOR_GLOBE_OF_INVULNERABILITY": 2406,
    "WIZARD_GLOBE_OF_INVULNERABILITY": 2602,
    "WIZARD_PROTECTION_FROM_MAGIC_ENERGY": 2606,
    "WIZARD_PROTECTION_FROM_THE_ELEMENTS": 2702,
    "WIZARD_PROTECTION_FROM_ENERGY": 2803,
}
SR_WEIDU_LOG_LINE = "~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #0 // Spell Revisions: v4.19"

EFFECT_TARGET_SELF = 1
EFFECT_TARGET_PROJECTILE = 2
ABILITY_TARGET_CASTER = (5, 7)


# --------------------------------------------------------------------------- helpers


def _first_effects(data: bytes) -> list[ie_formats.SplEffect]:
    spell = ie_formats.SplFile.from_bytes(data)
    assert spell.abilities, "fixture has no abilities"
    return [ability.effects[0] for ability in spell.abilities]


def _assert_refresh_first(data: bytes, resref: str, expected_target: int) -> None:
    spell = ie_formats.SplFile.from_bytes(data)
    for ability in spell.abilities:
        first = ability.effects[0]
        assert first.opcode == 321, first
        assert first.resource.upper() == resref, first
        assert first.timing == 1, first
        assert first.target == expected_target, (resref, first)
        # exactly one self-referencing 321 per ability
        selfrefs = [e for e in ability.effects if e.opcode == 321 and e.resource.upper() == resref]
        assert len(selfrefs) == 1, selfrefs


def _harness(tmp_path: Path, component: int, source: bytes, resource: str, extra: str | None = None) -> bytes:
    run_dir = tmp_path / f"run-{component}-{resource}-{len(list(tmp_path.iterdir()))}"
    run_dir.mkdir()
    src = run_dir / "in.spl"
    out = run_dir / "out.spl"
    src.write_bytes(source)
    args = [src.as_posix(), out.as_posix(), resource]
    if extra is not None:
        args.append(extra)
    process = nogame_harness(HARNESS, component, run_dir, args)
    assert_installed(process)
    assert out.is_file(), transcript(process)
    return out.read_bytes()


def build_upstream(tmp_path: Path, resref: str, resource: str | None = None) -> bytes:
    return _harness(tmp_path, 1, SOURCE_SPELLS[resref].read_bytes(), resource or resref)


def build_expected(tmp_path: Path, resref: str) -> bytes:
    return _harness(tmp_path, 2, SOURCE_SPELLS[resref].read_bytes(), resref)


def apply_live_fix(tmp_path: Path, data: bytes, resref: str) -> bytes:
    return _harness(tmp_path, 3, data, resref, LIVE_PATCH_LIB.as_posix())


def _spell_ids_text() -> bytes:
    lines = ["IDS V1.0"] + [f"{value} {symbol}" for symbol, value in SPELL_IDS.items()]
    return ("\n".join(lines) + "\n").encode("ascii")


def make_fake_game(tmp_path: Path, refresh_tpa: Path) -> FakeGame:
    resources: list[tuple[str, str, bytes]] = [
        ("OH6000", "ARE", b"synthetic BG2EE marker"),
        ("SPELL", "IDS", _spell_ids_text()),
    ]
    for resref, path in SOURCE_SPELLS.items():
        resources.append((resref, "SPL", path.read_bytes()))
    # Sub-spells the loop patches unconditionally at the end of refresh_non_stacking.tpa.
    resources.append(("SPPR203D", "SPL", (ROOT / "spell_rev" / "sppr2##" / "sppr203d.spl").read_bytes()))
    resources.append(("DVPR525D", "SPL", (ROOT / "spell_rev" / "sppr5##" / "dvpr525d.spl").read_bytes()))
    game = FakeGame(tmp_path / "game", tuple(resources))
    lib_dir = game.root / "spell_rev" / "lib"
    lib_dir.mkdir(parents=True)
    shutil.copy2(refresh_tpa, lib_dir / "refresh_non_stacking.tpa")
    shutil.copy2(FAKE_GAME_TP2, game.root / "setup-srcb_test_refresh.tp2")
    return game


def install_live_patch_into(game: FakeGame) -> None:
    shutil.copytree(LIVE_PATCH_DIR, game.root / LIVE_PATCH_DIR.name)


def _override_spl(game: FakeGame, resref: str) -> bytes:
    path = game.override_file(f"{resref}.SPL")
    assert path is not None, f"{resref}.SPL missing from override: {sorted(game.override_tree())}"
    return path.read_bytes()


# --------------------------------------------------------------------------- environment


def test_weidu_is_recent_enough() -> None:
    assert weidu_version() >= MIN_WEIDU_VERSION


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("TP2", LIVE_PATCH_TP2),
        ("TPA", LIVE_PATCH_LIB),
        ("TPA", FORK_REFRESH),
        ("TP2", HARNESS),
        ("TP2", FAKE_GAME_TP2),
    ],
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_parse_check(kind: str, path: Path) -> None:
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


# --------------------------------------------------------------------------- fixtures sanity


@pytest.mark.parametrize("resref", TARGETED)
def test_affected_spells_are_creature_targeted(resref: str) -> None:
    spell = ie_formats.read_spl(SOURCE_SPELLS[resref])
    assert all(ability.target == 1 for ability in spell.abilities)
    assert not any(e.opcode == 321 for a in spell.abilities for e in a.effects), "source already refreshing"


@pytest.mark.parametrize("resref", CASTER_ONLY)
def test_control_spells_are_caster_only(resref: str) -> None:
    spell = ie_formats.read_spl(SOURCE_SPELLS[resref])
    assert all(ability.target in ABILITY_TARGET_CASTER for ability in spell.abilities)


# --------------------------------------------------------------------------- --nogame harness


@pytest.mark.parametrize("resref", TARGETED)
def test_upstream_direct_refresh_targets_the_caster(tmp_path: Path, resref: str) -> None:
    """Reproduces the shipped bug state (matches override/spwi606.spl on an SR v4.19 install)."""
    built = build_upstream(tmp_path, resref)
    _assert_refresh_first(built, resref, EFFECT_TARGET_SELF)
    source_abilities = len(ie_formats.read_spl(SOURCE_SPELLS[resref]).abilities)
    assert len(_first_effects(built)) == source_abilities


@pytest.mark.parametrize("resref", TARGETED)
def test_live_patch_retargets_to_recipient_byte_exact(tmp_path: Path, resref: str) -> None:
    fixed = apply_live_fix(tmp_path, build_upstream(tmp_path, resref), resref)
    _assert_refresh_first(fixed, resref, EFFECT_TARGET_PROJECTILE)
    assert fixed == build_expected(tmp_path, resref)


@pytest.mark.parametrize("resref", TARGETED)
def test_live_patch_is_idempotent(tmp_path: Path, resref: str) -> None:
    once = apply_live_fix(tmp_path, build_upstream(tmp_path, resref), resref)
    twice = apply_live_fix(tmp_path, once, resref)
    assert twice == once


@pytest.mark.parametrize("resref", CASTER_ONLY)
def test_live_patch_leaves_caster_only_spells_untouched(tmp_path: Path, resref: str) -> None:
    built = build_upstream(tmp_path, resref)
    _assert_refresh_first(built, resref, EFFECT_TARGET_SELF)
    assert apply_live_fix(tmp_path, built, resref) == built


def test_live_patch_ignores_foreign_321(tmp_path: Path) -> None:
    """A 321 that removes a DIFFERENT resource (e.g. SCS cleanup) must not be retargeted."""
    built = build_upstream(tmp_path, "SPWI606", resource="DWOTHER")
    assert apply_live_fix(tmp_path, built, "SPWI606") == built


def test_live_patch_only_touches_the_target_byte(tmp_path: Path) -> None:
    buggy = build_upstream(tmp_path, "SPWI606")
    fixed = apply_live_fix(tmp_path, buggy, "SPWI606")
    assert len(buggy) == len(fixed)
    diffs = [i for i, (a, b) in enumerate(zip(buggy, fixed)) if a != b]
    spell = ie_formats.SplFile.from_bytes(buggy)
    assert len(diffs) == len(spell.abilities)
    assert all(buggy[i] == EFFECT_TARGET_SELF and fixed[i] == EFFECT_TARGET_PROJECTILE for i in diffs)


# --------------------------------------------------------------------------- fake game: real source file


def test_fork_refresh_code_targets_the_recipient(tmp_path: Path) -> None:
    game = make_fake_game(tmp_path, FORK_REFRESH)
    process = game.install("setup-srcb_test_refresh.tp2", 0)
    assert_installed(process)
    game.assert_inputs_unchanged()
    for resref in TARGETED:
        _assert_refresh_first(_override_spl(game, resref), resref, EFFECT_TARGET_PROJECTILE)
        assert _override_spl(game, resref) == build_expected(tmp_path, resref)
    for resref in CASTER_ONLY:
        _assert_refresh_first(_override_spl(game, resref), resref, EFFECT_TARGET_SELF)


def test_upstream_refresh_code_still_shows_the_bug(tmp_path: Path) -> None:
    """Control: the unmodified upstream v4.21 file must produce target 1 — proves detection."""
    game = make_fake_game(tmp_path, UPSTREAM_REFRESH)
    assert_installed(game.install("setup-srcb_test_refresh.tp2", 0))
    for resref in TARGETED:
        _assert_refresh_first(_override_spl(game, resref), resref, EFFECT_TARGET_SELF)
        assert _override_spl(game, resref) == build_upstream(tmp_path, resref)
    for resref in CASTER_ONLY:
        _assert_refresh_first(_override_spl(game, resref), resref, EFFECT_TARGET_SELF)


# --------------------------------------------------------------------------- fake game: live patch


def test_live_patch_public_install_and_uninstall(tmp_path: Path) -> None:
    game = make_fake_game(tmp_path, UPSTREAM_REFRESH)
    assert_installed(game.install("setup-srcb_test_refresh.tp2", 0))
    before = game.override_tree()
    install_live_patch_into(game)
    game.append_weidu_log(SR_WEIDU_LOG_LINE)

    process = game.install("SRCB_PROT_REFRESH/setup-SRCB_PROT_REFRESH.tp2", 0)
    assert_installed(process)
    assert "retargeted" in transcript(process)
    assert "~SRCB_PROT_REFRESH/SETUP-SRCB_PROT_REFRESH.TP2~ #0 #0" in game.active_weidu_log().upper()
    game.assert_inputs_unchanged()
    after = game.override_tree()
    assert set(after) == set(before)
    for resref in TARGETED:
        _assert_refresh_first(after[f"{resref}.SPL"], resref, EFFECT_TARGET_PROJECTILE)
        assert after[f"{resref}.SPL"] == build_expected(tmp_path, resref)
    for name in before:
        if name[:7] not in TARGETED:
            assert after[name] == before[name], name

    process = game.uninstall("SRCB_PROT_REFRESH/setup-SRCB_PROT_REFRESH.tp2", 0)
    assert "SUCCESSFULLY REMOVED" in transcript(process) or "Uninstalled" in transcript(process), transcript(process)
    assert game.override_tree() == before
    assert "SRCB_PROT_REFRESH" not in game.active_weidu_log().upper()


def test_live_patch_refuses_without_spell_revisions(tmp_path: Path) -> None:
    game = make_fake_game(tmp_path, UPSTREAM_REFRESH)
    assert_installed(game.install("setup-srcb_test_refresh.tp2", 0))
    before = game.override_tree()
    install_live_patch_into(game)  # no Spell Revisions line in WeiDU.log

    process = game.install("SRCB_PROT_REFRESH/setup-SRCB_PROT_REFRESH.tp2", 0)
    text = transcript(process)
    assert "SKIPPING" in text, text
    assert "requires Spell Revisions" in text, text
    assert game.override_tree() == before
    assert "SRCB_PROT_REFRESH" not in game.active_weidu_log().upper()
