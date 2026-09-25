# Changelog

## Unreleased (proposal, not accepted)

- Proposal 0004 (gap G4): explicit, opt-in pointer-only migration successors
  (`migrate` input `successor: "pointer-only"` and planning-only `hive`
  description; CLI `--successor pointer-only --hive <file>`). They bind a
  repository-seeded Hive, or a source with a world id longer than 64
  characters, by exact authority-byte commitments, and write only
  `rapp-work-pointer-successor/1` plus the existing receipt and recovery
  marker. A description is corroborated against the source's recognized Hive
  records, including a Private Hive publication's genesis declaration found
  through its current pointer; Git directories and Git internals are refused.
  New tokens: `rapp-work-pointer-successor/1`,
  `rapp-work-pointer-successor-plan/1`, and
  `rapp-work-pointer-successor-source/1`. World ids of up to 128 characters
  are accepted only inside the pointer token. Without `successor`, `migrate`,
  `update` and `verify` are unchanged; the static API metadata (returned by
  `status` and `discover`) lists the two new optional `migrate` inputs.
- Intended release: 1.1.0, after owner acceptance. The package version is
  unchanged.

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
