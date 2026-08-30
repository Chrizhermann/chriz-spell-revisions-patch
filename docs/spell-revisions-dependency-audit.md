# Spell Revisions dependency audit

This audit records the dependency decisions behind the configurable Spell
Revisions catalog. It is pinned to upstream Spell Revisions `v4.21`, commit
`af1dedb6d211f86ad7a321d4080e46c748e8abac`.

The canonical import was derived from three reviewed, hash-gated artifacts:

- `task4-canonical-catalog-projection.json`:
  `d4a44a02d69fe76dc62c2b4d9e4f6dad43b00589a9dba0938f29fe0a73a1baee`
- `task4-dynamic-resolution-final-v2.json`:
  `83369c2540725cd69ea79497d5e80ae64c77325df8448f333e20142cee34fab0`
- `task4-import-blueprint.json`:
  `7b6e6043ed17b56ae9f62fb716e4dd586bfe7355d22ac4f4ccfc4cd3cada5835`

The imported catalog contains 321 public choices and 76 internal
infrastructure records. Its 498 active source spans, 1,625 active resources,
and component-zero resource graph pass strict catalog loading and close with
zero coverage issues. Migration remains deliberately closed until generated
installer parity is proven.

## Public dependency result

After mechanically inseparable changes were bundled, the 321 public choices
have no cross-choice hard dependencies and no conflicts: both `requires` and
`conflicts` contain zero directed edges. Turning off one public choice never
silently turns on another one.

The catalog does retain 624 directed `soft_requires` edges. A soft edge means
that a cross-effect is emitted only when both choices are enabled. If the
counterpart is disabled, the optional cross-effect is omitted; the edge does
not force that counterpart on. Examples include protections against optional
offensive spells and interactions between independently useful spell changes.

Shared implementation is not exposed as extra user choices. The resolver
derives 75 consumer-selected infrastructure records from enabled public
changes, plus one always-on metadata record. The infrastructure graph has 24
explicit internal dependency edges, and 1,014 reciprocal public-change /
processor links. Those relations ensure that tables, compatibility passes,
dynamic spell-reference rewriting, auxiliary resources, projectiles, and
post-processing follow the public selections that consume them.

## Atomic public choices

Sixteen public choices contain more than one catalog member. Each is one
atomic switch because the upstream implementation jointly relocates or
replaces spell slots, shares subordinate resources, or applies one coupled
system across the members. Offering the members independently would leave
partial relocations, stale compatibility data, or incomplete behavior.

| Public choice | Catalog members |
| --- | --- |
| `arcane.petrification` | `SPWI108`, `SPWI604`, `SPWI625` |
| `arcane.dimension_jump_relocation` | `SPWI109`, `SPWI402` |
| `arcane.detect_alignment_relocation` | `SPWI126`, `SPWI202` |
| `arcane.elemental_protection_progression` | `SPWI225`, `SPWI319`, `SPWI320`, `SPWI426`, `SPWI512`, `SPWI517`, `SPWI606`, `SPWI702`, `SPWI803` |
| `arcane.haste_slow` | `SPWI305`, `SPWI312`, `SPWI613` |
| `arcane.spell_deflection_progression` | `SPWI318`, `SPWI522`, `SPWI618`, `SPWI701` |
| `arcane.spell_shield_anti_magic` | `SPWI321`, `SPWI419`, `SPWI510`, `SPWI513`, `SPWI519`, `SPWI608`, `SPWI704`, `SPWI705`, `SPWI805`, `SPWI903` |
| `arcane.mestils_acid_sheath_relocation` | `SPWI403`, `SPWI526` |
| `arcane.level4.monster_summoning_iv_relocation` | `SPWI407`, `SPWI423` |
| `arcane.summon_nishruu_relocation` | `SPWI624`, `SPWI719` |
| `arcane.imprisonment_freedom` | `SPWI910`, `SPWI917` |
| `divine.cure_wounds_progression` | `SPPR103`, `SPPR215`, `SPPR315`, `SPPR401`, `SPPR502` |
| `divine.goodberry` | `SPPR118`, `SPPR207` |
| `divine.cause_wounds_progression` | `SPPR119`, `SPPR219`, `SPPR321`, `SPPR414`, `SPPR510` |
| `divine.insects_and_gust_of_wind` | `SPPR218`, `SPPR318`, `SPPR319`, `SPPR517`, `SPPR717` |
| `divine.elemental_protections` | `SPPR306`, `SPPR407`, `SPPR520`, `SPPR521`, `SPPR522`, `SPPR523` |

Roles such as `deprecated_slot`, `ai_deprecated_slot`, and
`game_compatibility_slot` are intentional members of the same semantic choice;
they are not additional changes that can safely be selected alone.

## Deferred source scopes

Seven source scopes are inventoried but intentionally excluded from public
selection and active generation. Deferral is fail-closed: the source remains
covered and cannot accidentally become an installable choice merely because a
nearby change is enabled.

| Deferred scope | Reason |
| --- | --- |
| `deferred.projectile.dvmainpr` | `DVMAINPR` is added unconditionally upstream, but no active component-zero shipped spell ability uses it. |
| `deferred.projectile.newbolt1` | No active component-zero shipped spell ability stores projectile `NEWBOLT1` (240). |
| `deferred.projectile.smllarnc` | No active component-zero shipped spell ability stores projectile `SMLLARNC` (216). |
| `deferred.special.demilich_soul_trap` | `SPIN788` is unconditional gameplay content with no reviewed public selection. |
| `deferred.special.demilich_howl` | `SPIN789` is unconditional gameplay content with no reviewed public selection. |
| `deferred.compat.p3_12m4_empty_item` | `P3-12M4.ITM` is unconditional content whose gameplay purpose has not been resolved. |
| `excluded.hardiness_spcl907` | The component-zero `SPCL907` Hardiness edit belongs to a separate future balance decision. |

## Hardiness boundary

Hardiness is not a public setting in this catalog. The
`excluded.hardiness_spcl907` scope records the upstream component-zero edit so
coverage cannot lose it, but it does not activate or generate that edit. The
author's custom Hardiness balance work is a later component and must be
designed together with upstream component 65 and Wish-Hardiness behavior. It
must not be inferred from, or folded into, the current Spell Revisions choices.

## Compatibility warning for partial installs

The default all-on selection preserves conventional Spell Revisions
expectations. A custom partial selection may not be understood by external
mods that test only whether component 0 or a historical marker is present and
then assume that every Spell Revisions spell and table entry exists. Review
compatibility before using partial selections in a large mod stack. Updated
integrations should consume the generated installed feature facts rather than
inferring the selected feature set from component presence alone.
