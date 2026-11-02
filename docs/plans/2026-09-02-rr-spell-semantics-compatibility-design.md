# RR / Spell Revisions spell-semantics compatibility

From v4.21-chriz.8 this fork has Chaos at wizard level 5 again
(`2026-10-28-chaos-level-5-design.md`). The component then keeps RR's Chaos
spellbooks and casts and only fixes Selina's guard; everything below about
replacing RR's Chaos applies to SR up to v4.21-chriz.7, where Chaos is at level 7.

The decision of 2026-10-23 (last section) replaces the level-seven Chaos
migration described in the earlier sections: Chaos stays at level 7, and RR's
level-five copies become level-five spells.

## Scope

Add a standalone WeiDU mini-mod that is installed after both Spell Revisions and
Rogue Rebalancing. The first component deliberately covers only the two reviewed,
low-risk corrections:

- migrate RR's baked Chaos spellbook entries from the physical slot repurposed as
  Waves of Fatigue to the effective `WIZARD_CHAOS` resource;
- make Selina's one Spell Turning recast guard recognize SR's Greater Spell
  Deflection state.

Blindness, Deafness, Bigby's Clenched Fist, Infravision, and a wider SCS sample
audit are deferred because they require tactical redesign rather than a mechanical
identifier migration.

## Install order and discovery

The compatibility component belongs after both mods. It resolves
`WIZARD_WAVES_OF_FATIGUE` and `WIZARD_CHAOS` from the final effective `SPELL.IDS`
instead of assuming `SPWI508` or `SPWI711`. It requires Spell Revisions component
0 and at least one of RR's Chosen of Cyric (11) or Shadow Thief Improvements (12)
components.

## Exact transforms

The CRE migration is limited to the five RR v4.92 resources proven to contain the
baked old Chaos slot:

- component 11: `RR#SELI`, `RR#ZAER`;
- component 12: `RR#ARAN2`, `RR#SAW09`, `RR#SFL04`.

It accepts either the original shape (exactly one old known spell, no final Chaos)
or the already-migrated shape (no old spell, exactly one final Chaos). Original
active memorized copies are removed from the fifth-level wizard slice and restored
at Chaos's effective wizard level with their multiplicity preserved. Both levels'
maximum/current spell-slot counters are preserved; this avoids WeiDU's standard
add-spell operation inflating Selina's level-seven capacity. Mixed or unexpected
spellbook shapes fail rather than guessing.

The BCS migration is limited to the audited scripts and exact RR v4.92 occurrence
counts:

- `RR#SELI`: 17 Chaos references;
- `RR#ARAN2`: 13 Chaos references;
- `RR#STM01`: 12 Chaos references.

An RR-before-SR script decompiles those numeric 2508 references as
`WIZARD_WAVES_OF_FATIGUE`; an SR-before-RR script decompiles them as either
`WIZARD_CHAOS` or the same-number `WIZARD_SPHERE_OF_CHAOS`, depending on final IDS
alias order. The audited RR scripts contain no intended Sphere-of-Chaos references,
so the combined final-alias count remains exact. Each script must be wholly old or
final shape. Selina's exact
`!CheckStatGT(Myself,0,WIZARD_SPELL_TURNING)` trigger alone becomes
`!CheckStatGT(Myself,0,WIZARD_SPELL_DEFLECTION)`; her spell availability and cast
actions remain Spell Turning, which SR intentionally redirects to Greater Spell
Deflection.

## Verification

Real WeiDU tests use synthetic CREs with RR's audited copy counts and compiled BCS
fixtures. They prove both install orders converge, unrelated records and Turning
uses survive, a repeated pass is byte-exact, malformed mixed shapes fail closed,
the public predicates work, and uninstall restores the prior resources.

Release validation (2026-09-07): the full suite has 71 passing tests with WeiDU
249. Authentic RR v4.92 sources (commit
`18680008d468ec5014b4377beabb706376ad0fe0`) and SR v4.21 were also installed in
both orders before applying the compatibility component; the five CREs and
three decompiled BCS files matched the audited expectations.

The user reported the agreed quick in-game spellbook/casting smoke test successful
in an isolated BG2:EE 2.6.6.0 install. That is not full hostile-encounter acceptance
or evidence that SCS understands every revised spell. The temporary playable
install and its separate profile were subsequently moved to the Recycle Bin;
the normal game was not changed.

## Compatibility revision, 2026-10-17

Follow-up 4 of the 2026-10-08 SR/rebalance compatibility audit
(`docs/audits/2026-10-08-sr-rebalance-compatibility.md` in chriz-bg-rebalance):
the exact copy and reference counts above were fingerprints of one installation.
A creature with one copy fewer, or an RR script with one more Chaos branch, failed
although it had the same broken mapping.

- **Spellbooks.** A creature naming only the old slot is migrated, however many
  known or prepared copies it has. Known entries are renamed where they stand.
  Each prepared copy moves from the level-five to the end of the level-seven wizard
  row with its own flags, so copies already cast stay cast; the table keeps its
  size, and only the first indexes of the rows in between move. No slot counter
  changes, and no known entry is added for a copy that was only prepared. A
  creature naming only Chaos is left alone; one naming neither is left unchanged
  with a warning.
- **Scripts.** RR v4.92's sources (`rr#seli.baf`, `rr#aran2.baf`, `rr#stm01.baf`
  at the pinned commit) name Chaos only through `WIZARD_CHAOS`: 17, 13 and 12
  times, never by resource name. A script naming only the old slot therefore
  means Chaos by every such reference, and all of them are migrated. References
  are matched as spell arguments under every `SPELL.IDS` symbol of the number,
  because the decompiler prints the last of several same-number symbols;
  `WIZARD_CHAOS_SHIELD` is not mistaken for Chaos.
- **Selina.** The guard is changed in every block that casts the Spell Turning
  identifier on herself (by any symbol of its number), not by an exact
  occurrence count. Her source has one such block. Her many Spell Turning checks
  on enemies and before other spells keep their meaning.
- **Guards kept, each with a reason.** Both slots in one creature or script (a
  later mod's intended Waves of Fatigue cannot be told apart from RR's Chaos);
  old-slot entries outside the level-five wizard book; no single level-five and
  level-seven wizard row for moved copies; memorization rows sharing records (a
  move would change another level); the CRE structure checks; the final
  `SPELL.IDS` levels, with `WIZARD_SPHERE_OF_CHAOS` required to match Chaos only
  when it exists.

Validation: `tests/test_rr_compat.py` has 31 real-WeiDU tests. The 18 new ones
cover full priest/wizard/innate spellbooks in both physical row orders with
mixed flags, other copy counts, prepared-only and duplicate known entries,
migrated, unrelated and missing resources, the four rejected spellbook shapes,
extra and fewer script branches, a script naming both slots, a script naming
neither, Chaos Shield, IDS aliases for the old slot and for Spell Turning, and
Selina's guard identified among enemy and other-spell checks. 17 of them fail
against the previous library.

Independent review, same day (Codex source review), two more cases:

- **Empty level-seven row.** An empty memorization row's first index means
  nothing to the engine and may point between another row's records. Moving a
  copy there put it into that row and pushed the row's last record out of it.
  The level-seven row now starts after the row its index points into before the
  first copy moves; a row whose index already sits on a boundary is unchanged.
- **Hexadecimal IDS values.** `SPELL.IDS` lines such as `0x9cc
  WIZARD_WAVES_OF_FATIGUE` are read as the engine reads them, so the symbol
  alternation no longer fails with "no readable symbol".

`tests/test_rr_compat.py` now has 37 tests: four empty-row layouts (inside the
level-five row with the old slot in the middle or last, inside another level's
row, and on a boundary as a control), each also applied twice and compared
byte for byte, and hexadecimal IDS in both install orders. Five of the six fail
against the previous library; the boundary control passes on both.

Limits: synthetic fixtures only; no new authentic-install or in-game check. A
Waves of Fatigue reference that another mod added to these RR scripts before
this component, in a script without any Chaos reference, cannot be told apart
and becomes Chaos.

## Decision, 2026-10-23: Chaos stays at level 7

The BG2:EE 2.7.3.0 lab check of 2026-10-20 showed that the migration above
leaves Aran Linvail (`RR#ARAN2`) and the Zhentarim Mercenary (`RR#SFL04`) unable
to cast Chaos: their moved copies land behind their level-seven slot counters.
An exception to the slot-cap rule, moving each copy's slot along to level 7, was
proposed and not adopted. Christopher decided instead ("passt", 2026-10-23):

- Chaos stays SR's level-seven spell. No copy and no slot moves; every slot
  counter stays as it is (the slot-cap rule above still holds). Christopher
  ruled out keeping RR's copies as Waves of Fatigue.
- RR's prepared level-five Chaos copies, the `SPWI508` records in the level-five
  wizard row, become a level-five spell where they stand, each with its own
  flags: Hold Monster (`SPWI507`) for `RR#ARAN2`, Feeblemind (`SPWI509`) for
  `RR#SFL04`, and Domination (`SPWI506`) for Selina (`RR#SELI`), so that she keeps
  four different level-five spells.
- Known-only old-slot records stay as they are. `RR#SAW09` (cleric/mage) and
  `RR#ZAER` (fighter/mage/thief) know `SPWI508` but never prepare it; they are no
  longer changed, and nothing moves to level-seven Chaos any more.
- Every Chaos reference in the scripts names the replacement: `RR#ARAN2` Hold
  Monster, `RR#STM01` (the script of `RR#SFL04`, which already casts Feeblemind
  in blocks of its own) Feeblemind, `RR#SELI` Domination. Selina's opening Spell
  Trigger casts Domination as its third spell.

**A sorcerer's known record.** A wizard memorizes from a spellbook, and RR's
wizards know more spells than they prepare, so their known records stay. A
sorcerer casts from its known list: had Selina's known `SPWI508` stayed while her
six copies became Domination, her level-five book would list Waves of Fatigue as
a spell she casts. Her known record therefore changes with the copies (approved
the same day). The rule is keyed by meaning, not by name: it applies to class 19,
sorcerer, the engine's only class that casts wizard spells from its known list.
When the replacement is already known, the old record is removed instead, so no
spell is known twice. RR v4.92's Selina ends with level-five known `SPWI513`,
`SPWI506`, `SPWI505`, `SPWI514` and six memorized copies of each; slots stay 6/6.

**Script filters.** A retargeted block that picks a target and casts at it
(`Spell`, `SpellNoDec`) keeps every filter it had for Chaos and gains what the
replacement needs that Chaos did not, for the same target object, as RR checks
it in its own blocks for that spell or effect:

- Feeblemind and Domination are single-target spells, which Spell Turning, Spell
  Deflection, Spell Trap and Shield of the Archons reflect or stop. RR's own
  Feeblemind (`RR#STM01`) and Domination (`RR#STM02`) blocks skip such targets.
  Chaos and SR's Hold Monster use area projectiles (Hold Monster `HOLD.PRO`),
  which these protections do not stop.
- Domination also skips the charm-protection items RR's Domination blocks name:
  `HELM06`, `SHLD25`, `SPER07`, `SW1H35`, `SW2H14`.
- Hold Monster also skips free action (`CLERIC_FREE_ACTION`), the hold-immune
  Inquisitor and Undead Hunter kits, the items RR's Hold Person blocks name
  (`MORSWORD`, `RING09`, `SHLD25`, `NPSW01`, `SPER07`, `SW1H27`, `SW2H06`), and
  undead, which RR's Chaos blocks already skip.

A filter a block already has is not added again; improved-invisible and disabled
targets are already excluded by RR's `STATE_NOT_TARGETABLE` and `STATE_DISABLED`
checks. Saving-throw thresholds and difficulty gates are tactics and stay as RR
wrote them. A forced cast (Selina's Spell Trigger) is a scripted sequence and only
changes its spell: a filter there would skip the whole sequence. Every IDS symbol
the filters name must exist in the game first, because WeiDU can compile a
missing symbol as 0.

**Guards, each with a reason.** A creature naming both the old slot and Chaos (a
later mod's intended Waves of Fatigue cannot be told apart); a script naming both
(either could be RR's Chaos, depending on the compile order); a copy prepared
outside the level-five wizard row; a copy shared with another level's row
(renaming it would change that level too); a sorcerer knowing the old slot
outside its level-five book; the CRE structure checks; the final `SPELL.IDS`
levels of Waves of Fatigue, Chaos and the three replacements. A creature that
prepares neither the old slot nor its replacement, and a script that names
neither Chaos slot nor its replacement, are left unchanged with a warning; one
already in the final state is left unchanged without one. The earlier guard
against an empty or missing level-seven row is gone, since nothing moves there.

Validation: `tests/test_rr_compat.py` has 53 real-WeiDU tests; 39 of them fail
against the previous library. They cover the three creatures in both install
orders, Selina's sorcerer book (known and memorized together, six copies), a
sorcerer that already knows Domination, a sorcerer-shaped book of class mage,
Aran's and the Zhentarim Mercenary's wizard books, the unchanged known-only
creatures, creatures and scripts already changed by another mod, other copy
counts and row layouts, filters already present, `SpellNoDec` and other targets,
missing IDS symbols, replacements at the wrong level, and each component of RR
alone. Local check, not part of the repository: RR v4.92's own five CREs and its
three BAF sources, compiled for both install orders against the reference
install's final IDS files with SR's spell files, in a disposable synthetic game.
The three creatures got the books above (Aran memorizes `SPWI507` ×4 and
`SPWI505`, the Zhentarim Mercenary `SPWI509` ×4 and `SPWI505`, known records
unchanged); `RR#SAW09` and `RR#ZAER` stayed byte for byte; both orders gave the
same files; a second pass was byte-exact; every script change stayed inside RR's
Chaos blocks.

Limits: no in-game check of the new spellbooks and casts yet. Creatures already
spawned in a save keep their old books. A level-five Waves of Fatigue copy that a
later mod deliberately prepared for these creatures, without any Chaos record,
cannot be told apart from RR's Chaos and becomes the replacement.
