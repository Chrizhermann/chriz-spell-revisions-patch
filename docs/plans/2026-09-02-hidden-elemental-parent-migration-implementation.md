# Hidden Elemental Parent Migration Implementation Plan

**Goal:** Replace proven hidden elemental child grants with the effective Protection from
Elemental Energy parent across joinable-NPC CRE spellbooks and referenced NPC scripts.

**Architecture:** Reuse the existing semantic three-way child proof and resolved parent. Extend
the CRE transformer to migrate known/memorized entries to the parent, then patch only scripts
referenced by joinable-NPC CRE slots so exact `AddSpecialAbility(child)` actions grant the parent.

**Tech stack:** WeiDU 249 TP2/TPA/BCS patching, Python pytest fake-game and `--nogame` harnesses.

---

### Task 1: Lock the corrected behavior with failing tests

**Files:**
- Modify: `tests/test_npc_hidden_subspells.py`
- Modify: `tests/weidu/fake_game_npc_spellbooks.tp2`

1. Change CRE assertions from removal-only to parent replacement, including known and memorized
   multiplicity and an already-present parent.
2. Add a joinable Neera CRE whose override script contains `AddSpecialAbility(child)` plus an
   unrelated action, and an unrelated control script.
3. Run the focused test and verify it fails because the parent is absent and the child script
   action remains.

### Task 2: Implement the minimal semantic migration

**Files:**
- Modify: `spell_rev/lib/hidden_elemental_subspells_patch.tph`
- Modify: `spell_rev/lib/hidden_elemental_subspells.tpa`

1. Resolve and validate the parent wizard level.
2. For valid joinable CREs, count child known/memorized grants, remove them, add the parent once
   to known spells and with matching memorized multiplicity.
3. Collect effective script slots from joinable CREs and replace exact child
   `AddSpecialAbility` calls with the parent.
4. Run focused tests until green, then run the complete suite.

### Task 3: Correct documentation and acceptance evidence

**Files:**
- Modify: `README.md`
- Modify: `spell_rev/changelog.md`
- Modify: `spell_rev/readme-spell_rev.html`
- Modify: `docs/plans/2026-09-01-hidden-elemental-subspell-migration-design.md`

1. Remove all removal-only / no-parent-grant claims.
2. Record the natural Beregost Neera runtime injector and parent replacement behavior.
3. Reinstall the candidate in the isolated EET clone and verify effective CRE and BCS outputs.
4. Run the short natural-recruitment acceptance; then execute the already-authorized release
   sequence only on a pass.
