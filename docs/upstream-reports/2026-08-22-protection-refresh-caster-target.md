# Upstream report: "refresh, non-stacking" 321 targets the caster on Protection from Magic Energy / the Elements / Energy

Status: **draft — not yet posted upstream.** Target: https://github.com/Gibberlings3/SpellRevisions/issues
(fix PR: the `MAKE_REFRESHING_DIRECT` change in `spell_rev/lib/refresh_non_stacking.tpa`).

---

## Summary

On EE games, `spell_rev/lib/refresh_non_stacking.tpa` adds the opcode 321 "remove effects by
resource = itself" refresh effect to Protection from Magic Energy (`spwi606`), Protection from
the Elements (`spwi702`) and Protection from Energy (`spwi803`) with **effect target 1 (Self)**.
These three spells are creature-targeted (ability target 1), so the 321 fires on the **caster**
instead of the recipient:

- casting the spell on an ally removes the caster's own running instance;
- re-casting on the same ally does **not** replace the older instance (no refresh on the recipient).

The descriptions say "the recipient receives complete protection …", so this contradicts the
documented behaviour.

## SR version

v4.21 (code unchanged since PR #75, 2021-10-20). Also present in v4.19 installs.

## Where

`spell_rev/lib/refresh_non_stacking.tpa`, third `WITH_SCOPE` block ("Spell in which refresh
is added directly"):

```
LPF ADD_SPELL_EFFECT INT_VAR
    opcode = 321        //Remove effects by resource.
    timing = 1          //Instantaneous.
    target = 1          //Self.
    insert_point = 0    //First.
STR_VAR
    resource = EVAL "%spell_res%"
END
```

The list is `WIZARD_MIRROR_IMAGE`, `WIZARD_WRAITH_FORM`,
`WIZARD_MINOR_GLOBE_OF_INVULNERABILITY`, `WIZARD_GLOBE_OF_INVULNERABILITY` (all caster-only,
ability target 5 → target 1 is correct) and `WIZARD_PROTECTION_FROM_MAGIC_ENERGY`,
`WIZARD_PROTECTION_FROM_THE_ELEMENTS`, `WIZARD_PROTECTION_FROM_ENERGY` (creature-targeted,
ability target 1 → target 1 is wrong).

Effect target semantics (IESDP, SPL/EFF feature block offset 0x02): `1 = Self` (the caster),
`2 = Projectile target` (whoever the projectile hits). `MAKE_REFRESHING` — the path every other
spell takes — clones the spell's own 206 and therefore inherits target 2 for creature-targeted
spells; e.g. Spirit Armor ends up with `op=321 target=2`.

## Evidence (installed SR v4.19 + SCS, `override/spwi606.spl`)

```
ability[0] target=1 (creature)
  fx[0] op=321 tgt=1 res='SPWI606'     <- refresh on the CASTER
  fx[1] op=31  tgt=2 ...               <- every protective effect on the recipient
  ...
```

Identical shape for `spwi702` and `spwi803` (one such effect per ability header, 9/4/5 headers).

## Fix

Derive the 321's target from the ability's target type:

```
DEFINE_PATCH_FUNCTION MAKE_REFRESHING_DIRECT INT_VAR debug = 0 STR_VAR resource = "" BEGIN
    SET fx_target = 2                   //Projectile target.
    READ_LONG 0x64 ext_off
    READ_SHORT 0x68 ext_cnt
    PATCH_IF (ext_cnt > 0) BEGIN
        READ_BYTE (ext_off + 0x0c) ab_target
        PATCH_IF ((ab_target = 5) OR (ab_target = 7)) BEGIN
            SET fx_target = 1           //Self.
        END
    END
    LPF ADD_SPELL_EFFECT INT_VAR
        opcode = 321
        timing = 1
        target = fx_target
        insert_point = 0
    STR_VAR
        resource = EVAL "%resource%"
    END
END
```

and call `LPF MAKE_REFRESHING_DIRECT STR_VAR resource = EVAL "%spell_res%" END` from the
third block. The four caster-only spells produce byte-identical output; the three protections
get target 2.

## Reproduction

1. Install SR (EE game), recruit a second caster-capable character or any ally.
2. Mage casts Protection from Magic Energy on themself → icon appears.
3. Mage casts it on an ally → the mage's icon disappears, the ally's appears.
4. (Optional) cast it on the ally again → two instances stack in the ally's effect list
   instead of one.

## Test material

A pytest suite in the fork (`tests/test_prot_refresh_target.py`) runs the real
`refresh_non_stacking.tpa` in a synthetic game and checks the effect targets; the upstream
v4.21 file is kept as a control that must still show target 1.
