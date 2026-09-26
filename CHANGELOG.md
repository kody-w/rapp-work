# Changelog

## Unreleased

- Added an experimental `CONSTITUTION.md` (not in force until ratified):
  lessons from the Hive redesign and four pending amendments.
- Added an experimental `ECOSYSTEM.md`: the RAPP/1 organism layer by layer, with
  a graph and a gap register.
- Added `organism/`, a pullable template of that organism: one markdown file per fact and a
  standard-library builder that generates `ECOSYSTEM.md`, the genome `organism/ORGANISM.md` and
  every view (the graph moved from `docs/ecosystem.*` to `organism/views/`).
- The organism shows the path to a locked RAPP/1: each layer's lock status, five phases
  with who acts, and a printable lock-in page (`organism/views/lock-in.html`).

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
