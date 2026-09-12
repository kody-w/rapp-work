# Authenticated Hive acceptance

Run the complete profile gate from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 protocols/rapp-hive/1/reference/hive_conformance.py
```

`HiveAcceptance` consumes exact signed RAPP/1 frames through an immutable-byte
resolver and an independently anchored `RegistryAuthority`. Structural payload
validation is not acceptance. The [SPEC](../SPEC.md) defines the unchanged frame,
catalog, convergence, and projection contracts.

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
