# Changelog

## Unreleased (proposal, not accepted)

- Proposal 0011 (gap G11), documentation only: name the SDK's pointer-only
  Organization the "workspace index", with the new record tokens
  `rapp-work-workspace-index/1` and `rapp-work-workspace-index-pointers/1`,
  while every `rapp-work-organization/1` and
  `rapp-work-organization-pointers/1` record keeps verifying. See
  `docs/proposals/0011-workspace-index-name.md`. No code, token, profile
  text, pin or behavior changes. Intended releases if accepted: 1.1.0 (read
  both forms) and 1.2.0 (write the new form, convert through migration).

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
