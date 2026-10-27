# Live-install tail patches

WeiDU mini-mods that patch final effective resources at the tail of an install. Some retrofit
this fork's fixes onto an **already-installed** upstream Spell Revisions; others provide
cross-mod compatibility that can only run after all owning mods have installed their resources.
They can be appended without uninstalling the main Spell Revisions component (the
never-uninstall rule for the main EET install).

Fresh installs do not need the retrofit patches when they install this fork's `spell_rev/`
itself. They **do** need any applicable cross-mod patch, notably `SRCB_RR_COMPAT` when
Rogue Rebalancing is present and `SRCB_SCS_COMPAT` when SCS is. `SRCB_SCS_COMPAT` is no tail
patch: it changes SCS's source, so it goes after SR and before SCS's AI components.

## SRCB_CLASSIC_LIGHTNING (optional)

For an existing installation, the optional `SRCB_CLASSIC_LIGHTNING` mini-mod offers
classic bouncing (component 0, main-fork component 80) or non-bouncing spell/wands
with dedicated traps unchanged (component 1, main-fork component 81). Install one
alternative, not both the source and tail versions. The release includes its own
WeiDU executable. See [its detailed comparison and limitations](SRCB_CLASSIC_LIGHTNING/README.md).
Applying a mini-mod is not an automatic CEBG hotpatch and does not authorize changing a
running game; close the game and preserve a backup before any installation.

## NPC elemental-spell migration is component-owned

The hidden elemental-protection child-to-parent migration has no replacement tail mini-mod. It belongs
at the end of Spell Revisions component 60, after all NPC additions and class/kit/spellbook
or script assignments. Future full installs using this fork do not need the old standalone
`SR_SUBSPELL_FIX`; an existing frozen WeiDU stack should keep its already-installed copy until a
validated rebuild. It also patches matching runtime grants in scripts referenced by joinable NPC
resources. Component 60 cannot rewrite NPC creatures already embedded in a save.

## SRCB_PROT_REFRESH

**Fix: Protection from Magic Energy / Protection from the Elements / Protection from Energy
strip the caster's buff instead of refreshing the recipient's** (EE games, Spell Revisions
v4.19+; design and root cause in
`docs/plans/2026-08-22-fork-setup-and-protection-refresh-fix-design.md`).

Upstream inserts the "refresh, non-stacking" `opcode 321 remove-effects-by-resource = itself`
with effect target 1 (*Self* = the caster). On these three creature-targeted spells that
removes the **caster's** own protection every time the spell is cast on an ally, and never
replaces an older instance on the recipient. The patch rewrites exactly those effects to target
2 (*Projectile target* = the recipient) in every ability header of the three spells, resolved
by `spell.ids` symbol (`WIZARD_PROTECTION_FROM_MAGIC_ENERGY` / `…THE_ELEMENTS` / `…ENERGY`),
never by hard-coded resref. Caster-only spells are left alone. Idempotent; uninstall restores
the previous bytes.

Requires Spell Revisions' main component (`spell_rev` #0). Install from the game dir after
copying the `SRCB_PROT_REFRESH` folder there and creating `setup-SRCB_PROT_REFRESH.exe` as a
copy of any WeiDU v249 setup exe:

```
./setup-SRCB_PROT_REFRESH.exe --force-install-list 0 --language 0 --no-exit-pause
```

No console step: SPL files are read when a spell is cast, so the fix applies to existing
saves on the next cast. Buffs that are already running are unaffected either way.

Acceptance test in-game: a mage casts Protection from Magic Energy on themself, then on a
fighter — both keep the portrait icon; casting it on the fighter again leaves a single
instance. Undo: re-run the exe and `[U]ninstall`.

Verified with `python -m pytest tests` (WeiDU 249): byte-exact against an expected build,
idempotent, caster-only spells and foreign opcode-321 effects untouched, public
install/uninstall round-trips a synthetic game byte-exactly, and the component refuses to
install without Spell Revisions.

## SRCB_RR_COMPAT

**Rogue Rebalancing compatibility: Chaos spellbooks/scripts and Selina's Spell Deflection
guard.** Install this component after both Spell Revisions and Rogue Rebalancing, regardless of
which of those two was installed first. It requires SR's main component (`spell_rev` #0) and
RR's **Chosen of Cyric** (#11) and/or **Shadow Thief Improvements** (#12).

RR's creature files have the original physical `SPWI508` spellbook entry baked into them. The
patch resolves every identity from the final `SPELL.IDS` and reads where SR has Chaos.

**Chaos at level 5** (this fork from v4.21-chriz.8): `SPWI508` is Chaos again, so RR's
spellbooks and Chaos casts are right as they are and stay. Only Selina's self-recast guard
changes (last paragraph of this section). The Chaos spell must be a level-five wizard spell.

**Chaos at level 7** (SR up to v4.21-chriz.7): SR turns that slot into Waves of Fatigue and
makes Chaos a level-seven spell, which stays so. Each prepared level-five copy of the
old slot becomes a level-five spell where it stands, with its own flags and without changing
any spell-slot counter: Hold Monster for Aran Linvail (`RR#ARAN2`), Feeblemind for the
Zhentarim Mercenary (`RR#SFL04`) and Domination for Selina (`RR#SELI`). A wizard's known
records stay; Selina is a sorcerer, who casts from her known list, so her known old-slot
record becomes Domination too (or is removed if she already knows it). `RR#SAW09` and
`RR#ZAER` only know the old slot and are not changed.
All Chaos references in `RR#ARAN2`, `RR#STM01` and `RR#SELI` name the same replacement,
covering both possible compile orders; blocks that cast at a target they picked also get
the checks the replacement needs, such as Spell Turning for Feeblemind and Domination or free
action for Hold Monster. Selina's opening Spell Trigger casts Domination.
Finally, it changes only Selina's self-recast status check from Spell Turning to Spell
Deflection, found as the guard of a block that casts Spell Turning on herself; her
availability check, cast action and Spell Turning checks on enemies keep the spell's original
identifier. The decision and the exact checks are recorded in
`docs/plans/2026-09-02-rr-spell-semantics-compatibility-design.md` (2026-10-23).

Copy the `SRCB_RR_COMPAT` folder and `Setup-SRCB_RR_COMPAT.exe` from either release
archive into the game directory. When using a source checkout, create the setup
executable there as a copy of WeiDU v249 instead. Double-click it or run:

```
./setup-SRCB_RR_COMPAT.exe --force-install-list 0 --language 0 --use-lang en_US --no-exit-pause
```

Entries and references are recognized by the spell they name, not by the audited counts, so
another number of copies or an extra Chaos branch is changed as well. The component fails,
naming the resource, when a creature or script names both the old slot and SR's Chaos (a
later mod's intended Waves of Fatigue or Chaos cannot be told apart from RR's Chaos there),
when old-slot copies sit outside the level-five wizard row or share a record with another
level's row, or when the game lacks an IDS symbol the added checks name. A resource naming
neither, nor the replacement, is left unchanged with a warning. Blindness, Deafness, Bigby's
Clenched Fist, Infravision, and a wider SCS compatibility sample are outside this component.

Install before first entering/spawning the affected encounters. The patch does not edit save
files, so a creature whose spellbook is already embedded in a save is not retroactively
rewritten. While it is the last entry in WeiDU.log, a reinstall updates it in place and an
uninstall restores the prior game resources. Deeper in a stack, do not reinstall or uninstall
it: WeiDU 249 either skips the request or reinstalls every later component, which can drop
some of them. Automated coverage uses real WeiDU with
synthetic CREs with the audited copy counts and with other counts, flags, classes and full
spellbook layouts, plus compiled BCS fixtures: both SR/RR orders converge byte-exactly, a second
pass is idempotent, each RR prerequisite scopes its own resources, sorcerer and wizard known
records, added checks, extra branches, IDS aliases and Chaos Shield are handled, ambiguous or
malformed shapes fail closed, and public install/uninstall round-trips cleanly. With Chaos at
level 5, both install orders change only Selina's script, keep every Chaos reference, and
uninstall cleanly; RR's component 12 alone changes nothing, and a Chaos spell outside level
five fails. A local check applied the level-seven branch to RR v4.92's own creatures and
scripts in both install orders; the level-five branch has not been run against RR's own files.
A quick in-game spellbook/casting smoke test of the earlier level-seven migration was reported
successful by the user on 2026-09-07 in an isolated BG2:EE 2.6.6.0 install; the level-five
replacements have not been checked in game yet. Full hostile-encounter behavior, including the
recast guard in combat, and a wider SCS audit have not been tested.

## SRCB_SCS_COMPAT

**Sword Coast Stratagems compatibility: SCS mages use their own Chaos tactic.** SCS has a
tactic for its mages' Chaos (cast it at groups, skip targets that are confused already or
protected against confusion) and leaves it out whenever Spell Revisions is installed, because
SR up to v4.21-chriz.7 had no Chaos at level 5. With this fork's Chaos at level 5, the
component removes SCS's Spell Revisions gate (`Demivrgvs`) from the tactic blocks in
`stratagems/mage/ssl/combatblocks/l5_enchantment.ssl` that cast `WIZARD_CHAOS`. SCS's dragons
keep casting Confusion in place of Chaos, and Waves of Fatigue keeps SCS's own tactic.

It changes SCS's source, so it goes after Spell Revisions' main component and before SCS's AI
and tactical components (6000 and up), with SCS's files already in the game folder. Copy the
`SRCB_SCS_COMPAT` folder and `Setup-SRCB_SCS_COMPAT.exe` from its release archive into the
game directory. When using a source checkout, create the setup executable there as a copy of
WeiDU v249 instead. Double-click it or run:

```
./setup-SRCB_SCS_COMPAT.exe --force-install-list 0 --language 0 --use-lang en_US --no-exit-pause
```

The component fails without changing anything when the final `SPELL.IDS` does not map
`WIZARD_CHAOS` to a level-5 wizard spell, when SCS's library does not call Spell Revisions
`Demivrgvs`, or when the file has no block that casts Chaos. When SCS's AI components are
installed already, it warns: their mage scripts keep the skip until they are reinstalled.
Automated tests and disposable-lab results (114 of 114 SCS mages with Chaos got the tactic,
0 of 125 without the component) are in [its README](SRCB_SCS_COMPAT/README.md).
