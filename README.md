# Spell Revisions — Chriz Balance Patch

A personal fix-and-balance fork of **[Spell Revisions](https://github.com/Gibberlings3/SpellRevisions)**, the Baldur's Gate II / Enhanced Edition spell overhaul created by **Demivrgvs** (Marco Montagnoli) with **Ardanis**, and maintained today by the **Gibberlings3** team (Mike1072, lambda-dom, subtledoctor, kreso and many more — see the [upstream contributors](https://github.com/Gibberlings3/SpellRevisions/graphs/contributors)). All spell design, data, art and installer architecture are their work; this fork only adds bug fixes and a few balance knobs on top of upstream, and offers every fix back.

## Credit & original authors

- **Upstream repository:** https://github.com/Gibberlings3/SpellRevisions
- **Spell list / documentation:** https://gibberlings3.github.io/SpellRevisions/
- **Forum (bug reports, discussion):** https://www.gibberlings3.net/forums/forum/118-spell-revisions/
- **Readme shipped with the mod:** `spell_rev/readme-spell_rev.html`

Spell Revisions is © 2008–2015 Marco Montagnoli and the Gibberlings3 contributors; its readme
asks that the mod not be redistributed without the author's consent. This fork is a patch set on
top of upstream — not a competing release. Please support and report to upstream first; the
fixes here are written so they can be submitted as upstream pull requests
(`docs/upstream-reports/`).

## How this fork is maintained

- `master` = upstream `master` + the commits listed below. Sync: `git fetch upstream && git merge upstream/master`.
  A weekly GitHub Action (`.github/workflows/check-upstream.yml`) opens an `upstream-sync` issue when upstream moves.
- Fixes are made **in the mod source** (`spell_rev/…`) so fresh installs get them. Fixes that can
  safely retrofit effective resources are mirrored as **tail-installable mini-mods** in
  `live-patch/`; installer-order migrations stay in their owning Spell Revisions component.
- `spell_rev/setup-spell_rev.tp2` carries `VERSION ~v4.21-chriz.N~` so `WeiDU.log` shows which build an install came from.
- `tests/` drive a real `weidu.exe` against synthetic fixtures (`python -m pytest tests`; set `WEIDU=` to a WeiDU ≥ 249 binary). No live game is touched.

## Changes vs upstream

| # | Change | Kind | Source | Live patch |
|---|---|---|---|---|
| 1 | **Protection from Magic Energy / Protection from the Elements / Protection from Energy** strip the *caster's* buff instead of refreshing the *recipient's* (the EE "refresh, non-stacking" opcode 321 was inserted with effect target 1 = Self; creature-targeted spells need target 2 = Projectile target). Casting any of them on an ally removed it from the caster, and re-casting on the same ally never replaced the old instance. | bug fix | `spell_rev/lib/refresh_non_stacking.tpa` → `MAKE_REFRESHING_DIRECT` derives the target from the ability's target type | `live-patch/SRCB_PROT_REFRESH` |
| 2 | **Joinable NPCs can retain or receive SR's hidden Protection from Fire / Cold / Electricity / Acid implementation spells** even though SR repurposes them as choices behind Protection from Elemental Energy. | bug fix / migration | Component 60 resolves the effective container and replaces only proven hidden child grants—both CRE spellbook entries and exact `AddSpecialAbility` calls in joinable-NPC scripts—with the public parent spell | None — integrated into late component 60 |

Design notes live in `docs/plans/`; the upstream-ready write-up of each bug in `docs/upstream-reports/`.

## Installation

Same as upstream (below): copy `spell_rev/` into the game directory and run it with WeiDU.
For an **existing** install, don't reinstall Spell Revisions mid-stack — append the relevant
`live-patch/` mini-mod at the tail instead (see `live-patch/README.md`).

Install component 60, **Update Spellbooks of Joinable NPCs**, after every mod component that
adds an NPC or changes an NPC's class, kit, spellbook, or scripts. On future full installs this
makes the old standalone `SR_SUBSPELL_FIX` unnecessary. Do not uninstall an already-installed
copy from a frozen WeiDU stack merely to replace it; leave that stack untouched until a validated
rebuild. Component 60 patches game CRE and BCS resources, not NPCs already embedded in a save.

---

# Upstream README (Spell Revisions v4.21, unchanged below this line)

Spell Revisions aims to fix, tweak, and enhance arcane and divine spells in Baldur's Gate II, either the classical or the enhanced editions, including [BGT](https://github.com/SpellholdStudios/BGT-WeiDU) and [EET](https://github.com/Gibberlings3/EET).

The mod comes with documentation that you can find [here](./readme-spell_rev.html). Detailed lists of spells can be consulted [here](https://gibberlings3.github.io/SpellRevisions/).

note(s):
* The spell documentation, both the one shipped with the mod and the one in [GitHub](https://gibberlings3.github.io/SpellRevisions/), has *not* been updated to reflect the changes since the 4.18beta. The in-game documentation is of course, fully updated.

# A. Latest release.

Latest release is 4.21 downloadable from the releases sidebar.

From the github page, click on releases in the side-bar to download it. If you are feeling *really* adventurous, then you can download the absolute latest by clicking on the code button and then downloading the zip. Note that this is a *source release*; it just bundles the files in the GitHub repository in an archive and does not have any executables, so for the installation you will need the command line -- see section below. It is slightly more inconvenient for users than the standard release, but it allows for faster and more timely releases.

# B. Installation.

Installation is like any other WeiDU mod -- see [A New Player’s Guide to Installing and Playing Mods](https://www.gibberlings3.net/forums/topic/33164-a-new-player%E2%80%99s-guide-to-installing-and-playing-mods/).

## B. 1. Command line.

Assuming you have WeiDU [^1] installed and on the executable path [^2], just download the release zip file, unzip it with whatever archive unzipper your platform supports into some temporary location, and copy the folder [^3] `spell_rev` to your Baldur's Gate install directory. Then open a command line, change directory to the BG installation dir and do

```bash
weinstall spell_rev
```

and install the components you want.

## B. 2. Double-clicking.

If the command line is proving to be too difficult (e.g. Windows platform, do not have `weinstall` in the executable path, etc.), you can install as usual by double clicking the executable installer. For a *source release* that does not come with an executable installer, you can proceed as follows:

  * Do the same download, copy into BG installation dir, etc. as in previous point B. 1.

  * Download any, relatively recent updated, mod with such an installer, e.g. [Tweaks Anthology](https://www.gibberlings3.net/files/file/973-the-tweaks-anthology/).

  * Grab its executable installer, rename it as `setup-spell_rev.exe` and drop it on the parent dir of `spell_rev` (e. g. the folder with the `chitin.key` file).

  * Double-click the executable and proceed as usual.

[^1]: latest version can be grabbed from [here](https://github.com/WeiDUorg/weidu/releases).

[^2]: precise details depend on the platform.

[^3]: for a source release, the top folder is *not* what one wants, rather it is the `spell_rev` subfolder.

# C. Mod order.

For general advice on install order, you can consult various submitted mod load orders at [Baldur's Gate Install Order List Repository](https://github.com/morpheus562/Baldurs-Gate-Install-Order-List-Repository).

SR's main component does wholesale spell replacement, so it should be installed relatively early in the install order, certainly before Tweaks Anthology and SCS. On the other hand the "Update NPC spellbooks" component should be installed after all NPC mods.
