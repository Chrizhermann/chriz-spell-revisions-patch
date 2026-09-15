# Live-install tail patches

WeiDU mini-mods that patch final effective resources at the tail of an install. Some retrofit
this fork's fixes onto an **already-installed** upstream Spell Revisions; others provide
cross-mod compatibility that can only run after all owning mods have installed their resources.
They can be appended without uninstalling the main Spell Revisions component (the
never-uninstall rule for the main EET install).

Fresh installs do not need the retrofit patches when they install this fork's `spell_rev/`
itself. They **do** need any applicable cross-mod tail patch, notably `SRCB_RR_COMPAT` when
Rogue Rebalancing is present.

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

RR's five affected CRE files have the original physical `SPWI508` spellbook entry baked into
them. SR turns that slot into Waves of Fatigue and relocates Chaos. The patch resolves both
identities from the final `SPELL.IDS`, moves each audited known/memorized entry to the final
level-seven Chaos resource, and preserves its copy count and both levels' spell-slot counters.
It also normalizes all Chaos
references in `RR#SELI`, `RR#ARAN2`, and `RR#STM01`, covering both possible compile orders.
Finally, it changes only Selina's self-recast status check from Spell Turning to Spell
Deflection; her availability check and cast action still use the spell's original identifier.

Copy the `SRCB_RR_COMPAT` folder and `Setup-SRCB_RR_COMPAT.exe` from either release
archive into the game directory. When using a source checkout, create the setup
executable there as a copy of WeiDU v249 instead. Double-click it or run:

```
./setup-SRCB_RR_COMPAT.exe --force-install-list 0 --language 0 --use-lang en_US --no-exit-pause
```

The component deliberately fails if a present RR resource no longer has either the exact
audited v4.92 shape or the already-fixed shape. That avoids silently rewriting a future RR
version whose tactics may have changed. Blindness, Deafness, Bigby's Clenched Fist, Infravision,
and a wider SCS compatibility sample are outside this component.

Install before first entering/spawning the affected encounters. The patch does not edit save
files, so a creature whose spellbook is already embedded in a save is not retroactively
rewritten. Uninstall restores the prior game resources. Automated coverage uses real WeiDU with
synthetic CREs matching all five audited copy counts and compiled BCS fixtures: both SR/RR
orders converge byte-exactly, a second pass is idempotent, each RR prerequisite scopes its own
resources, malformed shapes fail closed, and public install/uninstall round-trips cleanly.
A quick in-game spellbook/casting smoke test was reported successful by the user
on 2026-09-07 in an isolated BG2:EE 2.6.6.0 install. Full hostile-encounter behavior,
including the recast guard in combat, and a wider SCS audit have not been tested.
