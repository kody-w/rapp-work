# Changelog

## Unreleased (proposal, not accepted)

- Proposal 0007 for gap G7
  ([`docs/proposals/0007-sdk-instruction-inventory.md`](docs/proposals/0007-sdk-instruction-inventory.md)):
  `rapp-work-sdk/1` §7 inventories AI instruction files. A new SDK-owned
  record, `.rapp-work/instructions.json` (`rapp-work-instruction-inventory/1`),
  covers the closed `rapp-work-instruction-set/1` and is listed in the
  unchanged `rapp-work-managed-files/1` inventory.
- Workspace and Organization verification refuses an edited, missing, new,
  symlinked, hard-linked, or non-regular instruction file, an exceeded scan
  bound, and a workspace without an inventory. It reports paths and reasons,
  never file content.
- The only acceptance path is a reviewed `update` plan, with a derived
  `rapp-work-instruction-review/1`, applied with its exact SHA-256. Apply,
  including a resumed apply, rescans before the first write.
- Scaffold and migration plans gain the inventory, so their canonical hashes
  differ for new plans; applied workspaces are unaffected until verified.
- Intended release 1.1.0. Not accepted; the owner decides. `SDK_VERSION` is
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
