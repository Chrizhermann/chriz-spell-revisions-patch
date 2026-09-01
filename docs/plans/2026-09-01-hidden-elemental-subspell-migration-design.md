# Design: Migrate hidden elemental-protection subspell grants into component 60

Date: 2026-09-01
Status: implementation correction in progress; **unreleased**
Release gate: automated synthetic coverage plus disposable live acceptance; no release or GitHub mutation is authorized by this design

## 1. Goal

Spell Revisions turns four ordinary wizard protections into the choices behind **Protection
from Elemental Energy**. The choice spells are hidden from normal spell selection, but old or
later-added joinable-NPC CRE files can still carry them as directly known or memorized spells.
That exposes implementation subspells alongside the intended selector container.

Move the migration into Spell Revisions component 60, **Update Spellbooks of Joinable NPCs**,
so the maintained fork owns the behavior and the standalone `SR_SUBSPELL_FIX` is unnecessary
for fresh installs of this fork.

The implementation must:

1. identify the effective selector and child spells semantically rather than assume physical
   `SPWI` slots;
2. replace only children proven to be both current selector choices and currently hidden;
3. replace those children with the effective parent in known and memorized lists of
   joinable-NPC CRE resources;
4. replace matching `AddSpecialAbility` grants in scripts referenced by joinable-NPC CREs so
   runtime join/XP paths grant the parent instead of reintroducing a child;
5. preserve existing parent entries, unrelated hidden spells, public selector choices, all
   non-target spellbook/script content, and non-joinable creatures;
6. be safe and byte-idempotent; and
7. run at the end of component 60, after its existing divine and arcane spellbook work.

## 2. Verified provenance and caveats

### 2.1 Historical standalone fix

The historical source was inspected read-only at:

`C:\src\private\chriz-bg-modpack\extras\snapshot\mods\SR_SUBSPELL_FIX\SR_SUBSPELL_FIX.tp2`

It records the original diagnosis and removes these hardcoded resources from joinable NPCs:

| Semantic child | Historical physical resref |
|---|---|
| `WIZARD_PROTECTION_FROM_FIRE` | `SPWI319` |
| `WIZARD_PROTECTION_FROM_COLD` | `SPWI320` |
| `WIZARD_PROTECTION_FROM_ELECTRICITY` | `SPWI512` |
| `WIZARD_PROTECTION_FROM_ACID` | `SPWI517` |

The snapshot says `NEERA6.CRE` and `NEERA7.CRE` were the affected joinable resources and
estimates roughly 170 affected non-joinable creatures. Those counts are historical evidence,
not a current-install oracle: they have not been re-established against every supported game,
NPC mod, or current effective resource set. Tests may use the named Neera variants as regression
fixtures, but production code must not special-case them.

The standalone fix is useful provenance, not implementation to transplant. It:

- hardcodes four physical spell slots;
- reads only the base `PDIALOG.2DA` rather than reusing SR's campaign-aware joinable-NPC array;
- does not prove that a candidate remains a choice of the current selector;
- does not intersect candidates with the effective `HIDESPL.2DA`; and
- cannot follow `ADD_SPELL` allocation or later resource drift.

The preserved narrative's broader claim that none of the children remains learnable is not used
as evidence here: current v4.21 source still copies `SCRL5T`, whose learn-spell effect references
`SPWI512`. That apparent stale-scroll inconsistency is outside this migration; the three-way
effective-resource proof below is authoritative for NPC cleanup.

### 2.2 Current Spell Revisions source

The current fork source verifies the underlying relationship:

- `spell_rev/components/main_component.tpa` installs the source file `spwi426.spl` with
  `ADD_SPELL ... WIZARD_PROTECTION_FROM_ELEMENTAL_ENERGY`. `ADD_SPELL` means the source
  filename is not a promise about the effective installed resref.
- The shipped container SPL has an opcode 214 selector effect whose resource is
  `DVWI426`.
- `spell_rev/spwi4##/dvwi426.2da` currently selects `SPWI319`, `SPWI320`, `SPWI512`, and
  `SPWI517`, each as a type-3 spell choice.
- `spell_rev/lib/hidespl_patch.2da` hides the four semantic child symbols listed above.
- Component 60 already builds `JOINABLE_NPC_ARRAY` with `spell_rev/lib/joinable_npcs.tpa`,
  including campaign-specific PDIALOG variants, and then runs the divine and arcane spellbook
  fixers.
- The arcane fixer removes disabled and opposed-school spells, but it does not consult the
  selector or `HIDESPL.2DA`; therefore it does not close this remnant path.

Disposable EET acceptance exposed a second delivery layer. `BG3300.BCS` naturally creates the
base `NEERA` resource and assigns the BG1 Neera script. That effective script contains a
32,000-XP join block with `AddSpecialAbility("SPWI319")`. Spawning `NEERA6` directly bypassed
the natural base-resource/XP path and therefore was not a valid acceptance substitute. The
runtime action must be migrated to the effective parent, not merely deleted.

This source evidence establishes the intended semantic relationship. It does not justify
freezing the current physical resrefs.

## 3. Ordering contract

Component 60 is an install-late component. It must run **after every mod component that adds
joinable-NPC CRE variants or changes an NPC's class, kit, or spellbook**. Running it earlier
cannot clean resources introduced or reassigned later.

There are two ordering requirements:

1. **Inter-mod order:** users and mod-manager manifests place component 60 after all NPC and
   class/kit assignment components. SR cannot reliably infer that the external stack is
   complete, so documentation is part of the release gate.
2. **Intra-component order:** the new cleanup call is the final spellbook transformation in
   component 60, after `fix_divine_spellbooks.tpa` and `fix_arcane_spellbooks.tpa`. Future
   component-60 work must not reintroduce a child after cleanup.

The cleanup is deliberately not mage-class-gated. A joinable resource may have been
reclassified by a kit or NPC mod while retaining a stale wizard spellbook. Joinable identity
and the three-way semantic proof below are the safety boundaries.

## 4. Effective-resource resolution

All comparisons are case-insensitive and normalized to eight-character resrefs. Duplicate
rows or symbols collapse to sets.

### 4.1 Semantic child set

Resolve these four symbols through the **effective** `SPELL.IDS` using WeiDU's spell-name
resolution, not literal slot arithmetic:

```text
WIZARD_PROTECTION_FROM_FIRE
WIZARD_PROTECTION_FROM_COLD
WIZARD_PROTECTION_FROM_ELECTRICITY
WIZARD_PROTECTION_FROM_ACID
```

Call the successfully resolved, existing spell resources set **S**. An unresolved or missing
symbol is warned about and excluded; it is never replaced with its historical resref.

### 4.2 Effective selector choices

Resolve `WIZARD_PROTECTION_FROM_ELEMENTAL_ENERGY` through the effective `SPELL.IDS`, require
its SPL to exist and have a structurally valid ability/effect table, then inspect ability
effects for opcode 214 (the engine's subspell-selector opcode).

The selector is valid only when its opcode-214 effects identify one unambiguous, existing 2DA
resource. Read that table by its header names, requiring a `ResRef` column and a valid `Type`
column. Collect the `ResRef` values from rows whose `Type` is `3` (spell choice) into set
**C**. Blank, `*`, malformed, non-spell, and missing-resource rows do not become candidates.

Do not assume `DVWI426.2DA`, its current row labels, row order, or current child resrefs. If
the container is absent, malformed, has no selector table, names multiple incompatible tables,
or the selected table cannot be validated, selector evidence is unavailable and the entire
cleanup is a warned no-op.

### 4.3 Effective hidden set

Read the effective `HIDESPL.2DA` and validate the layout expected for the active engine in the
same manner as SR's existing `hide_spells_from_array` path. A row belongs to set **H** only
when its row resref is valid and its active hidden flag is exactly enabled. A missing table,
unexpected width, malformed row, or ambiguous duplicate is not permission to delete.

Classic-engine installations without an active HIDESPL mechanism therefore take the safe
no-op path. The implementation must not infer hidden status from SR's shipped patch table
alone, because another component may have changed the effective HIDESPL state.

### 4.4 Exact removal set

The only resources eligible for removal are:

```text
R = S ∩ C ∩ H
```

Each member of **R** consequently has three independent facts:

1. it is one of the four intended elemental-protection child identities;
2. it is a choice of the effective Protection from Elemental Energy selector; and
3. it is hidden in the effective game state.

This intersection is intentionally stricter than either HIDESPL or selector membership alone:

- a hidden spell unrelated to this container is preserved;
- a selector choice that has become public is preserved;
- an old hardcoded slot no longer selected by the container is preserved; and
- a relocated child is removed when all three effective facts still agree.

## 5. CRE and script transformation

Reuse the existing `JOINABLE_NPC_ARRAY`; do not rescan PDIALOG independently. For each resource
in that array:

1. open the effective CRE with `COPY_EXISTING` and validate the CRE header sufficiently for
   WeiDU's spellbook operations;
2. record whether each resref in **R** occurs in known or memorized entries;
3. remove all matching child entries, add the resolved parent once to the known list when any
   child was known, and add one parent memorization for each removed child memorization;
4. use the parent SPL header's effective wizard level for the replacement records;
5. collect the effective script slots referenced by joinable-NPC CREs and, in those BCS files,
   replace each exact `AddSpecialAbility("<child>")` action with
   `AddSpecialAbility("<parent>")`;
6. let WeiDU maintain spellbook counts, memorization-info references, and later CRE offsets;
7. publish with `BUT_ONLY` so unaffected resources do not materialize or change bytes.

Identity is the spell resref only. A remnant known-spell entry can carry a stale or incorrect
stored level, so level and class metadata must not prevent migration. The replacement uses the
effective parent SPL level instead of inheriting stale child metadata.

The implementation must clear its working arrays at each invocation. Applying it twice in one
WeiDU process, reinstalling component 60, or running against an already-clean CRE must produce
the same bytes as one successful application. No random choice is involved.

Global evidence failures occur before CRE or BCS mutation. Container/table/HIDESPL validation
failure means zero writes. Individual child-symbol failures merely exclude that unproven
identity; they never activate a fallback slot. Warnings must name the missing evidence without
turning a safe no-op into an installation failure on otherwise supported games.

## 6. Test strategy and TDD order

Use the repository's real WeiDU 249 test plumbing. The `--nogame` layer exercises file-based
CRE patch behavior; the synthetic BG2EE fake game exercises `SPELL.IDS`, `COPY_EXISTING`,
game-resource resolution, component installation, and uninstall. No live game directory is a
test fixture.

The first production-changing test must be observed RED against the current component 60:
installation succeeds, but the hidden remnants remain. Implement only after that controlled
failure is established.

| Layer | Fixture / assertion |
|---|---|
| Fixture sanity | The generated CREs are valid and contain the declared known/memorized rows, including a child with a deliberately stale stored level. The container fixture has opcode 214 and a valid selector 2DA. |
| `--nogame` affected CRE | Replace every candidate in known and memorized lists with the effective parent while preserving unrelated spells, scripts, items, effects, and other header data. |
| `--nogame` idempotency | Run the production CRE patch twice; second output is byte-identical to first. Empty removal set and already-clean CRE are byte-identical no-ops. |
| Synthetic normal state | Joinable `NEERA6.CRE` and `NEERA7.CRE` lose all four proven children and gain the effective parent with the required known/memorized multiplicity. An unaffected joinable NPC is byte-identical. A non-joinable CRE containing the same remnants is byte-identical. |
| Synthetic runtime grant | A script referenced by a joinable Neera CRE replaces `AddSpecialAbility("<child>")` with the parent while retaining unrelated actions byte-semantically; an unrelated script remains byte-identical. |
| Synthetic effective drift | Relocate the container symbol, point opcode 214 at a renamed selector table, and relocate child symbols. Remove the relocated child in all three sets; preserve a hidden old slot not selected and a selected child whose HIDESPL flag is off. |
| Synthetic fail-closed cases | Missing container symbol/SPL, malformed opcode-214 structure, missing or malformed selector 2DA, and missing or malformed HIDESPL each leave all CRE bytes unchanged and emit the expected warning. |
| Repeated action execution | Invoke the production action twice in one fake-game component and compare its override tree byte-for-byte with a one-invocation game. This also catches stale WeiDU arrays. |
| Public install/uninstall | One affected CRE begins BIFF-only and one begins in override. Install component 60, assert the explicit publication allowlist and unchanged KEY/BIFF/TLK; uninstall, assert the BIFF-only publication disappears and the pre-existing override bytes return exactly. |
| Static gate | Parse-check every new or changed TP2/TPA and run the complete existing pytest suite. |

The synthetic KEY/BIFF writer needs resource types `CRE=1009` and `2DA=1012`. Do not copy
`SPELL.IDS` into override merely to resolve symbols; doing so can create an
`SPELL.IDS.INSTALLED` side file and weaken the publication assertions.

## 7. Migration boundaries

In scope:

- source-owned cleanup in SR component 60;
- known and memorized spell lists of install-time joinable-NPC CRE resources;
- semantic/effective resolution of the four elemental children;
- documentation that component 60 is a final NPC/class-assignment step; and
- automated install/uninstall restoration coverage.

Out of scope:

- modifying `C:\src\private\chriz-bg-modpack` or copying its standalone implementation;
- patching the roughly 170 historically reported non-joinable CREs;
- modifying `HIDESPL.2DA`, the selector SPL, or selector 2DA as part of component 60;
- cleaning unrelated hidden spells;
- editing save files or embedded party CREs;
- a separate tail mini-mod or live-patch component in this change; and
- commits, pushes, tags, releases, issues, pull requests, or other GitHub mutations.

The standalone `SR_SUBSPELL_FIX` becomes unnecessary only for installs that receive this fork's
updated component 60 at the correct late position. It is not automatically removed from an
existing WeiDU stack. An already-installed component 60 must be reinstalled through a separately
validated WeiDU workflow; that deployment is not authorized by this design.

Most importantly, CRE resources are snapshotted into saves when an NPC joins. Patching
`override/*.CRE` does not rewrite an already-joined party member's embedded CRE. This migration
prevents the problem for unjoined/future recruits; it is not save surgery.

## 8. Unreleased release gate

The change remains **unreleased** until every automated item and the disposable live acceptance
below is complete. Passing WeiDU/pytest fixtures is necessary evidence, not in-game acceptance.

### 8.1 Automated gate

- [x] Every new behavior was introduced test-first and observed failing for the intended reason.
- [x] New TP2/TPA files and the changed component source pass WeiDU 249 parse checks.
- [x] Normal, drift, fail-closed, unaffected, non-joinable, repeated-execution, and
      install/uninstall tests pass.
- [x] `python -m pytest tests` passes in full with no unexpected warnings or generated repository
      state.
- [x] Component 60 calls cleanup after both existing spellbook fixers.
- [x] README/install-order guidance and fork release notes identify the migration as unreleased
      and state the late-order requirement.
- [x] The separate modpack repository and every real game directory remain untouched.

### 8.2 Remaining disposable live acceptance

Use a disposable BG2EE or EET test installation, never the user's active game, and ensure the
game and loader are closed for every WeiDU operation.

1. Install the candidate SR main component, all intended NPC additions and class/kit assignments,
   then component 60 last.
2. Record the effective `SPELL.IDS` mappings, container SPL opcode-214 table, selector choices,
   HIDESPL rows, and the actual candidate set **R**.
3. Inspect each available unjoined Neera resource corresponding to the historical `NEERA6` /
   `NEERA7` cases. The direct child entries must be absent from known and memorized tables; the
   parent must replace them and unrelated legitimate spells must remain.
4. Inspect at least one unaffected joinable NPC and confirm its spellbook matches the expected
   pre-component state except for SR's already-established component-60 behavior.
5. From a fresh or pre-recruit state, recruit Beregost Neera through the natural area/script path.
   None of the four implementation children may appear independently, and Protection from
   Elemental Energy must appear where the join/XP script previously granted Protection from Fire.
6. Cast the parent from the affected NPC and confirm the selector still presents the four intended
   elements and each choice applies normally.
7. Record that an already-joined control is intentionally unchanged by resource patching; do not
   misreport that save-baked limitation as a failed install-time cleanup.

Only after this evidence is recorded should packaging, commit, push, tag, release, or an upstream
submission be considered, and each still requires separate user authorization. The source version
marker may identify this unreleased candidate without implying that the release gate passed.
