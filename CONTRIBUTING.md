# Contributing

Contributions must preserve RAPP/1 and include falsifiable evidence.

1. Keep the exact RAPP/1 identity, frame, hash, signature, egg, and registry
   contracts.
2. Use closed schemas for authority-bearing payloads.
3. State ownership, lifecycle, privacy, failure, and migration behavior.
4. Add positive and refusal vectors.
5. Prove critical tests turn red under controlled mutations.
6. Include no PII, secrets, Private Hive content, or private relationship graph.
7. Refresh exact package/profile pins after accepted upstream changes. Rewrite
   a signed estate registry only through its owner's explicit signing process.

SDK changes must also preserve the six-operation closed JSON API, default
plan-only effects, exact plan-hash apply gate, offline/no-credential default,
no-follow filesystem behavior, inert discovery, package data, and
`RELEASE-INVENTORY.json`. Do not edit the frozen signed registry merely to add
the package-qualified `rapp-work-sdk/1` integration profile or to repoint its
historical `rapp-work/1` evidence at the SDK parent pin.
