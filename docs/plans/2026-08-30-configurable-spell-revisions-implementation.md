# Configurable Spell Revisions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:executing-plans to implement this plan task-by-task.

**Goal:** Build a generated, dependency-aware Spell Revisions catalog whose editable config can enable or disable every supported semantic change while keeping the installer and both user-facing readmes synchronized with upstream v4.21.

**Architecture:** A reviewed JSON catalog is the sole inventory of public changes, source spans, owned resources, dependencies, and upstream provenance. Python tooling validates that catalog and generates the shipped WeiDU config/selection layer, a guarded main component, feature-fact metadata, Markdown, and an HTML readme section; release users need only WeiDU. The migration is fail-closed: component 0 continues using the known-good monolith until the catalog has complete executable coverage and all-on byte-parity, then switches atomically to the generated installer.

**Tech Stack:** Python 3.11 standard library, pytest, WeiDU 249, JSON, WeiDU TP2/TPA, synthetic Infinity Engine fixtures

---

Implementation must use @bg-modding, @weidu-modding, @test-driven-development, and @verification-before-completion. Never run an installer against `C:\Games`; all WeiDU execution belongs in `tmp_path` fake games or `--nogame` harnesses. Keep Christopher's uncommitted Hardiness research out of this branch.

### Task 1: Catalog schema and provenance contract

**Files:**
- Create: `tools/sr_config/__init__.py`
- Create: `tools/sr_config/catalog.py`
- Create: `spell_rev/catalog/changes.json`
- Create: `tests/test_sr_catalog.py`

**Step 1: Write the failing schema tests**

Test that the seed catalog loads through `load_catalog()`, has schema version 1, records upstream tag `v4.21` and commit `af1dedb6d211f86ad7a321d4080e46c748e8abac`, rejects unknown fields, duplicate IDs/settings, invalid tri-state defaults, missing parent groups, dependency cycles, and dependencies on unknown IDs. Use tiny dictionaries passed to `Catalog.from_dict()` for each negative case so failures identify one invariant.

```python
def test_catalog_provenance_is_pinned() -> None:
    catalog = load_catalog(ROOT / "spell_rev/catalog/changes.json")
    assert catalog.schema_version == 1
    assert catalog.upstream.tag == "v4.21"
    assert catalog.upstream.commit == "af1dedb6d211f86ad7a321d4080e46c748e8abac"

def test_dependency_cycle_is_rejected() -> None:
    raw = minimal_catalog(changes=[change("a", requires=["b"]), change("b", requires=["a"])])
    with pytest.raises(CatalogError, match=r"dependency cycle: a -> b -> a"):
        Catalog.from_dict(raw)
```

**Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_sr_catalog.py -q`

Expected: collection fails because `tools.sr_config.catalog` does not exist.

**Step 3: Implement the minimal strict model**

Use frozen dataclasses for `Upstream`, `Group`, `SourceSpan`, `ResourceOwnership`, `Change`, `Infrastructure`, and `Catalog`. Parse JSON with `json.loads`, compare each mapping's keys against an explicit allowed/required set, normalize IDs only for comparison, and preserve source order for generated documentation. Raise `CatalogError` with a path such as `changes[3].requires[0]` in every validation message. Implement deterministic DFS cycle detection.

The initial `changes.json` contains groups and provenance but an empty `changes` array; no pretend spell inventory is permitted. Set `migration.complete` to `false` and record `installer_source` as `spell_rev/components/main_component.tpa`.

**Step 4: Run focused and existing tests**

Run: `$env:WEIDU='C:\src\private\chriz-bg-rebalance\weidu.exe'; python -m pytest tests/test_sr_catalog.py tests/test_prot_refresh_target.py -q`

Expected: all tests pass (the pre-existing suite currently contributes 30 passing cases).

**Step 5: Commit**

```powershell
git add tools/sr_config/__init__.py tools/sr_config/catalog.py spell_rev/catalog/changes.json tests/test_sr_catalog.py
git commit -m "feat: define strict Spell Revisions catalog schema"
```

### Task 2: Deterministic source inventory and anchor validation

**Files:**
- Modify: `.gitignore`
- Create: `tools/sr_config/__main__.py`
- Create: `tools/sr_config/inventory.py`
- Create: `tools/sr_config/source.py`
- Create: `tools/sr_config/resources.py`
- Create: `tests/fixtures/sr_config/main_component_sample.tpa`
- Create: `tests/test_sr_inventory.py`
- Create: `tests/test_sr_resource_edges.py`
- Modify: `spell_rev/catalog/changes.json`

**Step 1: Write failing lexer and coverage tests**

The lexer must preserve every byte and classify top-level executable statements. Cover multiline `COPY`, paired source/destination arguments, `COPY_EXISTING`, `ADD_SPELL`, `INCLUDE`, `LAF`/`LAM`, `ACTION_IF`, comments, and nested patch bodies. A source span is selected by exact start/end anchors plus SHA-256 of the bytes between them. Separately, a deterministic binary scanner must enumerate resource references from shipped SPL/ITM/EFF/CRE files, including opcode resource fields and subordinate spell/item/creature/script references needed for ownership analysis.

```python
def test_anchor_hash_rejects_upstream_drift(tmp_path: Path) -> None:
    path = tmp_path / "main.tpa"
    path.write_text("// A\nCOPY ~a.spl~ ~override~\n// B\n", encoding="utf-8")
    span = SourceSpan(path="main.tpa", start="// A", end="// B", sha256="0" * 64)
    with pytest.raises(SourceError, match="anchor hash changed"):
        resolve_span(tmp_path, span)

def test_inventory_reconstructs_input_byte_exact() -> None:
    source = FIXTURE.read_bytes()
    assert b"".join(node.raw for node in inventory(FIXTURE)) == source

def test_binary_edges_include_dynamic_spell_reference() -> None:
    edges = scan_resource_edges(ROOT / "spell_rev/sppr2##/sppr210.spl")
    assert any(edge.target.upper() == "SPWI225" for edge in edges)
```

**Step 2: Run and verify RED**

Run: `python -m pytest tests/test_sr_inventory.py tests/test_sr_resource_edges.py -q`

Expected: import failure for the missing inventory module.

**Step 3: Implement lossless inventory and exact anchors**

Write a small state machine that tracks WeiDU comments, quoted strings, `BEGIN`/`END`, and command starts. It may classify an unrecognized statement as `unknown`, but may never discard it. `resolve_span()` must require exactly one start and one later end anchor and verify LF-normalized SHA-256 while returning original bytes for generation. Reuse the repository's Infinity Engine format helpers where sound, but add explicit bounds checks and resource-field provenance to the binary scanner; malformed files fail with the path and offset rather than being silently skipped.

**Step 4: Generate and review the baseline report**

Add `python -m tools.sr_config inventory --json build/sr-inventory.json` as a read-only report command. The report must list every executable node in `main_component.tpa` and referenced component-0 libraries with file, line, command, nearest section comments, and resource operands, followed by all binary resource edges with source file, field/opcode, target resref, and local/external classification. `build/` remains ignored and must not be committed.

Run: `python -m tools.sr_config inventory --json build/sr-inventory.json`

Expected: exit 0; report counts are deterministic across two runs.

**Step 5: Commit**

```powershell
git add tools/sr_config/inventory.py tools/sr_config/source.py tools/sr_config/resources.py tests/fixtures/sr_config/main_component_sample.tpa tests/test_sr_inventory.py tests/test_sr_resource_edges.py spell_rev/catalog/changes.json
git commit -m "feat: inventory configurable WeiDU source losslessly"
```

### Task 3: Tri-state resolver and synchronized config/docs generator

**Files:**
- Create: `tools/sr_config/resolve.py`
- Create: `tools/sr_config/generate.py`
- Create: `tools/sr_config/text.py`
- Modify: `tools/sr_config/__main__.py`
- Modify: `tools/sr_config/catalog.py`
- Modify: `tests/test_sr_catalog.py`
- Create: `tests/test_sr_resolve.py`
- Create: `tests/test_sr_generate.py`
- Generate: `spell_rev/settings.ini`
- Generate: `docs/spell-revisions-change-catalog.md`
- Modify/generated region: `spell_rev/readme-spell_rev.html`

**Clarified implementation contract:**

- Parse configuration assignments as an ordered sequence and reject unknown or duplicate names
  case-insensitively before constructing a mapping. Aggregate independent validation errors in a
  deterministic order. Booleans are not valid integers.
- A leaf value of `0` is the only explicit veto against hard-dependency or multi-record atomic
  closure. An inherited `0` from a group may be overridden by closure; otherwise enabling one
  leaf under a disabled tradition could not safely bring in its required leaves. A contradictory
  explicit leaf veto is an error. Apply conflicts after transitive hard/atomic closure. Soft edges
  never force enablement or fail resolution, but expose whether both endpoints are active.
- An explicitly enabled leaf that is unavailable on the selected game is an error; an inherited
  enablement resolves off. An active leaf whose hard/atomic requirement is unavailable is an
  error. Reject unknown games. Catalog game values use `all` or the supported installer/source
  vocabulary (`soa`, `tob`, `bgee`, `bg2ee`, `eet`, `iwdee`, `tutu`, `tutu_totsc`, `bgt`), with
  nonempty unique values and `all` mutually exclusive with named games.
- Every public leaf defaults to `-1`. Mechanically inseparable resources should normally be one
  public `Change`; multi-record `atomic_group` closure is a safety backstop, not an invitation to
  expose redundant switches.
- Resolve `name_ref` and `description_ref` against the current English `arcane.tra`, `divine.tra`,
  and `setup.tra`. Fail on missing, duplicate, malformed, or unterminated references rather than
  emitting raw `@123` tokens.
- The editable metadata contract is `sr_config_schema = 1` and
  `SPRINT sr_catalog_fingerprint ~<64 lowercase hex>~`; `install_tobex = 1` remains the first
  non-comment assignment. Fingerprint canonical semantic JSON so line-ending changes do not
  alter it. Keep metadata separate from catalog assignments when calling the resolver.
- Assign collision-free WeiDU flags by complete catalog order (`sr_feature_000001`, etc.); game
  filtering must not renumber them.
- The production HTML is ISO-8859-1 with CRLF and initially lacks generator markers. Bootstrap
  exactly one marker pair around the stale spell-overview region, retain exactly one
  `id="spell_changes"`, encode generated characters safely, and preserve every byte outside the
  markers. Missing, duplicate, or reversed markers after bootstrap are errors.
- Compute and validate all generated outputs before writing any of them. Preserve each target's
  existing newline convention. `--check` normalizes only for comparison where appropriate,
  writes nothing, and emits stable unified diffs.

**Step 1: Write failing resolution tests**

Cover the precedence leaf -> level -> tradition -> global, valid values `-1/0/1`, explicit dependency contradictions, automatic inherited dependency closure, atomic families, soft edges that do not force enablement, game applicability, unknown settings, duplicate settings, and aggregate error reporting. Define and test a collision-free WeiDU symbol encoding for dotted stable IDs (for example, a generated numeric index plus a comment mapping); never concatenate a raw dotted ID into a WeiDU variable name.

```python
def test_leaf_overrides_every_parent() -> None:
    values = {"sr_default": 0, "sr_arcane_default": 1,
              "sr_arcane_level_1_default": 0, "sr_wizard_magic_missile": 1}
    assert resolve(sample_catalog(), values).enabled("arcane.level1.magic_missile")

def test_explicitly_disabled_requirement_is_an_error() -> None:
    values = {"sr_default": 1, "sr_spell_shield": 1, "sr_antimagic_suite": 0}
    with pytest.raises(ConfigError, match="sr_spell_shield requires sr_antimagic_suite"):
        resolve(sample_catalog(), values)
```

**Step 2: Run and verify RED**

Run: `python -m pytest tests/test_sr_resolve.py tests/test_sr_generate.py -q`

Expected: missing resolver/generator modules.

**Step 3: Implement deterministic generation**

The config begins with existing `install_tobex = 1`, then schema/fingerprint, global/category/level defaults, and every leaf set to `-1`. Each generated key has an adjacent plain-language comment and stable ordering. Markdown and HTML show key, effective default, component, games, description, atomic family, hard dependencies, soft edges, and upstream provenance. Update only the HTML region between `<!-- SR_CONFIG_CATALOG_BEGIN -->` and `<!-- SR_CONFIG_CATALOG_END -->`; fail if either marker is missing or duplicated.

Expose:

```powershell
python -m tools.sr_config generate
python -m tools.sr_config generate --check
```

`--check` computes outputs in memory, emits a unified diff for stale files, and writes nothing.

**Step 4: Verify generated-file stability**

Run: `python -m tools.sr_config generate; git diff --exit-code -- spell_rev/settings.ini docs/spell-revisions-change-catalog.md spell_rev/readme-spell_rev.html` only after staging the intended generated outputs, then `python -m tools.sr_config generate --check`.

Expected: second generation has no diff and check exits 0.

**Step 5: Commit**

```powershell
git add tools/sr_config tests/test_sr_resolve.py tests/test_sr_generate.py spell_rev/settings.ini docs/spell-revisions-change-catalog.md spell_rev/readme-spell_rev.html
git commit -m "feat: generate synchronized SR config and change catalog"
```

### Task 4: Classify every upstream component-0 change and dependency

**Files:**
- Modify: `spell_rev/catalog/changes.json`
- Create: `docs/spell-revisions-dependency-audit.md`
- Modify: `tests/test_sr_catalog.py`
- Modify: `tests/test_sr_inventory.py`
- Modify: `tests/test_sr_resource_edges.py`

**Step 1: Tighten coverage tests before adding records**

Require every executable inventory node to be owned exactly once by a public change, derived infrastructure record, compatibility pass, or mandatory metadata record. Require every source-level and binary local resource reference to be classified as owned, atomic, hard, soft, shared, or external. Verify each public change has a current English name/description source and at least one source span or an explicit `documentation_only_reason`.

Run: `python -m pytest tests/test_sr_catalog.py tests/test_sr_inventory.py tests/test_sr_resource_edges.py -q`

Expected: FAIL listing all currently unclassified nodes; preserve this output in the commit message or implementation notes as the RED evidence.

**Step 2: Populate records in reviewable batches**

Classify and test one source section at a time in upstream order: shared substrate/projectiles, divine levels 1-7, arcane levels 1-9, specials/innates, compatibility branches, and global processors. Treat parent/subspells, scrolls, CRE/ITM/EFF/BCS assets, projectiles, and class/kit copies as one semantic bundle. Record these confirmed atomic systems explicitly: Cure Wounds progression; Cause Wounds progression; divine elemental protections; Protection from Elemental Energy and subspells; Spell Deflection relocation; Haste/Slow; Flesh to Stone/Stone to Flesh/petrification; insects/Gust of Wind; Spell Shield/anti-magic suite; Imprisonment/Freedom; each summon and assets.

After each batch run the three focused test files and commit using messages such as `data: catalog divine level 1 SR changes`. Do not use a generated guess as reviewed dependency data.

**Step 3: Document evidence and unresolved compatibility edges**

For every hard/atomic/soft edge, cite source path and anchors in `docs/spell-revisions-dependency-audit.md`. Mark external-mod assumptions separately; do not turn them into internal dependencies. Include the known partial-install warning and exclude the custom Hardiness rebalance. Upstream component 65's `SPCL907`/`SPWISH12` pairing is documented for its future seam only.

**Step 4: Prove exhaustive coverage**

Run: `python -m tools.sr_config inventory --check-catalog`

Expected: exit 0, zero unknown nodes, zero multiply owned nodes, zero unclassified local references.

Run: `python -m tools.sr_config generate --check`

Expected: FAIL until regenerated; regenerate, review, rerun, then PASS.

### Task 5: Generate and test WeiDU preflight validation

**Files:**
- Generate: `spell_rev/generated/config_schema.tpa`
- Generate: `spell_rev/generated/selection.tpa`
- Create: `tests/weidu/sr_config_harness.tp2`
- Create: `tests/test_sr_weidu_config.py`
- Modify: `spell_rev/setup-spell_rev.tp2:8-14`

**Step 1: Write failing `--nogame` config tests**

Copy `settings.ini` to a temporary mod tree and run the public generated preflight. Cover untouched all-on defaults, all-off, each precedence level, invalid values, missing key, unknown assignment, duplicate assignment, stale schema/fingerprint, atomic contradiction, hard dependency contradiction, and multiple errors reported before the harness creates its mutation sentinel.

**Step 2: Run and verify RED**

Run: `$env:WEIDU='C:\src\private\chriz-bg-rebalance\weidu.exe'; python -m pytest tests/test_sr_weidu_config.py -q`

Expected: missing generated TPA/harness failure.

**Step 3: Generate a fail-closed component-0 preflight**

Keep the user-facing assignment syntax (`sr_wizard_magic_missile = -1`). The generated preflight reads the config text into a WeiDU patch buffer, strips comments/blank lines, verifies every assignment name against a generated allow-list, counts each required key exactly once, then `PATCH_INCLUDE`s it and validates each value. It computes resolved flags using the tested encoded/indexed WeiDU symbols and appends errors to one buffer; `FAIL` occurs before component source is included.

`ALWAYS` may load function and schema definitions only. Invoke strict editable-config parsing and validation inside component 0's install body immediately before the main component include. A malformed or stale config must not prevent uninstall/recovery or installation of independent components 10, 20, 30, 55, 65, or 70. Add tests for those paths.

**Step 4: Parse-check and run all focused tests**

Run: `$env:WEIDU='C:\src\private\chriz-bg-rebalance\weidu.exe'; python -m pytest tests/test_sr_weidu_config.py -q`

Expected: all pass.

Run: `& $env:WEIDU --nogame --parse-check TPA spell_rev/generated/config_schema.tpa`

Expected: exit 0.

**Step 5: Commit**

```powershell
git add spell_rev/generated spell_rev/setup-spell_rev.tp2 tests/weidu/sr_config_harness.tp2 tests/test_sr_weidu_config.py
git commit -m "feat: validate SR selections before installation"
```

### Task 6: Freeze the legacy oracle, compile guarded component 0, and publish feature facts

**Files:**
- Modify: `tools/sr_config/generate.py`
- Generate: `spell_rev/generated/main_component.tpa`
- Generate: `spell_rev/generated/feature_facts.tpa`
- Create: `tests/fixtures/sr_config/guarded_source_sample.tpa`
- Create: `tests/fixtures/sr_config/pre_config_all_on_manifest.json`
- Create: `tests/test_sr_guard_generation.py`
- Create: `tests/weidu/sr_guard_harness.tp2`
- Create: `tests/test_sr_guard_weidu.py`

**Step 1: Freeze the pre-configuration oracle from commit `89b4701`**

Before any selected variant of a live component-0 library is created, export commit `89b4701` into a disposable worktree, run the agreed synthetic-game fixture with WeiDU 249, and record a structured manifest of resource names/hashes, table contents, dynamic symbol mappings, and normalized TLK strings. Commit the manifest and a script/test that can reproduce it; do not copy the baseline monolith into a second maintained source file. The fixture must cover dynamic spells, IDS, HIDESPL, Detectable Spells, projectiles, a summon, the protection refresh fix, and safely modeled compatibility branches.

**Step 2: Write failing byte-preservation and guard tests**

On the small fixture, assert all-on strips only generated guard scaffolding and reconstructs the source command stream byte-for-byte; all-off executes only mandatory metadata; enabled records keep source order; discontiguous spans for one atomic bundle share one encoded/indexed resolved flag; unknown/uncovered spans make generation fail.

**Step 3: Run and verify RED**

Run: `python -m pytest tests/test_sr_guard_generation.py tests/test_sr_guard_weidu.py -q`

Expected: guarded output is absent.

**Step 4: Implement the compiler**

Generate comments containing catalog ID, upstream anchor, source hash, and its collision-tested WeiDU flag mapping, followed by `ACTION_IF (sr_feature_0001)`-style guards around owned spans. Derived infrastructure uses a generated OR of its consumers. Never reorder original source bytes. Generate a feature-facts writer containing catalog schema/fingerprint, upstream commit, game, and every resolved public flag. Write installed facts under `weidu_external/data/spell_rev/installed_features.tpa`; optional components must read this persisted file, never the editable config.

**Step 5: Keep the migration gate closed and verify**

While `migration.complete` is false, `setup-spell_rev.tp2` must still include `spell_rev/components/main_component.tpa`; tests must assert the generated component is reachable only through its dedicated harness. Run generator check and both focused test files. Commit: `feat: generate guarded SR component and feature facts`.

### Task 7: Generate parallel selection-aware registries and global processors

**Files:**
- Modify: `tools/sr_config/generate.py`
- Generate from, but do not modify: `spell_rev/generated/lib/manage_add_spell_references.tpa`
- Generate: `spell_rev/generated/lib/ds_sr_extra.2da`
- Generate: `spell_rev/generated/lib/hidespl_patch.2da`
- Generate: `spell_rev/generated/lib/d5_set_spell_schools.tpa`
- Generate: `spell_rev/generated/lib/handle_spell_flags.tph`
- Generate: `spell_rev/generated/lib/refresh_non_stacking.tpa`
- Generate: selected variants of secondary-type/immunity/anti-magic libraries identified by Task 4
- Create: `tests/test_sr_selected_registries.py`
- Create: `tests/weidu/sr_selected_registries.tp2`

**Step 1: Write failing selected-registry tests**

Use two dynamic spell fixtures and one disabled parent/subspell family. The harness must include only generated parallel paths. Assert only enabled spells receive `ADD_SPELL`/`SPELL.IDS`, only their rows reach HIDESPL and Detectable Spells, school/flag/refresh passes touch selected resources, and no `dvpr*`/`dvwi*` reference survives. Add a soft-edge case where disabling an offensive spell removes its cross-protection effect without enabling it.

**Step 2: Run and verify RED**

Run: `$env:WEIDU='C:\src\private\chriz-bg-rebalance\weidu.exe'; python -m pytest tests/test_sr_selected_registries.py -q`

Expected: generated variants are absent or still include disabled resources.

**Step 3: Route the generated path through selected registries**

Generate one registry from resolved catalog facts and make all generated component-0 post-passes consume it. Rewrite generated `INCLUDE` targets in `generated/main_component.tpa`; do not edit the live upstream-input libraries. The generated prepass corresponding to `ASSIGN_TEMP_NAMES_FOR_NEW_SPELL_REFERENCES` mutates only assets owned by selected bundles; the final pass asserts no selected output contains unresolved temporary names. Preserve the existing recipient-target refresh fix in its generated variant and add its three spells to the relevant selected processor record.

**Step 4: Verify representative selection matrices**

Run the generated harness for all-on, all-off, every hard edge, every atomic family, and deterministic pairwise selections emitted by the Python resolver. Expected: all pass and source game KEY/BIFF/TLK hashes remain unchanged. Also assert the production TP2 and live upstream-input libraries are byte-identical to their pre-task versions.

**Step 5: Commit in processor-sized slices**

Use separate commits for dynamic `ADD_SPELL`, table registries, and effect post-processors. Do not combine an unexplained failing processor with another slice.

### Task 8: Prove the generated path and optional-component variants before switching

**Files:**
- Generate: `spell_rev/generated/components/celestials.tpa`
- Generate: `spell_rev/generated/components/mirror_image_vs_aoe.tpa`
- Generate: `spell_rev/generated/components/nwn_spell_deflection.tpa`
- Generate: `spell_rev/generated/components/fix_divine_spellbooks.tpa`
- Generate: `spell_rev/generated/components/fix_arcane_spellbooks.tpa`
- Generate: `spell_rev/generated/lib/kreso_hla.tph`
- Create: `tests/weidu/sr_generated_main_harness.tp2`
- Create: `tests/test_sr_main_integration.py`
- Create: `tests/test_sr_optional_components.py`

**Step 1: Write generated-path integration tests while production remains legacy**

The dedicated harness loads `generated/main_component.tpa` and generated optional variants directly. Assert generated all-on equals `pre_config_all_on_manifest.json` byte-for-byte except documented nondeterministic TLK indices, which are compared structurally. Assert all-off differs from the no-SR baseline only by catalog/version/feature-fact metadata. Test every singleton closure and invalid hard edge, install/uninstall/config-change/reinstall/final byte-exact restore, and package inclusion.

For components 10, 20, and 55, test both available and absent relevant facts. For component 60, verify only actually selected relocations/additions are written into NPC spellbooks. Component 30 remains independent. The generated component-65 variant keeps Whirlwind separate internally from the existing upstream Hardiness/Wish pair without adding Christopher's future balance choice. Component 70 remains independent.

**Step 2: Run and verify RED through the dedicated harness**

Run: `$env:WEIDU='C:\src\private\chriz-bg-rebalance\weidu.exe'; python -m pytest tests/test_sr_main_integration.py tests/test_sr_optional_components.py -q`

Expected: failures identify missing generated-path behavior; production `setup-spell_rev.tp2` still references the legacy files.

**Step 3: Implement only generated optional variants and close every gap**

Load persisted feature facts at the start of selection-dependent generated variants and emit an actionable skip/error when a required resource is absent. Iterate until catalog coverage, all-on parity, all-off isolation, dependency matrices, optional-component matrices, and uninstall restoration all pass through the harness.

**Step 4: Prove the migration gate is ready but closed**

Run generator check, catalog coverage, Tasks 5-8 tests, and the existing refresh suite. Expected: all pass. Assert `migration.complete` remains false and the production TP2 still includes the legacy monolith. Commit: `test: prove generated SR installer parity`.

### Task 9: Open the production migration gate atomically

**Files:**
- Modify: `spell_rev/catalog/changes.json` (`migration.complete` only)
- Modify: `spell_rev/setup-spell_rev.tp2:80-209`
- Regenerate: `spell_rev/generated/**`
- Modify: `tests/test_sr_main_integration.py`

**Step 1: Add a failing production-path smoke assertion**

Assert component 0 invokes config validation and the generated main include, components 10/20/55/60 use their generated selection-aware variants, component 65 uses its generated internally split variant, and components 30/70 remain independent. The pre-switch test must fail only because the gate is still closed.

**Step 2: Switch only after the pre-switch suite is green**

Set `migration.complete` true, regenerate, and update TP2 includes atomically. Keep the unmodified upstream monolith and libraries as generator inputs and sync references. Do not move strict editable-config validation into `ALWAYS`.

**Step 3: Run post-switch verification without accepting a new RED phase**

Run the production smoke assertion, all generated-path integration tests, and full pytest immediately. Expected: all pass on the first production switch; if not, revert the gate/include commit while diagnosing in the parallel harness.

**Step 4: Commit**

Commit: `feat: install dependency-aware SR selections`.

### Task 10: Upstream drift enforcement, packaging, and user guidance

**Files:**
- Create: `.github/workflows/test.yml`
- Modify: `.github/workflows/check-upstream.yml`
- Modify: `README.md`
- Modify: `package_mod.sh`
- Modify: `package_mod.bat`
- Modify: `tests/test_sr_generate.py`

**Step 1: Write failing workflow/package assertions**

Test that CI runs `python -m tools.sr_config generate --check`, catalog coverage, pytest with WeiDU 249+, and package-content validation. Test package manifests include `spell_rev/settings.ini`, generated TPA files, `docs/spell-revisions-change-catalog.md`, and `spell_rev/readme-spell_rev.html`.

**Step 2: Update generated and hand-written documentation**

The root README must explain the fork delta, default-all-on compatibility, the single settings workflow, schema-staleness failure, partial-install compatibility warning, feature-facts location, and links to the complete catalog/dependency audit. Remove or correct the stale instruction to comment raw `COPY` blocks. Preserve upstream credits and redistribution notice.

**Step 3: Make weekly upstream checks catalog-aware**

When upstream is ahead, the issue body must list commits and changed configurable paths and instruct maintainers to merge, update pinned provenance/anchors, classify new operations, regenerate, and run parity. CI must fail on source-anchor drift, unclassified nodes, or stale outputs.

**Step 4: Verify clean package contents**

Run generator check, inventory coverage, full pytest, and a dry package manifest test. Expected: all pass without touching a live game.

**Step 5: Commit**

Commit: `docs: ship synchronized SR configuration guidance`.

### Task 11: Independent review and final verification

**Files:**
- Review all changes since `89b4701`
- Update: `docs/plans/2026-08-30-configurable-spell-revisions-implementation.md.tasks.json`

**Step 1: Request specification review**

Have a fresh reviewer compare the implementation to the approved design and this plan. Resolve every correctness finding or document a genuinely out-of-scope item; do not waive catalog gaps, runtime config failures, or all-on parity.

**Step 2: Request code-quality and BG-modding review**

Review Python strictness/determinism, WeiDU transaction ordering, uninstall behavior, dynamic resource handling, external-mod compatibility language, and whether every dependency is evidenced rather than guessed.

**Step 3: Run final verification from a clean checkout state**

```powershell
$env:WEIDU='C:\src\private\chriz-bg-rebalance\weidu.exe'
python -m tools.sr_config generate --check
python -m tools.sr_config inventory --check-catalog
python -m pytest tests -q
git diff --check
git status --short
```

Expected: generator and inventory exit 0; pytest passes; `git diff --check` is silent; status contains only intentionally uncommitted files (normally none).

**Step 4: Record honest test boundaries**

State explicitly that synthetic/`--nogame` coverage is not live-game acceptance. If classic BG2, BG2EE/EET, or IWDEE branches could not be modeled completely, list each untested branch. Do not push, release, merge, or touch the separate dirty `chriz-bg-rebalance` checkout without new authorization.
