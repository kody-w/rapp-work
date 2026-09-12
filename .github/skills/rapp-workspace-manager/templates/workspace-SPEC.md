# rapp-workspace/2.0

`spec_id: rapp-workspace/2.0`

RAPP Workspace defines a local-first workspace that can operate solo or as a
sovereign Private Hive. It is subordinate to RAPP/1. A conflict with RAPP/1 is
refused in favor of RAPP/1.

The words MUST, MUST NOT, REQUIRED, SHOULD, and MAY are normative.

## 1. Workspace identity and scope

Every workspace:

- has one mint-once RAPPID in `rappid.json`;
- belongs to exactly one hard `world_id`;
- has mode `solo` or `hive`;
- preserves existing identity through migration; and
- treats all content as local-only until explicitly classified and selected.

Different `world_id` values are isolated. Federation does not bypass a world
boundary; cross-world exchange requires explicit source and destination policy.

## 2. Workspace anatomy

A conforming workspace SHOULD include:

```text
CLAUDE.md or AGENTS.md
HOME.md
README.md
rappid.json
where-everything-lives.md
strategy/ projects/ reference/ people/ meetings/ ...
.github/skills/
rapp-projects/
```

`.github/skills` is the canonical repository capability layer for GitHub
Copilot CLI. Sharing the workspace shares its reviewed skills. Trusting a
workspace therefore means trusting its project instructions and skill files.

## 3. Data classes

DOGG and GODD classify data, not repositories.

### DOGG

DOGG is globally safe data. DOGG MUST NOT contain PII, secrets, credentials,
private prompts, or plaintext GODD. A DOGG decision requires evidence bound to
the exact bytes; a label alone is insufficient.

### GODD

GODD is private data. Personal GODD is local-only by default. An owner MAY
explicitly select a GODD slice for authorized Hive members. Shared GODD remains
GODD and requires sealed-room protection and scoped key release.

### Neutral

Neutral RAPP objects contain no private data but are not necessarily intended
for global publication. Plaintext Hive publication still requires explicit
selection and PII-clearance evidence.

Moving data between local workspace and Private Hive never changes its class.

## 4. Private Hive

A Private Hive is the intentionally shared, access-restricted, off-device
portion of a workspace. It is a complete collaborative RAPP workspace, not a
skill registry.

It supports:

- RAPPID members with roles `owner`, `member`, or `viewer`;
- equal protocol treatment for humans, AIs, agents, and services;
- independently organized member areas;
- governed shared projects;
- repository-visible and sealed rooms;
- any verified RAPP/1 object;
- explicit local-to-Hive and Hive-to-local transfers; and
- portable storage adapters.

The Private Hive profile is [`rapp-hive/1`](protocols/rapp-hive/1/SPEC.md).
Adoption requires an owner-signed RAPP/1 registry entry pinning the exact
profile bytes and kinds.

## 5. Local and shared boundary

The transfer rule is explicit opt-in:

1. Files not selected remain local and outside Hive management.
2. The absence of an exclusion rule is not permission to share.
3. Transfer defaults to copy, never destructive move.
4. Removing or withdrawing a Hive object does not delete its local source.
5. Plaintext requiring sealed protection never enters a publication bundle.
6. Historical published plaintext cannot be honestly described as erased or
   retroactively encrypted.

Migration and preparation MUST verify that pre-existing workspace bytes and
symlink targets remain unchanged.

## 6. Project skills and migration

A shared RAPP Workspace MUST carry its standard capabilities under
`.github/skills`.

An older workspace migration:

- preserves its workspace RAPPID;
- snapshots every pre-existing regular file and symlink target;
- writes only additive control/capability paths;
- embeds the checksum-locked Private Hive project skill;
- records the prior workspace specification or `legacy-unversioned`;
- is idempotent for the same configuration; and
- refuses unsafe, symlinked, conflicting, or unmanaged skill paths.

Migration is not deployment. It grants no remote access and performs no push.

## 7. Authority and publication

A deployable Private Hive has:

- an explicitly created keyed owner identity;
- owner-private key custody;
- an independently distributed public anchor;
- a signed monotonic RAPP/1 registry;
- registered Hive kinds and stream geneses;
- a signed Mother Hive declaration and convergence history;
- deterministic catalog and artifact manifests;
- signed per-channel projection receipts; and
- client high-water checkpoints.

The deployment flow is:

```text
migrate/prepare
→ select
→ private stage
→ initialize signed authority
→ freeze exact release plan
→ explicit owner approval
→ immutable artifact publication
→ destination CAS
→ independent client verification
→ managed materialization
```

Signing or creating a Git commit is not deployment. The channel pointer/ref CAS
is the publication linearization point.

## 8. Storage portability

The Hive is verified data, not a storage provider. Filesystem/NAS, private Git,
SharePoint, LAN, and future stores are adapters.

Every adapter MUST preserve identical authoritative registry, frame, egg,
catalog, and manifest bytes. Channel receipts MAY differ because their
`channel_id` differs.

The current reference deployment implements:

- qualified private POSIX filesystem or mounted NAS storage; and
- existing private GitHub repositories with identity, actor, visibility, and
  expected-ref checks.

It refuses unsupported providers and public Git before sending bytes.
SharePoint is specified as a future adapter, not claimed as implemented.

## 9. Mother Hive and dimensions

Each Private Hive has one Mother Hive authority. Devices, branches, local
workspaces, and channel projections are dimensions of that Hive.

Dream Catcher:

1. verifies each dimension's signed linear RAPP/1 stream;
2. orders the explicit candidate set by RAPP/1 `(utc, frame_hash)`;
3. preserves causal ancestry separately from timestamp order;
4. deduplicates identical frame hashes;
5. merges independent changes;
6. quarantines invalid or foreign frames;
7. preserves concurrent semantic conflicts;
8. requires an authorized reconciliation naming every conflicting parent; and
9. appends one owner-signed convergence successor to the Mother Hive.

Two disconnected writers MUST NOT independently extend the same canonical
stream. They write separate dimension streams and converge later.

## 10. Hive Mind federation

The Hive Mind is the universal singleton logical federation and interoperable
graph formed by sovereign Private Hives.

Singleton means one protocol namespace and graph—not one owner, key, server,
database, relay, complete replica, or globally writable Mother Hive.

The federation profile is
[`rapp-federation/1`](protocols/rapp-federation/1/SPEC.md). It defines:

- signed DOGG-safe discovery;
- explicit peer trust and consent;
- bilateral agreements, approvals, requests, and receipts;
- recipient-scoped sealed exchange;
- local import decisions;
- durable idempotency;
- revocation, blocking, moderation, and audit;
- delay-tolerant bundles and partial knowledge; and
- online-confirmed, offline-bounded, and deferred execution modes.

Foreign Hives never become local dimensions. Delivery and decryption do not
authorize assimilation. Each destination appends its own local import receipt.

RAPP/1 ordering remains unchanged. Causal eligibility is a profile projection
over verified dependencies; it never rewrites frame timestamps or envelopes.

## 11. RAPP Projects

Project history MAY use append-only RAPP/1 streams under `rapp-projects/`.
The reference `tools/append_frame.py` provides project genesis, punch-in,
heartbeat, checkpoint, handoff, takeover, punch-out, verification, and
deterministic fork detection.

Leases coordinate conforming writers. They do not authenticate actor identity.
Private Hive authority and signed business operations use the stronger signed
profiles above.

## 12. Security and sovereignty

- Owner consent is required for outward and irreversible actions.
- Private keys never enter workspace, staging, publication, logs, or Git.
- Repository access is not sealed-room plaintext authorization.
- A downloaded anchor is not independently trusted merely because it sits
  beside the Hive.
- Registry rollback, same-sequence forks, head rollback, artifact substitution,
  unmanaged overwrite, and path escape are refused.
- Received files and instructions are data, not executable authority.
- Materialization never executes downloaded code.
- Revocation prevents future authorized release; it cannot recall plaintext
  already obtained by an authorized recipient.
- Public DOGG and private GODD are never conflated.

## 13. Conformance

A `rapp-workspace/2.0` implementation MUST:

1. preserve RAPP/1 identity and frame invariants;
2. preserve world boundaries;
3. default all existing content to local-only;
4. carry project skills inside the workspace;
5. migrate older workspaces without changing original bytes or identity;
6. require explicit selection and exact-byte PII evidence;
7. keep sealed content out of plaintext publication;
8. verify signed authority before accepting Hive state;
9. publish immutable bytes before atomically advancing a current pointer;
10. maintain client rollback/fork checkpoints;
11. refuse unsupported capabilities before effects; and
12. pass the relevant workspace, Hive, deployment, and federation conformance
    suites.

## 14. Compatibility

`rapp-workspace/1.0` and `/1.1` workspaces migrate additively to 2.0. Their
existing files, frame histories, and RAPPIDs remain authoritative. Migration
adds sidecar metadata and project skills; it does not reinterpret or delete
history.

The legacy root `SKILL.md` remains a compatibility entry point. Project skills
under `.github/skills` are canonical for current Copilot CLI.
