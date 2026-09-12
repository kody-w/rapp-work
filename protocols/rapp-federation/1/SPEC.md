# RAPP Federation / Work

**Identifier:** `rapp-federation/1`  
**Status:** Normative candidate; bounded first release; not estate-activated  
**Implemented conformance class:** `interval-local-receiver`  
**Parent:** RAPP/1; subordinate to the adopting estate's authenticated section-13 registry  
**Wire schema:** [`schema.json`](schema.json), JSON Schema Draft 2020-12  
**Reference implementation:** [`reference/rapp_federation.py`](reference/rapp_federation.py)

**Inspected parent reference:** [RAPP/1 at
`dda32d741c7218f41443a5bd17eebfe0eae82cb7`](https://github.com/kody-w/rapp-1/blob/dda32d741c7218f41443a5bd17eebfe0eae82cb7/SPEC.md).
This inspection reference does not replace an estate's authenticated parent
registry or amend a repository's separate authority pin.
The repository's structural rev-5 pin predates the inherited sealed-artifact
and current estate-registry provisions. Compatible parent adoption and real
owner trust remain **release blockers**, not facts a fixture, public beacon,
or successful local test may fabricate.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, and **MAY** are
normative. This profile defines authenticated collaboration and bounded work
between sovereign Private Hives. It does not create a new kernel, base frame,
identity system, global registry, transport endpoint, or payment rail.

## 1. One Hive Mind; many sovereign cells

`urn:rapp:hive-mind` names the **one universal logical Hive Mind**. It is a
constant namespace, not a RAPPID, key, owner, stream, membership authority,
database, consensus group, super-Hive, or globally writable head.

Every Private Hive is a sovereign cell with its own RAPPID, hard `world_id`,
owner-authorized registry, Mother Hive stream, private GODD, admission policy,
and local durable acceptance domain. A cell MAY communicate with any consenting
cell without joining a central operator. Knowing the same Hive Mind identifier
confers **zero** rights.

A foreign Hive **MUST NOT** become a local dimension, room, member, branch,
Mother Hive successor, or automatic GODD layer. A local Hive can accept a
specifically granted sealed artifact under an explicit destination decision;
that acceptance does not transfer sovereignty. A received foreign head remains
foreign evidence. Local `rapp-hive/1` convergence remains a separate gate.

Humans, AI agents, and services use the same keyed RAPPIDs, signatures, policy,
consent, approvals, and quotas. Implementations **MUST NOT** infer privilege or
disability from actor species, account type, display name, or whether a human
operated a transport.

## 2. Parent protocol and bounded scope

Every record is a signed **exact eleven-key** RAPP/1 frame:

```
spec kind stream_id seq utc payload payload_hash frame_hash prev prev_wave sig
```

`spec` is `rapp/1`. All thirteen kinds in section 4 are registered in the
`memory` family, on dedicated `<issuer-rappid>:<instance>` streams. The keyed
issuer MUST be exactly the RAPPID owning the stream, not merely a same-key
alias. Family comes from explicit registry entries, never a kind prefix.
`prev_wave` is always
`null`. Genesis has `seq:0`, `prev:null`; each successor has contiguous `seq`,
the preceding **payload** hash in `prev`, and nondecreasing stream-local `utc`.
Particle hashing is `H("rapp/1:particle", payload)`. Wave hashing excludes only
`frame_hash` and `sig`. Signatures cover the frame excluding only `sig`,
therefore including `frame_hash`. Hash domains and RAPPID SPKI bindings are
unchanged.

This closed profile uses only NFC strings, exact integers in the interoperable
53-bit domain, booleans, nulls, arrays, and objects. Floating-point tokens,
duplicate keys, lone surrogates, BOMs, unknown members, unsupported kinds,
ambiguous signatures, and documents over 1 MiB are refused, not repaired.
Canonical key order is RFC 8785 UTF-16 code-unit order. This integer-domain
restriction does not redefine general RAPP/1 numeric canonicalization.
This profile's frame octets MUST already be canonical UTF-8 JSON.
Noncanonical serialized envelopes are refused rather than rewritten; the
receiver retains exactly the bytes whose signatures it accepted.

The reference uses real Ed25519 keys, DER SubjectPublicKeyInfo identity
bindings, and detached RFC 7797 JWS with exactly
`alg:"EdDSA", b64:false, crit:["b64"], kid:<keyed RAPPID>`. Supporting other
RAPP/1 algorithms, key succession/re-anchor, or more registry entry families
requires an explicit extended verifier; there is no permissive fallback.

The registry MUST authenticate this SPEC's exact SHA-256 bytes and the thirteen
kinds. A repository pin, unsigned `index.json`, `authenticated:true` claim, Git
signature, OAuth session, TLS certificate, SharePoint membership, LAN address,
relay assertion, or copied public key is **not** that authority. This release
does not assert that the encompassing repository has completed its RAPP/1
owner-action blockers.
An adopting estate MUST first authenticate a parent revision supporting the
inherited sealed-egg form. A local implementation or structural pin cannot
silently amend RAPP/1; on conflict, the parent specification prevails.

### 2.1 Bounded conformance class, not complete federation deployment

The larger federation architecture is intentionally not claimed as shipped.
This candidate freezes the following **closed subset**; unknown semantics or
workloads requiring excluded features MUST be refused or deferred, not
silently approximated:

| Area | Implemented class | Explicitly outside this class |
|---|---|---|
| Authority | Independent direct-owner anchors, registered memory streams, signed checkpoints and durable forks/rollback detection | Owner succession/re-anchor and estate activation |
| Scope | Bilateral, one exact recipient per request, one directly authorized artifact, one operation, nondelegable grant | Multi-room live membership proofs, grant delegation trees, batch/partial item execution |
| Validity | Policy-configured finite UTC intervals and bounded/unknown receiver clock handling | Capability epochs, epoch closure and compaction markers; unknown time never becomes permission |
| Budget | Abstract finite units/uses in one protected receiver serialization domain | Currency settlement, global exclusive resources, multi-cell escrow allocation |
| Evidence | Signed native frames, explicit receipt assurance, exact whole-object manifests, bounded custody/observation records | Resumable chunk/range indexes, contact routing, anti-entropy inventory snapshots and transport guarantees |
| Execution | Durable authorization/attempt ledger and once-only use of authorized local key material | Arbitrary external executors, automatic Hive import, native ECDH key transport, outer-carriage encryption |
| Governance | Local consent, policy, revocation, cancellation and sticky blocks | Legal/jurisdiction/retention negotiation, moderation appeals, proof of company authority or universal deletion |

No open helper/index bags stand in for the excluded features: this schema does
not emit them. The existing Hive's room, export, world and publication guards
remain mandatory independent gates; an owner signature here is not evidence
that an unmodeled legal or underlying Hive restriction has been satisfied.
The `rapp-federation/1` registry fixture exercises this class, not all section-13
entry families, error registration, variant registration or owner lifecycle.
Real activation must satisfy the complete parent registry obligations,
including the required sealed variant and any native wire error mappings.
Local Python `Refusal` codes are diagnostics, not a replacement `/chat` error
envelope.

## 3. Trust bootstrap and checkpoints

### 3.1 Independent per-cell trust

Each receiver provisions a `CellAnchor` out of band: Hive RAPPID, world,
owner RAPPID and DER key, and one dedicated federation authority stream.
Discovery MUST NOT create or replace an anchor. Multiple anchors are independent
peer trust decisions, not a global estate-owner succession.

The reference verifies signed `rapp/1-registry` documents directly against
each cell's anchor. Its closed direct-owner registry subset supports
`estate_owner`, `protocol`, `kind`, `spki`, `genesis`, and independently
owner-signed `tombstone` entries. Other registered profiles/kinds may coexist
but cannot expand federation's accepted kinds. Unsupported entry forms,
including re-anchor, fail closed. Registry source URLs are locators only.
The native registry signature covers the **whole** unsigned document. A
publisher MUST NOT redact private registry entries and present the remaining
subset as if the original signature still authenticated it. Exchange the
complete document over an independently authorized protected channel, or
provision a separately anchored, expressly delegated federation estate.
Discovery does not authorize publication of a Private Hive's full registry.

The receiver MUST durably retain each cell's highest registry sequence and
exact unsigned-registry particle hash. Lower sequences, different bytes at
the same sequence, removed tombstones, changed registered genesi, duplicate
keys/owners/kinds, and competing authority streams MUST be refused. Once
observed, a revoked key cannot authorize a newly accepted record by backdating
its frame. Already accepted history remains evidence, not renewed permission.

### 3.2 Non-authorizing genesis

The first frame of every dedicated federation stream is
`federation.checkpoint`, `phase:"genesis"`. It identifies the cell, keyed actor,
and stream role (`authority`, `actor`, `discovery`, or `relay`). It grants no
capability and contains no registry commitment. The signed registry pins its
wave hash. This deliberately avoids a genesis/registry-hash cycle.

Only the configured authority stream may have role `authority`, and only the
owner may sign it. Other stream roots bind their actor to their stream's SPKI
and exact owning RAPPID. Discovery streams remain public-only; actor streams
remain private.
Relay streams may emit custody and observation records only.
Publishers SHOULD use dedicated private partner/work streams so that proving a
complete stream chain does not unnecessarily reveal unrelated private business
metadata to another consenting peer. A public discovery stream MUST never
share that private history.

### 3.3 External authority checkpoint

An owner-signed `phase:"authority"` checkpoint commits:

- the cell and hard world;
- a contiguous `authority_seq` and `previous_checkpoint`;
- exact registry sequence and hash;
- one Mother Hive head reference: stream, sequence, UTC, particle, wave, and
  `prev` particle;
- issuance, expiry, maximum clock uncertainty, and bounded offline horizon;
- every locally known owner control, by sorted frame hash;
- an optional destination-issued online challenge.

The first head must be the registered Mother Hive genesis. Later checkpoints
keep exactly the same head or attest one contiguous Mother Hive successor,
with its correct predecessor particle and nondecreasing stream time. Head
rollback, same-sequence competing heads, missing intermediate head commitments,
and a foreign Hive in the head slot MUST be refused.

This is the owner's signed **external commitment**, not an independent proof of
all internal Hive convergence decisions. A producing owner MUST obtain its
head from its authenticated local Hive gate. The standalone federation
reference validates endorsement and checkpoint continuity; it does not
reimplement the sibling Hive schema or assimilate the head. Conflicting
owner-signed successors are an equivocation requiring operator resolution,
never last-writer-wins or a new global head.
Upon verifying owner equivocation in an authority stream, same-sequence
registry, or sovereign head, the receiver MUST durably retain the signed
evidence and suspend **new** authorization involving that cell. A later
registry refresh or process restart MUST NOT clear that fault. In-flight
outcomes may still be recorded. An unauthenticated or non-owner forged fork
MUST NOT trigger an owner-fault latch. Recovery is outside this bounded
release and requires an explicit operator-authorized protocol.
`hive_head_assurance:"owner-attested-not-locally-verified"` is mandatory.
The reference MUST NOT report absent Mother Hive history as locally verified
merely because an owner checkpoint names it.

## 4. Closed record vocabulary

The normative schema is exhaustive. Its root validates complete signed frames;
`$defs/payload` validates payload shape only. Scalar syntax and JSON Schema
success do **not** establish cryptographic or stateful acceptance.

| Registered kind | Purpose |
|---|---|
| `federation.discovery` | Independently approved, signed DOGG advertisement |
| `federation.peer` | One owner's private consent to interact with another cell |
| `federation.policy` | One owner's monotonic policy |
| `federation.grant` | Nondelegable resource capability for one exact recipient |
| `federation.agreement` | Source-signed exact bilateral terms proposal |
| `federation.approval` | Destination-signed agreement or individual request decision |
| `federation.request` | Immutable work intent and durable business idempotency key |
| `federation.receipt` | Destination-signed business phase and bounded result claim |
| `federation.control` | Owner revocation, cancellation, or sticky peer block |
| `federation.checkpoint` | Non-authorizing stream genesis or sovereign authority checkpoint |
| `federation.bundle` | Immutable delay-tolerant manifest; not a delivery/acceptance claim |
| `federation.custody` | Signed bounded custody history, never business authority |
| `federation.observation` | Signed local observation, never execution authorization |

Except discovery and checkpoint forms, every payload contains `issuer` (cell,
world, actor), an issuer `checkpoint`, and sorted unique `depends_on` wave
hashes. Every explicit profile-frame reference MUST be declared as a dependency
and resolve to an independently accepted record of the required kind. Resource
addresses, registry hashes, and externally attested Mother Hive head hashes
are not disguised profile-frame dependencies.

All set-valued arrays MUST be sorted and unique. Resource descriptors name
exactly a `rapp/1:egg-manifest` address, artifact signer, and key-service
RAPPID. They never carry paths, credentials, DEKs, plaintext, executable
commands, wildcard audiences, transport accounts, or arbitrary extension maps.

## 5. Discovery is DOGG, not permission

A discovery advert contains only the logical Hive Mind constant, the
privacy-approved Hive/advertiser identities, a closed capability list, a
credential-free HTTPS `/chat` locator, expiry, `data_class:"dogg"`,
`pii_status:"none"`, and a publication-evidence commitment. Neither the advert
nor its dedicated stream may expose private worlds, rooms, members, policy,
grants, private head commitments, private URLs, prompts, or plaintext GODD.

Closed fields alone cannot prove that a name, hostname, signature `kid`, or
opaque string contains no PII. A separate authorized DOGG publishing review
MUST approve the **entire unsigned public frame**, including routing fields,
against the stated evidence. The local `approve_dogg` API records that
out-of-band decision; an untrusted wire `pii_status` is insufficient. Its
approval hash is `H("rapp/1:particle", frame_without_sig)`. The evidence hash
is already inside that frame; the approval record is not inserted into it.
The resolved signer MUST also be covered by that review.

Discovery changes neither anchors, consent, policy, membership, execution
state, nor key-release rights. It is safe to ignore, cache until expiry, or
replicate an approved advert. Advertisement of a capability is not a grant.

## 6. Consent, policy, grants, and bilateral agreement

Both owners independently sign `peer` consent naming the other's exact cell
and world, with validity bounds. One side's consent is insufficient. A peer
block on either side overrides all previously observed consent.

Policies have contiguous `policy_seq` and exact `previous_policy`. They
authorize explicit peer Hives and local keyed actors; closed actions are
`godd.exchange`, `task.execute`, and `proposal.submit`. They bound modes,
per-request units, total grant units, uses, offline horizon, clock uncertainty,
and irreversible effects. Units are abstract quota units, **not currency or
settlement**. Replacing a policy never silently widens an existing grant.

A grant is owner-signed and immutable under its `grant_id`. It names one
foreign cell, world, and actor; one sealed artifact and key service; an issuing
policy; allowed actions/modes; validity; per-use and aggregate budgets; and
offline-revocation limits. `delegation:false` and `dogg_publication:false` are
mandatory. Grant limits MUST be subsets of the issuing policy. Wildcards,
audience expansion, transitive trust, transport-based delegation, and
recipient substitution MUST be refused.

An agreement contains exact `terms` and their particle hash, with both peer
consents as dependencies. Terms bind source/destination parties, exact
resource/grant, both policy hashes, action, mode, units, validity,
irreversibility, and explicit offline-risk acknowledgement. The source actor
must be allowed by its source policy.

The destination actor independently signs an `approval`, `scope:"agreement"`,
targeting the proposal's **wave hash** and exact terms hash. A source signature
plus this destination acceptance constitutes bilateral agreement. Rejection
does not establish an agreement; one-sided, wrong-actor, wrong-world, altered
terms, or competing decisions are refused. A new decision needs a new
proposal; this version does not overwrite an approval.

## 7. Request, destination acceptance, receipts, and idempotency

Every request repeats the exact agreed terms and names the agreement and
destination agreement approval. It also binds source/destination authority
checkpoints, `request_id`, an online challenge when applicable, and optional
deferred predecessor. Requests addressed to a different receiver Hive or world
MUST NOT enter this receiver's business ledger.

Agreement approval is **not** individual task execution approval. Before
execution the exact destination actor MUST separately sign
`approval`, `scope:"request"`, committing the request wave and particle hashes.
A received file, consent, grant, agreement, content scan, custody receipt,
transport acknowledgement, or relay observation cannot substitute for it.

The only normal business phase sequence is:

```
received -> validated -> accepted -> executing -> completed
                                           \-> failed
```

`received`, `validated`, and `accepted` may instead transition to `rejected`.
Every destination-signed receipt names the original request, its id, preceding
receipt, and original authority checkpoints. Accepted/executing/terminal
execution receipts require the individual request approval. Early phases
cannot carry charged units or results. Terminal charges cannot exceed the
reserved request units. Any GODD result remains a sealed resource descriptor.
Completion is the signer's business attestation, not independently verified
real-world settlement.

Each receipt also carries a closed `assurance` value and `clock_basis`.
Delivery and terminal historical claims use `historical-snapshot`; accepted
or executing work distinguishes `online-confirmed` from `offline-authorized`.
Clock/dependency rejection uses `authority-unavailable`; `known-revoked`
requires locally known control/tombstone evidence; a failed attempt is
`indeterminate`, not proof that no external effect occurred. Authorizing
receipts MUST record the actual trusted receiving host's clock interval, not
an actor-invented tighter one. These labels never mean globally current
knowledge during a partition. Non-authorizing historical clock assertions
remain assertions by their signers, not newly trusted calibration.

The durable idempotency key is **(source Hive, destination Hive, request_id)**.
The original request payload hash, original wave, receiver, grant use, reserved
units, receipt frontier, and local execution state MUST survive restart.
Identical retransmissions return the existing outcome. Reusing a key with
changed payload, even changed metadata, MUST fail. A new envelope with the
same payload cannot become a second execution root.

The destination MUST atomically reserve grant use and aggregate units with its
accepted receipt. Reservations are conservative and never silently refunded
after rejection, failure, or timeout. Because a grant has exactly one
recipient, its quota has one serialized receiving domain. This is not a
globally consistent balance across separate grants or issuers.

The reference uses a receiver-local SQLite transaction, synchronous FULL
durability, uniqueness constraints, and a persisted configuration binding. It
marks key release `in-doubt` durably **before** invoking the scoped key service.
An immutable local attempt marker is committed in the same transaction.
On reopening, the verifier cross-checks retained requests/receipt chains,
ledger frontiers, reservations, attempts and aggregate consumption. Missing
or inconsistent state causes `recovery-quarantine`; it is never reconstructed
as fresh spendable rights.
It releases plaintext at most once from that ledger, after a signed executing
receipt. A crash/failure after reservation does not authorize retry.
External executors MUST also honor the same durable idempotency key and use
reconciliation for in-doubt effects. This profile does not claim exactly-once
network delivery or exactly-once arbitrary external side effects.

Losing or rolling back the entire durable store, restoring a stale machine
snapshot, or cloning an executor cannot be detected using that same store
alone. A production host MUST protect its durable frontier against rollback
and prevent multiple writable copies for the same recipient. Restore without
that evidence is fail-closed operator recovery, not permission to start over.

## 8. Three modes and clock uncertainty

`utc` on a frame is a signed logical ordering timestamp, not a trustworthy
measurement of the receiver's present. The receiver supplies a trusted local
interval `[earliest_utc, latest_utc]`, or explicitly unknown time.

Every relevant validity window is **half open**, `[not_before, expires)`.
The **whole** accepted clock interval `[lo, hi]` must fit: `lo >= not_before`
and `hi < expires`. The exact expiry instant is not one last permitted action.
Overlapping an expiry, excessive uncertainty, time entirely before issuance,
or rollback below the durable observed floor refuses execution. Unknown time
does not mean infinite freshness. It permits only non-authorizing retention.
The implementation MUST NOT infer time, registry freshness, or revocation
absence from relay delivery time or the newest-looking frame timestamp.

| Mode | Authority and execution rule |
|---|---|
| `online-confirmed` | Both latest known owner checkpoints answer one fresh, unpredictable destination-issued challenge bound to the exact terms and parties; the entire local interval fits the challenge and authority windows. The challenge is durably single-request scoped. No transport session substitutes for these signatures. |
| `offline-bounded` | Both policies and the grant explicitly permit lease-limited revocation and the terms acknowledge that risk. The whole local interval fits all signed windows and the minimum source/destination/grant/policy offline horizon. All locally known controls still apply. This first release **forbids irreversible effects offline**. |
| `deferred` | Retain and verify available evidence, obtain missing dependencies, and issue observational/received/validated records only. Never reserve work, release a key, execute, or claim completion. |

An offline lease may last months or longer, as explicitly bounded by each
policy and agreement; there is no universal one-year or short-network-timeout
ceiling. Its validity is bounded,
not a prediction that revocation will remain absent. A months-partitioned cell
cannot truthfully assert instantaneous global revocation. Once an authority
lease expires, its registry context is superseded locally, uncertainty
exceeds policy, or a known control prohibits the work, execution MUST stop.

A deferred request is immutable. Promotion requires a fresh request ID, new
live-mode agreed terms and approvals, fresh authority evidence, and a
`supersedes` link to the deferred request. An old request is never silently
reinterpreted as online/offline-authorized work.

## 9. Sealed GODD and key release

All exchanged GODD inputs/results MUST be signed RAPP/1 `sealed` eggs, not
plaintext attachments, public DOGG, raw URLs, or transport encryption alone.
The reference accepts the deterministic two-member sealed ZIP
(`manifest.json`, `ciphertext.bin`), exact manifest/content hashes, AES-256-GCM,
the inherited RAPP sealed AAD descriptor, and the keyed plaintext commitment.
Encryptors MUST ensure nonce uniqueness for each DEK; the fixed keys/nonces in
the public conformance fixture are test data, not a production key schedule.
Each new artifact MUST use a fresh random 256-bit DEK, not a shared master DEK.
The envelope is verified before key release; the authentication tag and keyed
commitment are verified before plaintext is returned. This class's business
resource opener is bounded to 64 KiB plaintext; oversized/alternate containers
fail closed. This does not lower the parent sealed-egg ceiling for independent
outer-carriage adapters.

The artifact's key service MUST independently enforce the exact destination
Hive, world, actor, grant, artifact, operation, validity, revocation mode, and
request. The reference passes a typed `ReleasePermit` only after local
authorization and durable reservation. Key-service code is a trusted local
adapter, not an untrusted remote claim that authorization succeeded.

The key-service URL in a sealed egg is only a locator. The key service is
identified by its registered keyed RAPPID and explicitly granted resource.
The DEK MUST NOT appear in frames, registries, bundles, locators, receipts, or
the receiver's protocol database. The reference does not contact a key service
or execute decrypted bytes. A production key service must authenticate the
recipient proof, not assume possession of a JSON permit confers authority.

Destination GODD adoption remains a distinct local Hive operation with explicit
namespace/precedence and provenance. Opening a permitted artifact does not
auto-mount it, overwrite local data, adopt a foreign Hive, publish DOGG, transfer
ownership, or grant access to sibling artifacts.

### 9.1 Native key acquisition is not redefined

A native remote key adapter MUST use RAPP/1's existing sealed key request and
release inside `/chat`; `ReleasePermit` is not another wire format. The signed
`rapp-sealed-key-request/1` binds egg, key id, recipient RAPPID and SPKI,
one-use nonce, and expiry. The service-signed `rapp-sealed-key-release/1` binds
that exact request hash, recipient, egg, key id, issuance, and expiry. The
native wrapping algorithm remains `ECDH-ES+A256KW` with JWE `enc:"A256GCM"`.
A remote adapter MUST verify both signatures, entitlement, recipient/key
bindings, nonce non-reuse, and release validity before using the unwrapped
material. A raw DEK returned by an HTTP endpoint is not a conforming release.

**Ed25519 is a signing algorithm, not an ECDH key-agreement algorithm.**
An implementation MUST NOT convert or reinterpret an Ed25519 SPKI as an
encryption key while retaining the original RAPPID fingerprint. Using a
different compatible encryption key requires an explicit authenticated
binding/delegation and the native recipient checks; matching account names,
tenants, transports, or owners is insufficient.

This bounded Ed25519-only reference does **not** implement that additional
encryption-key binding or the native wrapped-key transport. Its `key_service`
callable is an in-process scoped-material adapter: it supplies already
authorized, locally provisioned artifact material, not a wire response.
The fixtures exercise this local-material path. An Ed25519 recipient lacking
compatible, explicitly bound key-agreement material MUST defer native remote
key acquisition; there is no permissive conversion, alternative `wrap_alg`,
global key, or implied online key-release interoperability. Online-confirmed
**authority** may still govern work using already provisioned local material.

Acquiring a key in advance does not remove live grant checks, revocation
limits, or the original accepted delivery horizon. Signing-key rotation does
not by itself justify discarding required decryption material or extending
the expiry of an old native release.

## 10. Controls and the limits of revocation

Owner `control_seq` is contiguous and durable. `revoke` targets the owner's
grant or proposal; `cancel` may target a request involving that owner's cell;
`block` targets a foreign peer. Controls are signed, append-only, immediately
effective for **new local authorization** once observed, and included in the
next owner checkpoint's cumulative control frontier.

Blocks and revocations are sticky in this version. Renewal uses new immutable
grants/proposals; unblocking and owner/key recovery require an explicit
extended protocol or out-of-band operator recovery. They cannot be inferred
from a new transport connection, a stale registry, a new approval, or silence.

Revocation cannot erase accepted history, recall previously released plaintext,
undo an external effect, guarantee delivery across a partition, or necessarily
stop a release already durably authorized/in flight. Terminal receipts may
record the outcome of such prior work; they do not reauthorize it. Implementations
MUST describe these limits instead of claiming instantaneous universal recall.

## 11. Delay-tolerant artifacts, not another transport protocol

A bundle is an immutable, source-signed manifest addressed by its normal frame
wave. It binds one request, its exact destination, sorted typed item addresses,
each item's exact serialized-octet SHA-256, byte count/essentiality, expiry,
and a maximum of 32 custody hops.
There are at most 64 items and 8 MiB in a bundle; each item is at most 1 MiB.
The original request and its sealed resource MUST be essential items.
Other items must belong to the request's dependency/stream-chain closure.

Frames retain their original signatures and bytes. Egg addresses remain
manifest addresses, not raw ZIP hashes. Every listed byte count and content
address **and** `octets_sha256` must be checked. A new valid signature may
preserve a native object address while changing its serialized representation;
those bytes are not interchangeable under an existing signed manifest.
Wrapping, forwarding, storing, or verifying a bundle
never accepts its contained business request automatically. Partial bundles
or missing causal context remain staged. Multiple bounded bundles can supply
the closure over a long partition; this version has no fragmentation format,
mutable routing fields, contact planner, custody-transfer guarantees, or
implicit expiry extension.

Transport-copy expiry, business/grant expiry, replay retention, and archival
retention are distinct. Removing an expired carrier copy MUST NOT remove the
operation tombstone/idempotency frontier and permit an old command to execute
again. This reference does not compact or TTL-evict its replay ledger; any
future compaction must preserve equivalent closed-epoch rejection evidence.

Sealed payloads alone do **not** hide the collaboration graph: manifests,
identities, byte counts, policies, times, dependencies, and custody paths can
still disclose private relationships. Federation frames, full registries,
bundle manifests, and observations are private by default, except separately
approved DOGG discovery. Carriers MUST keep this metadata within its explicitly
authorized audience; where a relay is not authorized to see it, use
recipient-encrypted outer carriage with independently established compatible
key material, or defer transfer. A custody statement does not grant its signer
permission to receive plaintext metadata. This profile neither implements
outer-carriage encryption nor claims anonymous/private graph transport from
payload encryption alone.

Across a cell boundary, private control frames, registries, agreements,
receipts, and private manifest/index metadata MUST themselves travel in
signed parent RAPP/1 sealed eggs. Seal the full canonical signed frame as the
egg's opaque plaintext; do not invent another envelope or egg variant.
Private Git access or TLS alone is not a substitute for sealing GODD.
Transport-disclosure consent is separate from work authorization. The
reference's local byte APIs operate only after authorized decapsulation or
within the local test harness; they do not implement or authorize a plaintext
cross-cell carrier. If required sealed carriage/key bindings are unavailable,
the transfer remains deferred.

Custody has a signed predecessor and bounded hop. `stored` may become
`forwarded` by that custodian, followed by `stored/refused/expired` from the
named next custodian at the next hop. `stored` may also expire in place.
Initial custody is an assertion of observation, not proof that all bytes
exist. Custody signers cannot become grant issuers or destination approvers.

Observations distinguish `transport-arrived`, `content-verified`,
`pending-dependencies`, `expired`, and `rejected`, with an explicit known or
unknown clock interval. These are signed claims about what an observer saw,
not business receipts. Even `content-verified` does not mean policy-valid,
destination-accepted, executed, or settled.

Stores may be Git, private file services, HTTPS, LAN, removable media, or
delay-tolerant networks. Artifact transport never changes RAPP/1's `POST /chat`
wire. There is no required always-online DNS resolver, control plane, central
database, transport identity authority, or global synchronized clock.

## 12. Causality is not a replacement ordering rule

RAPP/1 cross-stream Dream Catcher ordering remains ascending **`(utc,
frame_hash)`**. Implementations MUST preserve that order for canonical
presentation/replay and preserve received envelopes unchanged.

`depends_on` expresses authorization and business causality separately.
A clock-skewed destination approval can have a smaller `utc` than a source
proposal while still depending on it. Consumers MUST wait for verified
dependency closure; they MUST NOT rewrite timestamps, change hashes, reparent
frames, pretend a missing grant exists, or replace RAPP ordering with a vector
clock. A readiness scheduler may process dependencies before dependents while
leaving canonical record order unchanged.

The reference exposes durable `stage`, dependency-aware `drain`, strict
`accept`, and canonically sorted `history`. An invalid dependent record cannot
authorize work. Invalid candidates are retained in quarantine rather than
blocking unrelated valid candidates. Forks and unsupported states fail
explicitly; verified owner equivocation additionally suspends that cell's
new authorizations.

## 13. Conformance and implementation boundary

Run from this directory on Python 3.10+, with the two pinned requirements installed:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 reference/schema_source.py --check
PYTHONDONTWRITEBYTECODE=1 python3 reference/conformance.py --report conformance-results.json
```

`schema_source.py --check` verifies the generated schema. The conformance
suite verifies checked-in fixture reproducibility; there is no
`vectors.py --check` option. `vectors.py --write` is an explicit regeneration
command, not a validation step. Finalize the SPEC and source files before
regenerating, then run both checks without further editing or regeneration.
The suite fails if its input tree changes while it runs, and an unchanged
report is not rewritten, allowing a second identical full run to be read-only
with respect to persistent files.

The suite verifies checked-in, reproducible Ed25519-signed frames and encrypted
fixtures, not zero-artifact scans or callbacks that return `True`. It tests
schema closure, signature binding, cross-world/recipient refusals, consent,
bilateral and individual approvals, limits, idempotent restart, registry and
head rollback/forks, missing dependencies, clock uncertainty, bounded long
partitions, controls, and transport substitution.

The directory is self-contained apart from `cryptography` and `jsonschema`.
It imports no sibling profile or mutable Grail module and opens no network
listener. Reference acceptance covers this bounded direct-owner profile only.
It does not prove malicious-owner honesty, real-world business completion,
secure key-custody deployment, or authenticated local Hive assimilation.
The [reference API guide](reference/README.md) documents trust inputs and the
boundary between evidence, durable authorization, and actual local effects.

### Standards informing the boundary

- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785): deterministic JSON bytes.
- [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032): Ed25519 signatures.
- [RFC 7797](https://www.rfc-editor.org/rfc/rfc7797): detached unencoded JWS payloads.
- [RFC 9171](https://www.rfc-editor.org/rfc/rfc9171): delay-tolerant bundles,
  lifetimes, and status reports; this profile does **not** claim BPv7 wire conformance.
- [RFC 9172](https://www.rfc-editor.org/rfc/rfc9172): end-to-end bundle security;
  authenticated forwarding is not application authorization.
- [RFC 9126](https://www.rfc-editor.org/rfc/rfc9126): binding authorization
  requests by reference; this profile does **not** implement an OAuth server.

These references inform separation of authority, payload, transport, and
observation. RAPP/1 remains the protocol authority.
