# Changelog

## Unreleased (proposal, not accepted)

- Proposal 0017 (gap G17): added `integrations/brainstem/agents/rapp_work_agent.py`,
  a single-file Brainstem agent for the newest Brainstem channel
  (`brainstem-v0.6.16`) that calls only the six public SDK operations and applies
  only a plan whose exact SHA-256 the person confirmed in a later turn. It is
  source-distribution only: the `rapp_work` package, the wheel, the public API and
  `SDK_VERSION` are unchanged.
- Added hot-load, isolation and end-to-end tests
  (`tests/test_brainstem_agent.py`, `tests/test_brainstem_agent_isolation.py`,
  `tests/brainstem_harness.py`) and brought the agent under ruff and mypy.

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
