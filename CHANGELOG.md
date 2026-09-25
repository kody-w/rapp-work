# Changelog

## Unreleased (proposal, not accepted)

- Proposal 0002 (gap G2), not accepted: `update` can plan and apply exact,
  reversible file moves as a new `rapp-work-move-plan/1` token through two
  optional closed inputs, `moves` and `inverse_of`, and the CLI flags `--move`
  and `--inverse-of`. `rapp-work-release-plan/1` is unchanged. A move links
  without replacing, verifies, then unlinks, under a plan-bound
  `rapp-work-move-recovery/1` marker; an SDK update apply is refused while a
  move recovery is pending. `rapp-work-sdk/1` §§2 and 4 carry the proposed
  text, and its SPEC hash pins in `protocols/index.json` and
  `src/rapp_work/data/profiles.json` are updated. See
  `docs/proposals/0002-sdk-move-action.md`.

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
