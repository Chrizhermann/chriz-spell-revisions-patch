# Two-Version Live Smoke Test Implementation Plan

**Goal:** Prepare clearly disposable BG2:EE 2.6.6.0 and 2.7.3.0 test games with the configurable mod and two settings profiles.

**Architecture:** Make full independent copies under one deletion-marked parent. Stage the same committed mod snapshot and WeiDU 249 executable in each copy, but do not install yet.

**Tech Stack:** PowerShell, Robocopy, Git, WeiDU 24900.

---

### Task 1: Validate sources and safety

- Confirm both `Baldur.exe` versions and zero WeiDU components.
- Confirm no game or loader process is running.
- Confirm at least 10 GB free space.

### Task 2: Create independent copies

- Copy each complete clean game with Robocopy `/E /COPY:DAT /DCOPY:DAT`.
- Treat Robocopy exit codes 0 through 7 as success.
- Hash-compare `Baldur.exe`, `chitin.key`, and `dialog.tlk` with each source.

### Task 3: Stage the mod and profiles

- Copy the repository `spell_rev` directory into each game.
- Copy WeiDU 24900 as `setup-spell_rev.exe`.
- Save `ALL-ON.settings.ini` and `SPARSE-SMOKE.settings.ini` under
  `SR-TEST-PROFILES` in each game.
- Leave the active `spell_rev/settings.ini` on ALL-ON for the first install.

### Task 4: Mark and verify cleanup boundary

- Add `DELETE_THIS_WHOLE_FOLDER_AFTER_TESTING.txt` to the parent.
- Record source paths, versions, commit, destination paths, and deletion rule.
- Verify destination versions, staged profiles, mod commit marker, and absence
  of installed components.

### Later interactive step

Install and smoke-test ALL-ON on both versions, restore/uninstall, switch to
SPARSE-SMOKE, install again, and test the five selected spells plus disabled
controls. Do not launch either copy automatically.

