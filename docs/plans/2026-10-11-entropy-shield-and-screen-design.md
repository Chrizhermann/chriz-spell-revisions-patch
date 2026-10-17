# Entropy Shield counters and enemy Dispelling Screen

Research/design only, 2026-10-11. No implementation, install, gameplay test,
packaging, publication or collection default change is authorized by this note.

## Current evidence and earlier report

The current reference is `%USERPROFILE%\Games\Chriz Easy BG\game`, read only:
SR v4.21-chriz.5, IWDification v11, SCS 35.21 with its spell tweaks. This is
different from the older SR 4.19 reference used in September's answer.

Entropy Shield comes from IWDification. SCS's
`stratagems/spell/entropy_shield_abjuration.tpa:9-20` changes it to a spell
protection, adds abjuration-school immunity and registers AI detection.
Current `SPPR620` and SCS prebuff `DWSP620` both have level-six effects,
spell-protection type 1, abjuration immunity, and the appropriate protection
markers in all ten observed abilities. These counts are observations, not
compatibility requirements.

The six ordinary counters still have the necessary removal and delivery:

| Counter | Current removal ceiling |
|---|---|
| Secret Word | One spell protection through level 7 |
| Pierce Magic | One through level 8 |
| Ruby Ray of Reversal | One through level 9 |
| Khelben's Warding Whip | Repeated removals through level 8 |
| Pierce Shield | One through level 9, plus combat protections |
| Spellstrike | All spell protections through level 9 |

Their parent delivery is either no projectile or SPATTCK2, neither blocked by
the effective Entropy Shield. Spell Thrust remains capped at five. Breach is
an ordinary abjuration and removes specific/combat protection categories, not
Entropy's spell-protection category. Dispel Magic is also blocked by the
school immunity, although Entropy's continuing effects are dispellable.
The engine exempts MagicAttack effects from school immunity:
<https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op204>.

The newer CBR balance changes do not explain a failed Spellstrike:

- Pierce Magic's bounded MR change is installed; its protection remover remains.
- The October 9 `CBR_GARITHOS_SPELLS` deployment applies canonical CBR
  Spellstrike code to `SPWI903B`: 15% arcane/divine failure for 12 seconds,
  refreshing its own timed effects. The level-nine type-1 remover and parent
  delivery are retained. The earlier October 6 note saying 211 was unapplied
  is superseded by this deployment and the current bytes.
- Current `SPWI903` casts its B payload before its C Spell Shield cleanup.
  Spell Shield protects against B; C then consumes that outer shield. Entropy
  can therefore survive that first cast legitimately. Impervious Sanctity of
  Mind supplies the same separate layer through `DW#ISSS` and also prevents
  spell failure. Failure to receive the 15% debuff is not proof that protection
  stripping failed.
- Dispelling Screen is a different protection: Spellstrike's B payload removes
  its custom category too. It is not interchangeable with Spell Shield.

No broken Spellstrike-versus-Entropy-alone mechanism was found. A reported
failed cast has not been reproduced, so its actual cause remains unestablished.
Do not add a redundant remover or silently bypass Spell Shield on that basis.

## Enemy counter selection

SCS already recognizes Entropy Shield on party priests; it is not restricted
to mage targets. Current effects assert ENTROPY_SHIELD, SI_ABJURATION,
BUFF_PRO_SPELLS and the level-six-to-eight protection bucket.
`ssl/library_sr.slb:7-8` explicitly retains the abjuration check for Entropy.

`mage/ssl/combatblocks/attack_antimagic.ssl:54-99` offers Secret Word and then
Spellstrike/Ruby Ray/Warding Whip against appropriate protections. It uses
ordinary available spells, casting checks and local antimagic timers; general
AI priorities and relative response weights still apply.

Two narrow improvements merit consideration:

1. Include already-available Pierce Magic and Pierce Shield as appropriate
   Entropy counters. They are absent from this normal generic stripping choice,
   although other SCS branches use them.
2. Check the earlier `attacks_on_pc_defences.ssl:163-179` branch: it offers
   Spell Thrust on a positive legacy SpellImmunity check without the ordinary
   level-five eligibility guard. Entropy carries that detection. This is a
   generated eligibility error: the existing `ssl_out/dw#mg191.baf:7890-7915`
   likewise permits Spell Thrust on that marker without a low-level protection
   or Spell Shield condition. This is not an observed combat failure; the
   effective BCS was not decompiled or byte-compared with the generated BAF.

Prefer an adequate inexpensive available counter for Entropy alone; retain
stronger options for layered defenses. Keep spellbook limits, casting times,
visibility, difficulty, failure and cooldown rules. No extra spells or free
casts, and no unrelated prebuff or script-engine changes.

## Why enemy Screen use is scarce

The current `stratagems.ini:167` has `iwd_overrides_sr=1`.
`lib/always.tph:106-115` selects the IWD spell-choice folder over SR.
There is no IWD defensive-choice directory, so
`mage/mage_shared.tph:568-572` falls back to vanilla defensive lists, which do
not allocate Dispelling Screen. SR's own defensive lists do allocate it.
Changing the global IWD/SR preference would alter many unrelated spell choices.

The source's sole dedicated Screen rule is the SR-only, difficulty-gated
opening self-prebuff in `mage/ssl/prep/long.ssl:3-8`. The prebuff consumes a
memorized copy. Its helper still applies the same nearby-group barrier as the
ordinary spell. There is no dedicated normal combat renewal or ally-coverage
rule in the inspected mage SSL.

All 577 current generated `dw#mg*.bcs` scripts lacked the Screen resource/cast
ID in a read-only scan. Six sampled creature resources using these scripts
(`DAVAEO`, `LAVOK01`, `TOLGER`, `TOLGER2`, `HLSHANG`, `NEVAZIAH`) had no known or memorized Screen
entries. This supports an allocation gap; it is not a claim about every
bespoke enemy script or creature.

For casters that already have Screen, a small ordinary-cast rule can cast it
when nearby allies lack its protection, including renewal after consumption,
without requiring the caster's own Screen to have expired. Screen is centered
on the caster: do not pretend it can target a distant ally. Avoid redundant
coverage and preserve normal defensive priorities and spell-slot expenditure.
That rule alone has limited reach when enemies never prepare the spell.

The earlier September 28 report about Screen failing to stop a dispel remains
an unproven, separate bug report. This task does not select a grace period,
sequencer restriction, longer duration or new protection mechanic.

## Recommended small design and open decisions

Keep numerical defenses and the existing Pierce Magic/Spellstrike balance
unchanged. Make removal vulnerability and narrow AI choices the whole batch.

1. **How removable should Entropy become?**
   - **A, recommended first step:** remove its added blanket abjuration immunity.
     Dispel Magic then gets its normal caster-level chance; the existing six
     counters remain. Breach can reach and remove other applicable buffs but
     does not itself remove Entropy.
   - **B, stronger:** A plus explicit Entropy removal by Breach. Preserve its
     spell-protection classification so the existing counters still work;
     do not turn Breach into a remover of every spell protection.
   Both drop the broad abjuration protection, including its Imprisonment
   protection; neither changes missile defenses, elemental resistances, AC,
   saves or duration. Retaining selected abjuration immunities would need a
   separate explicit decision, not an unnoticed side effect.
2. **Spellstrike against layers:** keep the normal rule that a separate Spell
   Shield absorbs the first cast (recommended), or explicitly make Spellstrike
   penetrate that layer too? Removing Entropy itself is firm; overriding the
   outer shield is a distinct balance change.
3. **Screen access for enemies:** improve only enemies that already prepare it,
   or separately authorize suitable SCS mages to prepare Screen in place of an
   existing fifth-level spell? The latter adds no slots, but changes allocation
   and needs a choice of eligible casters and replacement policy. It is outside
   the present no-new-grants authority. Recommend group-aware normal casting
   and renewal for eligible casters, not free opening buffs.

CBR is the appropriate implementation owner for the deliberate Entropy nerf
and SCS-facing AI adaptation. This SR fork remains the owner for any proven
SR spell/Screen implementation defect. Collection owns integration and future
defaults, not duplicate mechanics. This preserves the earlier Screen research
ownership without extending the unrelated script-engine project.

Implementation, if later authorized, must update Entropy's corresponding AI
immunity markers and prebuff variants consistently. Resolve spells symbolically,
preserve unrelated effects and linked resources, and support relevant SR/non-SR
layouts. A baseline that already permits dispelling should not acquire a new
immunity. AI changes need a supported SCS generation or semantic compiled-script
patch path; editing source templates after scripts are generated is insufficient.

## Evidence boundary

Read-only source, resource and generated-script inspection; no gameplay or
install tests. Small later checks should distinguish Entropy alone, Spell
Shield/Impervious Sanctity layering, Screen consumption, and ordinary enemy
spell-slot use. Existing source/deployment records are evidence, not fresh live
acceptance. Existing dirty owner work was left intact.
