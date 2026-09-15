# Rogue Rebalancing / Spell Revisions compatibility

Version: v4.21-chriz.5 (compatibility behavior unchanged from v4.21-chriz.4)

Restores the intended Chaos in the spellbooks and scripts of five Rogue
Rebalancing v4.92 mages, and corrects Selina's Spell Turning self-recast check for
SR's Spell Deflection state. Memorized copies, spell-slot caps, and tactics are
preserved. This does not redesign other spells or provide a general SCS patch.

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
resources, not creatures already embedded in a save. Unexpected RR resource shapes
are rejected instead of guessed at. Re-running the installer offers uninstall,
which restores the prior game resources.

## Validation and scope

Verified with real WeiDU automated tests, authentic RR/SR installs in both orders,
and a user-reported in-game spellbook/casting smoke test. Full hostile-encounter
behavior and a wider SCS compatibility audit remain untested. Blindness, Deafness,
Bigby's spells, and Infravision are not changed.

[Source, tests, and detailed notes](https://github.com/Chrizhermann/chriz-spell-revisions-patch)
