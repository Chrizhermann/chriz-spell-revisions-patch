# A. Changelog.

## Fork version: v4.21-chriz.6 (2026-10-23).

1. `SRCB_RR_COMPAT`: Chaos stays Spell Revisions' level-7 spell. Rogue Rebalancing
   v4.92's prepared level-5 Chaos copies become a level-5 spell where they stand, with
   their flags and every spell-slot cap: Hold Monster for Aran Linvail, Feeblemind for
   the Zhentarim Mercenary and Domination for Selina. This replaces the level-7
   migration of v4.21-chriz.4, whose moved copies Aran and the Mercenary could never
   cast behind their level-7 slot counters (BG2:EE 2.7.3.0 lab check).
2. Selina is a sorcerer and casts from her known list, so her known old-slot record
   becomes Domination too, without a duplicate. Wizards keep their known records;
   `RR#SAW09` and `RR#ZAER` only know the old slot and are no longer changed.
3. The three RR scripts cast the replacement in either SR/RR order. Blocks that pick a
   target keep their filters and gain the checks the replacement needs, written as RR's
   own blocks check them: Spell Turning and similar protections for Feeblemind and
   Domination, charm-protection items for Domination, and free action and hold-immune
   kits and items for Hold Monster. Selina's opening Spell Trigger casts Domination.
4. RR spellbook entries and script references are recognized by the spell they name,
   not by the audited counts, and hexadecimal `SPELL.IDS` values are read. A creature or
   script naming both RR's old slot and SR's Chaos, or holding the old slot outside the
   level-5 wizard book, fails with the resource named.
5. Lightning Bolt options (80, 81 and `SRCB_CLASSIC_LIGHTNING`): SR's two damage halves
   are identified by meaning, in either order. Damage another mod adds to the bolt is
   kept instead of failing the installation, and a repeat application is byte-exact.

Validation: 198 tests passed with real WeiDU 249, including 53 SR/RR compatibility and
88 Lightning Bolt tests. A local check applied the RR component to RR v4.92's own
creatures and scripts in both orders, and over a v4.21-chriz.5 installation of it as
the last WeiDU.log entry. Deeper in a stack, a WeiDU 249 reinstall skips the component
or reinstalls every later one and can drop some of them, so it is not an update path
there. The level-5 replacements have not been checked in game yet. The main SR
component, component 60 and the component menu are unchanged from v4.21-chriz.5.

## Fork version: v4.21-chriz.5 (2026-09-16).

1. Added optional, mutually exclusive Lightning Bolt behaviors: classic bouncing
   wizard spell (80), or non-bouncing wizard spell and direct lightning wands with
   dedicated traps unchanged (81). Skipping both preserves Spell Revisions.
2. Both alternatives restore path damage, a Spell save for half, and Mirror Image
   bypass for the wizard spell. Later saving-throw adjustments, other spell effects,
   and SCS casting features are retained. Non-bouncing uses its own projectile and
   clones supported projectile protections without replacing the trap projectile.
3. Preserved all v4.21-chriz.4 fixes, including the separate SR/RR compatibility
   package. Full and standalone Windows downloads include WeiDU 249 x64 installers.

Validation: 110 tests passed with real WeiDU, including 39 Lightning regressions.
The restored Lightning implementation matches the already rehearsed September 8
snapshot. New runtime casting acceptance is deferred to the combined CEBG install;
this release does not claim an in-game cast test or automatically patch existing saves.

## Fork version: v4.21-chriz.4 (2026-09-07).

1. Added the standalone `SRCB_RR_COMPAT` compatibility component, installed after
   both Spell Revisions and Rogue Rebalancing. It restores the intended Chaos in
   five RR v4.92 spellbooks and three AI scripts, including their forced-cast
   opening sequences, while preserving memorized copy counts and spell-slot caps.
2. Selina's Spell Turning self-recast guard now recognizes SR's Spell Deflection
   state. Her availability check, cast identifier, targeting, and tactics are unchanged.
3. Both Windows downloads include WeiDU 249 x64. The full archive includes the
   separately installed compatibility component; the smaller compatibility-only
   archive can be appended to an existing SR/RR install without reinstalling SR.

Validation: 71 automated tests with real WeiDU, authentic RR/SR installer checks in
both orders, and a successful user-reported in-game spellbook/casting smoke test.
Full hostile-encounter testing and a wider SCS compatibility audit remain deferred.
The main SR component menu and spell gameplay are unchanged from v4.21-chriz.3.

## Fork version: v4.21-chriz.3 (2026-09-04).

Packaging-only successor to v4.21-chriz.2. The gameplay code and component menu are
unchanged. The Windows release archive now includes WeiDU 249 x64 as
`Setup-spell_rev.exe` for a conventional double-click installation.

## Fork version: v4.21-chriz.2 (2026-09-02).

1. Fixed Protection from Magic Energy, Protection from the Elements, and Protection from Energy
   refresh behavior on creature targets. Their non-stacking effect now removes the previous
   instance from the recipient instead of stripping the caster's own protection. The same fix is
   available as the tail-installable `SRCB_PROT_REFRESH` mini-mod for existing EE installs.
2. Component 60 now replaces Spell Revisions' hidden Protection from Fire, Cold, Electricity,
   and Acid implementation-spell grants with Protection from Elemental Energy. Targets are
   derived from the effective parent container, its type-3 selector choices, HIDESPL, and
   semantic SPELL.IDS identities; no legacy spell slots are hard-coded.
3. The migration covers both joinable-NPC known/memorized spell entries and exact
   `AddSpecialAbility` grants in scripts referenced by joinable NPCs. This fixes the natural
   Beregost Neera path, whose join-XP script otherwise reintroduced Protection from Fire after
   clean CRE resources had been installed.
4. Synthetic and `--nogame` regressions cover affected and unaffected NPCs and scripts,
   relocated/reordered resources, safe failure, repeated execution, and public
   install/uninstall restoration.

Release verification: all 57 automated tests passed with WeiDU 249. Disposable EET static/install
acceptance confirmed the parent replacement in `NEERA6.CRE`, `NEERA7.CRE`, and Neera's effective
join-XP script while preserving the active WeiDU component set and unrelated patched resources.
Natural in-game recruitment and selector casting were not rerun; the maintainer explicitly waived
that final runtime smoke test after reviewing the static acceptance evidence.

## Version: 4.21.

1. [Fix bg1 ee strings](https://github.com/Gibberlings3/SpellRevisions/pull/153): patch by aigleborgne, with help of jmerry over at the G3 forums, to fix wrong strings being displayed in bg1 ee. Thanks to them both.

2. [Correct typos in description for Dispelling Screen](https://github.com/Gibberlings3/SpellRevisions/pull/155): patch by visionok.

3. [Fix Chromatic Orb description.](https://github.com/Gibberlings3/SpellRevisions/pull/156): delete reference to "multiple effects" of Chromatic Orb from description. It does not have them. Thanks to LichDiet over at the G3 forums for spotting the issue.

## Version: 4.20.

1. [Fix iwd install](https://github.com/Gibberlings3/SpellRevisions/pull/151): fixes several issues that made the installation in iwd ee fail. See the PR for more details.

## Version: 4.19.

The highlight of this new version is in the purely administrative side of leaving beta status behind and adding a readme to the GitHub site and a brand new spanking changelog in markdown, which you are now reading. Very little in terms of new features, most of the changes are in polishing old code (of which there is a lot) and bug fixes.

The most salient ones are:

1. [Fix icons for Obscuring Mist and Monster Summoning I scrolls](https://github.com/Gibberlings3/SpellRevisions/pull/25)
2. [Fix compatibility issue with DR v8+](https://github.com/Gibberlings3/SpellRevisions/pull/40)
3. Spell fixes. Too many to document here, so we just link to the respective PR's for the documentation.

   * [Arcane level 1 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/41)
   * [Arcane level 2 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/47)
   * [Arcane level 3 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/49)
   * [Arcane level 4 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/51)
   * [Arcane level 5 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/53)
   * [Arcane level 6 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/56)
   * [Arcane level 7 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/58)
   * [Arcane level 8 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/61)
   * [Arcane level 9 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/63)
   * [Divine level 1 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/46)
   * [Divine level 2 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/48)
   * [Divine level 3 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/50)
   * [Divine level 4 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/52)
   * [Divine level 5 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/54)
   * [Divine level 6 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/57)
   * [Divine level 7 Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/59)
   * [Incorrect patching](https://github.com/Gibberlings3/SpellRevisions/pull/67)
   * [More Spell Fixes](https://github.com/Gibberlings3/SpellRevisions/pull/74)

4. [Update spell school setting code](https://github.com/Gibberlings3/SpellRevisions/pull/42)
5. [Update nwn-like spell deflection code](https://github.com/Gibberlings3/SpellRevisions/pull/43)
6. [Update Haste + Slow patching code](https://github.com/Gibberlings3/SpellRevisions/pull/44)
7. [Handling of some IR items](https://github.com/Gibberlings3/SpellRevisions/pull/45)
8. [RFC:Greater Malison](https://github.com/Gibberlings3/SpellRevisions/pull/55)
9. [RFC:Neutral Charm Spells](https://github.com/Gibberlings3/SpellRevisions/pull/64)
10. [Patch to Fire Shield protection from insects](https://github.com/Gibberlings3/SpellRevisions/pull/66)
11. [Update description of Non-Detection](https://github.com/Gibberlings3/SpellRevisions/pull/71)
12. [RFC: Prismatic Mantle](https://github.com/Gibberlings3/SpellRevisions/pull/72)
13. Spell flags: a series of patches that allows users (and developers short on time) to fiddle with spell flags like break invisibility, hostile, etc. The first was [Invisibility and Hostile flags](https://github.com/Gibberlings3/SpellRevisions/pull/73), based on subtledoctor's work, the second, [Three-state flags](https://github.com/Gibberlings3/SpellRevisions/pull/84), allowed to clear the flags (i.e. set to 0), and the third, [Add more spell flags](https://github.com/Gibberlings3/SpellRevisions/pull/88), extended the ability to other spell flags like non-combat. At the moment, only the flags break invisible and hostile have meaningful set values, but these themselves need to be combed over.
14. [Re-write and bug-fix EE refresh, non-stacking code](https://github.com/Gibberlings3/SpellRevisions/pull/75)
15. [Drop concentration checks](https://github.com/Gibberlings3/SpellRevisions/pull/81): the formula for concentration checks is bugged, so until Beamdog fixes it, reverting to vanilla behavior.
16. [Berserk -> Feeblemind in Chaos](https://github.com/Gibberlings3/SpellRevisions/pull/87): The Berserk opcode does not work correctly on non-party members in old, non-EE BG versions, so it was decided to change the Chaos spells to inflict feeblemind instead.
17. [Avenger Cone of Cold -> Confusion](https://github.com/Gibberlings3/SpellRevisions/pull/90): SR changes the level 4 Avenger spell from Chaos to Cone of Cold. There is something to be said about this choice, but it has its downsides, not the least confusing SCS (in fairness, in part because it was implemented as a straight override) so it was decided to switch back to a spell that is closer to the original Chaos.
18. [Fix dvbanish](https://github.com/Gibberlings3/SpellRevisions/pull/92)
19. [French translation](https://github.com/Gibberlings3/SpellRevisions/pull/93): French translation files generously provided by mleduque.
20. [Fix Shapechange ability names in IWD](https://github.com/Gibberlings3/SpellRevisions/pull/96): Patch by gsz. Then improved in [Extract spirit troll shapechange name and add FR translation](https://github.com/Gibberlings3/SpellRevisions/pull/105) by mleduque.
21. [Power level fix on Vitriolic Sphere](https://github.com/Gibberlings3/SpellRevisions/pull/98): Power Level on Vitriolic Sphere acid damage opcode -> 4. Patch by Bartimeus.
22. [LABEL components](https://github.com/Gibberlings3/SpellRevisions/pull/100): Add `LABEL` commands to every (non-deprecated) component.
23. [Fix displayed strings in spells](https://github.com/Gibberlings3/SpellRevisions/pull/107): Improved in [Fix Ray Enfeeble message (and overall improvements)](https://github.com/Gibberlings3/SpellRevisions/pull/134).
24. [Fixes to Elemental Prince HLA](https://github.com/Gibberlings3/SpellRevisions/pull/114):
25. [Missing projectile in Avenger's chromatic orb](https://github.com/Gibberlings3/SpellRevisions/pull/117): patch by mercurier.
26. [Patching hidespl.2da instead of overriding](https://github.com/Gibberlings3/SpellRevisions/pull/116): as the name says; instead of overwriting `hidespl.2da` tables, patch them. Subsequently refined in [Fix hidespl.2da patching in tobex](https://github.com/Gibberlings3/SpellRevisions/pull/126).
27. [Imprisonment vs. Freedom patches](https://github.com/Gibberlings3/SpellRevisions/pull/118):
28. [Patch inquisitor true seeing](https://github.com/Gibberlings3/SpellRevisions/pull/119):
29. [Wrong dice in Talos' Lightning Bolt](https://github.com/Gibberlings3/SpellRevisions/pull/124): a sleuth of fixes to the Cleric of Talos' version of Lightning Bolt (more than the title suggests).
30. [rc5 fixes](https://github.com/Gibberlings3/SpellRevisions/pull/132): patch by subtledoctor to fix issues with 232 opcodes in Sleep, Magic Fang, etc.
31. [Find Traps fix](https://github.com/Gibberlings3/SpellRevisions/pull/138): Fix a targeting bug in the cleric Find Traps spell.
32. [Saves Component](https://github.com/Gibberlings3/SpellRevisions/pull/139): the code copying the new, revised saving throw tables has been relegated to its own component.
33. [Work around crashes with opcode 324](https://github.com/Gibberlings3/SpellRevisions/pull/148): Change `kreso_eestatsr.tph` opcode 324 -> 318 in spin561, spin642 and spwi022 to work around crashes.

## Earlier versions.

For earlier versions, see [Previous Changelog](./change-log.txt).
