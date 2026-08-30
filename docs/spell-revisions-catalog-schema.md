# Spell Revisions catalog schema

`spell_rev/catalog/changes.json` is the reviewed source of truth for configurable
Spell Revisions behavior and component-zero coverage. The parser is strict: all
required fields must be present, unknown fields fail, identifiers and paths are
matched case-insensitively for uniqueness, and repository paths retain their
exact spelling for checkout validation.

The catalog remains at `schema_version: 1`. No populated catalog has shipped, so
these additions tighten the unshipped version rather than introducing a migration.

## Top-level coverage collections

The following arrays are required, including while empty:

- `component_zero_closure_roots`: exact supplemental entry spans for component
  zero that live outside `migration.installer_source`. Each record contains an
  Infrastructure `owner` plus a complete `source_span` that must exactly equal
  one of that owner's declared spans. Coverage inventories only those pinned
  bytes, then recursively follows only `INCLUDE`/`REINCLUDE` occurrences reached
  inside them. Bytes before, between, and after the roots stay inert, so later
  `setup-spell_rev.tp2` components cannot enter component-zero coverage merely
  because they share the setup file. Roots add traversal, not ownership: their
  existing Infrastructure span remains the sole ownership declaration. One
  literal, exact-case include of `migration.installer_source` directly inside a
  validated root is retained as an `owned` structural edge when that source node
  has only the declared root owner. The already traversed primary entry's many
  fine-grained owners are not aggregated for this exact edge. Dynamic, shifted,
  duplicated, case-drifted, outside-root, or owner-mismatched occurrences receive
  ordinary fail-closed classification.

- `dormant_resources`: package payloads that exist exactly in the repository but
  are not owned or reachable from component-zero source. Each record contains an
  exact `path` and a nonblank `reason`. Dormant payloads are not selectable and
  their outgoing binary edges are not executed by the coverage model.
- `deferred_source_scopes`: executable source deliberately withheld from public
  configuration pending a later decision. Each record has a globally unique `id`,
  a nonblank `reason`, at least one exact `source_span`, and an explicit `resources`
  array, which may be empty. Deferred scopes own coverage evidence but produce no
  setting, feature flag, or execution output. Any deferred scope keeps
  `migration.complete` false.
- `binary_edge_resolutions`: exact, reviewed exceptions for scanner edges that
  would otherwise appear local because every same-resref package payload is
  non-runtime (dormant or preprocessing-only `source` ownership).
  Every record names the exact `source`, byte `offset`, `field`, nullable `opcode`,
  `target`, ordered `expected_types`, complete ordered `shadowed_candidates`, the
  fixed classification `external`, and a nonblank `reason`.

A binary override identifies one physical scanner edge by source, offset, and
field. Coverage requires every other metadata value and the complete scanner
candidate list to match before any filtering, requires every candidate to be
either dormant and unowned or owned only as preprocessing `source`, and requires
the override to be consumed exactly once. A runtime-owned candidate can never be
hidden. A stale, mismatched, missing, or multiply consumed override fails
coverage without changing any other edge.

Deferred scopes normally own only closed internal edge islands. A local source or
binary edge that crosses between deferred ownership and an active change or
infrastructure record remains unclassified and fails coverage until the deferred
scope is resolved; dependency metadata cannot make that boundary executable. Two
narrow coverage-only exceptions are documented below: exact read-only preprocessing
inputs and literal include path classification. Neither exception makes deferred
behavior selectable or executable on its own.

## Resource ownership and runtime payloads

`ResourceOwnership.kind` has closed coverage semantics:

- `asset` and `resource` own exact package files that component zero may install
  or use at runtime.
- `source` owns an exact package file only as preprocessing/read input. It still
  participates in exact-existence, duplicate-ownership, dormant-conflict, source
  command, and dynamic read-only checks, but it is never a runtime-installed
  payload. A file owned only as `source` is skipped as a binary origin and is
  removed from local binary target candidates before dependency classification.
- `generated_resource` owns an output created during installation and therefore
  does not require a matching package file.
- `2da_write`, `ids_write`, `table_write`, and `tlk_write` describe non-file or
  shared-table mutations and do not claim package-file ownership.

Binary candidate filtering is narrow and fail-closed. Only exact dormant paths
and paths owned exclusively as `source` are removed. Any remaining unowned or
multiply owned live candidate still fails classification. If no runtime candidate
remains, coverage requires an exact `binary_edge_resolutions` entry; it never
assumes that an unknown game lookup is safe.

## Occurrence-specific source resolutions

Each `infrastructure.source_resolutions` record identifies one physical source
operand by exact `source`, `line`, `command`, `operand_index`, and `operand`.
The operand may be percent-dynamic or static. A matching declaration is consumed
exactly once and takes precedence over ordinary static lookup; a static operand
without a declaration retains ordinary resolution. Percent-dynamic operands
still require a declaration. A shifted line, changed command, wrong operand
index, changed literal, stale source path, or duplicate physical match fails
closed instead of falling back to a nearby declaration.
Exactly one primary resolution mode is required:

- ordered concrete `targets`;
- ordered `generated_owners`; or
- `external: true`.

The optional closed `access` field defaults to `dependency`. Dependency access
retains the normal owner-relation checks for each resolved target. Explicit
`read_only` access is permitted only with concrete `targets`: every target must
exist with exact path spelling and normally have exactly one non-deferred
component-zero Change or Infrastructure owner (including `kind: source`
ownership). A target may instead have exactly one ownership hit when that hit is
the explicit `resources[]` declaration of one deferred scope with kind `asset` or
`resource`. Deferred source-span/path ownership, `source`, generated, unowned,
multiply owned, and active-plus-deferred targets remain invalid. Each accepted
edge is reported only as `read_only`, and the resolution owner must still be
reciprocal with the exact source occurrence. These complete inspected/read target
lists do not infer public processors, infrastructure consumers, change
dependencies, or `infrastructure_requires` edges. Preprocessing may read and
rewrite the same package bytes before installation, but this exact exception
creates no runtime-install or selection activation for the deferred scope.

A separate path-level exception applies only to literal `INCLUDE`/`REINCLUDE`.
When the included file has deferred ownership plus exactly one distinct active
Change or Infrastructure owner, and that active owner is the source occurrence's
sole owner, deferred hits are ignored only for classifying that include path.
Every node in the included file remains inventoried and must retain unique source
span ownership, including deferred nodes. Dynamic includes, COPY/LAF/binary
references, different or multiple active owners, and deferred-only targets do not
receive this filtering.

An external resolution may additionally list `internal_generated_owners` as
supplemental provenance for an occurrence whose runtime lookup is primarily
game-owned but can encounter internal `ADD_SPELL` outputs. This list is not a
fourth primary mode and does not expand the external lookup into resource-level
coverage edges. Every supplemental owner must be an executable component-zero
Change or Infrastructure record, declare at least one `generated_resource`, and
be reciprocal with the resolution-owner Infrastructure. Reciprocity means either
the same Infrastructure record or both sides of a Change processor/Infrastructure
consumer pair. A one-way `infrastructure_requires` edge is not reciprocity;
deferred, stale, resource-less, and unrelated owners fail coverage.

`LAF CREATE_SPELL STR_VAR spell=~...~ END` has one conservative special role:
the exact `spell` argument is a generated output, not a source dependency. The
output itself emits no dependency edge. A later `COPY_EXISTING` of `<spell>.spl`
is classified normally through the owning record's exact `generated_resource`.
Other action functions and other `STR_VAR` names keep their ordinary argument
semantics.

## Infrastructure

Every infrastructure record explicitly declares:

- `activation: consumer_selected` for derived or compatibility work that runs only
  for its selected public consumers; or
- `activation: always` for `category: mandatory_metadata` only.

`always` and `mandatory_metadata` imply each other. Gameplay, compatibility, and
derived infrastructure cannot use unconditional activation.

`infrastructure_requires` is an explicit array of infrastructure IDs. References
must be known, unique, non-self, and acyclic. Public `change.processors` and
`infrastructure.consumers` describe the same edge and must agree in both directions.
Infrastructure records and all classification collections are documented in the
generated Markdown and HTML catalogs, but only groups and public leaf changes are
emitted to `spell_rev/settings.ini`.

## Contributor checks

After editing the catalog, run:

```powershell
python -m pytest -q
python -m tools.sr_config inventory --check-catalog
python -m tools.sr_config generate
python -m tools.sr_config generate --check
git diff --check
```

Do not set `migration.complete` until every component-zero source node and resource
is classified, all deferred scopes are resolved, and the later installer parity
gate is satisfied.
