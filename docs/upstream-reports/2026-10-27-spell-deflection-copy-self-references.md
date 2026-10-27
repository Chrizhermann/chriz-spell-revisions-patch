# Upstream report: "Spell Deflection blocks AoE spells" leaves checks and refreshes naming the original spell

Status: **draft — not yet posted upstream.** Target: https://github.com/Gibberlings3/SpellRevisions/issues
(fix: `spell_rev/lib/deflection_self_refs.tpa`, called from `spell_rev/components/nwn_spell_deflection.tpa`).

---

## Summary

The component "Spell Deflection blocks AoE spells" copies each listed area spell X into a secondary
spell (X plus the first free letter from d to m) and reduces X to a single opcode 146 that casts the
copy on every creature the area reaches. On EE games the creatures then receive the copy's effects
under the **copy's** resource name.

References inside the copy that mean "this spell" still name X, so they never match:

- The immunity checks that `kreso_eestatsr.tph` inserts first in each ability (opcode 324 with an
  SPLPROT condition, naming the spell itself) never block anything. Examples:
  - the priest's Sphere of Chaos (`sppr709`) puts panic through Chaotic Commands;
  - Free Action, Death Ward, Resist Fear and elemental-immunity checks are also dead in Web, Hold
    Person, Wail of the Banshee, Horror, Fireball and others.
- Self-refreshes (opcode 321 naming X) never remove an earlier casting's effects. Greater Malison
  (`spwi412`) stacks with itself.

In an install with components 0, 10, 20, 30, 55 and 65, 69 of the 106 copies are affected: 66 with
checks and 3 more with refreshes only. In all, that is 151 checks and 19 refreshes.

## SR version

v4.21, the fork's base. Without component 55, the same checks work, because there they sit in the
spell that delivers the effects.

## Evidence (BG2:EE 2.7.3.0, EEex 1.3.1, SR v4.21 with components 0, 10, 20, 30, 55, 65)

Lab spells applied to a party member through EEex, then the creature's effect list read back:

| Check | Result |
|---|---|
| Effects of a wrapped spell | carry the copy's name as their source |
| Opcode 321 naming X | does not remove them; naming the copy does |
| Opcode 324 SPLSTATE guard naming X, target in that state | does not block; naming the copy blocks |
| `sppr709` 15 times on a creature under Chaotic Commands | panic (opcode 24, which Chaotic Commands' opcode 101 list does not cover) landed twice |
| Greater Malison cast 3 times | effects stack: 11, 21, 31 |

With the fix, the same tests show:

- Greater Malison refreshes: 11, 11, 11.
- Under Chaotic Commands, nothing but the guard itself lands from 15 pulses of either Chaos sphere.
- Without Chaotic Commands, the wizard sphere still lands normally.

## Fix

When cloning X, rename references to X inside the copy:

- opcode 321 anywhere;
- opcodes 206, 318 and 324, but only when other effects of the same ability follow them, so the
  protection guards those effects.

A protection that is the last effect of its ability stays unchanged (for example `sppr250`'s
opcode 206, which stops recasting for 5 seconds). Naming X already blocks the next cast of X.
Casting features are not touched.

## Related findings in `kreso_eestatsr.tph`

- SR's level-7 wizard Chaos (`spwi711`) has no Chaotic Commands check. The priest version
  (`sppr709`) has one.
- The Avenger's `spdr501` gets a cold-immunity check commented "cone of cold avenger". In SR that
  spell is Confusion (it replaces Chaos), so creatures immune to cold are immune to it.

The fork gives both spells the Chaotic Commands check of `spwi401`.
