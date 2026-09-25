# Authenticated Hive acceptance

Run the complete profile gate from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 protocols/rapp-hive/1/reference/hive_conformance.py
```

`HiveAcceptance` consumes exact signed RAPP/1 frames through an immutable-byte
resolver and an independently anchored `RegistryAuthority`. Structural payload
validation is not acceptance. The [SPEC](../SPEC.md) defines the unchanged frame,
catalog, convergence, and projection contracts.

## Owner succession (opt-in)

`RegistryAuthority` is direct-owner by default and still refuses any
`re-anchor` entry; that path does not import `rapp_registry.py`. Passing
`succession="rapp1-13.2"` together with a trusted
`tombstone_issued_at(entry_hash)` resolver selects RAPP/1 section 13.2 tenure:
the pinned `rapp_registry.py` (a byte copy of the reference named by
`RAPP1_REGISTRY_PIN.json`) validates every section 13.3 entry and lifecycle
signature, and every Hive signature is checked against the key history at the
artifact's `utc`, matching retired keys by SPKI tail.

- The out-of-band anchor may be the current estate owner or a predecessor
  reachable only through signed `rotation` records. An owner `compromise`
  record requires a newly distributed anchor.
- Declarations, reconciliations, convergences, and projection receipts must be
  signed by `owner_at(frame["utc"])`. History before a succession or a
  compromise cutoff keeps verifying; the outgoing or compromised key is refused
  after it. Membership in the immutable declaration is not inherited by a
  successor identity.
- Causal bounds stop a retired key from back-dating an owner act over later
  state: a convergence is not earlier than any candidate it lists, a
  reconciliation is not earlier than the Mother head it resolves, and a
  receipt is not earlier than its convergence or than the latest re-anchor or
  tombstone issuance in the registry it names. After a succession, the
  successor should promptly advance the Mother stream and every receipt
  stream past the boundary.
- Under succession, `checkpoint()` also carries `owner_lineage` and
  `registry_lifecycle`. Pass the registry members of the last persisted
  checkpoint back as `retained_registry` (`RETAINED_REGISTRY_KEYS`); it
  replaces `minimum_registry_seq` and `same_sequence_hash` and is required
  whenever the anchor is not the current owner. A later registry must extend
  the retained owner lineage and keep every retained `re-anchor` and
  `tombstone` entry, so no registry can undo a succession or revocation. A
  new `compromise` re-anchor must arrive one sequence after the retained state
  together with its tombstone. When switching an existing Hive to
  succession, a direct-owner authority's `retained_registry` supplies the
  first retained state.
- `restore()` replays signed Mother history across a succession boundary.

The vectors are in `succession_conformance.py` (check H22).

## Durable fork quarantine

An authenticated same-stream/sequence fork is not a mutation conflict that an
ordinary owner reconciliation can merge. The gate compares candidate ancestry
(including signed cross-stream sources) with previously retained history.
Once a Mother convergence accepts that evidence, it retains both signed
branches and their causal ancestry and latches the earliest conflicting
position of the stream. Retrying either branch alone, a later successor, or a
transitive dependent cannot escape quarantine.

The accepted Mother history already commits candidate wave addresses and
decisions; no new envelope or payload fields are added. `stream-fork` and
`fork-ancestor` diagnostics must agree with authenticated evaluation. They
assert retained fork evidence, not permission or an owner resolution. Other
reason codes remain descriptive. A signer cannot erase these diagnostics or
invent them for unauthenticated candidates.

The artifact manifest includes authenticated fork evidence, even though those
quarantined frames do not enter the accepted catalog. Unauthenticated frames
and false candidate summaries cannot create a latch or inject manifest entries.
Previously accepted catalog entries remain immutable historical evidence;
faulted branches and their dependents no longer participate as active effects.

Persist `checkpoint()` and all manifest artifacts atomically. A new verifier's
`restore(mother_head_frame_hash)` re-verifies the signed history and rebuilds the
fork frontier. Missing or invalid recorded fork evidence fails restoration; it
cannot silently become an ordinary invalid-candidate quarantine with a clean
frontier. A failed restore disables further acceptance and projection on that
verifier. Recover the complete authenticated history before using a fresh one.

Previewing a convergence or refusing its signature, decisions, or commitments
does not change accepted state or latch a fault. Only successful serialized
Mother acceptance does. Neither registry refresh nor ordinary reconciliation
clears a known fork. Owner resolution/re-genesis is not implemented by this
bounded gate; no reset API is provided.
