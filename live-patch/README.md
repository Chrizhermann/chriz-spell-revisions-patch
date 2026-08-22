# Live-install tail patches

WeiDU mini-mods that retrofit this fork's fixes onto an **already-installed** upstream Spell
Revisions, so they can be appended at the tail of a live install's WeiDU stack without
uninstalling anything (the never-uninstall rule for the main EET install).

Fresh installs don't need these — install the fork's `spell_rev/` itself instead; its
`lib/*.tpa` produce the same end state.

## SRCB_PROT_REFRESH

**Fix: Protection from Magic Energy / Protection from the Elements / Protection from Energy
strip the caster's buff instead of refreshing the recipient's** (EE games, Spell Revisions
v4.19+; design and root cause in
`docs/plans/2026-08-22-fork-setup-and-protection-refresh-fix-design.md`).

Upstream inserts the "refresh, non-stacking" `opcode 321 remove-effects-by-resource = itself`
with effect target 1 (*Self* = the caster). On these three creature-targeted spells that
removes the **caster's** own protection every time the spell is cast on an ally, and never
replaces an older instance on the recipient. The patch rewrites exactly those effects to target
2 (*Projectile target* = the recipient) in every ability header of the three spells, resolved
by `spell.ids` symbol (`WIZARD_PROTECTION_FROM_MAGIC_ENERGY` / `…THE_ELEMENTS` / `…ENERGY`),
never by hard-coded resref. Caster-only spells are left alone. Idempotent; uninstall restores
the previous bytes.

Requires Spell Revisions' main component (`spell_rev` #0). Install from the game dir after
copying the `SRCB_PROT_REFRESH` folder there and creating `setup-SRCB_PROT_REFRESH.exe` as a
copy of any WeiDU v249 setup exe:

```
./setup-SRCB_PROT_REFRESH.exe --force-install-list 0 --language 0 --no-exit-pause
```

No console step: SPL files are read when a spell is cast, so the fix applies to existing
saves on the next cast. Buffs that are already running are unaffected either way.

Acceptance test in-game: a mage casts Protection from Magic Energy on themself, then on a
fighter — both keep the portrait icon; casting it on the fighter again leaves a single
instance. Undo: re-run the exe and `[U]ninstall`.

Verified with `python -m pytest tests` (WeiDU 249): byte-exact against an expected build,
idempotent, caster-only spells and foreign opcode-321 effects untouched, public
install/uninstall round-trips a synthetic game byte-exactly, and the component refuses to
install without Spell Revisions.
