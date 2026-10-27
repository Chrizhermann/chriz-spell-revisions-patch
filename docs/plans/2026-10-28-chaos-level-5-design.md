# Design: Chaos back at wizard level 5

Date: 2026-10-28
Status: implemented on branch `claude/chaos-level5`; static and in-game lab checks passed on
BG2:EE 2.7.3.0. Merge after CEBG alpha.22 or with Christopher's OK. New installs only.

## 1. Problem

Upstream SR moved Chaos to wizard level 7 (`SPWI711`, merged with Sphere of Chaos) and put its
new Waves of Fatigue into Chaos's level-5 slot `SPWI508`, renaming `2508` to
`WIZARD_WAVES_OF_FATIGUE` and appending `2711 WIZARD_CHAOS`. Everything in the game that names
`SPWI508` or spell `2508` therefore got Waves of Fatigue: the Chaos scroll `SCRL5P` and the
stores and containers that hold it, 332 creature files (spellbooks), about 47 AI scripts, and
the protections and removals written for Chaos (Chaotic Commands, both Mind Blanks, Dispel
Confusion, Spiritual Clarity, some creature rings). SR's own Chaotic Commands guard for
`SPWI508` (`kreso_eestatsr.tph`) landed on Waves of Fatigue as well. The Avenger's level-5
spell, Chaos in the game, had become a copy of SR's Confusion.

## 2. Decisions (Christopher, 2026-10-26/27)

| Topic | Decision |
|---|---|
| Chaos | Back at wizard level 5 in `SPWI508`: SR's Confusion with its saving throw at -4 ("variant D"), nothing else added |
| Duration | Confusion and Chaos: 4 rounds, 5 from caster level 15, 6 from caster level 20 |
| Level-7 spell | SR's sphere stays, with its effects, and is called Sphere of Chaos (wizard and priest) |
| Waves of Fatigue | Stays a level-5 spell in a slot of its own, with its own scroll wherever a Chaos scroll is |
| Avenger | Casts Chaos again |
| Scope | New installs; the streamed game stays as it is |

## 3. Implementation

- `spell_rev/lib/chaos_confusion.tpa`
  - `srcb_confusion_rounds` turns SR's one-ability Confusion into abilities for caster levels
    1, 15 and 20. Every effect that lasts as long as the first confusion effect (op128) lasts
    24, 30 or 36 s in them. It fails on another layout instead of guessing.
  - `srcb_chaos_from_confusion` makes Chaos from Confusion: level 5, save -4 on every effect
    with a save, power 5 where it was the old level. It uses the game's Chaos icons when the
    game has them.
- Main component: `SPWI508` = Confusion → Chaos; `SCRL5P` teaches it again. Waves of Fatigue
  (`spwiwof.spl`, icons `SRCBWOF[ABC]`, scroll `SRCBWOFS`) is added with `ADD_SPELL` as
  `WIZARD_WAVES_OF_FATIGUE` (registry name `spwiwof`). `SPELL.IDS` keeps vanilla's
  `2508 WIZARD_CHAOS`. `spdr501` is a priest copy of the new Chaos.
- `spell_rev/lib/item_beside.tpa`: `srcb_scrolls_teaching` finds every scroll that teaches Chaos
  (op147), including IWD:EE's `SCCHAO` and Tutu's copies. `srcb_add_item_beside` puts
  `SRCBWOFS` beside each of them, with the Chaos scroll's fields:
  - in stores, right after the scroll;
  - in area containers, in the same container;
  - in creature inventories, in the first free inventory slot, with a warning if none is free.
- School list, spell flags table, Spell Deflection's list (component 55) and the Avenger's
  guard follow the move. New strings @90000/@90001 in English and French; the other languages
  are disabled in the tp2.
- `live-patch/SRCB_RR_COMPAT` reads where Chaos is: at level 5 it keeps RR's Chaos and only
  fixes Selina's guard (see the RR design note).

## 4. Verification

**Automated:** `tests/test_chaos_level5.py` (24 real-WeiDU tests), the Spell Deflection
fake game with the new registry name, and 4 new RR compatibility tests.

**Static lab check** (local evidence in `CEBG-Tests/_runs-20261028-chaos-level5`, not in the
repository). Two disposable BG2:EE 2.7.3.0 + EEex labs got CEBG's SR components [0, 10, 20,
30] then [55, 65]: one from the branch (369e8a3), one from master (50ba2ca). Both override
folders were compared before and after component 55. Strrefs with the same text and sound on
both sides were ignored, since the new strings shift later strrefs. Every other difference is
explained:
- `SPELL.IDS`: `2508 WIZARD_CHAOS`, `2525 WIZARD_WAVES_OF_FATIGUE`, no `2711 WIZARD_CHAOS`.
- Confusion = master's with the three level abilities (24/30/36 s).
- Chaos = this Confusion at level 5, power 5, save -4, its own Chaotic Commands guard, the
  game's icons.
- Avenger's Chaos = Chaos as a priest spell with its own guard.
- Waves of Fatigue = master's `SPWI508` with new icons and without the Chaotic Commands guard.
  `SRCBWOFS` = master's `SCRL5P` teaching `SPWI525`.
- `SCRL5P` teaches Chaos with enchantment usability.
- Texts: only Confusion's scroll, both spheres and the sphere scroll changed text.
- Placements: 10 stores, `AR1202` container 6 and `REMAGE02` got `SRCBWOFS` with the Chaos
  scroll's fields and nothing else. The only other change is the empty projectile-trap
  section's offset that `fj_are_structure` sets.
- Component 55: wrappers cast their copies with op146 at the caster's level, and the copies are
  the spells above with the component's own changes. No nominal `spwiwof`/`dvwiwof` name is
  left.

**In game** (same lab, Player1 a mage whose level was set with `ChangeStat`, the target a
level-9 mage with saves -20): Chaos through component 55's wrapper confused for 24 s at caster
levels 9 and 14, 30 s at 15, 18 and 19, and 36 s at 20, so it follows the caster's level, not
the target's. Confusion: 24 s at 9, 36 s at 20. Avenger's Chaos by the cleric: 30 s at 18,
36 s at 20. Waves of Fatigue's copy applied its fatigue. Chaotic Commands stopped Chaos.

## 5. Behaviour changes and limits

- Everything that names `SPWI508` means Chaos again, as in the unmodded game: Chaotic Commands,
  both Mind Blanks and some creature rings protect against Chaos, Dispel Confusion and
  Spiritual Clarity remove it, and creatures and AI scripts that know or cast Chaos get Chaos.
  Waves of Fatigue loses the Chaotic Commands guard SR's guard pass gave it.
- `REMAGE02` carries its Chaos scroll in a quick slot; its Waves of Fatigue scroll goes to
  the inventory.
- The Avenger's Chaos has the Hostile flag but not "breaks Sanctuary/Invisibility" (0x200),
  which Hostile already implies. SR's flags table names spells through `SPELL.IDS`, which has
  no Avenger spells (same as master for all of them).
- A scroll casts at its own level (`SCRL5P`: 10), so a Chaos scroll gives 4 rounds.
- Not updated: Russian, Spanish and Polish texts (disabled in the tp2), IWD:EE's own `SCCHAO`
  description. Not checked: an install with Rogue Rebalancing's own files on the level-five
  branch, IWD:EE and EET labs, existing saves.
- Open: SCS skips its Chaos handling under SR and needs a look (question to DavidW, a
  temporary CEBG fix before SCS).
