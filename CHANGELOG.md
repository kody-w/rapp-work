# Changelog

## Unreleased (proposal, not accepted)

- Proposal 0007 for gap G7
  ([`docs/proposals/0007-sdk-instruction-inventory.md`](docs/proposals/0007-sdk-instruction-inventory.md)):
  `rapp-work-sdk/1` §7 inventories AI instruction files. A new SDK-owned
  record, `.rapp-work/instructions.json` (`rapp-work-instruction-inventory/1`),
  covers the closed `rapp-work-instruction-set/1` and is listed in the
  unchanged `rapp-work-managed-files/1` inventory.
- A Workspace or Organization that owns the record is verified against it: an
  edited, missing, new, hard-linked, or non-regular instruction file, a link
  that exposes content the bounded no-follow scan cannot see, an incomplete
  scan, and an exceeded bound are refused, with paths and reasons, never file
  content. In-tree links are recorded with the bytes read through them.
- A tree without the record (for example one integrated by SDK 1.0.0) is not
  refused: it verifies as `verified-without-instruction-inventory` with
  `instruction_inventory: "absent"`. The new optional `verify` input
  `require_instruction_inventory` (CLI `--require-instruction-inventory`)
  refuses it with `REFUSE_INSTRUCTION_INVENTORY_ABSENT`.
- The only acceptance path is a reviewed `update` plan, with a derived
  `rapp-work-instruction-review/1`, applied with its exact SHA-256. A fresh
  apply rescans before its first write; a resumed apply completes the reviewed
  writes and reports later changes. An apply whose closing verification
  refuses reports `updated-unverified` with the refusal instead of hiding its
  effects. A tree without the record that cannot be inventoried is updated as
  SDK 1.0.0 would, and the review says why.
- Scaffold and migration plans gain the inventory, so their canonical hashes
  differ for new plans.
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
