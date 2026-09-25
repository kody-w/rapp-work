# Changelog

## Unreleased (proposal, not accepted)

- Draft proposal 0001 (gap G1: a `rapp-hive/1` roster can never change):
  [`docs/proposals/0001-rapp-hive-roster-declaration.md`](docs/proposals/0001-rapp-hive-roster-declaration.md).
  It proposes owner-signed later `hive.declaration` frames on the Mother
  stream, with the unchanged closed `rapp-hive/1-declaration` schema, as the
  single next Mother frame. The owner can then add or remove members, change
  roles and room membership, add rooms, and switch channels. Roster authority
  is judged at the acceptance position. Accepted history is never re-evaluated.
  A declaration changes the roster, never the RAPP/1 registry; the proposal
  requires the registry first for an admission and keeps a removed member's
  key registered.
- The reference `HiveAcceptance` gains an explicit, keyword-only
  `roster_declarations=False` opt-in, `accept_declaration(frame_hash)`, and a
  read-only `declaration` property. With the opt-in, a projection receipt's
  channel is also checked against the roster in effect when it is accepted.
  The default gate still refuses every later declaration. Its behavior is
  unchanged, and the 56 existing authenticated vectors are unchanged.
- Added `protocols/rapp-hive/1/reference/roster_declaration_conformance.py`
  (96 vectors, run as Hive check H21). It covers default refusal, positive
  and refusal vectors with real Ed25519 signatures, the registry side of
  roster changes, and a replay of every authenticated vector in proposal mode.
  Mirrored the reference into the vendored `rapp-private-hive` copy, moved
  that skill to version 3.2.1, and updated its lock.
- The SPEC, schema, signed registry and every signed pin are unchanged.
  Activation needs the owner to accept the text and re-sign the registry.
  Intended release: `rapp-work` 1.1.0.

## 1.0.0 — 2026-09-18

- Replaced the standards-only front door with the installable, typed
  `rapp-work` / `rapp_work` SDK.
- Added canonical JSON operations: `status`, `verify`, `discover`, `scaffold`,
  `update`, and `migrate`.
- Added exact plan-hash apply gates, no-follow filesystem effects, closed
  inputs, canonical output, and offline/no-credential defaults.
- Added the `rapp-work-sdk/1` workspace integration profile without modifying
  frozen signed parent authority.
- Pinned RAPP/1 and the canonical `rapp-work/1` specification/schema to
  accepted `kody-w/rapp-1` commit `591e014`, while preserving root `SPEC.md`
  and the signed registry as distinct historical estate evidence.
- Added RAPP/1 Frame wrappers, `ProfileRegistry`, Workspace, pointer-only
  Organization, Hive high-water vectors, release evidence/observations,
  create-only migration receipts/recovery, inert Portable Neuron compatibility,
  static discovery metadata, and filesystem/local-private-Git transports.
- Exposed historical workspace-manager and Private Hive behavior through
  deprecated SDK compatibility wrappers.
- Required explicit privacy evidence and token files for historical hosted
  private-Git transport; ambient credentials are no longer inherited.
- Added adversarial SDK, CLI, migration, discovery, transport, packaging, and
  compatibility tests.
