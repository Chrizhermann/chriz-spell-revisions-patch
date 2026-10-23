# Rogue Rebalancing / Spell Revisions compatibility

Version: v4.21-chriz.6

Three Rogue Rebalancing v4.92 mages prepare Chaos in the level-5 slot that Spell
Revisions gives to Waves of Fatigue; SR's Chaos is a level-7 spell. Their level-5
Chaos copies become a level-5 spell that their scripts cast instead: Hold Monster
for Aran Linvail, Feeblemind for the Zhentarim Mercenary and Domination for Selina,
each with the target checks that spell needs. Selina's Spell Turning self-recast
check is corrected for SR's Spell Deflection state. Memorized copies (prepared or
already cast), spell-slot caps, and the other tactics are preserved; Chaos itself
stays SR's level-7 spell. This does not redesign other spells or provide a general
SCS patch.

## Installation

Requires Spell Revisions' main component (0), plus Rogue Rebalancing's Chosen of
Cyric (11) and/or Shadow Thief Improvements (12). Install after both mods, even
on a fresh install. SR before RR is the preferred base order.

1. Close the game and back up your installation.
2. Extract `SRCB_RR_COMPAT/` and `Setup-SRCB_RR_COMPAT.exe` into the game directory
   containing `chitin.key`.
3. Run `Setup-SRCB_RR_COMPAT.exe` and install component 0.

The Windows installer is [official WeiDU 249 x64](https://github.com/WeiDUorg/weidu/releases/tag/v249.00)
([source](https://github.com/WeiDUorg/weidu/tree/v249.00)); its license and manual
are included as `WeiDU-COPYING.txt` and `README-WeiDU.html`.
On another platform, use a native WeiDU
249 or newer binary to install `SRCB_RR_COMPAT/setup-SRCB_RR_COMPAT.tp2` from the
game directory. The mod itself does not require EEex.

Do not reinstall the main SR component mid-stack just to apply this patch.
Install before first entering/spawning the affected encounters: it updates game
resources, not creatures already embedded in a save. Spellbook entries and script
references are recognized by the spell they name, so other copy counts and extra
Chaos branches are changed too. A creature or script naming both RR's old Chaos
slot and SR's Chaos is rejected instead of guessed at; one naming neither, nor the
replacement, is left unchanged with a warning. Re-running the installer offers
uninstall, which restores the prior game resources.

## Validation and scope

Verified with real WeiDU automated tests and a local check with RR v4.92's own
creatures and scripts in both install orders. The user-reported in-game smoke test
of v4.21-chriz.4 predates the level-5 replacements; the new spellbooks and casts
have not been checked in game yet. Full hostile-encounter behavior and a wider SCS
compatibility audit remain untested. Blindness, Deafness, Bigby's spells, and
Infravision are not changed.

[Source, tests, and detailed notes](https://github.com/Chrizhermann/chriz-spell-revisions-patch)
