# Spell Revisions catalog schema

`spell_rev/catalog/changes.json` is the reviewed source of truth for configurable
Spell Revisions behavior and component-zero coverage. The parser is strict: all
required fields must be present, unknown fields fail, identifiers and paths are
matched case-insensitively for uniqueness, and repository paths retain their
exact spelling for checkout validation.

The catalog remains at `schema_version: 1`. No populated catalog has shipped, so
these additions tighten the unshipped version rather than introducing a migration.

## Top-level classification collections

The following arrays are required, including while empty:

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
  would otherwise appear local because a same-resref package payload is dormant.
  Every record names the exact `source`, byte `offset`, `field`, nullable `opcode`,
  `target`, ordered `expected_types`, complete ordered `shadowed_candidates`, the
  fixed classification `external`, and a nonblank `reason`.

A binary override identifies one physical scanner edge by source, offset, and
field. Coverage requires every other metadata value and the complete scanner
candidate list to match, requires every candidate to be dormant and unowned, and
requires the override to be consumed exactly once. A stale, mismatched, missing,
or multiply consumed override fails coverage without changing any other edge.

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
