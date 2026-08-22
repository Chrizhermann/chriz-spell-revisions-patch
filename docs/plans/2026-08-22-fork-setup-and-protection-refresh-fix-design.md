# Design: Spell Revisions fork setup + "Protection from … refresh strips the caster" fix

Date: 2026-08-22
Status: implemented (see "Verification"); in-game confirmation pending

## 1. Goal

1. A public, credited fork of [Gibberlings3/SpellRevisions](https://github.com/Gibberlings3/SpellRevisions)
   that tracks upstream and carries Chriz's fixes/balance changes, in the same shape as the
   sibling forks (`The-Artisan-s-Kitpack-Chriz-Balance-Patch`, `Bardic-Wonders-Chriz-Balance-Patch`).
2. First fix: **Protection from Magic Energy (L6), Protection from the Elements (L7) and
   Protection from Energy (L8)** behave as if only one creature can hold the buff at a time,
   contradicting their descriptions ("the recipient receives complete protection …").

## 2. Fork shape (mirrors the sibling forks)

| Piece | Decision |
|---|---|
| GitHub | `Chrizhermann/chriz-spell-revisions-patch`, a real GitHub fork of `Gibberlings3/SpellRevisions` (public). Local remotes: `origin` = fork, `upstream` = G3. |
| Branching | Work on `master`; sync with `git fetch upstream && git merge upstream/master`. Merge, never rebase, so upstream commits keep their hashes. |
| README | Fork banner + credits at the top, upstream README kept verbatim below a divider (merge-friendly). |
| Where fixes live | In the mod source (`spell_rev/...`) so fresh installs get them, **plus** `live-patch/<NAME>/` tail mini-mods that retrofit an *already installed* SR without uninstalling (never-uninstall rule for the main EET install). |
| Version marker | `VERSION ~v4.21-chriz.1~` in `spell_rev/setup-spell_rev.tp2` so `WeiDU.log` shows which build an install came from (provenance). Bump the `-chriz.N` suffix per fork release; it resets when upstream bumps. |
| Upstream drift | `.github/workflows/check-upstream.yml` (weekly) opens an `upstream-sync` issue listing new upstream commits and the files this fork patches. |
| Tests | `tests/` — pytest driving a real `weidu.exe` against synthetic fixtures (the `--nogame` harness and the synthetic fake-game patterns from `chriz-bg-rebalance`). No live game is ever touched. |
| Docs | `docs/plans/` design docs (committed, like the AK fork); `docs/upstream-reports/` bug reports written so they can be pasted into an upstream issue/PR. |

Upstream has no LICENSE file; its readme says the mod "may not be … redistributed in any form
without the consent of its author" (© Marco Montagnoli). The fork therefore presents itself as a
patch set on top of upstream, credits the authors first, and offers every fix back upstream — not
as a competing release.

## 3. The bug

### Symptom
Casting Protection from Magic Energy / the Elements / Energy on a second party member removes the
buff from the first one (when the first one was the caster). Re-casting on the same ally does
not replace the older instance either.

### Root cause — verified in the installed binaries and in upstream source
Upstream `spell_rev/lib/refresh_non_stacking.tpa` (PR #75, 2021, "Re-write and bug-fix EE refresh,
non-stacking code") makes buffs *refreshing* by inserting an opcode 321 "Remove effects by
resource = itself" as the first effect, so a new cast replaces the old instance instead of
stacking. Most spells get it via `MAKE_REFRESHING`, which **clones the spell's existing op206
self-protection** — inheriting that effect's target byte (2 = "Projectile target", i.e. the
recipient). Seven spells have no op206 to clone, so the 321 is added directly:

```
LPF ADD_SPELL_EFFECT INT_VAR opcode = 321 timing = 1 target = 1 /*Self*/ insert_point = 0 ...
```

Effect target **1 = "Self" = the caster**, not the recipient (IESDP SPL/EFF target types:
1 Self, 2 Projectile target; e.g. vanilla `SPWI119A` Larloch's Minor Drain puts its damage on
target 2 and its caster-side sound on target 1). For the four *caster-only* spells in that list
(Mirror Image, Wraith Form, Minor Globe, Globe — ability target 5) Self and recipient coincide
and the code is right. For the three *creature-targeted* ones (ability target 1) every cast
now strips the **caster's** own instance and never refreshes the recipient's.

Installed evidence (`SR v4.19 + SCS`, `override/spwi606.spl`, same for 702/803):

```
ability[0] target=1 (creature)
  fx[0] op=321 tgt=1 res='SPWI606'   <- refresh hits the caster
  fx[1] op=31  tgt=2 ...             <- everything else hits the recipient
```

Control: Spirit Armor (`spwi414`, creature-targeted, `MAKE_REFRESHING` path) has
`fx[0] op=321 tgt=2` — correct.

SR's own description says "the recipient receives complete protection" — the user's reading is
right; the behaviour is a bug, not a design choice. Not reported upstream (issue #144 is a
different, engine-side 321 topic).

## 4. Fix options

| | Option | Verdict |
|---|---|---|
| A | **Derive the 321's target from the ability's target type** (5/7 → Self, otherwise → Projectile target) in a new `MAKE_REFRESHING_DIRECT` patch function; the direct list calls it. | **Chosen.** Minimal, self-describing, upstreamable, keeps refresh semantics for all seven spells. |
| B | Always `target = 2`. | Works in-engine (projectile target of a self-cast is the caster) but rewrites four correct spells for no reason; bigger diff. |
| C | Drop the 321 and rely on op206 self-immunity (vanilla behaviour). | Loses the refresh design SR wants. |
| D | Binary-replace the SPLs in override (old modpack style). | Brittle vs. SCS/other edits; not upstreamable. |

## 5. Components

### 5.1 Source fix — `spell_rev/lib/refresh_non_stacking.tpa`
New `DEFINE_PATCH_FUNCTION MAKE_REFRESHING_DIRECT` next to `MAKE_REFRESHING`; reads
`0x64` (ability offset) / `0x68` (ability count) / ability `+0x0c` (target type) and calls
`ADD_SPELL_EFFECT` with `target = fx_target`. The third `WITH_SCOPE` block calls it instead of
inlining `ADD_SPELL_EFFECT`. Everything else in the file is untouched (merge-friendly).

### 5.2 Live patch — `live-patch/SRCB_PROT_REFRESH`
Tail-installable WeiDU mini-mod for an already-installed SR (v4.19+ on EE):
`REQUIRE_PREDICATE` SR main installed + EE engine; resolves the three spells **by
`spell.ids` symbol** (`WIZARD_PROTECTION_FROM_MAGIC_ENERGY` / `…THE_ELEMENTS` / `…ENERGY`)
via `RES_NUM_OF_SPELL_NAME` — never hard-coded resrefs (SR relocates spells). For each, walks
every ability header and rewrites effects matching `opcode 321 AND target 1 AND resource ==
own resref` to target 2; skips spells whose ability target is 5/7. Idempotent; `BUT_ONLY`;
uninstall restores bytes. Active saves: SPLs are read at cast time, so no console step.

### 5.3 Tests — `tests/test_prot_refresh_target.py`
- `--nogame` harness (`tests/weidu/prot_refresh_harness.tp2`): reproduce upstream's
  `ADD_SPELL_EFFECT target=1` build from the fork's source SPLs (= the bug state), build the
  `target=2` expectation, and assert `live-patch fix(bug build) == expectation` **byte-exact**
  for 606/702/803; idempotency; caster-only spells (212/406) untouched; foreign 321s untouched.
- Synthetic fake game: runs the real `spell_rev/lib/refresh_non_stacking.tpa` (needs
  `spell.ids`, `COPY_EXISTING`) and asserts the fork produces target 2 for the three spells and
  target 1 for the caster-only ones; runs the **upstream v4.21 copy** of the file as a control
  and asserts it produces target 1 (proves the test detects the bug); installs/uninstalls the
  live patch through its public tp2 and asserts byte-exact override restore.
- `--parse-check` on every new tp2/tpa.

## 6. Verification status
- Static/WeiDU: see `tests/` run log in the commit message.
- In-game (to do, needs the live client): Mage casts PfME on self, then on a fighter → both
  keep the icon; recast on the fighter → still one instance (effect list via EEex console).

## 7. Out of scope (candidates for later fork work)
- Migrate the modpack's existing SR fixes here: `SR_SUBSPELL_FIX` (hidden Prot.-from-element
  subspells left in NPC spellbooks) and the `spwi910` Imprisonment/Death Ward rework.
- The SR "wishlist" (cherry-pick/revert/re-tune) from `chriz-bg-rebalance/docs/00-project-scope.md`.
