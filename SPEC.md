# rapp-work/1

`spec_id: rapp-work/1`

RAPP Work is the business collaboration and compliance layer of the RAPP/1
ecosystem. It is subordinate to RAPP/1 and MUST refuse in favor of RAPP/1 on
any conflict.

## 1. Inherited authority

RAPP Work does not redefine:

- RAPPID identity;
- RFC 8785 canonicalization;
- RAPP/1 particle and wave hashes;
- the eleven-key frame envelope;
- stream chaining and fork refusal;
- detached signatures;
- eggs and sealed artifacts; or
- signed registry authority.

An estate adopts a RAPP Work profile only through an owner-signed RAPP/1
`protocol` registry entry pinning the exact repository, path, and SHA-256.

## 2. Participants

A participant is a RAPP identity. Humans, AIs, agents, services, and hybrid
teams receive no automatic privilege or disability based on actor type.
Authority comes from signatures, roles, grants, policy, and evidence.

## 3. Worlds

Every workspace and Hive belongs to a hard `world_id`. Data may slosh inside a
world under policy. It MUST NOT cross a world boundary without explicit source
authorization, destination authorization, purpose, and provenance.

## 4. DOGG and GODD

DOGG and GODD classify data, not storage locations.

- **DOGG** is globally safe. DOGG MUST NOT contain PII, secrets, credentials,
  private prompts, or plaintext GODD.
- **GODD** is private data. Personal GODD is local-only by default. Explicitly
  shared GODD remains GODD and requires access restriction and, where declared,
  sealed-artifact protection.
- **Neutral** RAPP objects contain no private data but require explicit
  publication authorization before leaving a workspace.

A private repository does not make unsafe data DOGG. A public-safe object does
not become GODD merely because it is stored privately.

## 5. RAPP Workspace

RAPP Workspace is the local-first product layer. It carries project skills in
`.github/skills`, preserves one workspace identity and world, and can migrate
older workspaces additively without changing their original data or frame
history.

Canonical implementation:
[`kody-w/rapp-workspace`](https://github.com/kody-w/rapp-workspace).

## 6. Private Hive

A Private Hive is the intentionally shared, access-restricted portion of a
workspace. It is itself a RAPP/1 workspace object and may contain any verified
RAPP/1 object.

The normative profile is
[`rapp-hive/1`](protocols/rapp-hive/1/SPEC.md). It defines membership, member
areas, shared projects, sealed rooms, GODD slices, storage channels, Mother
Hive authority, dimensions, Dream Catcher convergence, projections, and
PII-free template eggs.

Each Private Hive remains sovereign.

## 7. Hive Mind

The Hive Mind is the universal singleton logical federation and interoperable
graph of sovereign Private Hives.

Singleton means one protocol namespace and graph—not one owner, key, server,
database, complete replica, mandatory relay, or globally writable head.

The normative candidate profile is
[`rapp-federation/1`](protocols/rapp-federation/1/SPEC.md). It defines public
DOGG-safe discovery, explicit peer trust, bilateral agreements, grants,
approvals, requests, phased receipts, moderation, durable idempotency, sealed
exchange, delay-tolerant carriage, and partial knowledge.

Foreign Hives never become local dimensions. Delivery, decryption, and
assimilation are separate authorization events.

## 8. Business operations

Consequential operations MUST bind:

- acting and accountable RAPPIDs;
- source and destination worlds;
- exact terms and policy hashes;
- exact input/output object addresses;
- authorization and grant references;
- idempotency identity;
- execution mode and validity;
- receipts and evidence; and
- rollback, compensation, dispute, or indeterminate state.

Transport delivery, a Git push, a follow relationship, or repository access
does not prove business acceptance or execution.

## 9. Compliance

RAPP Work policies MAY express privacy, retention, jurisdiction, residency,
moderation, approval, audit, budget, and operational controls.

Policies MUST:

- be explicit and machine-checkable where they authorize effects;
- preserve provenance;
- fail closed when required evidence is missing;
- distinguish claims from independently verified evidence;
- avoid silent last-write-wins for semantic conflicts;
- state deletion and revocation limits honestly; and
- never weaken the parent protocol.

## 10. Open implementation

The standards, schemas, reference validators, conformance vectors, and project
skills are public. Any implementation may participate if it produces and
verifies the same RAPP/1 bytes and satisfies the adopted profile.

No AI vendor, hosting provider, transport, identity directory, or central
service is required for protocol participation.

## 11. Conformance

A conforming RAPP Work implementation:

1. pins an authenticated RAPP/1 parent;
2. uses exact RAPP/1 envelopes and address domains;
3. activates profiles through signed registry entries;
4. preserves world and ownership boundaries;
5. distinguishes DOGG, GODD, and neutral data;
6. uses explicit consent and authorization for sharing and effects;
7. verifies immutable artifacts before use;
8. persists rollback, fork, replay, and idempotency state;
9. refuses unsupported operations before effects; and
10. passes the applicable profile conformance suites.

This repository's `registry.json` signs its own adoption record. That signature
does not activate the profiles in another estate.
