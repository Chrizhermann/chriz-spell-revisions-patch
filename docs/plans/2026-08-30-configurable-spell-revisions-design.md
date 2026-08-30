# Design: Dependency-Aware Spell Revisions Configuration

**Status:** Approved 2026-08-30

**Upstream baseline:** Spell Revisions v4.21, commit
`af1dedb6d211f86ad7a321d4080e46c748e8abac`

## Goal

Ship an editable configuration file and synchronized documentation that let a player choose
which Spell Revisions changes to install without exposing combinations that leave missing
resources, stale spell-table entries, or partially applied systems.

The default configuration must reproduce the current fork's complete behavior: upstream
v4.21 with the fork's existing Protection from Magic Energy / the Elements / Energy refresh
fix. Existing optional WeiDU components remain separate because they have independent use and
installation-order semantics.

Christopher's proposed Hardiness rebalance is explicitly outside this implementation. This
design only creates a clean future seam for it.

## Evidence and constraints

Upstream component 0 is not a collection of independent `COPY` statements. Its 3,601-line
main implementation contains about 370 semantic spell or special-spell entries plus shared
projectiles, AI, dynamic spell allocation, compatibility patches, and global post-processing.

The following operations can affect a spell even when its primary `COPY` is skipped:

- `ADD_SPELL` allocation and temporary/final resource rewriting;
- `SPELL.IDS` aliases and relocations;
- `HIDESPL.2DA` changes;
- Detectable Spells rows;
- spell-school and EE spell-flag passes;
- refresh/non-stacking, secondary-type, immunity, and anti-magic systems;
- Item Revisions, Tutu, BG1EE, IWDEE, and other compatibility paths.

Player-visible switches therefore represent semantic change bundles, never raw files.
Every bundle owns its parent spell, scrolls, subordinate SPL/EFF/ITM/CRE/BCS resources,
projectiles and graphics, table entries, descriptions, and applicable post-processing.

The shipped HTML readme is not authoritative. It describes removed components and tells users
to comment `COPY` blocks out of the wrong source file. Upstream also states that the spell
documentation was not comprehensively updated after 4.18 beta. Current executable source and
English TRA strings are the authority for the catalog.

## Considered approaches

### Canonical catalog plus generated guarded installer — selected

A reviewed catalog is the only manually maintained inventory. A build-time generator emits
the user config, WeiDU selection/validation data, guarded installer implementation, Markdown
catalog, and installer-facing HTML. Python is a development dependency only; release users
receive generated WeiDU files.

This provides a single source of truth, fail-closed upstream synchronization, and strong
coverage of dependencies and documentation drift.

### Hand-written guards in the existing monolith — migration aid only

Adding guards in upstream order minimizes initial code movement, but hand-maintained guards
would eventually drift from binary resource dependencies and global post-passes. Generated,
catalog-owned guards may use this shape internally during migration; the catalog remains the
source of truth.

### Hundreds of WeiDU components or full-install-then-restore — rejected

Hundreds of components would make prompting, uninstall restacking, ordering, and global table
ownership unusable. Installing everything and restoring disabled resources cannot safely undo
dynamic `ADD_SPELL`, TLK, IDS, HIDESPL, SPLPROT, Detectable Spells, or shared-resource changes.

## User-facing configuration

The configuration uses stable semantic keys rather than source-template resrefs. Dynamic
spells can move to different final resrefs, and several template names deliberately collide
with pre-existing spell slots.

Settings are hierarchical and tri-state:

```weidu
sr_default = 1                    // 1 enabled, 0 disabled
sr_arcane_default = -1            // -1 inherits from its parent
sr_arcane_level_1_default = -1
sr_wizard_mage_armor = -1
```

Resolution order is leaf, spell-level group, arcane/divine group, then global default. Every
generated leaf defaults to inheritance and the global default is enabled, so an untouched
configuration installs all current changes.

The config has a schema/catalog version. Missing generated keys, unknown keys, invalid values,
or a stale schema fail before any gameplay resource, table, or TLK mutation. Silent migration
would make newly introduced upstream changes ambiguous for a customized installation.

## Catalog model

Each public change record contains at least:

- stable ID and display name;
- default and parent group;
- upstream component and source anchors/hashes;
- game/engine applicability;
- current TRA name and description references;
- owned resources and table writes;
- atomic bundle membership;
- hard dependencies and conflicts;
- soft or conditional resource edges;
- global processors that may operate on the bundle;
- upstream tag and commit provenance.

Shared infrastructure is cataloged but is not necessarily user-visible. The installer derives
the required infrastructure from the selected public changes.

Exact source anchors or block hashes make generation fail when upstream edits an owned block.
Every executable operation in configurable paths must be assigned to a public bundle, shared
substrate, compatibility pass, or mandatory correctness operation.

## Dependency policy

Mechanically inseparable behavior is exposed as one option. Confirmed examples include:

- each summon plus its CRE, scripts, items, effects, projectiles, and graphics;
- the Cure and Cause Wounds relocation progressions;
- divine elemental-protection relocations;
- Protection from Elemental Energy plus its hidden elemental subspells;
- Spell Deflection relocation;
- Haste and Slow;
- Flesh to Stone, Stone to Flesh, and petrification handling;
- the insect family plus Gust of Wind dispersal;
- Spell Shield and the anti-magic remover suite;
- Imprisonment and Freedom;
- Hardiness and Wish-Hardiness within upstream component 65;
- class/kit/innate variants that mirror a selected base spell.

If two changes remain independently meaningful but one requires the other, an explicitly
contradictory configuration fails with a precise pre-install message. The installer does not
silently enable a setting the user disabled.

Soft dependencies do not force unrelated gameplay changes on. For example, if an elemental
protection spell contains a protection against an optional new offensive spell, disabling the
offensive spell removes or omits that cross-protection edge rather than forcing the offensive
spell on.

## Installation flow

Component 0 performs these phases in upstream order:

1. Load catalog metadata and user settings.
2. Validate schema, values, anchors, applicability, atomic groups, and dependencies.
3. Compute resolved public choices, conditional edges, and shared substrate.
4. Allocate only selected dynamic spells and build a selected `new_spells` registry.
5. Install selected semantic bundles in upstream order.
6. Run selection-filtered IDS, HIDESPL, Detectable Spells, school, flag, refresh, secondary-type,
   and compatibility passes.
7. Assert that no temporary `dvpr*` or `dvwi*` spell reference remains.
8. Publish an installed feature-facts file containing the resolved catalog version and choices.

The installed feature-facts file is authoritative for later components. Reading the current
editable config would be incorrect if it changed after component 0 was installed.

## Existing optional components

Components 10, 20, 30, 55, 60, 65, and 70 retain their existing WeiDU identities and remain
explicit installer choices.

- Components 10, 20, and 55 currently infer that every SR resource exists when component 0 is
  present. They must consult feature facts or resource-specific predicates instead.
- Component 60 continues to require component 0 and must update NPC spellbooks from the actual
  selected relocations, additions, containers, and hidden spells.
- Component 65 keeps Whirlwind/Greater Whirlwind separate internally from the Hardiness and
  Wish-Hardiness pair, creating a future replacement seam without implementing a custom balance
  choice now.

Partial SR installations may be misunderstood by external mods that only inspect component 0
or the historical SR marker files. Default-all-on remains conventionally compatible. The
generated readme must warn that custom partial selections require compatibility review, while
the feature-facts file gives updated integrations an exact interface.

## Documentation and synchronization

The generator emits:

- the editable default config under `spell_rev/`;
- a complete Markdown change catalog;
- a corresponding installer-facing HTML section targeted by the TP2 `README` directive;
- generated WeiDU selection, validation, and feature-facts data.

Every documented option includes its stable key, effective default, owning component,
applicability, current SR description, atomic family, dependencies, and upstream provenance.
The root README links to the detailed catalog and describes the fork-specific delta.

CI runs the generator in check mode. A source change, catalog mismatch, undocumented key,
unclassified operation, stale generated artifact, or changed source anchor fails the build.
The weekly upstream workflow reports not only new commits but also whether configurable source
paths need catalog acknowledgement and regeneration.

## Failure behavior

Validation happens before mutations and reports all configuration errors in one actionable
summary when practical. Runtime generation is not attempted during installation.

The installer fails rather than guessing when it encounters:

- stale or incomplete configuration;
- contradictory hard dependencies;
- an unrecognized game applicability state;
- an expected source anchor or generated artifact mismatch;
- unresolved dynamic resource references;
- required optional-component assets absent from the installed feature set.

## Verification strategy

All implementation follows red-green-refactor TDD against disposable fixtures.

Static coverage:

- catalog schema, stable unique IDs, valid tri-state defaults, and acyclic public dependencies;
- exact source-anchor ownership and no unclassified executable blocks;
- config, Markdown, HTML, and generated WeiDU drift checks;
- resource-reference edges classified as atomic, hard, soft, shared, or external;
- no unresolved temporary dynamic-spell references.

WeiDU `--nogame` tests:

- config resolution and pre-mutation failures;
- individual bundle transforms and idempotency;
- selected dynamic spell allocation and reference rewriting.

Synthetic-game integration tests:

- default all-on parity with a frozen install from the pre-configuration fork;
- all-off isolation from the no-SR baseline except explicitly documented metadata;
- each singleton dependency closure and every invalid hard-dependency edge;
- representative soft-edge omission;
- components 10, 20, 55, and 60 with relevant changes enabled and disabled;
- install, uninstall, config change, reinstall, and final byte-exact restoration;
- EE, classic, and IWDEE applicability branches where the implementation differs;
- package contents include the config and both documentation forms.

An exhaustive `2^N` matrix is unnecessary. All-on, all-off, every dependency closure,
forbidden edges, atomic groups, and a deterministic pairwise set cover the meaningful state
space.

## Hardiness boundary

The existing research in `C:\src\private\chriz-bg-rebalance\research\06-sr-hardiness.md`
proposes 30% and 40% physical-resistance variants after upstream component 65. That work is
uncommitted and deliberately untouched.

When implemented later, the custom balance component must treat `SPCL907` and `SPWISH12` as
one option and explicitly decide whether SR's 20% elemental/magic riders remain. It depends on
upstream component 65 but not on the independent Whirlwind changes. Component 0's separate
secondary-type edit for `SPCL907` remains compatibility metadata, not the custom rebalance.
