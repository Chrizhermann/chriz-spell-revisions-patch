# RR / Spell Revisions spell-semantics compatibility

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

Limits: synthetic fixtures only; no new authentic-install or in-game check. A
Waves of Fatigue reference that another mod added to these RR scripts before
this component, in a script without any Chaos reference, cannot be told apart
and becomes Chaos.
