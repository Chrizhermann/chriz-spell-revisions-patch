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
