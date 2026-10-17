# Lightning Bolt behavior options

Three Enhanced Edition choices for Spell Revisions. These are preference changes: SR
deliberately replaces the original bouncing wizard bolt with a single-target spell.
Components 80 and 81 are included starting with release `v4.21-chriz.5`.

| Behavior | Spell Revisions | Original (80) | Non-bouncing spell and wands (81) |
|---|---|---|---|
| Wizard spell targets | One creature | Creatures along the path | Creatures along the path |
| Wizard spell bouncing | None | Bounces off walls; can hit again | None |
| Friendly fire | No path damage | Allies and caster can be hit | Allies can be hit; brief caster protection |
| Wizard spell damage | 1d6/level, maximum 10d6 | Same cap | Same cap |
| Wizard saving throw | Breath at -4; roughly half the dice survive a save | Spell for half; no built-in penalty | Spell for half; no built-in penalty |
| Wizard spell vs. Mirror Image | Images can intercept damage | Bypasses images | Bypasses images |
| Direct lightning wands | Unchanged | Unchanged | Non-bouncing; existing damage, saves, targets and charges retained |
| Dedicated lightning traps | Unchanged | Unchanged | Original projectile retained; traps can still bounce |

Both alternatives restore the original wizard spell's per-level range, capped at level 10.
At level 10 SR implements damage as 5d6 without a save plus 5d6 negated by the save. The
original EE spell rolls one 10d6 damage effect and halves that roll on a save, rounding down.
Both alternatives restore this calculation and keep later mods' additional save penalties.

SR's Mirror Image Fix recognizes the original bolt's area projectile but does not include
the replacement single-target projectile. Its damage effects also lack the Mirror Image
bypass flag. A normal successful save alone should leave some damage; images, magic
resistance, electrical immunity, Evasion, or spell protections can explain a zero-damage
result. A particular failed cast requires runtime evidence.

## Why a separate non-bouncing option?

[Tweaks Anthology component 2530, by Angel](https://github.com/Gibberlings3/Tweaks-Anthology/blob/v18/cdtweaks/lib/comp_2530.tpa),
already implements non-bouncing lightning. It changes shared projectiles, including trap
bolts. This option applies the same projectile-field changes to a private copy, `SRCBLBN`,
and redirects the wizard spell and real direct-damage lightning wand abilities to that copy.
The original `LIGHTB.PRO` and dedicated trap spells remain unchanged.

Wands that cast the ordinary wizard spell also follow the chosen spell behavior. Separate
innate lightning spells, Chain Lightning, and other projectile families are outside scope.
A modded trap that explicitly casts the ordinary wizard spell follows that spell too; the
promise about bouncing traps applies to dedicated trap spells, including `SPWI002`.

## Install

Requires Spell Revisions' main component and BG:EE/BG2:EE, including EET. For non-bouncing
lightning, the game must provide an externalized `LIGHTB.PRO` resource. Choose one row:

| Choice | Fresh install: Spell Revisions | Existing stack: this mini-mod |
|---|---|---|
| Spell Revisions | Skip 80 and 81 | Do not install either component |
| Original | Component 80 | Component 0 |
| Non-bouncing spell and wands | Component 81 | Component 1 |

Install after other spell modifications. To append to an existing stack, close the game,
copy the `SRCB_CLASSIC_LIGHTNING` directory into the game directory, and use WeiDU 249 or
newer. For example, to select non-bouncing spell and wands:

```text
weidu.exe SRCB_CLASSIC_LIGHTNING/setup-SRCB_CLASSIC_LIGHTNING.tp2 --force-install-list 1 --language 0 --use-lang en_US --no-exit-pause
```

The two alternatives are mutually exclusive. To change variants, uninstall the selected
option through WeiDU before installing the other. Do not stack the source and mini-mod
versions. Installing neither preserves SR; returning to SR means uninstalling the selected
alternative. Normal WeiDU dependency/cascade rules apply if later components are installed.

Restart the game and load the existing save; memorized copies use the same spell resource.
Both player and enemy casts of that resource change. The wizard spell, scroll descriptions,
and direct wand behavior notes are updated in English; wand statistics are retained.
Already active projectile protections stored in a save are not rewritten. Refresh those
buffs and re-equip projectile-protecting items, such as the Cloak of Reflection, so their
new protection against the private projectile takes effect.

## Compatibility and rollback

The spell patch resolves the spell and projectiles through IDS symbols. In each spell
tier it identifies SR's two electrical damage effects by meaning: the unsaved half and the
breath-save half, in either order. It combines them, removes only SR's built-in -4 save
penalty, and preserves other effects, casting features, and spell metadata. For example, a
later mod's -5 total penalty becomes -1. Installed Evasion and electrical-immunity checks
survive. Other damage that a mod adds to the spell, such as a fire rider or a separate
electrical effect with different dice, save or delivery, is left unchanged.
Only scrolls with a learn effect for the resolved spell receive the new description.

Installation fails, naming the spell tier, when the wizard projectile is unexpected, when a
tier lacks one of SR's two halves, or when the halves disagree in save flags or metadata.
It also fails when several effects match the same half, because the bolt's own damage is
then ambiguous. An already classic tier is left unchanged when it holds at least one
classic damage effect; a foreign effect of the same shape, kept beside the converted
damage, therefore does not stop a repeat application. A classic tier without one fails.

The non-bouncing option keeps the old projectile identity for traps and clones existing
immunity/reflection effects for its new projectile in item, spell and creature resources.
It also adds a short caster-protection effect for its new projectile, as the existing
non-bouncing approach does. External EFF resources that protect against the original
projectile require a compatibility adapter; installation rejects those combinations rather
than silently bypassing their protection. A pre-existing `SRCBLBN` resource or IDS entry is
also rejected.

Neither alternative can be combined with Tweaks Anthology 2530: that component globally
changes the original projectile required here. Omit 2530 from a new installation to retain
bouncing traps. This patch does not undo an arbitrary other mod's changes to `LIGHTB.PRO`.

This changes spell resources and preserves SCS casting features; it does not regenerate
SCS AI scripts or rewrite copies of the wizard spell that another mod created under a
different resource name. AI casting the ordinary wizard spell gets the selected behavior,
including its path and friendly-fire consequences.

WeiDU backs up changed resources. Uninstalling the selected component restores prior resource
bytes, removes the private projectile, and restores its IDS registration and cloned
protections. An appended, unused TLK description may remain. For the example above:

```text
weidu.exe SRCB_CLASSIC_LIGHTNING/setup-SRCB_CLASSIC_LIGHTNING.tp2 --force-uninstall-list 1 --language 0 --use-lang en_US --no-exit-pause
```

## Verification

The 88 Lightning Bolt tests pass with WeiDU 249, alongside the retained SR/RR
compatibility coverage. They run real WeiDU
against actual SR source spells and disposable synthetic games. They
check damage/save semantics, Mirror Image bypass, preservation of foreign effects, foreign
damage and casting features, reordered damage halves, ambiguous damage rejection, repeat
application, resource relocation, malformed input rejection, both externalized
projectile layouts, selective wand routing, unchanged traps, projectile protection cloning,
component exclusivity, and byte-exact resource restoration on uninstall. The source and
tail libraries are kept byte-identical by a test.

A disposable rehearsal with copies of effective resources from the 2026-09-07 EET game
also verifies the Wand of Lightning's six targets, 50 charges and 3d6 save-for-half damage,
the Cloak of Reflection's cloned protection, unchanged trap/projectile resources, preserved
SCS casting hooks and later save penalties, and byte-exact resource uninstall restoration.
No runtime casts are implied by these checks.

In-game acceptance is scheduled with the full CEBG collection installation, not another
prerequisite standalone install: test Mirror Image, creatures in a line, a wall,
friendly fire, the Wand of Lightning, a dedicated lightning trap, and projectile reflection.
Use a disposable save and targets without electrical immunity or unrelated spell protections
for geometry checks. No live installation is performed by the automated tests.

Sources: [SR spell](https://gibberlings3.github.io/SpellRevisions/spells/arcane/level-3/lightning-bolt),
[original spell](https://gibberlings3.github.io/SpellRevisions/vanilla-spells/arcane/level-3/lightning-bolt),
[IESDP damage opcode](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op12),
[IESDP projectile format](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/pro_v1.htm).
