# Sword Coast Stratagems / Spell Revisions compatibility

Version: v4.21-chriz.8

Sword Coast Stratagems (SCS) has a tactic of its own for its mages' Chaos: cast it early at
groups, and skip targets that are already confused or protected against confusion. SCS leaves
that tactic out whenever Spell Revisions is installed, because SR up to v4.21-chriz.7 moved
Chaos off wizard level 5. This fork keeps Chaos at level 5 from v4.21-chriz.8, so this
component removes that one gate from SCS's source before SCS compiles its mage scripts. SCS
mages that know Chaos then cast it as SCS does without SR. Without it they cast Chaos only on
the easiest difficulty or from a Spell Trigger. Waves of Fatigue keeps SCS's own tactic, and
SCS's dragons still cast Confusion in place of Chaos.

## Installation

Requires Spell Revisions' main component (0) with Chaos at wizard level 5 (v4.21-chriz.8 or
later), and SCS's files in the game folder. Install it after Spell Revisions and before SCS's
AI and tactical components, which read the changed file when they install.

1. Close the game and back up your installation.
2. Extract SCS into the game directory, but do not install its AI components yet.
3. Extract `SRCB_SCS_COMPAT/` and `Setup-SRCB_SCS_COMPAT.exe` into the game directory
   containing `chitin.key`.
4. Run `Setup-SRCB_SCS_COMPAT.exe` and install component 0.
5. Install SCS.

The Windows installer is [official WeiDU 249 x64](https://github.com/WeiDUorg/weidu/releases/tag/v249.00)
([source](https://github.com/WeiDUorg/weidu/tree/v249.00)); its license and manual
are included as `WeiDU-COPYING.txt` and `README-WeiDU.html`.
On another platform, use a native WeiDU 249 or newer binary to install
`SRCB_SCS_COMPAT/setup-SRCB_SCS_COMPAT.tp2` from the game directory. The mod itself does
not require EEex.

## What it changes

Only `stratagems/mage/ssl/combatblocks/l5_enchantment.ssl`. In each tactic block there that
casts `WIZARD_CHAOS`, `Demivrgvs` leaves the `IgnoreBlock` list; SCS sets `Demivrgvs` when
Spell Revisions is installed. A list with nothing else goes with its line, and every other
byte stays. Blocks and lists are read the way SCS's own compiler reads them. WeiDU keeps the
original file, and uninstalling the component restores it.

The component fails without changing anything when the final `SPELL.IDS` does not map
`WIZARD_CHAOS` to a level-5 wizard spell (SCS's skip is right then), when SCS's library does
not call Spell Revisions `Demivrgvs`, or when the file has no block that casts `WIZARD_CHAOS`.
When SCS's AI or tactical components (6000 and up) are installed already, it warns: their
mage scripts keep the skip until they are reinstalled.

## Validation and scope

Verified with real WeiDU automated tests on a synthetic SCS-shaped file: only gated Chaos
blocks change, Windows and Unix line endings, comments and blank runs, gate lists with other
entries, an open tactic, a second pass, uninstall, the warning, and every refusal. On SCS
35.21's own file it removes exactly one line, the Chaos tactic's `IgnoreBlock(Demivrgvs)`,
and uninstalling restores the file.

Disposable BG2:EE 2.7.3.0 labs with this fork's components 0, 10, 20, 30, 55 and 65,
IWDification's arcane spells and SCS 35.21's components 5900 and 6030 (2026-10-28):

| Lab | SCS mages | Chaos prepared | with SCS's Chaos tactic |
|---|---|---|---|
| with this component | 404 | 114 | 114 |
| without it | 404 | 125 | 0 |

SCS picks its mages' spells at random on every install, so the labs are compared by counts.
In the first lab, no mage without Chaos got the tactic, and the 23 mages that got the same
spells in both labs (none with Chaos) got the same scripts. With SCS's Spell Revisions tables
(a third lab without IWDification), no SCS mage prepares Chaos: those tables pick Waves of
Fatigue at level 5 and Sphere of Chaos at level 7. There, 59 mages prepared Waves of Fatigue
in its own slot, and all 59 had SCS's tactic for it. SCS also skipped 7 mages of level 7 or 8
in that lab: its Spell Revisions list of defensive spells for invokers writes `NULL` where its
other lists write `null`. That happens without this component as well; it never happens with
the IWD tables.

These are install checks: the mages' scripts were compiled and compared, and no game was
started.

[Source, tests, and detailed notes](https://github.com/Chrizhermann/chriz-spell-revisions-patch)
