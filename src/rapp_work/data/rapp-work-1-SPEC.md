# RAPP Work
## Additive organization, catalog, migration, and custody profile

**Protocol identifier:** `rapp-work/1`
**Status:** Normative RAPP/1 additive profile
**Parent:** [`rapp/1`](../../../SPEC.md)
**Depends on:** `rapp-hive/1`, [`rapp-cicd/1`](../../rapp-cicd/1/SPEC.md),
and [`rapp-deploy/1`](../../rapp-deploy/1/SPEC.md)
**Schema:** [`schema.json`](schema.json)

RAPP Work binds one work organization to an authenticated Private Hive,
qualified releases, bounded observations, create-only migrations, and exact
rollback custody. It changes no RAPP/1 byte, identity, hash, signature,
registry-entry type, stream form, egg, or endpoint.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, and **MAY** are
used as defined by RAPP/1 section 2.

## 1. Foundation and registration

Every authoritative RAPP Work payload:

1. is canonical RAPP/1 I-JSON and is identified by
   `H("rapp/1:particle", payload)`;
2. travels in the frozen eleven-key RAPP/1 frame;
3. is signed, including body-stream frames for which base RAPP/1 would permit
   `sig:null`;
4. is appended to the work organization's body stream; and
5. is accepted only after registry, signature, signer, stream, and payload
   authorization.

An adopting estate **MUST** append one ordinary RAPP/1 `protocol` entry pinning
this exact specification and these seven ordinary `kind` entries, all bound to
the `body` family:

| Kind | Only permitted payload schema |
| --- | --- |
| `work.organization` | `rapp-work/1-organization` |
| `work.catalog` | `rapp-work/1-catalog` |
| `work.vector` | `rapp-work/1-vector` |
| `work.migration` | `rapp-work/1-migration` |
| `work.receipt` | `rapp-work/1-receipt` |
| `work.observation` | `rapp-work/1-observation` |
| `work.rollback` | `rapp-work/1-rollback` |

The set is closed for `rapp-work/1`. No eighth `work.*` kind, new registry
entry type, alternate envelope, or endpoint is implied. The adopting registry
also pins `rapp-hive/1`, `rapp-cicd/1`, and `rapp-deploy/1`. A profile conflict
is refused in favor of RAPP/1.

An estate already pinning different bytes under the `rapp-work/1` name cannot
silently repoint that entry. It must preserve the prior signed adoption record
and complete its owner-authorized protocol migration before activating this
exact hash. Repository movement or a newer locator does not transfer authority.

## 2. Work organization

The `rapp-work/1-organization` payload is the genesis declaration for one work
body stream. It binds:

- `organization_rappid`, which is also the frame stream id;
- the accountable `owner_rappid`;
- one hard `world_id`;
- one sovereign `hive_rappid`;
- the RAPP CI/CD `release_scope`;
- an exact `policy_sha256`; and
- `created_utc`.

The organization and Hive identities are distinct. A name, repository,
checkout, URL, plugin directory, or local path cannot derive or replace either
RAPPID. Owner authority is evaluated through the adopting estate's signed
registry and time-scoped signer rules, never from an organization claim alone.

## 3. Catalogs are discovery, not authority

A `rapp-work/1-catalog` is an append-only discovery list bound to the
organization. Successors identify the prior catalog particle hash. Items are
sorted by unique `id`, are bounded to 256 entries, and have exactly:

- `kind`: `plugin`, `skill`, `static-api`, or `portable-neuron`;
- an existing typed RAPP address;
- a Git, raw, or static locator;
- `authority:"discovery-only"`; and
- optional Portable Neuron compatibility data.

Duplicate ids and duplicate `(kind, address)` pairs are refused. Signing a
catalog attests what the organization advertised; it does not grant execution,
membership, installation, tool, network, filesystem, model, or publication
authority. A plugin manifest, skill file, or static API document is data until
separately authorized through the existing RAPP/1 model. A static API document
does not create a transport endpoint beside `POST /chat`.

Portable Neurons are accepted only as typed **inert data**. Compatibility data
names one stable `/2` Portable Neuron format, sets `mode:"inert-data"`,
sets `verdict:"compatible"`, and binds evidence by SHA-256. A missing,
incompatible, executable-as-authority, or unknown-format neuron is refused.
This profile neither executes a neuron nor lets neuron content become
instructions or authority.

Locators help a consumer find candidate bytes. The typed RAPP address, verified
bytes, signed frame, and registry authority decide what those bytes are and
whether they may be used.

## 4. Signed Hive vector high-water

`rapp-work/1-vector` captures the authenticated `rapp-hive/1` checkpoint:

```json
{
  "registry_seq": 8,
  "registry_hash": "<64 lowercase hex>",
  "hive_rappid": "<RAPPID>",
  "mother_head_frame_hash": "<64 lowercase hex>",
  "catalog_hash": "<64 lowercase hex>"
}
```

It also carries the resolved signed Mother Hive head
`{stream_id, seq, utc, payload_hash, frame_hash}` and the prior work-vector
particle hash. Payload validation alone does not authenticate the Hive. The
consumer **MUST** verify the registry, Mother history, catalog, and signed
checkpoint under `rapp-hive/1` before accepting the vector.

Consumers persist the accepted vector as high-water:

- lower registry or Mother sequence is rollback;
- different hashes at the same registry or Mother sequence are a fork;
- a higher Mother head must cryptographically extend the retained head;
- the same Mother head cannot name a different catalog; and
- resetting or deleting retained vector state is not recovery.

The signed `work.vector` occurrence records which authenticated Hive state the
organization accepted. Git ancestry, fetch success, a newer file timestamp, or
a moving branch cannot substitute for this check.

## 5. Immutable rollback target

`rapp-work/1-rollback` binds one already authorized RAPP CI/CD release by:

- release particle hash;
- artifact SHA-256;
- Grail id;
- state-schema SHA-256;
- a typed source snapshot address;
- restore-evidence SHA-256; and
- an immutable Git source descriptor containing repository, object format,
  commit object id, and relative path.

The release particle and content digests are authority. The Git descriptor is
only a locator and reproducibility receipt. A branch, moving tag, `main` raw
URL, mutable static path, or locator that disagrees with the release capsule is
refused as a rollback target.

When a RAPP Deploy plan is supplied, the target **MUST** equal its exact
`rollback_release_payload_hash`, prior state schema, and restore evidence. A
second payload cannot rebind one retained rollback release to different bytes.

## 6. Create-only source-bound migration

`rapp-work/1-migration` is an immutable intent. It binds:

- a stable `migration_id`;
- `mode:"create-only"`;
- the source workspace RAPPID, world, typed snapshot, and signed frame head;
- a fresh target workspace RAPPID;
- the exact target RAPP CI/CD release particle;
- the accepted target `work.vector`;
- sorted catalog item ids; and
- the exact `work.rollback` particle.

The deterministic migration id is the RAPP particle hash of the closed
`rapp-work/1-migration-identity` tuple:

`organization payload hash, source workspace RAPPID, target workspace RAPPID,
target release payload hash`.

The id intentionally excludes mutable source state. If source snapshot or head
changes during retry or recovery, the same migration id now carries a
different intent and is refused. A consumer stores the first payload hash for
each migration id. Exact replay is idempotent; replacement, in-place upgrade,
source rewrite, target identity reuse, and a second payload under that id are
forbidden.

Migration copies or derives only explicitly selected compatible objects. It
does not import old keys, private history, prompts, executable authority, or
unlisted state. Source retirement is a separate owner-authorized operation.

## 7. Receipts, completion, and custody

`rapp-work/1-receipt` has three closed types:

- `migration-completed`;
- `catalog-verified`; and
- `release-verified`.

Every authoritative receipt is a signed `work.receipt` frame. This includes a
receipt found beside a static API document: a static file with `sig:null` is a
draft or cache and proves no verification.

A completed-migration receipt binds the migration particle, source snapshot and
head, target workspace/release/vector, rollback particle, sorted typed evidence,
and key-custody evidence for the target holder. Before **any** setup,
regeneration, identity mint, write, transport publication, subscription change,
or other mutation, recovery performs all of these checks:

1. retained create-only intent exists and is byte-equivalent;
2. the signed receipt and signer are authorized;
3. every required completion-evidence address resolves and verifies;
4. source snapshot and head still equal the intent;
5. target release, vector, rollback, and workspace bindings are exact; and
6. the retained target key is in verified custody.

Missing evidence, changed source, changed receipt, or missing custody is a
preflight refusal. Nothing may be regenerated to make the check pass.

## 8. Bounded release observations

`rapp-work/1-observation` binds one exact RAPP CI/CD release, one exact RAPP
Deploy plan, the accepted work vector, typed evidence, verdict, timestamp, and
prior observation particle hash. A `healthy` verdict requires authorized RAPP
Deploy health evidence; a candidate cannot self-certify.

The reference bounded profile retains at most **128** release observations.
Validation, authorization, predecessor checks, and the capacity check all
complete before append. At the bound, a new observation is refused; an
implementation must not silently delete history, reset its cursor, overwrite
an old observation, or record a partial write as success.

## 9. Authority and effects

RAPP Work reuses, and cannot weaken:

- `rapp-hive/1` registry/head/catalog replay and rollback/fork refusal;
- `rapp-cicd/1` immutable release, evaluator, and promotion evidence; and
- `rapp-deploy/1` isolated rollout, health, state continuity, and exact
  rollback.

JSON Schema, a payload particle, Git commit, raw URL, static file, catalog item,
unsigned receipt, or local success result is not authority. Consequential
effects require the signed RAPP/1 occurrence, authenticated registry, retained
high-water, profile-specific evidence, and authorized signer.

## 10. Conformance

An implementation claiming `rapp-work/1` conformance must:

1. validate all seven closed payload schemas and kind-to-schema bindings;
2. reproduce every RAPP/1 particle and frame wave without changing the frozen
   eleven-key envelope;
3. require all seven kinds in the signed adopting registry;
4. authenticate Hive vectors and persist rollback/fork high-water;
5. enforce create-only migration and immutable rollback targets;
6. finish completed-migration evidence and custody preflight before mutation;
7. treat Portable Neurons and discovery entries as inert, non-authoritative
   data;
8. bind observations to authorized CI/CD and Deploy evidence and retain no
   more than 128; and
9. pass `python3 work_conformance.py`.

The stdlib reference is [`rapp_work.py`](../../../rapp_work.py). JSON Schema
provides portable structural validation; the reference additionally enforces
cross-document, high-water, authorization, custody, temporal, and bounded-state
rules that JSON Schema cannot express.
