# Two-Version Live Smoke Test Design

## Goal

Test the configurable Spell Revisions installer on clean BG2:EE 2.6.6.0 and
2.7.3.0 installations without touching any active playthrough or mod stack.

## Disposable layout

Create one deletion boundary:

`C:\Users\chris\Games\DELETE_AFTER_SR_CONFIG_TESTS_2026-08-30`

It contains two independent full copies:

- `BG2EE-2.6.6.0-SR-CONFIG-TEST`
- `BG2EE-2.7.3.0-SR-CONFIG-TEST`

The copies use ordinary copied files, not hard links. Deleting the parent folder
after testing removes every game copy, staged mod file, log, backup, and test
artifact created by this exercise.

## Sources

- 2.6.6.0: `C:\Games\Baldur's Gate II Enhanced Edition modded - dev clean install`
- 2.7.3.0: `C:\Program Files (x86)\Steam\steamapps\common\Baldur's Gate II Enhanced Edition`

Both sources have zero installed WeiDU components. Their `Baldur.exe` product
versions are checked before and after copying.

## Profiles

Each copy receives the current mod plus two saved settings profiles:

1. **ALL-ON**: the untouched generated defaults.
2. **SPARSE-SMOKE**: root default off, with only Grease, True Strike,
   Polymorph Other, Armor of Faith, and Sunscorch enabled.

The sparse selection covers a projectile patch, a relocated spell, a shared
runtime helper, a normal divine replacement, and a dynamically added spell.
Magic Missile is retained as a disabled control.

## Safety boundary

- Do not install while `Baldur.exe` or `InfinityLoader.exe` is running.
- Do not use an existing save or user profile for the first smoke test.
- Install this mod last in each disposable copy.
- Prepare the copies and profiles now; perform installation and play testing
  interactively in a later step.

