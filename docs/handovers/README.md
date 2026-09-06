# Deferred handovers

Received follow-ups are recorded here without treating them as implemented changes,
release commitments, or authorization to touch a live game.

## Death Ward and physical vorpal attacks

- **Status:** received 2026-09-06; deferred until separately requested. Keep the
  current RR/SR AI compatibility work independent.
- **Handover:** [SR Death Ward and physical vorpal attacks](2026-09-06-sr-death-ward-vorpal.md).
- **Requested semantics:** Christopher wants SR Death Ward to protect against death
  magic, but not physical vorpal attacks. The inspected blanket opcode-13 immunity
  is reported as confirmed behavior; SR author intent remains unconfirmed. This
  is a requested correction, not a proven upstream bug.
- **Required before implementation:** revalidate the current supported spell and
  helper chain; audit death-magic dependencies, actual vorpal delivery, resource
  protections, and state guards before removing any blanket immunity. Preserve
  Death Spell, Finger of Death, Power Word Kill, Disintegrate, Wail of the Banshee,
  and other protection promises found by that audit, along with unrelated effects.
  Retain the handover's dynamic resolution, ownership/shape preflight, fixture,
  idempotence, application-order, and fresh-cast acceptance requirements.
- **Scope boundary:** Death Ward only. Avoid Death, Hindo's Doom, other immunity
  providers, global death handling, and BG Rebalance's dragon attack implementation
  remain outside this follow-up. Preserve SR Planetar weapon probabilities and saves.
- **Authorization:** record only. No implementation, component number, release,
  live-game write, install, launch, save mutation, or deployment is authorized.
