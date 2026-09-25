# Proposal 0006: owner succession in the Hive reference and the SDK

## Status

Draft, not accepted. Branch `experimental/gap-g6-owner-succession`. The owner
decides what moves. Intended release: `rapp-work` `1.1.0` (additive; the
package version and `SDK_VERSION` are unchanged on this branch).

## Gap

**G6 — implementations refuse owner succession.** RAPP/1 already defines
time-scoped owner succession and compromise re-anchor (RAPP/1 sections 13.2
and 13.3), but the `rapp-hive/1` reference fails closed on any `re-anchor`
record and the SDK lists owner rotation among its refusals. Folder Hives need
no owner and are out of scope. G6 blocks the Private Hive part.

## Home specification and section

- `rapp-hive/1` (`protocols/rapp-hive/1/SPEC.md`) section 8.1 item 2 and
  section 14.2. That file is pinned by the frozen signed `registry.json`, so
  its text is proposed here only.
- `rapp-work-sdk/1` (`protocols/rapp-work-sdk/1/SPEC.md`) section 12, plus a
  new section 5.1. That file is not registry-pinned; the edit is on this
  branch with its profile pins refreshed.

## Context: what is true today

1. **RAPP/1 already specifies succession.** `vendor/rapp-1/SPEC.md` (pinned by
   `RAPP1_PIN.json`, `kody-w/rapp-1` commit `591e014`):
   - section 13.2: "owner-signed" means the `kid` is the estate owner *in
     effect at the artifact's `utc`*, the current owner or a predecessor
     reachable through re-anchor records, with tenure
     `[record.utc, successor.utc)`; root-key compromise is recovered only by
     redistributing a new out-of-band anchor (section 13.1);
   - section 13.3: `re-anchor {old_rappid, new_rappid, case, utc, sig,
     old_key_sig?}`, `old_key_sig` required for `rotation`; `tombstone
     {rappid, revoked_utc, sig}`;
   - section 6.3: a `compromise` re-anchor needs a registered tombstone; the
     estate owner's own record is signed by the outgoing owner key;
   - section 10: a superseded `kid` is refused on artifacts with `utc` at or
     after the re-anchor, and a tombstoned key at or after `revoked_utc`;
   - Constitution Art. 6: owner authority is evaluated against the owner in
     effect at the artifact's time; succession never rewrites history.
2. **The pinned reference verifier exists upstream.** `rapp_registry.py` at
   `kody-w/rapp-1@591e014` implements the owner-succession walk
   (`Registry.owner_at`), lifecycle signature checks
   (`check_lifecycle_signatures`), superseded-key and tombstone refusal at a
   time, fresh-tail and single-predecessor rules, key-tail alias matching, and
   the explicit authenticated `tombstone_issued_at` resolver
   (`EXTENDING.md`, "The reference will check your estate").
3. **Finding: the vendored copy here was stale.**
   `vendor/rapp-1/rapp_registry.py` on `main` (SHA-256 `f055a4f9…`) equals
   `kody-w/rapp-1@35278ef`, older than the accepted pin `591e014` (SHA-256
   `eec22844…`). It lacked `check_lifecycle_signatures`, the issuance
   resolver, alias matching, and the fresh-tail rules. Nothing pinned it:
   `RAPP1_PIN.json` covers only `SPEC.md` and `rapp.py`, and `tools/check.py`
   used it without a hash check.
4. **The Hive reference fails closed.**
   `protocols/rapp-hive/1/reference/hive_acceptance.py` `RegistryAuthority`
   verifies the registry against one anchored owner SPKI, verifies tombstones
   against that key, and raises "registry: succession requires a full
   section-13 tenure verifier" on any `re-anchor` entry. `HiveAcceptance`
   compares declaration, reconciliation, convergence, and projection signers
   with that single `registry.owner`. SPEC section 8.1 item 2 scopes this as
   "the direct-owner profile"; section 14.2 says the reference "fails closed on
   owner succession records requiring a full time-scoped section 13 tenure
   verifier" and that a production adapter must supply "the full parent
   verifier where those features are needed".
5. **The Hive reference copies are standalone.** The reference imports its own
   `protocols/rapp-hive/1/reference/rapp.py` (byte-identical to
   `vendor/rapp-1/rapp.py`, SHA-256 `1a04362b…`). The legacy project skill
   vendors a byte-exact copy under
   `.github/skills/rapp-private-hive/vendor/hive/`, enforced by
   `test_vendored_authenticated_profile_is_byte_exact_and_standalone` and its
   checksum lock `rapp/agent.lock.json`. The wheel ships the reference as
   `rapp_work._protocols` and the vendored parent as `rapp_work._vendor_rapp1`.
6. **The SDK refuses owner rotation** in three places:
   `protocols/rapp-work-sdk/1/SPEC.md` section 12 ("owner rotation … are
   explicit refusals"); `docs/API.md` "Explicitly deferred"; and the legacy
   `rotate-owner` command, which `rapp_work.compat.run_private_hive_cli`
   passes to `.github/skills/rapp-private-hive/scripts/deploy_hive.py`, where
   it is refused before effects. Implicitly, `HiveVector.from_verified_bundle`
   (`src/rapp_work/hive.py`) and `verify_source_estate`
   (`src/rapp_work/profiles.py`) verify registry signatures against one
   anchored key. The legacy Private Hive publisher itself refuses every
   non-direct-owner registry (`lib/private_hive/authority.py`), so a legacy
   bundle can never contain a succession.

## Design decisions

1. **Reuse the pinned reference; do not re-type it (Art. 10).** Sync
   `vendor/rapp-1/rapp_registry.py` to the exact bytes of the already accepted
   commit `591e014` (cross-checked against `raw.githubusercontent.com`) and
   pin them with a new additive record, `RAPP1_REGISTRY_PIN.json`. The
   accepted canonical revision does not change.
2. **Keep the Hive reference standalone.** Carry a byte-exact
   `protocols/rapp-hive/1/reference/rapp_registry.py` beside its existing
   `rapp.py` copy, exactly as `rapp.py` is carried. It then runs unchanged from
   the checkout, the wheel (`rapp_work._protocols`), and the legacy skill's
   vendored copy. `tools/check.py` and Hive check H21 require every copy to
   equal the pin.
3. **Default stays fail-closed; succession is an explicit opt-in.** The
   `rapp-hive/1` text does not already require succession by default.
   Section 1 item 8 ("refuse in favor of RAPP/1 whenever this profile
   conflicts") is a fail-closed tie-break: a verifier that refuses a registry
   it cannot fully evaluate never accepts what RAPP/1 forbids, and it never
   evaluates authority against "only the current" owner, because it refuses
   instead. Section 8.1 item 2 explicitly scopes the reference to the
   direct-owner profile, and section 14.2 explicitly delegates the full tenure
   verifier. So `RegistryAuthority(...)` without the new arguments behaves
   exactly as before: its direct-owner branch is unchanged and the new
   arguments default to `None`. `RegistryAuthority(..., succession="rapp1-13.2",
   tombstone_issued_at=resolver)` selects the new path. Any other `succession`
   value, a missing or non-callable resolver, or a resolver or retained lineage
   passed without `succession` is refused.
4. **Anchor semantics: the original anchor, walked forward, rotation only.**
   RAPP/1 section 13.1 distributes the owner anchor once. The anchor may be
   the current estate owner or any predecessor in the registry's owner lineage,
   provided every transition from the anchor forward is `case:"rotation"`
   (outgoing-owner `sig` and `old_key_sig`, checked by the pinned reference).
   An owner `compromise` transition cannot extend an old anchor: sections 13.1
   and 13.2 say root-key compromise "cannot be expressed inside the registry it
   signs" and is recovered only by redistributing a new anchor. A consumer that
   holds the newly distributed anchor verifies the same registry, and history
   before the compromise still resolves through the predecessor record.
   Owner transitions of `case` `upgrade` or `tag-migrate` are refused: the
   pinned reference does not check their historical evidence.
5. **The pinned reference decides every section 13 question.** In succession
   mode the Hive authority calls `rapp_registry.Registry` and
   `rapp_registry.load_document(..., trust_anchor=<current owner>,
   persisted_seq=..., tombstone_issued_at=...)`: exact entry member sets,
   one estate owner, the registry signature by the current owner, lifecycle
   signatures by the owner in tenure (the outgoing owner for its own
   transition), nonempty forward tenure, rotation continuity from a key not
   already retired, a registered tombstone for every compromise, single
   predecessors, and fresh (never ancestral or renamed) key tails. The
   resolver maps the exact signed tombstone's particle hash to an
   authenticated issuance UTC; it is never inferred from `revoked_utc`, and
   lookup failures are refusals.
6. **Hive signatures use the key history at the artifact's `utc`.**
   `verify_signature` calls the pinned reference's
   `Registry._signer_acceptable(kid, utc, match_key_aliases=True)`, the same
   primitive the reference applies to rotation continuity proofs, so a
   superseded or tombstoned SPKI is refused under any RAPPID name. Owner checks
   in `HiveAcceptance._authorized` use `registry.owner_at(frame["utc"])` for
   declarations, reconciliations, convergences, and projection receipts; in
   direct-owner mode `owner_at` returns the one anchored owner, so the default
   is unchanged. A projection's signed egg is checked with the owner at its
   `created_utc`.
7. **Additional fail-closed rules in succession mode.** The current estate
   owner key must be live (registered, never deprecated, superseded, or
   tombstoned). The authority exposes `owner_lineage`; a caller that persists it
   and passes it back as `retained_owner_lineage` refuses a later registry that
   rewrites accepted succession (for example by inventing an earlier owner).
   Registry sequence floors and same-sequence commitments are unchanged.
8. **Membership is not inherited.** The declaration is immutable and names
   member RAPPIDs. A successor owner receives the owner *authority* that
   `rapp-hive/1` defines against the registry owner (Mother convergence,
   reconciliation, projection receipts). It does not silently inherit the
   predecessor's member record, area, or room audience; a re-anchored member
   likewise. Changing the roster is G1 (an owner-signed later declaration).
9. **The SDK verifies; it does not rotate.** Performing a rotation or a
   compromise recovery means minting keys and signing and appending registry
   records: an estate owner's signing act that the SDK SPEC already refuses as
   a parent-authority change. Routing it through a plan-hash-gated operation
   would add a seventh operation or overload `scaffold`, `update`, or `migrate`
   with signed-authority effects. The legacy `rotate-owner` command therefore
   stays refused. What G6 needs from the SDK is lawful *verification*: the new
   explicit submodule `rapp_work.registry` verifies a registry or a registry
   lineage across owner succession through the pinned reference, read-only,
   offline, with no new JSON operation and no change to `rapp_work.__all__`.
   `verify_source_estate` and `HiveVector.from_verified_bundle` are unchanged:
   the first verifies this repository's frozen evidence, which has no
   succession; the second consumes legacy bundles, which cannot contain one.
10. **Succession never rewrites history (Art. 6).** `verify_registry_lineage`
    requires contiguous `registry_seq`, requires every earlier `re-anchor` and
    `tombstone` entry to survive byte-for-byte, and requires the owner lineage
    to extend, never rewrite, the previous one. After an owner compromise the
    new segment is verified under the new anchor with the last old-segment
    snapshot as `retained`.

## Proposed change

### A. `rapp-hive/1` normative text (activation owner-blocked)

Activation owner-blocked: the signed registry pins the SPEC hash; the owner
must accept the text and re-sign.

**Section 8.1 item 2.** Replace:

> 2. The owner-signed declaration at the Mother's registered creation genesis.
>    In the direct-owner profile, the declaration owner is the anchored estate
>    owner. Mother Hive `stream_id` is exactly `hive_rappid`.

with:

> 2. The owner-signed declaration at the Mother's registered creation genesis.
>    The declaration owner is the estate owner in effect at the declaration's
>    `utc` (RAPP/1 section 13.2): in the direct-owner profile, the anchored
>    estate owner; under owner succession, the owner whose tenure contains that
>    time. Declarations, reconciliations, convergences, and projection
>    receipts are signed by the owner in effect at their own `utc`. A
>    successor never re-signs or invalidates history signed inside a
>    predecessor's tenure and does not inherit a predecessor's declared
>    membership. Mother Hive `stream_id` is exactly `hive_rappid`.

**Section 14.2, third paragraph.** Replace:

> The direct-owner registry reference checks real detached JWS/SPKI binding,
> the exact profile pin, kinds, active genesis, sequence floor/same-sequence
> commitment, and signed tombstones. It fails closed on owner succession
> records requiring a full time-scoped section 13 tenure verifier. A production
> adapter must supply fresh registry retrieval, persistent high-water marks,
> distributed storage CAS, retention, and the full parent verifier where those
> features are needed. These are trust prerequisites, not Boolean payload
> flags. No result here certifies key release, plaintext consent, global DOGG
> publication, or full estate-wide RAPP/1 conformance.

with:

> The registry reference checks real detached JWS/SPKI binding, the exact
> profile pin, kinds, active genesis, sequence floor/same-sequence commitment,
> and signed tombstones. By default it is direct-owner and fails closed on any
> `re-anchor` record. With `succession="rapp1-13.2"` and a trusted tombstone
> issuance resolver, it verifies RAPP/1 section 13.2 owner tenure and section
> 13.3 `re-anchor` and `tombstone` records through the pinned RAPP/1 registry
> reference (`reference/rapp_registry.py`, pinned by
> `RAPP1_REGISTRY_PIN.json`):
>
> - the out-of-band anchor is the current estate owner or a predecessor
>   reachable only through signed `rotation` records; an owner `compromise`
>   record requires a newly distributed anchor (RAPP/1 sections 13.1 and
>   13.2); owner transitions of any other case are refused;
> - each owner succession record is signed by the outgoing owner; owner
>   tenures are nonempty and forward; a successor identity has exactly one
>   predecessor and a fresh key tail;
> - a tombstone is signed by the owner in effect at its authenticated issuance
>   time, which the trusted resolver supplies and `revoked_utc` never does; a
>   compromise record requires a registered tombstone;
> - every Hive signature is refused at or after its key's supersession or
>   revocation time, matching the key by SPKI tail so that a renamed RAPPID
>   cannot revive it; history before those times keeps verifying;
> - the current estate owner key is live; and
> - when the caller supplies its retained owner lineage, a later registry
>   must extend it.
>
> Registry sequence floors and same-sequence commitments are unchanged; the
> caller persists the owner lineage beside them. A production adapter must
> supply fresh registry retrieval, persistent high-water marks, append
> provenance for compromise tombstones, distributed storage CAS, and retention.
> These are trust prerequisites, not Boolean payload flags. No result here
> certifies key release, plaintext consent, global DOGG publication, or full
> estate-wide RAPP/1 conformance.

Optional editorial change, section 8.2 second bullet: "registry SPKI/RAPPID
binding, and time-scoped revocation" becomes "registry SPKI/RAPPID binding,
and time-scoped supersession and revocation".

### B. `rapp-work-sdk/1` normative text (on this branch)

New section 5.1 inserted after section 5:

> ### 5.1 Registry authority and owner succession
>
> `RAPP1_REGISTRY_PIN.json` pins the exact `rapp_registry.py` of the same
> accepted `kody-w/rapp-1` revision named by `RAPP1_PIN.json`. The SDK
> verifies those bytes, and binds their `rapp` import to the already verified
> parent, before use.
>
> `rapp_work.registry` verifies a signed `rapp/1-registry` document read-only.
> The caller supplies the entries member name, the out-of-band anchor RAPPID
> and SPKI, and a trusted tombstone issuance resolver keyed by the exact
> signed tombstone's particle hash. None of these is read from the document.
> The pinned reference decides every section 13.3 entry, owner tenure,
> lifecycle signature, and time-scoped key retirement. The SDK additionally
> requires that:
>
> 1. the anchor is the current estate owner or a predecessor reachable only
>    through `case:"rotation"` re-anchor records; an owner `compromise`
>    record requires a newly distributed out-of-band anchor (RAPP/1 sections
>    13.1 and 13.2);
> 2. every owner transition is a `rotation` or `compromise` record;
> 3. the current estate owner key is registered and never deprecated,
>    superseded, or tombstoned;
> 4. key retirement matches the SPKI tail, so a renamed RAPPID cannot revive
>    a superseded or tombstoned key; and
> 5. a registry lineage is contiguous, and each later snapshot retains every
>    earlier `re-anchor` and `tombstone` entry and extends, never rewrites,
>    the verified owner lineage.
>
> A verified registry reports the owner in effect at an artifact time and
> supplies a signature verifier for `validate_frame` and `validate_chain`.
> This is verification only. The SDK never mints keys or signs, appends, or
> rewrites a registry, re-anchor, or tombstone, and adds no JSON operation.

Section 12, replace:

> Unsupported sharing, public Git, credential inheritance, implicit apply,
> unknown JSON members, parent-authority changes, plugin execution, neuron
> execution, source deletion, owner rotation, and unverified Hive rollback/fork
> acceptance are explicit refusals.

with:

> Unsupported sharing, public Git, credential inheritance, implicit apply,
> unknown JSON members, parent-authority changes, plugin execution, neuron
> execution, source deletion, performing owner rotation or compromise recovery
> (minting keys or signing or appending re-anchor, tombstone, or registry
> records), owner succession that does not descend from the out-of-band anchor
> through signed rotation, and unverified Hive rollback/fork acceptance are
> explicit refusals. Read-only verification of lawful RAPP/1 owner succession
> (section 5.1) is supported.

## Token and compatibility analysis

- **Frozen `rapp/1` forms (Art. 18):** unchanged. No frame key, canonical form,
  hash tag, RAPPID rule, consumer-checklist step, wire form, or egg form moves.
  No new envelope, endpoint, kind, or registry entry type (Art. 4).
- **`rapp-hive/1`:** no payload schema, kind, catalog, manifest, or checkpoint
  shape changes; `schema.json` is untouched. The proposed text evaluates the
  existing word "owner" by the parent's own section 13.2 rule; every existing
  direct-owner artifact keeps verifying because a registry without `re-anchor`
  records has exactly one owner in effect at all times. No token move is
  needed (Art. 2 concerns shapes; this is Art. 6 authority evaluation).
- **`RegistryAuthority` default:** the direct-owner branch is unchanged; the
  existing H1–H20, including all 64 authenticated vectors, pass unmodified.
  New keyword arguments default to `None`. `owner_at()`, `anchor`,
  `owner_lineage`, and `succession` are additive attributes.
- **New token `rapp-work-parent-registry-pin/1`:** a new closed record
  (`schema`, `protocol`, `repository`, `commit`, `reference_path`,
  `reference_sha256`) rather than widening `rapp-work-parent-pin/1` (Art. 2).
  `RAPP1_PIN.json` and `RAPP_WORK_PIN.json` are unchanged, and the canonical
  commit stays `591e014`.
- **`rapp-work-sdk/1`:** the six-operation closed JSON API, its inputs, its
  envelopes, plan-hash apply, offline default, no-follow effects, and inert
  discovery are unchanged. `rapp_work.registry` is an explicit submodule; the
  top-level `rapp_work.__all__` contract test is unchanged. The SPEC edit
  refreshes `protocols/index.json` and `src/rapp_work/data/profiles.json`
  (`rapp-work-sdk/1` `spec_sha256` `cf64a90f…` → `ca246a9d…`).
- **Vendored `rapp_registry.py` sync:** stricter validation (fresh tails,
  single predecessors, alias matching, lifecycle signatures). The frozen
  `registry.json` has no `re-anchor` or `tombstone` entries, so
  `tools/check.py` is unaffected.
- **Legacy skill:** the vendored reference is re-synced byte-exact (plus the
  new `rapp_registry.py`), and `rapp/agent.lock.json` gains two hashes. The
  skill's own authority layer still refuses every succession, so its behavior
  is unchanged. Its lock `version` stays `3.2.0` (open question 7).
- **Python:** the 3.10 floor and 3.13 are verified. `cryptography` stays the
  only runtime dependency.

## Security and privacy analysis

- **Trust inputs are explicit and never read from the document:** the anchor
  RAPPID and SPKI (tail-bound), the tombstone issuance resolver, and the
  retained owner lineage and high-water. Resolver failures and invalid UTC
  values are refusals, never a fallback to `revoked_utc`.
- **Anchor strength is the anchor key's strength.** A consumer that still
  anchors a compromised owner key accepts whatever that key signs, including a
  forged `rotation`. RAPP/1 recovers root-key compromise only by redistributing
  a new anchor; this proposal cannot change that. It refuses to extend an old
  anchor across a `compromise` record, and a consumer holding the new anchor
  refuses a forged lineage that does not reach it.
- **Forward security:** a superseded key is refused at and after the re-anchor
  `utc`, and a tombstoned key at and after `revoked_utc`, including every
  renamed RAPPID with the same SPKI tail. A tombstone dated before a rotation
  invalidates that rotation's continuity proof.
- **Producer-controlled `utc`** (RAPP/1 section 14): a compromised key can
  still sign artifacts dated before its cutoff. Mother, dimension, and receipt
  chains cannot regress in time, so accepted history cannot be back-filled;
  after a compromise the owner should advance affected heads or re-genesis.
  Between a compromise cutoff and its re-anchor time no key holds owner
  authority, which fails closed.
- **Same-append provenance** of a compromise tombstone (RAPP/1 section 6.3)
  cannot be proven from one snapshot; the pinned reference says so. The
  resolver and the persisted lineage are the caller's evidence; a production
  adapter must retain append provenance.
- **History rewrite:** the retained owner lineage (Hive) and
  `verify_registry_lineage` (SDK) refuse a later registry that drops a
  succession or revocation record or invents an earlier owner.
- **Denial of service:** lineage walks are bounded by the number of re-anchor
  records; registry documents stay within the RAPP/1 one-MiB I-JSON bound; an
  SDK lineage is capped at 4096 snapshots.
- **Loading the pinned reference:** the SDK reads the bytes once, checks their
  SHA-256 against the pin, and executes exactly those bytes with their single
  `import rapp` bound to the already verified parent module, as
  `rapp_work.rapp1` does for `rapp.py`. It does not touch `sys.path` or
  `sys.modules`.
- **Privacy:** no new data flow, network access, credential, or storage.
  Vectors use published `PUBLIC TEST VECTOR ONLY` seeds and `example.invalid`
  locators. DOGG/GODD boundaries, rooms, and sealed eggs are unchanged.

## Migration

- **Existing direct-owner Hives and SDK users:** nothing changes.
- **Planned rotation (owner process, outside the SDK):** register the
  successor `spki`; append `re-anchor {case:"rotation"}` signed by the outgoing
  owner (`sig` and `old_key_sig`); name the successor in the single
  `estate_owner` entry, as the pinned reference requires; increment
  `registry_seq`; sign with the successor key. Consumers keep their original
  anchor, switch `RegistryAuthority` to `succession="rapp1-13.2"` with a
  resolver, keep their sequence floor and hash, and persist `owner_lineage`.
  Existing checkpoints restore unchanged across the boundary.
- **Owner compromise:** append `re-anchor {case:"compromise"}` and a tombstone
  with the compromise cutoff, redistribute the new anchor out of band, and
  advance affected heads past the cutoff. Consumers re-anchor to the new owner.
- **This repository's own estate:** `registry.json` and root `SPEC.md` stay
  frozen. Adopting succession for it is the estate owner's signing decision.

## Rollback

Revert the branch. The default direct-owner path is unchanged, so rollback
only removes the opt-in: registries with `re-anchor` records fail closed again
(the safe direction), and `(registry_seq, registry_hash)` checkpoints stay
valid. The `vendor/rapp-1/rapp_registry.py` sync and its pin can be kept
independently, because they restore the accepted canonical bytes.

## Conformance and test vectors

All identities are real Ed25519 keys from published fixture seeds.

**Hive (`python3 protocols/rapp-hive/1/reference/hive_conformance.py`, now 22
checks):** H21 requires the reference's `rapp.py` and `rapp_registry.py` to
equal their pins; H22 runs `succession_conformance.py` (21 vectors):

| Vector | Result |
|---|---|
| default authority on a member re-anchor, on a succeeded registry anchored at the heir, and at the original owner | refused (fails closed) |
| unsupported mode; resolver or retained lineage without the opt-in; missing or non-callable resolver | refused |
| planned rotation A→B from the original anchor A; from anchor B | accepted; `owner_at` is A before and B at the boundary |
| history accepted under the direct-owner registry, restored under the succeeded registry | accepted |
| post-boundary object and convergence by A | quarantined / refused (superseded); state unchanged |
| post-boundary convergence by B; `restore()` of the full head on a fresh gate | accepted; identical checkpoint and catalog |
| declarations dated after the boundary: B signs naming B; A naming A; B naming A; A naming B | accepted; refused ×3 |
| post-boundary reconciliation by B, by A; projection receipt by A, by B | accepted, quarantined; refused, current |
| succession record signed by B, continuity by B, registry signed by an outsider (anchored at A or B) | refused |
| next owner at, before, or after the boundary (empty, backwards, forward tenure) | refused, refused, accepted |
| retained lineage vs. a registry inventing an earlier owner; vs. a forward extension | refused; accepted |
| anchor outside the lineage (outsider, member); anchor SPKI not bound | refused |
| owner compromise with tombstone and resolver: old anchor; without tombstone; new anchor | refused; refused; accepted |
| under compromise: history before the cutoff; object and convergence by A after it; B before the re-anchor; B after it; fresh `restore()` | accepted; refused; refused; accepted; identical |
| resolver: missing entry, invalid UTC, `None`, issuance in the successor's tenure | refused (never guessed) |
| tombstone signed by the stale owner vs. the owner in tenure at issuance | refused; accepted |
| predecessor tombstoned before its own rotation | refused |
| member compromise: object before the cutoff, after it, by the successor identity; forged record; no tombstone | accepted, quarantined, quarantined; refused; refused |
| ambiguous predecessor | refused |
| rotation to a renamed alias of the same key; back to an ancestral tail; alias member before and after the boundary | refused; refused; accepted, quarantined |
| `upgrade` or `tag-migrate` owner transition | refused |
| current owner key tombstoned | refused |
| predecessor SPKI deprecated after rotation | history still restores |
| rollback, same-sequence fork, missing same-sequence hash, tampered sequence; identical same-sequence | refused; accepted |

**SDK (`python3 -m pytest -q tests/test_registry_succession.py`, 17 tests):**
the pinned-reference hash and `rapp` binding; tampered reference bytes and a
wrong pin refused before use; rotation from the original and current anchors;
`validate_chain` across the boundary (A before accepted, A after refused as
superseded, B after accepted, wrong expected signer refused); records not
signed by the outgoing owner; empty and backwards tenure; owner compromise
(old anchor, missing resolver, missing entry, missing tombstone refused; new
anchor accepted; A acceptable before the cutoff and refused after); member
compromise and stale-owner tombstones; ambiguous predecessor; renamed-alias
revival; anchor lineage and SPKI binding; a live owner key; rollback and
same-sequence fork; a lineage across the boundary feeding `HiveVector`
high-water; lineage gaps, dropped revocations, and rewritten owner history
refused; a lineage continued under a new anchor after compromise; and
performing rotation still refused (`execute("rotate-owner")` and the legacy
`rotate-owner` command).

**Controlled mutations.** Each mutation was applied in place, the targeted
suite run, and the original bytes restored and hash-verified. All 20 turned
the suite red:

| Mutation | Killed by |
|---|---|
| H-M1 Hive retirement by exact RAPPID, not SPKI tail | `test_renamed_alias_cannot_become_a_fresh_owner_or_revive_a_retired_key` |
| H-M2 old anchor may walk through an owner compromise | `test_owner_compromise_recovers_only_through_a_new_anchor` |
| H-M3 owner checks use the current owner, not the owner in tenure | declaration, deprecated-predecessor, compromise, and pre-boundary tests, among others |
| H-M4 default authority skips `re-anchor` | `test_default_authority_still_fails_closed_on_reanchor` |
| H-M5 succession mode without a resolver | `test_succession_mode_is_explicit_closed_and_needs_trusted_issuance` |
| H-M6 anchor need not descend to the current owner | `test_anchor_must_be_in_the_owner_lineage_and_bind_its_key` |
| H-M7 current owner key need not be live | `test_current_owner_key_must_be_live` |
| H-M8 retained owner lineage may be rewritten | `test_retained_owner_lineage_refuses_rewritten_succession_history` |
| H-M9 `upgrade`/`tag-migrate` owner transitions accepted | `test_unverifiable_owner_succession_cases_fail_closed` |
| S-M1 SDK loads `rapp_registry.py` without its pinned hash | `test_tampered_registry_reference_or_pin_is_refused_before_use` |
| S-M2 SDK retirement by exact RAPPID | `test_renamed_alias_cannot_revive_a_retired_key` |
| S-M3 SDK old anchor may walk through a compromise | `test_owner_compromise_needs_a_new_anchor_and_trusted_issuance`, `test_lineage_continues_under_a_new_anchor_after_owner_compromise` |
| S-M4 lineage may drop a lifecycle record | `test_lineage_refuses_gaps_dropped_revocations_and_rewritten_owner_history` |
| S-M5 lineage may rewrite owner succession | same test (distinct assertion) |
| S-M6 lineage need not be contiguous | same test (distinct assertion) |
| S-M7 SDK without a resolver | `test_owner_compromise_needs_a_new_anchor_and_trusted_issuance` |
| S-M8 SDK owner key need not be live | `test_current_owner_key_must_be_live` |
| S-M9 same-sequence fork accepted | `test_registry_high_water_and_same_sequence_fork` |
| S-M10 SDK anchor need not descend | `test_anchor_must_descend_and_bind_its_key` |
| P-M1 the Hive reference's `rapp_registry.py` altered | `tools/check.py` ("pinned rapp_registry.py copy differs") |

Unchanged suites: H1–H20 (including the 64 authenticated vectors), the
Federation conformance, the legacy skill suites, and every existing SDK test.

## Reference implementation and gating

| File | Change |
|---|---|
| `vendor/rapp-1/rapp_registry.py` | exact `kody-w/rapp-1@591e014` bytes |
| `RAPP1_REGISTRY_PIN.json`, `src/rapp_work/data/RAPP1_REGISTRY_PIN.json` | new additive pin |
| `protocols/rapp-hive/1/reference/rapp_registry.py` | byte copy for standalone execution |
| `protocols/rapp-hive/1/reference/hive_acceptance.py` | opt-in succession; `owner_at`; tenure-scoped owner checks |
| `protocols/rapp-hive/1/reference/succession_conformance.py` | new vectors |
| `protocols/rapp-hive/1/reference/hive_conformance.py` | H21, H22 |
| `protocols/rapp-hive/1/reference/README.md` | opt-in documentation |
| `.github/skills/rapp-private-hive/vendor/hive/reference/{hive_acceptance,rapp_registry}.py`, `rapp/agent.lock.json` | byte-exact re-sync and lock |
| `src/rapp_work/registry.py` | read-only SDK verifier (explicit submodule) |
| `tests/test_registry_succession.py` | SDK vectors |
| `tools/check.py`, `tools/verify_package.py`, `MANIFEST.in` | pin, copy, and wheel checks |
| `protocols/rapp-work-sdk/1/SPEC.md`, `protocols/index.json`, `src/rapp_work/data/profiles.json` | SDK SPEC edit and pins |
| `README.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/RELEASE.md`, `protocols/README.md`, `CHANGELOG.md`, `RELEASE-INVENTORY.json` | documentation and inventory |

Gating: the Hive behavior requires `succession="rapp1-13.2"` plus a callable
resolver; the default is the unchanged direct-owner path. The SDK behavior
requires an explicit `import rapp_work.registry`; `import rapp_work` does not
load it and no JSON operation reaches it. Neither path signs or writes.

## Open questions for the owner

1. Should `rapp-hive/1` make succession the default after the section 14.2
   text is accepted? This proposal keeps it opt-in.
2. Should a re-anchored member or owner inherit declared membership? This
   proposal says no; the roster changes through G1's owner-signed later
   declaration.
3. Upstream (RAPP/1 section 13.3): `estate_owner` is "exactly one
   non-deprecated" but its member set has no `deprecated`, and the pinned
   reference accepts exactly one `estate_owner` entry. A successor registry
   therefore replaces that entry, against "every entry is append-only (never
   removed/renamed)". Which reading is intended?
4. Upstream: key-tail retirement is the reference's private
   `_signer_acceptable(..., match_key_aliases=True)`; section 10 speaks of a
   "tombstoned key". Should the public `signer_acceptable` match by tail?
5. Upstream: a compromise tombstone's same-append provenance and issuance time
   remain unspecified (`rapp-backlog.md`). Should RAPP/1 define an
   issuance/append record?
6. Upstream: the reference requires the estate owner's own `compromise` record
   to be signed by the outgoing, compromised key (section 6.3). Is that
   intended for root-key compromise?
7. Bump the legacy skill lock `version` (`3.2.0`) because vendored bytes
   changed?
8. The `rapp-federation/1` reference also fails closed on succession
   (`RegistryAuthority` in `reference/rapp_federation.py`). Follow-up gap?
9. Should the `verify` JSON operation later accept registry lineages? That
   needs a closed input extension and a data form of the issuance resolver.

## Owner actions needed

1. Accept or refuse this proposal and the `rapp-work-sdk/1` edit on the branch.
2. Accept the `rapp-hive/1` section 8.1 item 2 and section 14.2 text, then
   update `protocols/rapp-hive/1/SPEC.md` and its pins (`protocols/index.json`,
   `src/rapp_work/data/profiles.json`, the legacy skill's `vendor/hive/SPEC.md`
   copy and lock `protocol.spec_sha256`) and re-sign `registry.json`.
   Activation owner-blocked: the signed registry pins the SPEC hash; the owner
   must accept the text and re-sign.
3. Decide the `1.1.0` release, and whether to raise open questions 3–6 in
   `kody-w/rapp-1` (draft text below).

### Ready-to-file upstream note (not filed)

> **Title:** Registry lifecycle: estate_owner append-only reading, tail-matched
> retirement, and compromise provenance
>
> A PII-free Hive verifier adopting `rapp_registry.py@591e014` for owner
> succession found four places where RAPP/1 section 13 is ambiguous. It fails
> closed meanwhile. (1) Section 13.3 says `estate_owner` is "exactly one
> non-deprecated" but defines no `deprecated` member; the reference accepts
> one entry, so succession replaces it, against append-only. (2) Section 10
> refuses a "tombstoned key"; the reference matches by SPKI tail only in the
> private `_signer_acceptable(..., match_key_aliases=True)`. Should public
> `signer_acceptable` match by tail? (3) Compromise tombstones need same-append
> provenance and an issuance time that a snapshot cannot prove. (4) The estate
> owner's own compromise record is signed by the compromised key. Is that
> intended when the anchor must be redistributed anyway?

## References

- RAPP/1 `SPEC.md` (pinned, `vendor/rapp-1/SPEC.md`): sections 6.2, 6.3, 7.5,
  10, 12.1, 13.1, 13.2, 13.3, 14.
- RAPP/1 `CONSTITUTION.md` Articles 2, 4, 5, 6, 8, 10, 18.
- `kody-w/rapp-1@591e014`: `rapp_registry.py`, `test_registry_lifecycle.py`,
  `EXTENDING.md` ("The reference will check your estate", "What is not yet
  closed"), `examples/07_your_own_estate.py`.
- `rapp-hive/1` `SPEC.md` sections 1, 8.1, 8.2, 9.1, 14.2;
  `reference/hive_acceptance.py`; `reference/README.md`.
- `rapp-work-sdk/1` `SPEC.md` sections 5, 8, 12; `docs/API.md`;
  `docs/ARCHITECTURE.md`; `CONTRIBUTING.md`; `docs/RELEASE.md`.
- Gap G6: `kody-w/rapp-work` branch `experimental/rapp-work-constitution`,
  `organism/gaps/G06.md`; related G1 (`organism/gaps/G01.md`).
