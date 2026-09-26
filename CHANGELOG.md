# Changelog

## Unreleased (proposal, not accepted)

- Proposal 0003 (gap G3, `docs/proposals/0003-sdk-agent-discovery.md`):
  `discover` accepts the optional input `agents` (CLI `--agents`). With
  `agents: true` it records Brainstem single-file agents (`*_agent.py`) as
  inert `rapp-work-discovered-agent/1` data in an `agents` result member.
  Agent source is parsed, never imported, compiled to bytecode, or executed;
  `live` marks a file at the top level of the scanned root's live `agents`
  directory by position only, and `basic_agent.py` is recorded as the base
  class. Without `agents`, discover results are unchanged apart from the
  embedded static API document.
- Every parse of discovered Python, including Portable Neurons, now follows a
  token-level measure with fixed nesting, cost, integer-literal, and
  replacement-field bounds, which removes a process crash on Python 3.10 and
  bounds time and memory. A Portable Neuron outside the bounds is refused like
  one the parser rejects.
- The proposed normative text is `rapp-work-sdk/1` §11.1 and §11.2, and the
  SDK profile pins follow its bytes. The package version is unchanged until
  the owner accepts a release.

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
