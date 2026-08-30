# Spell Revisions dependency audit

This audit records the dependency decisions behind the configurable Spell
Revisions catalog. It is pinned to upstream Spell Revisions `v4.21`, commit
`af1dedb6d211f86ad7a321d4080e46c748e8abac`.

The canonical catalog and dependency evidence were derived from five reviewed,
hash-gated artifacts:

- `task4-canonical-catalog-projection.json`:
  `d4a44a02d69fe76dc62c2b4d9e4f6dad43b00589a9dba0938f29fe0a73a1baee`
- `task4-dynamic-resolution-final-v2.json`:
  `83369c2540725cd69ea79497d5e80ae64c77325df8448f333e20142cee34fab0`
- `task4-import-blueprint.json`:
  `7b6e6043ed17b56ae9f62fb716e4dd586bfe7355d22ac4f4ccfc4cd3cada5835`
- `task4-arcane-audit.json`:
  `68ec3fa8508ab8f6eee219ecfd25fe8cae962d7e9fb6d157fb66f6a937ae19c6`
- `task4-divine-audit.json`:
  `f761ee7215173a2da8ffbfa9bb1c580a50c66937e7c0328940198ef2592b7561`

The imported catalog contains 321 public choices and 79 internal
infrastructure records. Its 501 active source spans, 1,625 active resources,
and component-zero resource graph pass strict catalog loading and close with
zero coverage issues. Migration remains deliberately closed until generated
installer parity is proven.

## Public dependency result

After mechanically inseparable changes were bundled, the 321 public choices
have no cross-choice hard dependencies and no conflicts: both `requires` and
`conflicts` contain zero directed edges. Turning off one public choice never
silently turns on another one.

There is no hard-relation appendix because the final catalog contains
exactly zero directed hard dependency edges.

The catalog does retain 621 directed `soft_requires` edges. A soft edge means
that a cross-effect is emitted only when both choices are enabled. If the
counterpart is disabled, the optional cross-effect is omitted; the edge does
not force that counterpart on. Examples include protections against optional
offensive spells and interactions between independently useful spell changes.

Three relationships from the imported evidence are deliberately not soft
relations in the final catalog. Arcane Contagion casts the custom
`DVPR311D.SPL`, arcane Polymorph Other creates the custom `DVSQUIR.ITM`, and
the Summon Fiend glabrezu item conditionally casts the custom `SPWI609D.SPL`.
Opcodes 146, 111, and 232 dereference those payloads at runtime, so selecting
the source while omitting the target-owned copy would be unsafe. Each helper
resource and its exact source-copy span is instead consumer-selected shared
infrastructure; it is installed whenever any public choice that uses it is
enabled.

Shared implementation is not exposed as extra user choices. The resolver
derives 78 consumer-selected infrastructure records from enabled public
changes, plus one always-on metadata record. The infrastructure graph has 25
explicit internal dependency edges, and 1,023 reciprocal public-change /
processor links. Those relations ensure that tables, compatibility passes,
dynamic spell-reference rewriting, auxiliary resources, projectiles, and
post-processing follow the public selections that consume them.

## Atomic public choices

Sixteen public choices contain more than one catalog member. Each is one
atomic switch because the upstream implementation jointly relocates or
replaces spell slots, shares subordinate resources, or applies one coupled
system across the members. Offering the members independently would leave
partial relocations, stale compatibility data, or incomplete behavior.

<!-- BEGIN ATOMIC COMPOSITE EVIDENCE -->

| Public choice | Catalog members | Source evidence |
| --- | --- | --- |
| `arcane.petrification` | `SPWI108`, `SPWI604`, `SPWI625` | `spell_rev/components/main_component.tpa:lines 1547-1553 [sha256:1e1ea4bddfc3026c8e5f357a38486466aac0f759f4840c45fb12c0ac879d1393]`<br>`spell_rev/components/main_component.tpa:lines 2621-2627 [sha256:2e4125623d0bb986bec1145c9d5f0c826a740fbbe543215ba1fb77f6e1331086]`<br>`spell_rev/components/main_component.tpa:lines 2786-2793 [sha256:ebc9ee61ad3fb1a74b40ad8e801229b46d32f9e9307a287a4d3555b5a842b541]`<br>`spell_rev/lib/kreso_petrification.tph:lines 1-115 [sha256:742de0df55cfc82a7f09ba8b777fd9c8cca1d5085ae5c12e574962b0629eebef]` |
| `arcane.dimension_jump_relocation` | `SPWI109`, `SPWI402` | `spell_rev/components/main_component.tpa:lines 1777-1785 [sha256:d6d5a6242cbe4c7bcdf338239b34854a569af0066338bc6d4ac4d4aa061bd416]`<br>`spell_rev/components/main_component.tpa:lines 2148-2151 [sha256:0c29a4aa6509c65675b51be3225aedda309c36ad1ccc6cfcc9e1e3bff917c19b]` |
| `arcane.detect_alignment_relocation` | `SPWI126`, `SPWI202` | `spell_rev/components/main_component.tpa:lines 1786-1791 [sha256:a5cc212a1685f5efef0429f339dd9c1f19acda9f0c6ad3edc942933f43a5c09c]`<br>`spell_rev/components/main_component.tpa:lines 1799-1802 [sha256:1009d900afd13fed8f5aa1750c9eddcd0bdedfdcfd0e73f539a0d02b32ffd0ed]` |
| `arcane.elemental_protection_progression` | `SPWI225`, `SPWI319`, `SPWI320`, `SPWI426`, `SPWI512`, `SPWI517`, `SPWI606`, `SPWI702`, `SPWI803` | `spell_rev/components/main_component.tpa:lines 1939-1945 [sha256:3c9451a932cabcda8e48b07d99d6c0c7d19e6364b4808a22331f4a20ac324549]`<br>`spell_rev/components/main_component.tpa:lines 2087-2091 [sha256:cb5d8bc11e811d14805fd7abe771c17b009daffff585a50c58c06482682f19b8]`<br>`spell_rev/components/main_component.tpa:lines 2092-2096 [sha256:55315f7c60f170df1de5f5077a2e086b097d4aa65b9f4210acc9c4bdad70c17d]`<br>`spell_rev/components/main_component.tpa:lines 2334-2343 [sha256:f1097e49000b537df02eead5ae3cd5f4c4a45275c0fb3fba6a0fd9d1ad9409a4]`<br>`spell_rev/components/main_component.tpa:lines 2475-2480 [sha256:fb0ebec47d8f773b72d38aaf362a4bf70f3f1b104aedae35bc313bc19dea9bc4]`<br>`spell_rev/components/main_component.tpa:lines 2506-2510 [sha256:182d07cf764f97edfda9f60300069439458998957aa9f473cc7b1e45f1ca608b]`<br>`spell_rev/components/main_component.tpa:lines 2637-2641 [sha256:a69cf15dce6cafc5aef24d9e45b08d0d1b7d4967de3b4bd91571e969707c0c6f]`<br>`spell_rev/components/main_component.tpa:lines 2824-2828 [sha256:73da73a15bef6017cb0c4ec4ecfe0ada989b8691ea58850a9c971fcabf83cee4]`<br>`spell_rev/components/main_component.tpa:lines 3031-3035 [sha256:1cec0bafccdc008a971611b61ef9f860c52254e7be0e353d8c56fc3f5fa89c0a]` |
| `arcane.haste_slow` | `SPWI305`, `SPWI312`, `SPWI613` | `spell_rev/components/main_component.tpa:lines 1999-2004 [sha256:3a9acd87b3eec32c12e79666809bfd868b25b22bf4b1861fc963b0d88b260225]`<br>`spell_rev/components/main_component.tpa:lines 2052-2056 [sha256:970c34a33ac87b8f101fc1cf34eb6e6567de6193abd25167128b7783630bb444]`<br>`spell_rev/components/main_component.tpa:lines 2670-2674 [sha256:5724de1ced7aca5de09cd0b3b238723de98a7a6a87021e3e47264167689c8425]`<br>`spell_rev/components/main_component.tpa:lines 278-279 [sha256:e8537fa735294da271f7b428e6d8b2b77d3a68f164760e281764166d80c16b73]`<br>`spell_rev/lib/kreso_haste_slow.tph:lines 1-235 [sha256:5a17b097d00096b1c13fc5c9e1dd9a795c26f75fc77620410a6deb5672fa9929]` |
| `arcane.spell_deflection_progression` | `SPWI318`, `SPWI522`, `SPWI618`, `SPWI701` | `spell_rev/components/main_component.tpa:lines 2082-2086 [sha256:1ccb913d31ada7865ce49c462daf8664b381029bc9544541ebad42360b2db648]`<br>`spell_rev/components/main_component.tpa:lines 2545-2555 [sha256:22abd5ccf1681fb145f8de49a1360ad7ee0f9bb701ced8b30c8293d9380dad06]`<br>`spell_rev/components/main_component.tpa:lines 2703-2709 [sha256:750632876dabb5d7e39b7ee6aed817576f77625dedddb4bbee58d72d4dfc9a25]`<br>`spell_rev/components/main_component.tpa:lines 2813-2823 [sha256:acd6fda74fb1f4cb24e1d9ebedc392145836d192968ac2892983c27303670146]` |
| `arcane.spell_shield_anti_magic` | `SPWI321`, `SPWI419`, `SPWI510`, `SPWI513`, `SPWI519`, `SPWI608`, `SPWI704`, `SPWI705`, `SPWI805`, `SPWI903` | `spell_rev/components/main_component.tpa:lines 2097-2103 [sha256:c3f948a6be0c6c4ee9e4f626e332a6bef7abb4c9c9fe5ac7a4e225d99d7465ff]`<br>`spell_rev/components/main_component.tpa:lines 2291-2295 [sha256:62865f0f5e97172c4cf48351a8165e374713f7a3748143fc2b4141539b4becb7]`<br>`spell_rev/components/main_component.tpa:lines 2449-2469 [sha256:7886d6d57269c4e4c6b20c83fc88fdc93e896ed9a46a4531a89cc99066f3fde9]`<br>`spell_rev/components/main_component.tpa:lines 2481-2485 [sha256:4a0f11076ebf6af5a8f59f3d3aed06d20b549db725525c4cea0e67e308abda54]`<br>`spell_rev/components/main_component.tpa:lines 2517-2524 [sha256:5ea61024d42262d253e65d11caff66c73a5e36068cacb55ee3b5895dc8615f91]`<br>`spell_rev/components/main_component.tpa:lines 2649-2653 [sha256:a085e28059fc741392b0f6b23763fdf83f221ced8c6f2235a879bd3d2a221a33]`<br>`spell_rev/components/main_component.tpa:lines 2836-2840 [sha256:9639167c82ee56d4cc0a53d5905fb0d1b2593dc1c9ab8a5adf75722e99f6eb44]`<br>`spell_rev/components/main_component.tpa:lines 2841-2845 [sha256:2cd343a9419204cb4ed64f81cd35fefdf1e1a1ef9f64cde6025de29b2eecd119]`<br>`spell_rev/components/main_component.tpa:lines 3042-3046 [sha256:a913070ace94d90540a82f9c86cd1f5297f7d26258d773e0bb8652477eb2cae8]`<br>`spell_rev/components/main_component.tpa:lines 3166-3170 [sha256:064eb124b7cefa4b093e3a371ee48a2f27dc2c95e00892f68663a53378765c15]` |
| `arcane.mestils_acid_sheath_relocation` | `SPWI403`, `SPWI526` | `spell_rev/components/main_component.tpa:lines 2152-2164 [sha256:15f3c63fdd660aa9eeb468810a6fd1d66aa63d4398c43a295ab5d7915d37e5e5]`<br>`spell_rev/components/main_component.tpa:lines 2578-2593 [sha256:53647ea07137cec7f38b6a3a139f032fc477980009d9b0690b82fa58623203a0]` |
| `arcane.level4.monster_summoning_iv_relocation` | `SPWI407`, `SPWI423` | `spell_rev/components/main_component.tpa:lines 2186-2199 [sha256:97d03a00283ff1d36d08c8493601e33540f58ddea8b20634120e12c7dcd7e354]`<br>`spell_rev/components/main_component.tpa:lines 2308-2323 [sha256:5aa7cfa0ba4146ac534070a985dfb41a86baf4bcf5ea13041b83cbe61aa18934]` |
| `arcane.summon_nishruu_relocation` | `SPWI624`, `SPWI719` | `spell_rev/components/main_component.tpa:lines 2781-2785 [sha256:e0d67b0e88eb34be931c25b48ca82fe08d40ff15881aa558255ef29ec495e41b]`<br>`spell_rev/components/main_component.tpa:lines 2963-2976 [sha256:dd7f1f9af885e54eb4399e8e01cb05a278b5acae1cd5c54c68d45f90cff02154]` |
| `arcane.imprisonment_freedom` | `SPWI910`, `SPWI917` | `spell_rev/components/main_component.tpa:lines 3197-3201 [sha256:4161acf95e38919980b68832f2e3d2ee5c4a8899ae53501de3f522263208cdd3]`<br>`spell_rev/components/main_component.tpa:lines 3256-3261 [sha256:bbcb01e9da4c0c34a4845d64943b6d26fe768471a7b3a5ad2a6541173fa79de5]` |
| `divine.cure_wounds_progression` | `SPPR103`, `SPPR215`, `SPPR315`, `SPPR401`, `SPPR502` | `spell_rev/components/main_component.tpa:lines 200-207 [sha256:231a9f1f98ef3f51f484a1b56b7d494ccbbb55cd8db2f6b423539f71f1f8dacc]`<br>`spell_rev/components/main_component.tpa:lines 625-628 [sha256:8f813278b4030696573a9697365f7c6a250a1bdfe7a873e06f05fe9a57004021]`<br>`spell_rev/components/main_component.tpa:lines 760-764 [sha256:738baafe4db39a20a33ce9248a957e5fc7862561804a4b6e80ca6276748483e2]`<br>`spell_rev/components/main_component.tpa:lines 856-860 [sha256:53f26509f3162fee562bf48cb0c8e69e93331e8a5653c2bfb837f871fea13704]`<br>`spell_rev/components/main_component.tpa:lines 991-994 [sha256:1effbd986c9e6548f308c7149f7fb67c76714528b9bd9efc736d6cb07b1a7863]`<br>`spell_rev/components/main_component.tpa:lines 350-352 [sha256:72c1c5117919e7c5f82d43f3c7134a497a17bb77b9fe51abd7fc6e269b74d515]` |
| `divine.goodberry` | `SPPR118`, `SPPR207` | `spell_rev/components/main_component.tpa:lines 567-584 [sha256:fed07a27ca4bd9af8d1b2268548b31e2780d0178a1caa66dd31eae4e0428f364]`<br>`spell_rev/components/main_component.tpa:lines 441-444 [sha256:02e2332422a85aa89c2e115b285b90c744b3263b86fc129f8b460f96e281287a]` |
| `divine.cause_wounds_progression` | `SPPR119`, `SPPR219`, `SPPR321`, `SPPR414`, `SPPR510` | `spell_rev/components/main_component.tpa:lines 658-670 [sha256:5ce8ad2441097012b091d705925a5db3f5b2f1dde62f546de87f1ed542c271ca]`<br>`spell_rev/components/main_component.tpa:lines 802-810 [sha256:b48c281a5e66bd4f9b7e28c1658161a7b9e4f6b25366869d73aaeed7e55d28ec]`<br>`spell_rev/components/main_component.tpa:lines 944-950 [sha256:178494dac19f4a7a2b2b2ea6e2769ab81d55d75f49de24de74354bab10af78d9]`<br>`spell_rev/components/main_component.tpa:lines 1032-1037 [sha256:4a34921faff7fdeb5bc8be2171f06229a0ab73f23ba05002775a77fe670fe47c]`<br>`spell_rev/components/main_component.tpa:lines 445-457 [sha256:830acde8b8498df0b61ea4a0a75d777e86b2ba8eedd8e2af255b2048c29d90ab]` |
| `divine.insects_and_gust_of_wind` | `SPPR218`, `SPPR318`, `SPPR319`, `SPPR517`, `SPPR717` | `spell_rev/components/main_component.tpa:lines 768-782 [sha256:6927fb7c84adefb985e75e9e106a885397ce1cd035f786f204d8f05f254567a2]`<br>`spell_rev/components/main_component.tpa:lines 1081-1087 [sha256:a7ac482a41a6e2c0f76d6bde6f08bb51224f1bd5e474d6771d39531e10878c88]`<br>`spell_rev/components/main_component.tpa:lines 1330-1336 [sha256:f554047ebc90d443ca686f9045c699e6e604e3775edfe660e85ad8c2187eb985]`<br>`spell_rev/lib/insects.tph:lines 4-68 [sha256:527f68677606e690c87c6f377d054d9ab010e453be43cca32214765524b8b01a]`<br>`spell_rev/components/main_component.tpa:lines 643-657 [sha256:0f6e381010726472b08eb3ebeaae4b47a608ed9c61971fdeaa8a717f878ad91f]`<br>`spell_rev/components/main_component.tpa:lines 167-170 [sha256:7cf80b660858963d5fadbaacefbec017d643ec837576e8430b173a7045026d0d]` |
| `divine.elemental_protections` | `SPPR306`, `SPPR407`, `SPPR520`, `SPPR521`, `SPPR522`, `SPPR523` | `spell_rev/components/main_component.tpa:lines 895-902 [sha256:20075d4750d3d76046d5464d29e92493c54f87e28985362ee006b0fca07157de]`<br>`spell_rev/components/main_component.tpa:lines 1093-1109 [sha256:4cbc54cba7e0cd8c7845392b82c8b155d830ae10f360cbf32935d6734c3fdbb7]`<br>`spell_rev/components/main_component.tpa:lines 715-719 [sha256:66b052156177ec9857da7a0ebbab9df2e7e6ed1d1afada457a9bd1d0bbf5da82]` |

<!-- END ATOMIC COMPOSITE EVIDENCE -->

Roles such as `deprecated_slot`, `ai_deprecated_slot`, and
`game_compatibility_slot` are intentional members of the same semantic choice;
they are not additional changes that can safely be selected alone.

<!-- BEGIN SOFT RELATION EVIDENCE -->

## Soft relation evidence

Each row below corresponds to exactly one final directed `soft_requires`
pair. The physical edge count includes every binary occurrence found by
the pinned audits; the cited source is one representative occurrence, so
counts can exceed the number of anchors printed here. `direct` means the
binary source belongs to the row's `From` choice.

One row is explicitly marked `reverse-family`:
`divine.regenerate_light_wounds` to `divine.mass_regenerate`. The audited
regeneration-family relation is symmetric, but only revised Mass Regenerate
contains this pair's physical opcode-206 anti-stacking references. Its
SPPR524 evidence is therefore cited in the honest physical direction; this
exception applies to no other row.

| From | To | Physical edge count | Evidence direction | Representative source anchor |
| --- | --- | --- | --- | --- |
| `arcane.level1.armor` | `arcane.level3.ghost_armor` | 4 | `direct` | `spell_rev/spwi1##/spwi102.spl:0x246:ability[0].effect[6].resource` |
| `arcane.level1.armor` | `arcane.level4.spirit_armor` | 4 | `direct` | `spell_rev/spwi1##/spwi102.spl:0x276:ability[0].effect[7].resource` |
| `arcane.level1.shield` | `arcane.level1.magic_missile` | 1 | `direct` | `spell_rev/spwi1##/spwi114.spl:0x25e:ability[0].effect[9].resource` |
| `arcane.level1.larlochs_minor_drain` | `arcane.level9.larlochs_energy_drain` | 1 | `direct` | `spell_rev/spwi1##/spwi119.eff:0x30:effect.resource` |
| `arcane.level1.reflected_image` | `arcane.level2.mirror_image` | 9 | `direct` | `spell_rev/spwi1##/spwi120.spl:0x28e:ability[0].effect[5].resource` |
| `arcane.level1.find_familiar` | `arcane.level2.blur` | 19 | `direct` | `spell_rev/spwi1##/famdust.cre:0x2d4:known_spell[0]` |
| `arcane.level1.find_familiar` | `arcane.level2.glitterdust` | 6 | `direct` | `spell_rev/spwi1##/famdus25.cre:0x2ec:known_spell[2]` |
| `arcane.level1.find_familiar` | `arcane.level2.horror` | 5 | `direct` | `spell_rev/spwi1##/famqua25.cre:0x2d4:known_spell[0]` |
| `arcane.level1.find_familiar` | `arcane.level2.mirror_image` | 4 | `direct` | `spell_rev/spwi1##/famfai25.cre:0x2d4:known_spell[0]` |
| `arcane.level1.find_familiar` | `arcane.level3.detect_illusion` | 3 | `direct` | `spell_rev/spwi1##/fampsd25.cre:0x2e0:known_spell[1]` |
| `arcane.level1.find_familiar` | `arcane.level3.invisibility_sphere` | 4 | `direct` | `spell_rev/spwi1##/famfai25.cre:0x2e0:known_spell[1]` |
| `arcane.level1.find_familiar` | `arcane.level4.improved_invisibility` | 2 | `direct` | `spell_rev/spwi1##/famfai25.cre:0x2ec:known_spell[2]` |
| `arcane.level1.find_familiar` | `arcane.level4.polymorph_self` | 4 | `direct` | `spell_rev/spwi1##/famimp.cre:0x2e0:known_spell[1]` |
| `arcane.level1.find_familiar` | `arcane.level4.stoneskin` | 2 | `direct` | `spell_rev/spwi1##/famdus25.cre:0x2e0:known_spell[1]` |
| `arcane.level1.find_familiar` | `arcane.level7.prismatic_spray` | 2 | `direct` | `spell_rev/spwi1##/famdus25.cre:0x2d4:known_spell[0]` |
| `arcane.level2.know_opponent` | `divine.know_opponent` | 1 | `direct` | `spell_rev/spwi2##/spwi208.spl:0x28e:ability[0].effect[10].resource` |
| `arcane.level2.mirror_image` | `arcane.level1.reflected_image` | 6 | `direct` | `spell_rev/spwi2##/spwi212.spl:0x206:ability[0].effect[3].resource` |
| `arcane.level2.chaos_shield` | `arcane.level7.improved_chaos_shield` | 18 | `direct` | `spell_rev/spwi2##/spwi222.spl:0x3e6:ability[0].effect[3].resource` |
| `arcane.elemental_protection_progression` | `arcane.level1.burning_hands` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x496:ability[0].effect[10].resource` |
| `arcane.elemental_protection_progression` | `arcane.level1.larlochs_minor_drain` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x3ce:ability[0].effect[10].resource` |
| `arcane.elemental_protection_progression` | `arcane.level1.magic_missile` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x39e:ability[0].effect[9].resource` |
| `arcane.elemental_protection_progression` | `arcane.level2.agannazars_scorcher` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x4c6:ability[0].effect[11].resource` |
| `arcane.elemental_protection_progression` | `arcane.level2.melfs_acid_arrow` | 23 | `direct` | `spell_rev/spwi5##/spwi517.spl:0x406:ability[0].effect[7].resource` |
| `arcane.elemental_protection_progression` | `arcane.level3.fireball` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x526:ability[0].effect[13].resource` |
| `arcane.elemental_protection_progression` | `arcane.level3.flame_arrow` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x4f6:ability[0].effect[12].resource` |
| `arcane.elemental_protection_progression` | `arcane.level3.lightning_bolt` | 23 | `direct` | `spell_rev/spwi5##/spwi512.spl:0x436:ability[0].effect[8].resource` |
| `arcane.elemental_protection_progression` | `arcane.level3.skull_trap` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x3fe:ability[0].effect[11].resource` |
| `arcane.elemental_protection_progression` | `arcane.level3.vampiric_touch` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x42e:ability[0].effect[12].resource` |
| `arcane.elemental_protection_progression` | `arcane.level4.ice_storm` | 23 | `direct` | `spell_rev/spwi3##/spwi320.spl:0x436:ability[0].effect[8].resource` |
| `arcane.elemental_protection_progression` | `arcane.level4.vitriolic_sphere` | 14 | `direct` | `spell_rev/spwi5##/spwi517.spl:0x436:ability[0].effect[8].resource` |
| `arcane.elemental_protection_progression` | `arcane.level5.cone_of_cold` | 23 | `direct` | `spell_rev/spwi3##/spwi320.spl:0x466:ability[0].effect[9].resource` |
| `arcane.elemental_protection_progression` | `arcane.level5.fireburst` | 24 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x556:ability[0].effect[14].resource` |
| `arcane.elemental_protection_progression` | `arcane.level6.acid_fog` | 23 | `direct` | `spell_rev/spwi5##/spwi517.spl:0x466:ability[0].effect[9].resource` |
| `arcane.elemental_protection_progression` | `arcane.level6.chain_lightning` | 23 | `direct` | `spell_rev/spwi5##/spwi512.spl:0x466:ability[0].effect[9].resource` |
| `arcane.elemental_protection_progression` | `arcane.level6.disintegrate` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x45e:ability[0].effect[13].resource` |
| `arcane.elemental_protection_progression` | `arcane.level7.delayed_blast_fireball` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x586:ability[0].effect[15].resource` |
| `arcane.elemental_protection_progression` | `arcane.level8.abi_dalzims_horrid_wilting` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x48e:ability[0].effect[14].resource` |
| `arcane.elemental_protection_progression` | `arcane.level8.incendiary_cloud` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x5b6:ability[0].effect[16].resource` |
| `arcane.elemental_protection_progression` | `arcane.level9.meteor_swarm` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x5e6:ability[0].effect[17].resource` |
| `arcane.elemental_protection_progression` | `divine.bolt_of_glory` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x36e:ability[0].effect[8].resource` |
| `arcane.elemental_protection_progression` | `divine.call_lightning` | 23 | `direct` | `spell_rev/spwi5##/spwi512.spl:0x3d6:ability[0].effect[6].resource` |
| `arcane.elemental_protection_progression` | `divine.fire_storm` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x466:ability[0].effect[9].resource` |
| `arcane.elemental_protection_progression` | `divine.fire_trap` | 23 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x406:ability[0].effect[7].resource` |
| `arcane.elemental_protection_progression` | `divine.flame_strike` | 22 | `direct` | `spell_rev/spwi3##/spwi319.spl:0x436:ability[0].effect[8].resource` |
| `arcane.elemental_protection_progression` | `divine.glyph_of_warding` | 23 | `direct` | `spell_rev/spwi5##/spwi512.spl:0x406:ability[0].effect[7].resource` |
| `arcane.elemental_protection_progression` | `divine.holy_smite` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x30e:ability[0].effect[6].resource` |
| `arcane.elemental_protection_progression` | `divine.ice_storm` | 23 | `direct` | `spell_rev/spwi3##/spwi320.spl:0x406:ability[0].effect[7].resource` |
| `arcane.elemental_protection_progression` | `divine.resist_elements` | 18 | `direct` | `spell_rev/spwi2##/spwi225.spl:0x4d6:ability[0].effect[8].resource` |
| `arcane.elemental_protection_progression` | `divine.unholy_blight` | 14 | `direct` | `spell_rev/spwi6##/spwi606.spl:0x33e:ability[0].effect[7].resource` |
| `arcane.level2.monster_summoning_ii` | `arcane.level1.obscuring_mist` | 1 | `direct` | `spell_rev/spwi2##/jellgrsu.itm:0x4de:equipped_effect[22].resource` |
| `arcane.level2.monster_summoning_ii` | `arcane.level2.stinking_cloud` | 1 | `direct` | `spell_rev/spwi2##/jellgrsu.itm:0x50e:equipped_effect[23].resource` |
| `arcane.level2.monster_summoning_ii` | `arcane.level5.cloudkill` | 1 | `direct` | `spell_rev/spwi2##/jellgrsu.itm:0x53e:equipped_effect[24].resource` |
| `arcane.level2.monster_summoning_ii` | `divine.obscuring_mist` | 1 | `direct` | `spell_rev/spwi2##/jellgrsu.itm:0x4ae:equipped_effect[21].resource` |
| `arcane.level3.monster_summoning_iii` | `divine.armor_of_faith` | 2 | `direct` | `spell_rev/spwi3##/hobshasu.cre:0x2f8:known_spell[3]` |
| `arcane.level3.monster_summoning_iii` | `divine.bless` | 2 | `direct` | `spell_rev/spwi3##/hobshasu.cre:0x2d4:known_spell[0]` |
| `arcane.level3.monster_summoning_iii` | `divine.chant` | 2 | `direct` | `spell_rev/spwi3##/hobshasu.cre:0x304:known_spell[4]` |
| `arcane.level3.monster_summoning_iii` | `divine.cure_wounds_progression` | 3 | `direct` | `spell_rev/spwi3##/hobshasu.cre:0x2e0:known_spell[1]` |
| `arcane.level3.monster_summoning_iii` | `divine.hold_person` | 2 | `direct` | `spell_rev/spwi3##/hobshasu.cre:0x310:known_spell[5]` |
| `arcane.level3.monster_summoning_iii` | `divine.resist_fear` | 2 | `direct` | `spell_rev/spwi3##/hobshasu.cre:0x2ec:known_spell[2]` |
| `arcane.level3.monster_summoning_iii` | `divine.silence` | 2 | `direct` | `spell_rev/spwi3##/hobshasu.cre:0x31c:known_spell[6]` |
| `arcane.level3.non_detection` | `arcane.level2.detect_invisibility` | 2 | `direct` | `spell_rev/shared/spra302.spl:0x1ce:ability[0].effect[6].resource` |
| `arcane.level3.non_detection` | `arcane.level5.oracle` | 2 | `direct` | `spell_rev/shared/spra302.spl:0x22e:ability[0].effect[8].resource` |
| `arcane.level3.non_detection` | `arcane.level6.true_seeing` | 2 | `direct` | `spell_rev/shared/spra302.spl:0x25e:ability[0].effect[9].resource` |
| `arcane.level3.non_detection` | `divine.invisibility_purge` | 1 | `direct` | `spell_rev/spwi3##/spwi310.spl:0x22e:ability[0].effect[8].resource` |
| `arcane.level3.non_detection` | `divine.true_seeing` | 2 | `direct` | `spell_rev/shared/spra302.spl:0x1fe:ability[0].effect[7].resource` |
| `arcane.level3.ghost_armor` | `arcane.level1.armor` | 1 | `direct` | `spell_rev/spwi3##/spwi317.spl:0x6de:ability[0].effect[33].resource` |
| `arcane.level3.ghost_armor` | `arcane.level4.spirit_armor` | 1 | `direct` | `spell_rev/spwi3##/spwi317.spl:0x70e:ability[0].effect[34].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.detect_alignment_relocation` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x9de:ability[0].effect[49].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level1.grease` | 12 | `direct` | `spell_rev/spwi5##/spwi591.spl:0x266:ability[0].effect[0].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level1.sleep` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x7ce:ability[0].effect[38].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level1.spook` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x7fe:ability[0].effect[39].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level2.detect_invisibility` | 1 | `direct` | `spell_rev/spwi5##/spwi592.spl:0x1fe:ability[0].effect[7].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level2.know_opponent` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0xa3e:ability[0].effect[51].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level2.power_word_sleep` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x82e:ability[0].effect[40].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level2.stinking_cloud` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x4a6:ability[0].effect[12].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level2.web` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x476:ability[0].effect[11].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level3.dire_charm` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x85e:ability[0].effect[41].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level3.fireball` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x446:ability[0].effect[10].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level3.lightning_bolt` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x416:ability[0].effect[9].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level3.skull_trap` | 12 | `direct` | `spell_rev/spwi5##/spwi596.spl:0x2c6:ability[0].effect[2].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level4.ice_storm` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x3e6:ability[0].effect[8].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level5.cloudkill` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x3b6:ability[0].effect[7].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level5.cone_of_cold` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x386:ability[0].effect[6].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level5.feeblemind` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x8be:ability[0].effect[43].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level5.fireburst` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x356:ability[0].effect[5].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level5.oracle` | 2 | `direct` | `spell_rev/spwi5##/spwi592.spl:0x25e:ability[0].effect[9].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level5.waves_of_fatigue` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x88e:ability[0].effect[42].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level6.acid_fog` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x326:ability[0].effect[4].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level6.power_word_silence` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x8ee:ability[0].effect[44].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level6.true_seeing` | 1 | `direct` | `spell_rev/spwi5##/spwi592.spl:0x28e:ability[0].effect[10].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level7.delayed_blast_fireball` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x2f6:ability[0].effect[3].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level7.power_word_stun` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x91e:ability[0].effect[45].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level8.incendiary_cloud` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x2c6:ability[0].effect[2].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level8.power_word_blind` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x94e:ability[0].effect[46].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level9.meteor_swarm` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x296:ability[0].effect[1].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level9.power_word_kill` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x97e:ability[0].effect[47].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level9.wish` | 2 | `direct` | `spell_rev/spwi5##/spwi510.spl:0x13e:ability[0].effect[3].resource` |
| `arcane.spell_shield_anti_magic` | `arcane.level8.mind_blank` | 2 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x3a:header.spellbook_icon` |
| `arcane.spell_shield_anti_magic` | `divine.command` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x73e:ability[0].effect[35].resource` |
| `arcane.spell_shield_anti_magic` | `divine.detect_alignment` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x9ae:ability[0].effect[48].resource` |
| `arcane.spell_shield_anti_magic` | `divine.earthquake` | 12 | `direct` | `spell_rev/spwi5##/spwi597.spl:0x266:ability[0].effect[0].resource` |
| `arcane.spell_shield_anti_magic` | `divine.entangle` | 12 | `direct` | `spell_rev/spwi5##/spwi597.spl:0x296:ability[0].effect[1].resource` |
| `arcane.spell_shield_anti_magic` | `divine.fire_storm` | 12 | `direct` | `spell_rev/spwi5##/spwi595.spl:0x266:ability[0].effect[0].resource` |
| `arcane.spell_shield_anti_magic` | `divine.greater_command` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x79e:ability[0].effect[37].resource` |
| `arcane.spell_shield_anti_magic` | `divine.holy_smite` | 12 | `direct` | `spell_rev/spwi5##/spwi596.spl:0x296:ability[0].effect[1].resource` |
| `arcane.spell_shield_anti_magic` | `divine.know_opponent` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0xa0e:ability[0].effect[50].resource` |
| `arcane.spell_shield_anti_magic` | `divine.mental_domination` | 1 | `direct` | `spell_rev/spwi5##/spwi593.spl:0x76e:ability[0].effect[36].resource` |
| `arcane.spell_shield_anti_magic` | `divine.true_seeing` | 1 | `direct` | `spell_rev/spwi5##/spwi592.spl:0x22e:ability[0].effect[8].resource` |
| `arcane.spell_shield_anti_magic` | `divine.unholy_blight` | 12 | `direct` | `spell_rev/spwi5##/spwi596.spl:0x266:ability[0].effect[0].resource` |
| `arcane.level3.dispel_magic` | `arcane.level3.remove_magic` | 2 | `direct` | `spell_rev/spwi3##/scrl1e.itm:0xf6:ability[0].effect[0].resource` |
| `arcane.mestils_acid_sheath_relocation` | `divine.insects_and_gust_of_wind` | 6 | `direct` | `spell_rev/spwi4##/spwi403.spl:0x13e:ability[0].effect[3].resource` |
| `arcane.level4.minor_globe_of_invulnerability` | `arcane.level1.grease` | 1 | `direct` | `spell_rev/spwi4##/spwi406.spl:0x13e:ability[0].effect[3].resource` |
| `arcane.level4.minor_globe_of_invulnerability` | `arcane.level2.stinking_cloud` | 1 | `direct` | `spell_rev/spwi4##/spwi406.spl:0x10e:ability[0].effect[2].resource` |
| `arcane.level4.minor_globe_of_invulnerability` | `arcane.level2.web` | 1 | `direct` | `spell_rev/spwi4##/spwi406.spl:0xde:ability[0].effect[1].resource` |
| `arcane.level4.minor_globe_of_invulnerability` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/spwi4##/spwi406.spl:0xae:ability[0].effect[0].resource` |
| `arcane.level4.minor_globe_of_invulnerability` | `divine.holy_smite` | 1 | `direct` | `spell_rev/spwi4##/spwi406.spl:0x19e:ability[0].effect[5].resource` |
| `arcane.level4.minor_globe_of_invulnerability` | `divine.strength_of_stone` | 1 | `direct` | `spell_rev/spwi4##/spwi406.spl:0x1ce:ability[0].effect[6].resource` |
| `arcane.level4.minor_globe_of_invulnerability` | `divine.unholy_blight` | 1 | `direct` | `spell_rev/spwi4##/spwi406.spl:0x16e:ability[0].effect[4].resource` |
| `arcane.level4.monster_summoning_iv_relocation` | `arcane.level2.web` | 4 | `direct` | `spell_rev/spwi4##/spidswsu.cre:0x2d4:known_spell[0]` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level2.stinking_cloud` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x55e:ability[0].effect[25].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level2.web` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x52e:ability[0].effect[24].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level3.skull_trap` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x5be:ability[0].effect[27].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level5.cloudkill` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x6ae:ability[0].effect[32].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level6.acid_fog` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x6de:ability[0].effect[33].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level7.delayed_blast_fireball` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x73e:ability[0].effect[35].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level8.incendiary_cloud` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x8ee:ability[0].effect[44].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level8.symbol_of_death` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x85e:ability[0].effect[41].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level8.symbol_of_stunning` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x88e:ability[0].effect[42].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level8.symbol_of_weakness` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x8be:ability[0].effect[43].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `arcane.level9.meteor_swarm` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x9de:ability[0].effect[49].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.call_lightning` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x67e:ability[0].effect[31].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.entangle` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x4fe:ability[0].effect[23].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.fire_storm` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x82e:ability[0].effect[40].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.globe_of_blades` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x76e:ability[0].effect[36].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.glyph_of_warding` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x64e:ability[0].effect[30].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.holy_smite` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x61e:ability[0].effect[29].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.silence` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x58e:ability[0].effect[26].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.symbol_of_death` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x79e:ability[0].effect[37].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.symbol_of_stunning` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x7ce:ability[0].effect[38].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.symbol_of_weakness` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x7fe:ability[0].effect[39].resource` |
| `arcane.level4.otilukes_resilient_sphere` | `divine.unholy_blight` | 2 | `direct` | `spell_rev/spwi4##/spwi413c.spl:0x5ee:ability[0].effect[28].resource` |
| `arcane.level4.spirit_armor` | `arcane.level1.armor` | 1 | `direct` | `spell_rev/spwi4##/spwi414.spl:0x22e:ability[0].effect[8].resource` |
| `arcane.level4.spirit_armor` | `arcane.level3.ghost_armor` | 1 | `direct` | `spell_rev/spwi4##/spwi414.spl:0x25e:ability[0].effect[9].resource` |
| `arcane.level4.polymorph_self` | `arcane.level1.magic_missile` | 1 | `direct` | `spell_rev/spwi4##/spwi463.itm:0x6ee:equipped_effect[33].resource` |
| `arcane.level4.polymorph_self` | `arcane.level8.ghostform` | 1 | `direct` | `spell_rev/spwi4##/spwi416.spl:0x3de:ability[0].effect[17].resource` |
| `arcane.level4.polymorph_self` | `arcane.level9.shapechange` | 1 | `direct` | `spell_rev/spwi4##/spwi416.spl:0x40e:ability[0].effect[18].resource` |
| `arcane.level4.fire_shield_red` | `divine.insects_and_gust_of_wind` | 42 | `direct` | `spell_rev/spwi4##/spwi418.spl:0x2b6:ability[0].effect[0].resource` |
| `arcane.level5.summon_shadow` | `divine.natures_beauty` | 2 | `direct` | `spell_rev/spwi5##/dvwraith.itm:0x11e:equipped_effect[2].resource` |
| `arcane.level5.monster_summoning_v` | `arcane.haste_slow` | 2 | `direct` | `spell_rev/spwi5##/ogremasu.cre:0x310:known_spell[5]` |
| `arcane.level5.monster_summoning_v` | `arcane.level1.magic_missile` | 3 | `direct` | `spell_rev/spwi5##/ogremasu.cre:0x2e0:known_spell[1]` |
| `arcane.level5.monster_summoning_v` | `arcane.level1.obscuring_mist` | 2 | `direct` | `spell_rev/spwi5##/ogremasu.cre:0x2d4:known_spell[0]` |
| `arcane.level5.monster_summoning_v` | `arcane.level1.shield` | 2 | `direct` | `spell_rev/spwi5##/ogremasu.cre:0x2ec:known_spell[2]` |
| `arcane.level5.monster_summoning_v` | `arcane.level2.horror` | 2 | `direct` | `spell_rev/spwi5##/ogremasu.cre:0x2f8:known_spell[3]` |
| `arcane.level5.monster_summoning_v` | `arcane.level2.mirror_image` | 2 | `direct` | `spell_rev/spwi5##/ogremasu.cre:0x304:known_spell[4]` |
| `arcane.level5.monster_summoning_v` | `arcane.level3.dire_charm` | 2 | `direct` | `spell_rev/spwi5##/ogremasu.cre:0x31c:known_spell[6]` |
| `arcane.level6.invisible_stalker` | `divine.hold_person` | 1 | `direct` | `spell_rev/spwi6##/stalker.itm:0x3e6:equipped_effect[18].resource` |
| `arcane.level6.invisible_stalker` | `divine.natures_beauty` | 1 | `direct` | `spell_rev/spwi6##/stalker.itm:0x416:equipped_effect[19].resource` |
| `arcane.level6.globe_of_invulnerability` | `arcane.level1.grease` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0x16e:ability[0].effect[4].resource` |
| `arcane.level6.globe_of_invulnerability` | `arcane.level2.stinking_cloud` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0x13e:ability[0].effect[3].resource` |
| `arcane.level6.globe_of_invulnerability` | `arcane.level2.web` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0x10e:ability[0].effect[2].resource` |
| `arcane.level6.globe_of_invulnerability` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0xde:ability[0].effect[1].resource` |
| `arcane.level6.globe_of_invulnerability` | `arcane.level4.ice_storm` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0xae:ability[0].effect[0].resource` |
| `arcane.level6.globe_of_invulnerability` | `divine.holy_smite` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0x1ce:ability[0].effect[6].resource` |
| `arcane.level6.globe_of_invulnerability` | `divine.strength_of_stone` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0x1fe:ability[0].effect[7].resource` |
| `arcane.level6.globe_of_invulnerability` | `divine.unholy_blight` | 1 | `direct` | `spell_rev/spwi6##/spwi602.spl:0x19e:ability[0].effect[5].resource` |
| `arcane.level6.true_seeing` | `arcane.detect_alignment_relocation` | 1 | `direct` | `spell_rev/spwi6##/spwi609.spl:0x5be:ability[0].effect[27].resource` |
| `arcane.level6.true_seeing` | `arcane.level1.obscuring_mist` | 1 | `direct` | `spell_rev/spwi6##/spwi609.spl:0x4fe:ability[0].effect[23].resource` |
| `arcane.level6.true_seeing` | `arcane.level1.spook` | 1 | `direct` | `spell_rev/spwi6##/spwi609.spl:0x52e:ability[0].effect[24].resource` |
| `arcane.level6.true_seeing` | `arcane.level5.shadow_door` | 1 | `direct` | `spell_rev/spwi6##/spwi609.spl:0x55e:ability[0].effect[25].resource` |
| `arcane.level6.true_seeing` | `divine.obscuring_mist` | 1 | `direct` | `spell_rev/spwi6##/spwi609.spl:0x58e:ability[0].effect[26].resource` |
| `arcane.summon_nishruu_relocation` | `arcane.level5.lower_resistance` | 2 | `direct` | `spell_rev/spwi7##/haksu.itm:0xbe:equipped_effect[0].resource` |
| `arcane.summon_nishruu_relocation` | `arcane.spell_shield_anti_magic` | 2 | `direct` | `spell_rev/spwi7##/haksu.itm:0xee:equipped_effect[1].resource` |
| `arcane.level7.project_image` | `arcane.level8.simulacrum` | 1 | `direct` | `spell_rev/spwi7##/projimag.spl:0x25e:ability[0].effect[9].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level1.burning_hands` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x26e:equipped_effect[9].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level2.agannazars_scorcher` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x29e:equipped_effect[10].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level2.melfs_acid_arrow` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x44e:equipped_effect[19].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x2ce:equipped_effect[11].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level3.lightning_bolt` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x50e:equipped_effect[23].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level4.ice_storm` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x3ee:equipped_effect[17].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level5.cloudkill` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x74e:equipped_effect[35].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level5.cone_of_cold` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x41e:equipped_effect[18].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x2fe:equipped_effect[12].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level6.acid_fog` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x47e:equipped_effect[20].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level6.chain_lightning` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x53e:equipped_effect[24].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x32e:equipped_effect[13].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level7.finger_of_death` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x5ce:equipped_effect[27].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level8.abi_dalzims_horrid_wilting` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x5fe:equipped_effect[28].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x35e:equipped_effect[14].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level9.larlochs_energy_drain` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x68e:equipped_effect[31].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x38e:equipped_effect[15].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level9.power_word_kill` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x62e:equipped_effect[29].resource` |
| `arcane.level7.mordenkainens_sword` | `arcane.level9.wail_of_the_banshee` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x65e:equipped_effect[30].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.call_lightning` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x4ae:equipped_effect[21].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.finger_of_death` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x59e:equipped_effect[26].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.fire_storm` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x23e:equipped_effect[8].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.fire_trap` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x1de:equipped_effect[6].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.flame_strike` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x20e:equipped_effect[7].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.glyph_of_warding` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x4de:equipped_effect[22].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.ice_storm` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x3be:equipped_effect[16].resource` |
| `arcane.level7.mordenkainens_sword` | `divine.poison` | 1 | `direct` | `spell_rev/spwi7##/morsword.itm:0x71e:equipped_effect[34].resource` |
| `arcane.level7.summon_efreeti` | `arcane.level1.burning_hands` | 3 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x2d4:known_spell[0]` |
| `arcane.level7.summon_efreeti` | `arcane.level1.magic_missile` | 3 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x2e0:known_spell[1]` |
| `arcane.level7.summon_efreeti` | `arcane.level1.shield` | 2 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x2ec:known_spell[2]` |
| `arcane.level7.summon_efreeti` | `arcane.level2.agannazars_scorcher` | 3 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x304:known_spell[4]` |
| `arcane.level7.summon_efreeti` | `arcane.level2.invisibility` | 3 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x2f8:known_spell[3]` |
| `arcane.level7.summon_efreeti` | `arcane.level3.fireball` | 5 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x310:known_spell[5]` |
| `arcane.level7.summon_efreeti` | `arcane.level3.flame_arrow` | 2 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x31c:known_spell[6]` |
| `arcane.level7.summon_efreeti` | `arcane.level4.fire_shield_red` | 3 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x328:known_spell[7]` |
| `arcane.level7.summon_efreeti` | `arcane.level5.conjure_lesser_fire_elemental` | 2 | `direct` | `spell_rev/spwi7##/dvefreet.cre:0x334:known_spell[8]` |
| `arcane.level7.summon_efreeti` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/spwi7##/dvefreet.itm:0x20e:equipped_effect[7].resource` |
| `arcane.level7.summon_efreeti` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/spwi7##/dvefreet.itm:0x23e:equipped_effect[8].resource` |
| `arcane.level7.summon_efreeti` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/spwi7##/dvefreet.itm:0x26e:equipped_effect[9].resource` |
| `arcane.level7.summon_efreeti` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/spwi7##/dvefreet.itm:0x29e:equipped_effect[10].resource` |
| `arcane.level7.summon_efreeti` | `divine.fire_storm` | 1 | `direct` | `spell_rev/spwi7##/dvefreet.itm:0x11e:equipped_effect[2].resource` |
| `arcane.level7.summon_efreeti` | `divine.fire_trap` | 1 | `direct` | `spell_rev/spwi7##/dvefreet.itm:0xbe:equipped_effect[0].resource` |
| `arcane.level7.summon_efreeti` | `divine.flame_strike` | 1 | `direct` | `spell_rev/spwi7##/dvefreet.itm:0xee:equipped_effect[1].resource` |
| `arcane.level7.summon_djinni` | `arcane.haste_slow` | 2 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x304:known_spell[4]` |
| `arcane.level7.summon_djinni` | `arcane.level1.grease` | 1 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x724:effect[2].resource` |
| `arcane.level7.summon_djinni` | `arcane.level1.magic_missile` | 4 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x2d4:known_spell[0]` |
| `arcane.level7.summon_djinni` | `arcane.level1.shield` | 2 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x2e0:known_spell[1]` |
| `arcane.level7.summon_djinni` | `arcane.level2.invisibility` | 3 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x2ec:known_spell[2]` |
| `arcane.level7.summon_djinni` | `arcane.level2.mirror_image` | 2 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x2f8:known_spell[3]` |
| `arcane.level7.summon_djinni` | `arcane.level2.web` | 1 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x82c:effect[3].resource` |
| `arcane.level7.summon_djinni` | `arcane.level3.lightning_bolt` | 3 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x310:known_spell[5]` |
| `arcane.level7.summon_djinni` | `arcane.level4.improved_invisibility` | 2 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x31c:known_spell[6]` |
| `arcane.level7.summon_djinni` | `arcane.level4.minor_globe_of_invulnerability` | 2 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x328:known_spell[7]` |
| `arcane.level7.summon_djinni` | `arcane.level5.conjure_lesser_air_elemental` | 2 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x334:known_spell[8]` |
| `arcane.level7.summon_djinni` | `divine.earthquake` | 1 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x61c:effect[1].resource` |
| `arcane.level7.summon_djinni` | `divine.entangle` | 1 | `direct` | `spell_rev/spwi7##/dvdjinni.cre:0x514:effect[0].resource` |
| `arcane.level7.improved_chaos_shield` | `arcane.level2.chaos_shield` | 1 | `direct` | `spell_rev/spwi7##/spwi723.spl:0x13e:ability[0].effect[3].resource` |
| `arcane.level7.monster_summoning_vii` | `arcane.level2.stinking_cloud` | 1 | `direct` | `spell_rev/spwi7##/otyughsu.itm:0x11e:equipped_effect[2].resource` |
| `arcane.level8.ghostform` | `arcane.level1.grease` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x89e:ability[0].effect[39].resource` |
| `arcane.level8.ghostform` | `arcane.level2.web` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x8ce:ability[0].effect[40].resource` |
| `arcane.level8.ghostform` | `arcane.level4.polymorph_other` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x8fe:ability[0].effect[41].resource` |
| `arcane.level8.ghostform` | `arcane.level4.polymorph_self` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x92e:ability[0].effect[42].resource` |
| `arcane.level8.ghostform` | `arcane.level6.disintegrate` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x98e:ability[0].effect[44].resource` |
| `arcane.level8.ghostform` | `arcane.level9.shapechange` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x9be:ability[0].effect[45].resource` |
| `arcane.level8.ghostform` | `arcane.petrification` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x95e:ability[0].effect[43].resource` |
| `arcane.level8.ghostform` | `divine.earthquake` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x83e:ability[0].effect[37].resource` |
| `arcane.level8.ghostform` | `divine.entangle` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x7de:ability[0].effect[35].resource` |
| `arcane.level8.ghostform` | `divine.implosion` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x86e:ability[0].effect[38].resource` |
| `arcane.level8.ghostform` | `divine.polymorph_other` | 5 | `direct` | `spell_rev/spwi8##/spwi801.spl:0x80e:ability[0].effect[36].resource` |
| `arcane.level8.mind_blank` | `arcane.detect_alignment_relocation` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xe8e:ability[0].effect[74].resource` |
| `arcane.level8.mind_blank` | `arcane.level1.sleep` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xc7e:ability[0].effect[63].resource` |
| `arcane.level8.mind_blank` | `arcane.level1.spook` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xcae:ability[0].effect[64].resource` |
| `arcane.level8.mind_blank` | `arcane.level2.know_opponent` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xeee:ability[0].effect[76].resource` |
| `arcane.level8.mind_blank` | `arcane.level2.power_word_sleep` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xcde:ability[0].effect[65].resource` |
| `arcane.level8.mind_blank` | `arcane.level3.dire_charm` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xd0e:ability[0].effect[66].resource` |
| `arcane.level8.mind_blank` | `arcane.level5.feeblemind` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xd6e:ability[0].effect[68].resource` |
| `arcane.level8.mind_blank` | `arcane.level5.oracle` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xf1e:ability[0].effect[77].resource` |
| `arcane.level8.mind_blank` | `arcane.level5.waves_of_fatigue` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xd3e:ability[0].effect[67].resource` |
| `arcane.level8.mind_blank` | `arcane.level6.power_word_silence` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xd9e:ability[0].effect[69].resource` |
| `arcane.level8.mind_blank` | `arcane.level7.power_word_stun` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xdce:ability[0].effect[70].resource` |
| `arcane.level8.mind_blank` | `arcane.level8.power_word_blind` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xdfe:ability[0].effect[71].resource` |
| `arcane.level8.mind_blank` | `arcane.level9.power_word_kill` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xe2e:ability[0].effect[72].resource` |
| `arcane.level8.mind_blank` | `divine.command` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xbee:ability[0].effect[60].resource` |
| `arcane.level8.mind_blank` | `divine.detect_alignment` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xe5e:ability[0].effect[73].resource` |
| `arcane.level8.mind_blank` | `divine.greater_command` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xc4e:ability[0].effect[62].resource` |
| `arcane.level8.mind_blank` | `divine.know_opponent` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xebe:ability[0].effect[75].resource` |
| `arcane.level8.mind_blank` | `divine.mental_domination` | 1 | `direct` | `spell_rev/spwi8##/spwi802.spl:0xc1e:ability[0].effect[61].resource` |
| `arcane.level8.simulacrum` | `divine.greater_restoration` | 1 | `direct` | `spell_rev/spwi8##/simulacr.spl:0x19e:ability[0].effect[5].resource` |
| `arcane.level8.simulacrum` | `divine.lesser_restoration` | 1 | `direct` | `spell_rev/spwi8##/simulacr.spl:0x16e:ability[0].effect[4].resource` |
| `arcane.level8.power_word_blind` | `arcane.level1.obscuring_mist` | 2 | `direct` | `spell_rev/spwi8##/spwi815.spl:0x28e:ability[0].effect[10].resource` |
| `arcane.level8.power_word_blind` | `divine.obscuring_mist` | 2 | `direct` | `spell_rev/spwi8##/spwi815.spl:0x2be:ability[0].effect[11].resource` |
| `arcane.level8.symbol_of_death` | `divine.symbol_of_death` | 2 | `direct` | `spell_rev/shared/spwi897.spl:0x3a:header.spellbook_icon` |
| `arcane.level9.gate` | `arcane.level1.burning_hands` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x2fe:equipped_effect[12].resource` |
| `arcane.level9.gate` | `arcane.level2.agannazars_scorcher` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x32e:equipped_effect[13].resource` |
| `arcane.level9.gate` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x38e:equipped_effect[15].resource` |
| `arcane.level9.gate` | `arcane.level3.flame_arrow` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x35e:equipped_effect[14].resource` |
| `arcane.level9.gate` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x3be:equipped_effect[16].resource` |
| `arcane.level9.gate` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x3ee:equipped_effect[17].resource` |
| `arcane.level9.gate` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x41e:equipped_effect[18].resource` |
| `arcane.level9.gate` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x44e:equipped_effect[19].resource` |
| `arcane.level9.gate` | `divine.fire_storm` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x2ce:equipped_effect[11].resource` |
| `arcane.level9.gate` | `divine.fire_trap` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x26e:equipped_effect[9].resource` |
| `arcane.level9.gate` | `divine.flame_strike` | 1 | `direct` | `spell_rev/spwi9##/dempitsu.itm:0x29e:equipped_effect[10].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level1.burning_hands` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x55e:ability[0].effect[25].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level1.larlochs_minor_drain` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x79e:ability[0].effect[37].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level1.magic_missile` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x76e:ability[0].effect[36].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level2.agannazars_scorcher` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x58e:ability[0].effect[26].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level2.melfs_acid_arrow` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x31e:ability[0].effect[13].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x5ee:ability[0].effect[28].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level3.flame_arrow` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x5be:ability[0].effect[27].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level3.lightning_bolt` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x46e:ability[0].effect[20].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level3.skull_trap` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x7ce:ability[0].effect[38].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level3.vampiric_touch` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x7fe:ability[0].effect[39].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level4.ice_storm` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x3ae:ability[0].effect[16].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level5.cone_of_cold` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x3de:ability[0].effect[17].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x61e:ability[0].effect[29].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level6.acid_fog` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x34e:ability[0].effect[14].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level6.chain_lightning` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x49e:ability[0].effect[21].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level6.disintegrate` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x82e:ability[0].effect[40].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x64e:ability[0].effect[30].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level8.abi_dalzims_horrid_wilting` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x85e:ability[0].effect[41].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x67e:ability[0].effect[31].resource` |
| `arcane.level9.absolute_immunity` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x6ae:ability[0].effect[32].resource` |
| `arcane.level9.absolute_immunity` | `divine.bolt_of_glory` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x73e:ability[0].effect[35].resource` |
| `arcane.level9.absolute_immunity` | `divine.call_lightning` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x40e:ability[0].effect[18].resource` |
| `arcane.level9.absolute_immunity` | `divine.fire_storm` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x52e:ability[0].effect[24].resource` |
| `arcane.level9.absolute_immunity` | `divine.fire_trap` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x4ce:ability[0].effect[22].resource` |
| `arcane.level9.absolute_immunity` | `divine.flame_strike` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x4fe:ability[0].effect[23].resource` |
| `arcane.level9.absolute_immunity` | `divine.glyph_of_warding` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x43e:ability[0].effect[19].resource` |
| `arcane.level9.absolute_immunity` | `divine.holy_smite` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x6de:ability[0].effect[33].resource` |
| `arcane.level9.absolute_immunity` | `divine.ice_storm` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x37e:ability[0].effect[15].resource` |
| `arcane.level9.absolute_immunity` | `divine.unholy_blight` | 1 | `direct` | `spell_rev/spwi9##/spwi907.spl:0x70e:ability[0].effect[34].resource` |
| `arcane.level9.shapechange` | `arcane.level4.polymorph_self` | 1 | `direct` | `spell_rev/spwi9##/spwi916.spl:0x37e:ability[0].effect[15].resource` |
| `arcane.level9.shapechange` | `arcane.level8.ghostform` | 1 | `direct` | `spell_rev/spwi9##/spwi916.spl:0x3ae:ability[0].effect[16].resource` |
| `arcane.level10.summon_planetar` | `arcane.level3.lightning_bolt` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x4a6:equipped_effect[22].resource` |
| `arcane.level10.summon_planetar` | `arcane.level4.ice_storm` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x3e6:equipped_effect[18].resource` |
| `arcane.level10.summon_planetar` | `arcane.level5.cloudkill` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x566:equipped_effect[26].resource` |
| `arcane.level10.summon_planetar` | `arcane.level5.cone_of_cold` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x416:equipped_effect[19].resource` |
| `arcane.level10.summon_planetar` | `arcane.level6.chain_lightning` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x4d6:equipped_effect[23].resource` |
| `arcane.level10.summon_planetar` | `arcane.level9.larlochs_energy_drain` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x506:equipped_effect[24].resource` |
| `arcane.level10.summon_planetar` | `divine.aid` | 4 | `direct` | `spell_rev/spwi9##/plangood.cre:0x2ec:known_spell[2]` |
| `arcane.level10.summon_planetar` | `divine.blade_barrier` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x394:known_spell[16]` |
| `arcane.level10.summon_planetar` | `divine.bless` | 4 | `direct` | `spell_rev/spwi9##/plangood.cre:0x2d4:known_spell[0]` |
| `arcane.level10.summon_planetar` | `divine.bolt_of_glory` | 2 | `direct` | `spell_rev/spwi9##/plangood.cre:0x3ac:known_spell[18]` |
| `arcane.level10.summon_planetar` | `divine.break_enchantment` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x31c:known_spell[6]` |
| `arcane.level10.summon_planetar` | `divine.call_lightning` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x446:equipped_effect[20].resource` |
| `arcane.level10.summon_planetar` | `divine.chaotic_commands` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x388:known_spell[15]` |
| `arcane.level10.summon_planetar` | `divine.cure_disease` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x334:known_spell[8]` |
| `arcane.level10.summon_planetar` | `divine.cure_wounds_progression` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x340:known_spell[9]` |
| `arcane.level10.summon_planetar` | `divine.death_ward` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x364:known_spell[12]` |
| `arcane.level10.summon_planetar` | `divine.draw_upon_divine_might` | 2 | `direct` | `spell_rev/spwi9##/plangood.cre:0x310:known_spell[5]` |
| `arcane.level10.summon_planetar` | `divine.find_traps` | 2 | `direct` | `spell_rev/spwi9##/plangood.cre:0x2f8:known_spell[3]` |
| `arcane.level10.summon_planetar` | `divine.glyph_of_warding` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x476:equipped_effect[21].resource` |
| `arcane.level10.summon_planetar` | `divine.greater_restoration` | 2 | `direct` | `spell_rev/spwi9##/plangood.cre:0x3c4:known_spell[20]` |
| `arcane.level10.summon_planetar` | `divine.heal` | 2 | `direct` | `spell_rev/spwi9##/plangood.cre:0x3a0:known_spell[17]` |
| `arcane.level10.summon_planetar` | `divine.holy_smite` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x328:known_spell[7]` |
| `arcane.level10.summon_planetar` | `divine.holy_word` | 2 | `direct` | `spell_rev/spwi9##/plangood.cre:0x3b8:known_spell[19]` |
| `arcane.level10.summon_planetar` | `divine.ice_storm` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x3b6:equipped_effect[17].resource` |
| `arcane.level10.summon_planetar` | `divine.know_opponent` | 2 | `direct` | `spell_rev/spwi9##/plangood.cre:0x304:known_spell[4]` |
| `arcane.level10.summon_planetar` | `divine.magic_circle_against_evil` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x358:known_spell[11]` |
| `arcane.level10.summon_planetar` | `divine.neutralize_poison` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x34c:known_spell[10]` |
| `arcane.level10.summon_planetar` | `divine.poison` | 1 | `direct` | `spell_rev/spwi9##/dvplangr.itm:0x536:equipped_effect[25].resource` |
| `arcane.level10.summon_planetar` | `divine.raise_dead` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x370:known_spell[13]` |
| `arcane.level10.summon_planetar` | `divine.resist_fear` | 4 | `direct` | `spell_rev/spwi9##/plangood.cre:0x2e0:known_spell[1]` |
| `arcane.level10.summon_planetar` | `divine.true_seeing` | 3 | `direct` | `spell_rev/spwi9##/plangood.cre:0x37c:known_spell[14]` |
| `arcane.level10.summon_dark_planetar` | `arcane.level1.burning_hands` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x446:equipped_effect[20].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level2.agannazars_scorcher` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x476:equipped_effect[21].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x4a6:equipped_effect[22].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level3.lightning_bolt` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x5f6:equipped_effect[29].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level5.cloudkill` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x6b6:equipped_effect[33].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x4d6:equipped_effect[23].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level6.chain_lightning` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x626:equipped_effect[30].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x506:equipped_effect[24].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x536:equipped_effect[25].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level9.larlochs_energy_drain` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x656:equipped_effect[31].resource` |
| `arcane.level10.summon_dark_planetar` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x566:equipped_effect[26].resource` |
| `arcane.level10.summon_dark_planetar` | `divine.blade_barrier` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x394:known_spell[16]` |
| `arcane.level10.summon_dark_planetar` | `divine.break_enchantment` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x31c:known_spell[6]` |
| `arcane.level10.summon_dark_planetar` | `divine.call_lightning` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x596:equipped_effect[27].resource` |
| `arcane.level10.summon_dark_planetar` | `divine.cause_wounds_progression` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x358:known_spell[11]` |
| `arcane.level10.summon_dark_planetar` | `divine.cloak_of_fear` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x364:known_spell[12]` |
| `arcane.level10.summon_dark_planetar` | `divine.contagion` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x328:known_spell[7]` |
| `arcane.level10.summon_dark_planetar` | `divine.dolorous_decay` | 2 | `direct` | `spell_rev/spwi9##/planevil.cre:0x3ac:known_spell[18]` |
| `arcane.level10.summon_dark_planetar` | `divine.doom` | 4 | `direct` | `spell_rev/spwi9##/planevil.cre:0x2d4:known_spell[0]` |
| `arcane.level10.summon_dark_planetar` | `divine.find_traps` | 2 | `direct` | `spell_rev/spwi9##/planevil.cre:0x2f8:known_spell[3]` |
| `arcane.level10.summon_dark_planetar` | `divine.fire_storm` | 3 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x416:equipped_effect[19].resource` |
| `arcane.level10.summon_dark_planetar` | `divine.fire_trap` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x3b6:equipped_effect[17].resource` |
| `arcane.level10.summon_dark_planetar` | `divine.flame_strike` | 4 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x3e6:equipped_effect[18].resource` |
| `arcane.level10.summon_dark_planetar` | `divine.glyph_of_warding` | 1 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x5c6:equipped_effect[28].resource` |
| `arcane.level10.summon_dark_planetar` | `divine.greater_command` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x388:known_spell[15]` |
| `arcane.level10.summon_dark_planetar` | `divine.harm` | 2 | `direct` | `spell_rev/spwi9##/planevil.cre:0x3a0:known_spell[17]` |
| `arcane.level10.summon_dark_planetar` | `divine.hold_person` | 4 | `direct` | `spell_rev/spwi9##/planevil.cre:0x2ec:known_spell[2]` |
| `arcane.level10.summon_dark_planetar` | `divine.know_opponent` | 2 | `direct` | `spell_rev/spwi9##/planevil.cre:0x304:known_spell[4]` |
| `arcane.level10.summon_dark_planetar` | `divine.mental_domination` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x340:known_spell[9]` |
| `arcane.level10.summon_dark_planetar` | `divine.poison` | 4 | `direct` | `spell_rev/spwi9##/dvplaner.itm:0x686:equipped_effect[32].resource` |
| `arcane.level10.summon_dark_planetar` | `divine.resist_fear` | 4 | `direct` | `spell_rev/spwi9##/planevil.cre:0x2e0:known_spell[1]` |
| `arcane.level10.summon_dark_planetar` | `divine.silence` | 2 | `direct` | `spell_rev/spwi9##/planevil.cre:0x310:known_spell[5]` |
| `arcane.level10.summon_dark_planetar` | `divine.true_seeing` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x37c:known_spell[14]` |
| `arcane.level10.summon_dark_planetar` | `divine.unholy_blight` | 3 | `direct` | `spell_rev/spwi9##/planevil.cre:0x334:known_spell[8]` |
| `arcane.level10.summon_dark_planetar` | `divine.unholy_word` | 2 | `direct` | `spell_rev/spwi9##/planevil.cre:0x3b8:known_spell[19]` |
| `divine.faerie_fire` | `arcane.level2.glitterdust` | 1 | `direct` | `spell_rev/sppr1##/sppr114.spl:0x58e:ability[0].effect[26].resource` |
| `divine.strength_of_stone` | `divine.insects_and_gust_of_wind` | 1 | `direct` | `spell_rev/sppr1##/sppr115.spl:0x16e:ability[0].effect[4].resource` |
| `divine.regenerate_light_wounds` | `divine.regenerate_moderate_wounds` | 10 | `direct` | `spell_rev/sppr1##/sppr117.spl:0x3c6:ability[0].effect[9].resource` |
| `divine.regenerate_light_wounds` | `divine.regenerate_serious_wounds` | 10 | `direct` | `spell_rev/sppr1##/sppr117.spl:0x3f6:ability[0].effect[10].resource` |
| `divine.regenerate_light_wounds` | `divine.regenerate_critical_wounds` | 10 | `direct` | `spell_rev/sppr1##/sppr117.spl:0x426:ability[0].effect[11].resource` |
| `divine.regenerate_light_wounds` | `divine.mass_regenerate` | 10 | `reverse-family` | `spell_rev/sppr5##/sppr524.spl:0x396:ability[0].effect[8].resource` |
| `divine.regenerate_light_wounds` | `divine.regeneration_druid` | 10 | `direct` | `spell_rev/sppr1##/sppr117.spl:0x336:ability[0].effect[6].resource` |
| `divine.regenerate_light_wounds` | `divine.regeneration` | 10 | `direct` | `spell_rev/sppr1##/sppr117.spl:0x366:ability[0].effect[7].resource` |
| `divine.animal_summoning_i` | `divine.entangle` | 1 | `direct` | `spell_rev/sppr1##/batsu.itm:0x17e:equipped_effect[4].resource` |
| `divine.animal_summoning_i` | `divine.obscuring_mist` | 1 | `direct` | `spell_rev/sppr1##/batsu.itm:0x1ae:equipped_effect[5].resource` |
| `divine.animal_summoning_i` | `arcane.level1.grease` | 1 | `direct` | `spell_rev/sppr1##/batsu.itm:0x11e:equipped_effect[2].resource` |
| `divine.animal_summoning_i` | `arcane.level1.obscuring_mist` | 1 | `direct` | `spell_rev/sppr1##/batsu.itm:0x14e:equipped_effect[3].resource` |
| `divine.know_opponent` | `arcane.level2.know_opponent` | 1 | `direct` | `spell_rev/sppr2##/sppr209.spl:0x2be:ability[0].effect[11].resource` |
| `divine.resist_elements` | `arcane.elemental_protection_progression` | 18 | `direct` | `spell_rev/sppr2##/sppr210.spl:0x4d6:ability[0].effect[8].resource` |
| `divine.regenerate_moderate_wounds` | `divine.regenerate_critical_wounds` | 10 | `direct` | `spell_rev/sppr2##/sppr217.spl:0x426:ability[0].effect[11].resource` |
| `divine.regenerate_moderate_wounds` | `divine.regenerate_light_wounds` | 10 | `direct` | `spell_rev/sppr2##/sppr217.spl:0x396:ability[0].effect[8].resource` |
| `divine.regenerate_moderate_wounds` | `divine.regenerate_serious_wounds` | 10 | `direct` | `spell_rev/sppr2##/sppr217.spl:0x3f6:ability[0].effect[10].resource` |
| `divine.regenerate_moderate_wounds` | `divine.regeneration` | 10 | `direct` | `spell_rev/sppr2##/sppr217.spl:0x366:ability[0].effect[7].resource` |
| `divine.regenerate_moderate_wounds` | `divine.regeneration_druid` | 10 | `direct` | `spell_rev/sppr2##/sppr217.spl:0x336:ability[0].effect[6].resource` |
| `divine.elemental_protections` | `divine.call_lightning` | 24 | `direct` | `spell_rev/sppr4##/sppr407.spl:0x386:ability[0].effect[6].resource` |
| `divine.elemental_protections` | `divine.fire_storm` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x416:ability[0].effect[9].resource` |
| `divine.elemental_protections` | `divine.fire_trap` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x3b6:ability[0].effect[7].resource` |
| `divine.elemental_protections` | `divine.flame_strike` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x3e6:ability[0].effect[8].resource` |
| `divine.elemental_protections` | `divine.glyph_of_warding` | 24 | `direct` | `spell_rev/sppr4##/sppr407.spl:0x3b6:ability[0].effect[7].resource` |
| `divine.elemental_protections` | `divine.ice_storm` | 12 | `direct` | `spell_rev/sppr5##/sppr521.spl:0x3b6:ability[0].effect[7].resource` |
| `divine.elemental_protections` | `arcane.level1.burning_hands` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x446:ability[0].effect[10].resource` |
| `divine.elemental_protections` | `arcane.level2.agannazars_scorcher` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x476:ability[0].effect[11].resource` |
| `divine.elemental_protections` | `arcane.level2.melfs_acid_arrow` | 12 | `direct` | `spell_rev/sppr5##/sppr520.spl:0x3b6:ability[0].effect[7].resource` |
| `divine.elemental_protections` | `arcane.level3.fireball` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x4d6:ability[0].effect[13].resource` |
| `divine.elemental_protections` | `arcane.level3.flame_arrow` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x4a6:ability[0].effect[12].resource` |
| `divine.elemental_protections` | `arcane.level3.lightning_bolt` | 24 | `direct` | `spell_rev/sppr4##/sppr407.spl:0x3e6:ability[0].effect[8].resource` |
| `divine.elemental_protections` | `arcane.level4.ice_storm` | 12 | `direct` | `spell_rev/sppr5##/sppr521.spl:0x3e6:ability[0].effect[8].resource` |
| `divine.elemental_protections` | `arcane.level5.cone_of_cold` | 12 | `direct` | `spell_rev/sppr5##/sppr521.spl:0x416:ability[0].effect[9].resource` |
| `divine.elemental_protections` | `arcane.level5.fireburst` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x506:ability[0].effect[14].resource` |
| `divine.elemental_protections` | `arcane.level6.acid_fog` | 12 | `direct` | `spell_rev/sppr5##/sppr520.spl:0x3e6:ability[0].effect[8].resource` |
| `divine.elemental_protections` | `arcane.level6.chain_lightning` | 24 | `direct` | `spell_rev/sppr4##/sppr407.spl:0x416:ability[0].effect[9].resource` |
| `divine.elemental_protections` | `arcane.level7.delayed_blast_fireball` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x536:ability[0].effect[15].resource` |
| `divine.elemental_protections` | `arcane.level8.incendiary_cloud` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x566:ability[0].effect[16].resource` |
| `divine.elemental_protections` | `arcane.level9.meteor_swarm` | 24 | `direct` | `spell_rev/sppr3##/sppr306.spl:0x596:ability[0].effect[17].resource` |
| `divine.storm_shield` | `divine.insects_and_gust_of_wind` | 12 | `direct` | `spell_rev/shared/spcl721.spl:0x40e:ability[0].effect[18].resource` |
| `divine.storm_shield` | `arcane.level2.stinking_cloud` | 2 | `direct` | `spell_rev/shared/spcl721.spl:0x34e:ability[0].effect[14].resource` |
| `divine.storm_shield` | `arcane.level5.cloudkill` | 2 | `direct` | `spell_rev/shared/spcl721.spl:0x37e:ability[0].effect[15].resource` |
| `divine.storm_shield` | `arcane.level6.acid_fog` | 2 | `direct` | `spell_rev/shared/spcl721.spl:0x3de:ability[0].effect[17].resource` |
| `divine.storm_shield` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/sppr3##/sppr322.spl:0x52e:ability[0].effect[24].resource` |
| `divine.regenerate_serious_wounds` | `divine.regenerate_critical_wounds` | 10 | `direct` | `spell_rev/sppr3##/sppr323.spl:0x426:ability[0].effect[11].resource` |
| `divine.regenerate_serious_wounds` | `divine.regenerate_light_wounds` | 10 | `direct` | `spell_rev/sppr3##/sppr323.spl:0x396:ability[0].effect[8].resource` |
| `divine.regenerate_serious_wounds` | `divine.regenerate_moderate_wounds` | 10 | `direct` | `spell_rev/sppr3##/sppr323.spl:0x3c6:ability[0].effect[9].resource` |
| `divine.regenerate_serious_wounds` | `divine.regeneration` | 10 | `direct` | `spell_rev/sppr3##/sppr323.spl:0x366:ability[0].effect[7].resource` |
| `divine.regenerate_serious_wounds` | `divine.regeneration_druid` | 10 | `direct` | `spell_rev/sppr3##/sppr323.spl:0x336:ability[0].effect[6].resource` |
| `divine.magic_fang` | `divine.entangle` | 6 | `direct` | `spell_rev/sppr3##/mfang/batm1.itm:0x17e:equipped_effect[4].resource` |
| `divine.magic_fang` | `divine.ice_storm` | 3 | `direct` | `spell_rev/sppr3##/mfang/bearpom1.itm:0xbe:equipped_effect[0].resource` |
| `divine.magic_fang` | `divine.obscuring_mist` | 3 | `direct` | `spell_rev/sppr3##/mfang/batm1.itm:0x1ae:equipped_effect[5].resource` |
| `divine.magic_fang` | `arcane.level1.grease` | 6 | `direct` | `spell_rev/sppr3##/mfang/batm1.itm:0x11e:equipped_effect[2].resource` |
| `divine.magic_fang` | `arcane.level1.obscuring_mist` | 3 | `direct` | `spell_rev/sppr3##/mfang/batm1.itm:0x14e:equipped_effect[3].resource` |
| `divine.magic_fang` | `arcane.level2.web` | 3 | `direct` | `spell_rev/sppr3##/mfang/snakegm1.itm:0x11e:equipped_effect[2].resource` |
| `divine.magic_fang` | `arcane.level4.ice_storm` | 3 | `direct` | `spell_rev/sppr3##/mfang/bearpom1.itm:0xee:equipped_effect[1].resource` |
| `divine.magic_fang` | `arcane.level5.cloudkill` | 3 | `direct` | `spell_rev/sppr3##/mfang/snakegm1.itm:0x29e:equipped_effect[10].resource` |
| `divine.free_action` | `divine.entangle` | 14 | `direct` | `spell_rev/sppr4##/sppr403.spl:0x856:ability[0].effect[30].resource` |
| `divine.free_action` | `arcane.haste_slow` | 14 | `direct` | `spell_rev/sppr4##/sppr403.spl:0x886:ability[0].effect[31].resource` |
| `divine.free_action` | `arcane.level1.grease` | 14 | `direct` | `spell_rev/sppr4##/sppr403.spl:0x826:ability[0].effect[29].resource` |
| `divine.free_action` | `arcane.level2.web` | 14 | `direct` | `spell_rev/sppr4##/sppr403.spl:0x8e6:ability[0].effect[33].resource` |
| `divine.free_action` | `arcane.level4.otilukes_resilient_sphere` | 14 | `direct` | `spell_rev/sppr4##/sppr403.spl:0x8b6:ability[0].effect[32].resource` |
| `divine.neutralize_poison` | `divine.poison` | 14 | `direct` | `spell_rev/sppr4##/sppr404.spl:0x496:ability[0].effect[10].resource` |
| `divine.neutralize_poison` | `arcane.level5.cloudkill` | 14 | `direct` | `spell_rev/sppr4##/sppr404.spl:0x4c6:ability[0].effect[11].resource` |
| `divine.death_ward` | `arcane.level6.disintegrate` | 14 | `direct` | `spell_rev/sppr4##/sppr409.spl:0x406:ability[0].effect[7].resource` |
| `divine.call_woodland_beings` | `divine.animal_summoning_iv` | 2 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x358:known_spell[11]` |
| `divine.call_woodland_beings` | `divine.barkskin` | 4 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x304:known_spell[4]` |
| `divine.call_woodland_beings` | `divine.call_lightning` | 2 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x334:known_spell[8]` |
| `divine.call_woodland_beings` | `divine.charm_person_or_animal` | 6 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x310:known_spell[5]` |
| `divine.call_woodland_beings` | `divine.cure_wounds_progression` | 6 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x2d4:known_spell[0]` |
| `divine.call_woodland_beings` | `divine.doom` | 4 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x2f8:known_spell[3]` |
| `divine.call_woodland_beings` | `divine.entangle` | 6 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x2e0:known_spell[1]` |
| `divine.call_woodland_beings` | `divine.hold_person_or_animal` | 2 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x340:known_spell[9]` |
| `divine.call_woodland_beings` | `divine.insects_and_gust_of_wind` | 2 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x34c:known_spell[10]` |
| `divine.call_woodland_beings` | `divine.resist_elements` | 4 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x31c:known_spell[6]` |
| `divine.call_woodland_beings` | `divine.shillelagh` | 4 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x2ec:known_spell[2]` |
| `divine.call_woodland_beings` | `divine.slow_poison` | 4 | `direct` | `spell_rev/sppr4##/dvnymph.cre:0x328:known_spell[7]` |
| `divine.call_woodland_beings` | `arcane.dimension_jump_relocation` | 6 | `direct` | `spell_rev/sppr4##/hamasu.cre:0x4ec:memorized_spell[14]` |
| `divine.call_woodland_beings` | `arcane.level3.dire_charm` | 3 | `direct` | `spell_rev/sppr4##/hamasu.cre:0x4c8:memorized_spell[11]` |
| `divine.regenerate_critical_wounds` | `divine.regenerate_light_wounds` | 10 | `direct` | `spell_rev/sppr4##/sppr419.spl:0x3c6:ability[0].effect[9].resource` |
| `divine.regenerate_critical_wounds` | `divine.regenerate_moderate_wounds` | 10 | `direct` | `spell_rev/sppr4##/sppr419.spl:0x3f6:ability[0].effect[10].resource` |
| `divine.regenerate_critical_wounds` | `divine.regenerate_serious_wounds` | 10 | `direct` | `spell_rev/sppr4##/sppr419.spl:0x426:ability[0].effect[11].resource` |
| `divine.regenerate_critical_wounds` | `divine.regeneration` | 10 | `direct` | `spell_rev/sppr4##/sppr419.spl:0x396:ability[0].effect[8].resource` |
| `divine.regenerate_critical_wounds` | `divine.regeneration_druid` | 10 | `direct` | `spell_rev/sppr4##/sppr419.spl:0x366:ability[0].effect[7].resource` |
| `divine.animal_summoning_v` | `divine.entangle` | 1 | `direct` | `spell_rev/sppr5##/snakegsu.itm:0xbe:equipped_effect[0].resource` |
| `divine.animal_summoning_v` | `arcane.level1.grease` | 1 | `direct` | `spell_rev/sppr5##/snakegsu.itm:0xee:equipped_effect[1].resource` |
| `divine.animal_summoning_v` | `arcane.level2.web` | 1 | `direct` | `spell_rev/sppr5##/snakegsu.itm:0x11e:equipped_effect[2].resource` |
| `divine.animal_summoning_v` | `arcane.level5.cloudkill` | 1 | `direct` | `spell_rev/sppr5##/snakegsu.itm:0x29e:equipped_effect[10].resource` |
| `divine.raise_dead` | `arcane.level4.simbuls_spell_matrix` | 1 | `direct` | `spell_rev/sppr5##/sppr504.spl:0x52e:ability[0].effect[24].resource` |
| `divine.raise_dead` | `arcane.level7.simbuls_spell_sequencer` | 1 | `direct` | `spell_rev/sppr5##/sppr504.spl:0x58e:ability[0].effect[26].resource` |
| `divine.raise_dead` | `arcane.level8.simbuls_spell_trigger` | 1 | `direct` | `spell_rev/sppr5##/sppr504.spl:0x55e:ability[0].effect[25].resource` |
| `divine.true_seeing` | `divine.obscuring_mist` | 1 | `direct` | `spell_rev/sppr5##/sppr505.spl:0x58e:ability[0].effect[26].resource` |
| `divine.true_seeing` | `arcane.level1.obscuring_mist` | 2 | `direct` | `spell_rev/sppr5##/sppr505.spl:0x4fe:ability[0].effect[23].resource` |
| `divine.true_seeing` | `arcane.level1.spook` | 1 | `direct` | `spell_rev/sppr5##/sppr505.spl:0x52e:ability[0].effect[24].resource` |
| `divine.true_seeing` | `arcane.level5.shadow_door` | 1 | `direct` | `spell_rev/sppr5##/sppr505.spl:0x55e:ability[0].effect[25].resource` |
| `divine.chaotic_commands` | `divine.charm_person_or_animal` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x536:ability[0].effect[15].resource` |
| `divine.chaotic_commands` | `divine.command` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x566:ability[0].effect[16].resource` |
| `divine.chaotic_commands` | `divine.greater_command` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x476:ability[0].effect[11].resource` |
| `divine.chaotic_commands` | `divine.hold_person_or_animal` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x4d6:ability[0].effect[13].resource` |
| `divine.chaotic_commands` | `divine.hold_person` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x506:ability[0].effect[14].resource` |
| `divine.chaotic_commands` | `divine.mental_domination` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x4a6:ability[0].effect[12].resource` |
| `divine.chaotic_commands` | `arcane.level1.charm_person` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x446:ability[0].effect[10].resource` |
| `divine.chaotic_commands` | `arcane.level1.sleep` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x416:ability[0].effect[9].resource` |
| `divine.chaotic_commands` | `arcane.level2.power_word_sleep` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x3e6:ability[0].effect[8].resource` |
| `divine.chaotic_commands` | `arcane.level3.dire_charm` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x386:ability[0].effect[6].resource` |
| `divine.chaotic_commands` | `arcane.level3.hold_person` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x3b6:ability[0].effect[7].resource` |
| `divine.chaotic_commands` | `arcane.level4.confusion` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x356:ability[0].effect[5].resource` |
| `divine.chaotic_commands` | `arcane.level5.domination` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x326:ability[0].effect[4].resource` |
| `divine.chaotic_commands` | `arcane.level5.feeblemind` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x296:ability[0].effect[1].resource` |
| `divine.chaotic_commands` | `arcane.level5.hold_monster` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x2f6:ability[0].effect[3].resource` |
| `divine.chaotic_commands` | `arcane.level5.waves_of_fatigue` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x2c6:ability[0].effect[2].resource` |
| `divine.chaotic_commands` | `arcane.level7.power_word_stun` | 12 | `direct` | `spell_rev/sppr5##/sppr508.spl:0x266:ability[0].effect[0].resource` |
| `divine.mass_regenerate` | `divine.regenerate_critical_wounds` | 10 | `direct` | `spell_rev/sppr5##/sppr524.spl:0x426:ability[0].effect[11].resource` |
| `divine.mass_regenerate` | `divine.regenerate_light_wounds` | 10 | `direct` | `spell_rev/sppr5##/sppr524.spl:0x396:ability[0].effect[8].resource` |
| `divine.mass_regenerate` | `divine.regenerate_moderate_wounds` | 10 | `direct` | `spell_rev/sppr5##/sppr524.spl:0x3c6:ability[0].effect[9].resource` |
| `divine.mass_regenerate` | `divine.regenerate_serious_wounds` | 10 | `direct` | `spell_rev/sppr5##/sppr524.spl:0x3f6:ability[0].effect[10].resource` |
| `divine.mass_regenerate` | `divine.regeneration` | 10 | `direct` | `spell_rev/sppr5##/sppr524.spl:0x366:ability[0].effect[7].resource` |
| `divine.mass_regenerate` | `divine.regeneration_druid` | 10 | `direct` | `spell_rev/sppr5##/sppr524.spl:0x336:ability[0].effect[6].resource` |
| `divine.harpers_call` | `arcane.level4.simbuls_spell_matrix` | 1 | `direct` | `spell_rev/sppr5##/spja01.spl:0x67e:ability[0].effect[31].resource` |
| `divine.harpers_call` | `arcane.level7.simbuls_spell_sequencer` | 1 | `direct` | `spell_rev/sppr5##/spja01.spl:0x6de:ability[0].effect[33].resource` |
| `divine.harpers_call` | `arcane.level8.simbuls_spell_trigger` | 1 | `direct` | `spell_rev/sppr5##/spja01.spl:0x6ae:ability[0].effect[32].resource` |
| `divine.blade_barrier` | `divine.globe_of_blades` | 2 | `direct` | `spell_rev/sppr6##/sppr603.spl:0x3ae:ability[0].effect[16].resource` |
| `divine.regeneration_druid` | `divine.cause_wounds_progression` | 1 | `direct` | `spell_rev/sppr6##/sppr619.spl:0x1fe:ability[0].effect[7].resource` |
| `divine.regeneration_druid` | `divine.insects_and_gust_of_wind` | 1 | `direct` | `spell_rev/sppr6##/sppr619.spl:0x22e:ability[0].effect[8].resource` |
| `divine.regeneration_druid` | `divine.magic_fang` | 1 | `direct` | `spell_rev/sppr6##/sppr619.spl:0x25e:ability[0].effect[9].resource` |
| `divine.regeneration_druid` | `divine.regenerate_critical_wounds` | 1 | `direct` | `spell_rev/sppr6##/sppr619.spl:0x28e:ability[0].effect[10].resource` |
| `divine.regeneration_druid` | `divine.regeneration` | 1 | `direct` | `spell_rev/sppr6##/sppr619.spl:0x1ce:ability[0].effect[6].resource` |
| `divine.regeneration` | `divine.cause_wounds_progression` | 1 | `direct` | `spell_rev/sppr7##/sppr711.spl:0x28e:ability[0].effect[10].resource` |
| `divine.regeneration` | `divine.insects_and_gust_of_wind` | 1 | `direct` | `spell_rev/sppr7##/sppr711.spl:0x25e:ability[0].effect[9].resource` |
| `divine.regeneration` | `divine.magic_fang` | 1 | `direct` | `spell_rev/sppr7##/sppr711.spl:0x22e:ability[0].effect[8].resource` |
| `divine.regeneration` | `divine.regenerate_critical_wounds` | 1 | `direct` | `spell_rev/sppr7##/sppr711.spl:0x1fe:ability[0].effect[7].resource` |
| `divine.regeneration` | `divine.regeneration_druid` | 1 | `direct` | `spell_rev/sppr7##/sppr711.spl:0x19e:ability[0].effect[5].resource` |
| `divine.resurrection` | `arcane.detect_alignment_relocation` | 1 | `direct` | `spell_rev/sppr7##/sppr712.spl:0x2be:ability[0].effect[11].resource` |
| `divine.resurrection` | `arcane.level4.simbuls_spell_matrix` | 1 | `direct` | `spell_rev/sppr7##/sppr712.spl:0x55e:ability[0].effect[25].resource` |
| `divine.resurrection` | `arcane.level7.simbuls_spell_sequencer` | 1 | `direct` | `spell_rev/sppr7##/sppr712.spl:0x5be:ability[0].effect[27].resource` |
| `divine.resurrection` | `arcane.level8.simbuls_spell_trigger` | 1 | `direct` | `spell_rev/sppr7##/sppr712.spl:0x58e:ability[0].effect[26].resource` |
| `divine.greater_restoration` | `divine.polymorph_other` | 1 | `direct` | `spell_rev/sppr7##/sppr713.spl:0x43e:ability[0].effect[19].resource` |
| `divine.animal_summoning_vii` | `divine.ice_storm` | 1 | `direct` | `spell_rev/sppr7##/bearposu.itm:0xbe:equipped_effect[0].resource` |
| `divine.animal_summoning_vii` | `arcane.level4.ice_storm` | 1 | `direct` | `spell_rev/sppr7##/bearposu.itm:0xee:equipped_effect[1].resource` |
| `divine.globe_of_blades` | `divine.blade_barrier` | 1 | `direct` | `spell_rev/sppr7##/sppr725.spl:0x37e:ability[0].effect[15].resource` |
| `divine.summon_deva` | `divine.aid` | 4 | `direct` | `spell_rev/sppr7##/devagood.cre:0x2ec:known_spell[2]` |
| `divine.summon_deva` | `divine.blade_barrier` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x388:known_spell[15]` |
| `divine.summon_deva` | `divine.bless` | 4 | `direct` | `spell_rev/sppr7##/devagood.cre:0x2d4:known_spell[0]` |
| `divine.summon_deva` | `divine.break_enchantment` | 3 | `direct` | `spell_rev/sppr7##/devagood.cre:0x31c:known_spell[6]` |
| `divine.summon_deva` | `divine.call_lightning` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x3b6:equipped_effect[17].resource` |
| `divine.summon_deva` | `divine.cure_disease` | 3 | `direct` | `spell_rev/sppr7##/devagood.cre:0x334:known_spell[8]` |
| `divine.summon_deva` | `divine.cure_wounds_progression` | 3 | `direct` | `spell_rev/sppr7##/devagood.cre:0x340:known_spell[9]` |
| `divine.summon_deva` | `divine.draw_upon_divine_might` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x310:known_spell[5]` |
| `divine.summon_deva` | `divine.find_traps` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x2f8:known_spell[3]` |
| `divine.summon_deva` | `divine.glyph_of_warding` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x3e6:equipped_effect[18].resource` |
| `divine.summon_deva` | `divine.heal` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x394:known_spell[16]` |
| `divine.summon_deva` | `divine.holy_smite` | 3 | `direct` | `spell_rev/sppr7##/devagood.cre:0x328:known_spell[7]` |
| `divine.summon_deva` | `divine.holy_word` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x3a0:known_spell[17]` |
| `divine.summon_deva` | `divine.ice_storm` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x326:equipped_effect[14].resource` |
| `divine.summon_deva` | `divine.know_opponent` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x304:known_spell[4]` |
| `divine.summon_deva` | `divine.magic_circle_against_evil` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x358:known_spell[11]` |
| `divine.summon_deva` | `divine.mass_cure` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x37c:known_spell[14]` |
| `divine.summon_deva` | `divine.neutralize_poison` | 3 | `direct` | `spell_rev/sppr7##/devagood.cre:0x34c:known_spell[10]` |
| `divine.summon_deva` | `divine.poison` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x4a6:equipped_effect[22].resource` |
| `divine.summon_deva` | `divine.raise_dead` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x364:known_spell[12]` |
| `divine.summon_deva` | `divine.resist_fear` | 4 | `direct` | `spell_rev/sppr7##/devagood.cre:0x2e0:known_spell[1]` |
| `divine.summon_deva` | `divine.true_seeing` | 2 | `direct` | `spell_rev/sppr7##/devagood.cre:0x370:known_spell[13]` |
| `divine.summon_deva` | `arcane.level3.lightning_bolt` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x416:equipped_effect[19].resource` |
| `divine.summon_deva` | `arcane.level4.ice_storm` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x356:equipped_effect[15].resource` |
| `divine.summon_deva` | `arcane.level5.cloudkill` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x4d6:equipped_effect[23].resource` |
| `divine.summon_deva` | `arcane.level5.cone_of_cold` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x386:equipped_effect[16].resource` |
| `divine.summon_deva` | `arcane.level6.chain_lightning` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x446:equipped_effect[20].resource` |
| `divine.summon_deva` | `arcane.level9.larlochs_energy_drain` | 1 | `direct` | `spell_rev/sppr7##/dvdevagr.itm:0x476:equipped_effect[21].resource` |
| `divine.summon_fallen_deva` | `divine.blade_barrier` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x388:known_spell[15]` |
| `divine.summon_fallen_deva` | `divine.break_enchantment` | 3 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x328:known_spell[7]` |
| `divine.summon_fallen_deva` | `divine.call_lightning` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x506:equipped_effect[24].resource` |
| `divine.summon_fallen_deva` | `divine.cause_wounds_progression` | 3 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x340:known_spell[9]` |
| `divine.summon_fallen_deva` | `divine.cloak_of_fear` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x358:known_spell[11]` |
| `divine.summon_fallen_deva` | `divine.contagion` | 3 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x31c:known_spell[6]` |
| `divine.summon_fallen_deva` | `divine.doom` | 4 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x2d4:known_spell[0]` |
| `divine.summon_fallen_deva` | `divine.find_traps` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x2f8:known_spell[3]` |
| `divine.summon_fallen_deva` | `divine.fire_storm` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x386:equipped_effect[16].resource` |
| `divine.summon_fallen_deva` | `divine.fire_trap` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x326:equipped_effect[14].resource` |
| `divine.summon_fallen_deva` | `divine.flame_strike` | 3 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x364:known_spell[12]` |
| `divine.summon_fallen_deva` | `divine.glyph_of_warding` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x536:equipped_effect[25].resource` |
| `divine.summon_fallen_deva` | `divine.greater_command` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x37c:known_spell[14]` |
| `divine.summon_fallen_deva` | `divine.harm` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x394:known_spell[16]` |
| `divine.summon_fallen_deva` | `divine.hold_person` | 4 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x2ec:known_spell[2]` |
| `divine.summon_fallen_deva` | `divine.know_opponent` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x304:known_spell[4]` |
| `divine.summon_fallen_deva` | `divine.poison` | 4 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x34c:known_spell[10]` |
| `divine.summon_fallen_deva` | `divine.resist_fear` | 4 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x2e0:known_spell[1]` |
| `divine.summon_fallen_deva` | `divine.silence` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x310:known_spell[5]` |
| `divine.summon_fallen_deva` | `divine.true_seeing` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x370:known_spell[13]` |
| `divine.summon_fallen_deva` | `divine.unholy_blight` | 3 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x334:known_spell[8]` |
| `divine.summon_fallen_deva` | `divine.unholy_word` | 2 | `direct` | `spell_rev/sppr7##/devaevil.cre:0x3a0:known_spell[17]` |
| `divine.summon_fallen_deva` | `arcane.level1.burning_hands` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x3b6:equipped_effect[17].resource` |
| `divine.summon_fallen_deva` | `arcane.level2.agannazars_scorcher` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x3e6:equipped_effect[18].resource` |
| `divine.summon_fallen_deva` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x416:equipped_effect[19].resource` |
| `divine.summon_fallen_deva` | `arcane.level3.lightning_bolt` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x566:equipped_effect[26].resource` |
| `divine.summon_fallen_deva` | `arcane.level5.cloudkill` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x626:equipped_effect[30].resource` |
| `divine.summon_fallen_deva` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x446:equipped_effect[20].resource` |
| `divine.summon_fallen_deva` | `arcane.level6.chain_lightning` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x596:equipped_effect[27].resource` |
| `divine.summon_fallen_deva` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x476:equipped_effect[21].resource` |
| `divine.summon_fallen_deva` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x4a6:equipped_effect[22].resource` |
| `divine.summon_fallen_deva` | `arcane.level9.larlochs_energy_drain` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x5c6:equipped_effect[28].resource` |
| `divine.summon_fallen_deva` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/sppr7##/dvdevaer.itm:0x4d6:equipped_effect[23].resource` |
| `divine.mass_raise_dead` | `arcane.detect_alignment_relocation` | 1 | `direct` | `spell_rev/sppr7##/sppr729.spl:0x28e:ability[0].effect[10].resource` |
| `divine.mass_raise_dead` | `arcane.level4.simbuls_spell_matrix` | 1 | `direct` | `spell_rev/sppr7##/sppr729.spl:0x5be:ability[0].effect[27].resource` |
| `divine.mass_raise_dead` | `arcane.level7.simbuls_spell_sequencer` | 1 | `direct` | `spell_rev/sppr7##/sppr729.spl:0x61e:ability[0].effect[29].resource` |
| `divine.mass_raise_dead` | `arcane.level8.simbuls_spell_trigger` | 1 | `direct` | `spell_rev/sppr7##/sppr729.spl:0x5ee:ability[0].effect[28].resource` |
| `divine.aura_of_flaming_death` | `divine.fire_storm` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x2be:ability[0].effect[11].resource` |
| `divine.aura_of_flaming_death` | `divine.fire_trap` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x25e:ability[0].effect[9].resource` |
| `divine.aura_of_flaming_death` | `divine.flame_strike` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x28e:ability[0].effect[10].resource` |
| `divine.aura_of_flaming_death` | `arcane.level1.burning_hands` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x2ee:ability[0].effect[12].resource` |
| `divine.aura_of_flaming_death` | `arcane.level2.agannazars_scorcher` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x31e:ability[0].effect[13].resource` |
| `divine.aura_of_flaming_death` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x37e:ability[0].effect[15].resource` |
| `divine.aura_of_flaming_death` | `arcane.level3.flame_arrow` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x34e:ability[0].effect[14].resource` |
| `divine.aura_of_flaming_death` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x3ae:ability[0].effect[16].resource` |
| `divine.aura_of_flaming_death` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x3de:ability[0].effect[17].resource` |
| `divine.aura_of_flaming_death` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x40e:ability[0].effect[18].resource` |
| `divine.aura_of_flaming_death` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/sppr7##/sppr730.spl:0x43e:ability[0].effect[19].resource` |
| `divine.fire_elemental_transformation` | `divine.earth_elemental_transformation` | 1 | `direct` | `spell_rev/sppr7##/sppr731.spl:0x13e:ability[0].effect[3].resource` |
| `divine.fire_elemental_transformation` | `divine.earthquake` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x89e:equipped_effect[42].resource` |
| `divine.fire_elemental_transformation` | `divine.entangle` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x80e:equipped_effect[39].resource` |
| `divine.fire_elemental_transformation` | `divine.fire_storm` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x47e:equipped_effect[20].resource` |
| `divine.fire_elemental_transformation` | `divine.fire_trap` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x41e:equipped_effect[18].resource` |
| `divine.fire_elemental_transformation` | `divine.flame_strike` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x44e:equipped_effect[19].resource` |
| `divine.fire_elemental_transformation` | `divine.natures_beauty` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x86e:equipped_effect[41].resource` |
| `divine.fire_elemental_transformation` | `divine.polymorph_other` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x83e:equipped_effect[40].resource` |
| `divine.fire_elemental_transformation` | `arcane.level1.burning_hands` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x4ae:equipped_effect[21].resource` |
| `divine.fire_elemental_transformation` | `arcane.level1.grease` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x8ce:equipped_effect[43].resource` |
| `divine.fire_elemental_transformation` | `arcane.level1.sleep` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x8fe:equipped_effect[44].resource` |
| `divine.fire_elemental_transformation` | `arcane.level2.agannazars_scorcher` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x4de:equipped_effect[22].resource` |
| `divine.fire_elemental_transformation` | `arcane.level2.power_word_sleep` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x95e:equipped_effect[46].resource` |
| `divine.fire_elemental_transformation` | `arcane.level2.web` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x92e:equipped_effect[45].resource` |
| `divine.fire_elemental_transformation` | `arcane.level3.fireball` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x50e:equipped_effect[23].resource` |
| `divine.fire_elemental_transformation` | `arcane.level4.polymorph_other` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x98e:equipped_effect[47].resource` |
| `divine.fire_elemental_transformation` | `arcane.level5.fireburst` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x53e:equipped_effect[24].resource` |
| `divine.fire_elemental_transformation` | `arcane.level7.delayed_blast_fireball` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x56e:equipped_effect[25].resource` |
| `divine.fire_elemental_transformation` | `arcane.level8.incendiary_cloud` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x59e:equipped_effect[26].resource` |
| `divine.fire_elemental_transformation` | `arcane.level9.meteor_swarm` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x5ce:equipped_effect[27].resource` |
| `divine.fire_elemental_transformation` | `arcane.petrification` | 1 | `direct` | `spell_rev/sppr7##/sppr731.itm:0x9be:equipped_effect[48].resource` |
| `divine.earth_elemental_transformation` | `divine.earthquake` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x65e:equipped_effect[30].resource` |
| `divine.earth_elemental_transformation` | `divine.entangle` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x5ce:equipped_effect[27].resource` |
| `divine.earth_elemental_transformation` | `divine.fire_elemental_transformation` | 1 | `direct` | `spell_rev/sppr7##/sppr732.spl:0x10e:ability[0].effect[2].resource` |
| `divine.earth_elemental_transformation` | `divine.natures_beauty` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x62e:equipped_effect[29].resource` |
| `divine.earth_elemental_transformation` | `divine.polymorph_other` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x5fe:equipped_effect[28].resource` |
| `divine.earth_elemental_transformation` | `arcane.level1.grease` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x68e:equipped_effect[31].resource` |
| `divine.earth_elemental_transformation` | `arcane.level1.sleep` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x6be:equipped_effect[32].resource` |
| `divine.earth_elemental_transformation` | `arcane.level2.power_word_sleep` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x71e:equipped_effect[34].resource` |
| `divine.earth_elemental_transformation` | `arcane.level2.web` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x6ee:equipped_effect[33].resource` |
| `divine.earth_elemental_transformation` | `arcane.level4.polymorph_other` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x74e:equipped_effect[35].resource` |
| `divine.earth_elemental_transformation` | `arcane.petrification` | 1 | `direct` | `spell_rev/sppr7##/sppr732.itm:0x77e:equipped_effect[36].resource` |

<!-- END SOFT RELATION EVIDENCE -->

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
