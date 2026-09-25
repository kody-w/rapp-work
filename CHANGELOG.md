# Changelog

## Unreleased (proposal, not accepted)

Proposal 0006 (gap G6), intended for `1.1.0`; see
`docs/proposals/0006-owner-succession.md`.

- Synced `vendor/rapp-1/rapp_registry.py` to the exact bytes at the already
  accepted canonical commit `591e014` and pinned them with the additive
  `RAPP1_REGISTRY_PIN.json` record (`rapp-work-parent-registry-pin/1`). This
  also fixes drift: the vendored copy lagged its `RAPP1_PIN.json` commit.
- Added opt-in RAPP/1 section 13.2 owner succession to the `rapp-hive/1`
  reference: `RegistryAuthority(..., succession="rapp1-13.2",
  tombstone_issued_at=..., retained_registry=...)`. The default authority
  still fails closed on `re-anchor`, and its behavior and `checkpoint()` are
  unchanged; it no longer needs `rapp_registry.py` to import. Under
  succession: retained registry state (owner lineage and lifecycle entries,
  carried in `checkpoint()`) is required for a predecessor anchor or any
  persisted floor, so no later registry can undo a succession or revocation;
  causal bounds stop back-dated owner acts over later state; and a compromise
  re-anchor must share one observed append with its tombstone. Added check H21
  (pinned reference parity) and H22 (30 succession vectors).
- Added the read-only `rapp_work.registry` submodule: registry, owner
  succession, compromise re-anchor, and lineage verification through the
  pinned reference, with a `retained` input for the caller's last verified
  registry. Performing owner rotation stays refused.
- Updated `rapp-work-sdk/1` section 5.1, inserted a section 12 paragraph, and
  refreshed their profile pins.

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
