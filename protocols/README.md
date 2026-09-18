# RAPP Work protocols

These public profiles extend RAPP/1 by registration rather than changing its
eleven-key frame envelope.

| Protocol | Purpose | Conformance |
|---|---|---|
| [`rapp-work-sdk/1`](rapp-work-sdk/1/SPEC.md) | Installable SDK and workspace integration profile; package-qualified, not silent signed-estate activation | `python3 -m pytest -q tests/test_profiles.py tests/test_sdk_workspace.py` |
| [`rapp-hive/1`](rapp-hive/1/SPEC.md) | Sovereign Private Hives, sealed GODD rooms, Dream Catcher convergence, and storage portability | `python3 rapp-hive/1/reference/hive_conformance.py` |
| [`rapp-federation/1`](rapp-federation/1/SPEC.md) | The universal logical Hive Mind and consent-bound, delay-tolerant business federation | `python3 rapp-federation/1/reference/conformance.py --report rapp-federation/1/conformance-results.json` |

This repository's frozen signed registry adopts `rapp-work/1`, `rapp-hive/1`,
and `rapp-federation/1` at their historical checked-in hashes. Separately,
`RAPP_WORK_PIN.json` binds the SDK to the accepted canonical `rapp-work/1`
specification and schema in `kody-w/rapp-1`. The SDK integration profile is
qualified package metadata and intentionally does not rewrite or forge the
historical authority. Every estate activates protocols independently through
its own owner-signed RAPP/1 registry.
