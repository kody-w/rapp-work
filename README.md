# RAPP Work

**Business collaboration and compliance for the RAPP/1 ecosystem.**

RAPP Work adds organizational policy around RAPP/1 objects without changing
the RAPP/1 frame, identity, hashing, signature, egg, or registry contracts.

## What lives here

- [`SPEC.md`](SPEC.md) — the `rapp-work/1` business/compliance profile.
- [`protocols/rapp-hive/1`](protocols/rapp-hive/1/SPEC.md) — sovereign Private
  Hives, sealed GODD rooms, Dream Catcher convergence, and storage portability.
- [`protocols/rapp-federation/1`](protocols/rapp-federation/1/SPEC.md) — the
  universal logical Hive Mind: consent-bound federation among sovereign Hives.
- [`.github/skills/rapp-work`](.github/skills/rapp-work/SKILL.md) — project
  skill for navigating and extending RAPP Work.
- [`.github/skills/rapp-workspace-manager`](.github/skills/rapp-workspace-manager/SKILL.md)
  — the main entrypoint for creating, registering, listing, and opening local
  RAPP Workspaces.
- [`rappid.json`](rappid.json), [`owner-anchor.json`](owner-anchor.json), and
  [`registry.json`](registry.json) — the public identity and signed adoption
  record for this standards estate.

The runnable RAPP Workspace and Private Hive project skills ship in
[`kody-w/rapp-workspace`](https://github.com/kody-w/rapp-workspace).

## Start here

Clone this repository and launch Copilot:

```bash
git clone https://github.com/kody-w/rapp-work.git ~/rapp-work
cd ~/rapp-work
copilot
```

Then ask:

```text
Use /rapp-workspace-manager to create my first RAPP Workspace.
```

## Core boundary

| Layer | Responsibility |
|---|---|
| **RAPP/1** | Canonical bytes, RAPPIDs, frames, hashes, signatures, eggs, registries, and trust. |
| **RAPP Work** | Business policy: worlds, data classes, membership, rooms, agreements, approvals, receipts, compliance, and audit. |
| **RAPP Workspace** | The local-first workspace product and project skills. |
| **Private Hive** | The access-restricted shared portion of a workspace. |
| **Hive Mind** | The universal singleton logical federation of sovereign Private Hives. |

## Principles

- Humans, AIs, agents, and services participate through the same RAPPID,
  signature, policy, and evidence rules.
- DOGG is globally safe and never contains PII.
- GODD is private; selected GODD remains GODD and requires scoped protection.
- Private Hives remain sovereign. Federation never creates a global owner,
  key, database, or writable Mother Hive.
- Storage and transports are replaceable adapters, never authority.
- Unsupported capabilities fail closed rather than returning success-shaped
  placeholders.

## Verify

```bash
python3 tools/check.py
```

The check validates the vendored RAPP/1 pin, signed registry, profile index,
schemas, Hive conformance, and Federation conformance.

## Status

The public repository is a signed RAPP/1 standards estate. Profile activation
still occurs independently in each adopting estate through its own signed
registry and trust anchor.

MIT.
