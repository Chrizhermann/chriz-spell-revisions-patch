# Handoff: SR Death Ward and physical vorpal attacks

Date: 2026-09-06 · Owning repository: `chriz-spell-revisions-patch`

## Receipt and follow-up status

Received 2026-09-06 from the BG Rebalance dragon-design task
(`01a07181-c25c-7c53-a3ef-39623e56ea3d`), at Christopher's request.

**Deferred: receipt and backlog recording only.** Implementation, component allocation,
release, live-game writes, installation, launch, save mutation, and deployment are not
authorized by this receipt. The current RR/SR AI compatibility work remains separate
and unchanged.

Source handover:
[C:\Users\chris\.codex\worktrees\a947\chriz-bg-rebalance\docs\handovers\2026-09-06-sr-death-ward-vorpal.md](<C:/Users/chris/.codex/worktrees/a947/chriz-bg-rebalance/docs/handovers/2026-09-06-sr-death-ward-vorpal.md>).
The original research below is retained locally so the follow-up does not depend on
that worktree remaining available. It reports an inspected SR v4.19 / SCS v35.21
installation; it is not a fresh verification of this repository's current fork or
another installation. Revalidate the supported resources when implementation is
separately requested.

Coordination snapshot from the forwarding task: BG Rebalance's separate dragon
component targets permanent death, with Firkraag at 15% and a -4 death save, and
other selected dragons at 5% or 10% and a -2 death save. Those attack changes belong
to BG Rebalance, not this SR follow-up. Do not apply those numbers to SR's Planetar
weapons.

Backlog entry: [Deferred handovers](README.md).

## Original handover content

The user requests that **Death Ward protect against death magic, but not physical vorpal attacks**. Implement this in the Spell Revisions patch repository. This is a user-requested semantics correction; SR's authorial intent is unconfirmed, so do not present it as a proven upstream bug.

This handoff records read-only research from the installed SR v4.19 / SCS v35.21 stack. It authorizes no live-game installation, launch, save repair, or deployment. No component number is allocated here.

## Verified installed behavior

Reference install: `C:\Games\Baldur's Gate II Enhanced Edition modded`.

- [SPELL.IDS, line 98](<C:/Games/Baldur's Gate II Enhanced Edition modded/override/SPELL.IDS:98>) resolves `CLERIC_DEATH_WARD` to `1409`, hence `SPPR409.SPL` on this install. Resolve the symbol afresh in the implementation.
- All **14 ability headers** of effective [SPPR409.SPL](<C:/Games/Baldur's Gate II Enhanced Edition modded/override/SPPR409.SPL>) contain opcode 101 immunities to **55, 13, 209, and 238**. Each has parameter1 `0`, special `0`, and probability bytes `100/0`. The opcode-13 immunity is blanket immunity, with no restricted death subtype encoded.
- First-ability effect-record offsets are `0x2A2` (immunity to 55), **`0x2D2` (immunity to 13)**, `0x302` (immunity to 209), and `0x452` (immunity to 238). These are file offsets in the researched effective binary, not portable patch locations.
- The [bundled SR spell](<C:/Games/Baldur's Gate II Enhanced Edition modded/spell_rev/sppr4##/sppr409.spl>) already contains those four immunities. Its opcode-238 immunity is at `0x3C2`; earlier three offsets match. The installed copy additionally has opcode-328 markers for spell states **8 and 67**, and retains the resource protection against `SPWI616` (opcode 206). Preserve legitimate protections, markers, visuals, duration, targeting, and other effects.
- SR copies this spell in [main_component.tpa, line 916](<C:/Games/Baldur's Gate II Enhanced Edition modded/spell_rev/components/main_component.tpa:916>). Its [English description, line 883](<C:/Games/Baldur's Gate II Enhanced Edition modded/spell_rev/languages/english/divine.tra:883>) describes death magic and names Death Spell, Disintegrate, Power Word Kill, Finger of Death, and Wail of the Banshee.

The actual SR summoned Planetars equip **`DVPLANGW.ITM` / `DVPLANEW.ITM`**, as verified in both bundled and effective `PLANGOOD.CRE` / `PLANEVIL.CRE`. The current installer copies those weapons at [main_component.tpa, line 3314](<C:/Games/Baldur's Gate II Enhanced Edition modded/spell_rev/components/main_component.tpa:3314>) and [line 3326](<C:/Games/Baldur's Gate II Enhanced Edition modded/spell_rev/components/main_component.tpa:3326>).

Both effective weapons have a direct opcode-13 effect at file offset `0x58A`: parameter1 `0`, parameter2 `8`, timing `1`, resist/dispel `2`, probability upper/lower `15/0`, death-save bit `4`, save bonus `-2`, special `0`. Bundled weapon records match at `0x16A`. Death Ward currently blocks them through its blanket opcode-13 immunity. Current [English Planetar text, line 3027](<C:/Games/Baldur's Gate II Enhanced Edition modded/spell_rev/languages/english/arcane.tra:3027>) describes 15% and save versus death at -2. The old readme's 5%/-6 and bundled `PLANETAR.ITM` are not the current summoned creatures' weapon behavior. Preserve these bytes; do not silently retune proc probabilities or saves in this fix.

## SCS context and scope

The bundled [SCS design essay, line 160](<C:/Games/Baldur's Gate II Enhanced Edition modded/stratagems/doc/subdocuments_dw/dw_opcodes.html:160>) argues that Death Ward should protect from death magic without protecting against beheading. **That essay does not describe the effective SR spell above**, and does not establish SR author intent.

SCS component **4130**, revised handling of permanent-death effects, is absent from the researched WeiDU log and explicitly forbids SR component 0 in [setup-stratagems.tp2, lines 716–721](<C:/Games/Baldur's Gate II Enhanced Edition modded/stratagems/setup-stratagems.tp2:716>). SR component 0 and SCS improved fiends/celestials are installed ([WeiDU.log, line 110](<C:/Games/Baldur's Gate II Enhanced Edition modded/WeiDU.log:110>), [line 307](<C:/Games/Baldur's Gate II Enhanced Edition modded/WeiDU.log:307>)). This request does not change chunking, resurrection, or global death handling.

The current **Firkraag permanent-death direction belongs to the separate dragon component in `chriz-bg-rebalance`**. Coordinate its protection contract, but keep that dragon's attack implementation out of this SR patch. Do not extend this work to Avoid Death, Hindo's Doom, death-immune creatures, or other immunity providers without separate scope.

## Narrow implementation candidate and acceptance

1. Map Death Ward's final spell and any delivery/helper chain, then map the relevant death spells and physical vorpal attacks against their actual opcodes, death subtypes, and resource guards. Include spell-specific protections and any effects that could still block vorpal after removing opcode-13 immunity. The inspected Silver Sword, Axe of the Unyielding, and BALOR weapons also have opcode-324 guards against spell state 140 (`DEATH_IMMUNITY`); audit their interaction instead of assuming removal of one immunity record settles every attack. Do not infer semantics solely from an opcode number or description.
2. Candidate change: remove **only Death Ward's blanket opcode-13 immunity**, if that mapping proves this preserves the requested death-magic protection. If installed death spells legitimately rely on opcode 13, design the necessary narrower protection before removing the blanket record. Do not sweep unrelated resources and strip their immunities.
3. Use dynamic `SPELL.IDS` resolution, prerequisite guards, strict shape/ownership preflight, and an idempotent patch. Recognize the unmodified supported shape and the already-corrected shape; fail clearly on an ambiguous foreign shape. Add binary evidence and captured fixtures in the owning repository before code; do not depend on this install's offsets or allocated resrefs.
4. Verify with meaningful fixture and isolated installer checks: all ability tiers corrected, unrelated bytes/effects preserved, repeated application stable, supported variants handled, and foreign inputs rejected before publication. Test actual effect delivery where needed: **Death Spell, Finger of Death, Power Word Kill, and Disintegrate remain blocked; physical vorpal effects are no longer blocked by Death Ward**. Include resource/subtype guard interactions, both relevant application orders, and other death-magic promises exposed by the dependency audit.
5. Separate automated evidence from gameplay acceptance. Effects already active in a loaded or saved character are copied effect records: changing the SPL does **not** rewrite them. Validate with the old Death Ward expired or removed and the revised spell recast; no blanket save mutation is authorized.

No implementation or live acceptance has been performed for this proposed correction.
