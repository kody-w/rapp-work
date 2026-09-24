# RAPP Work SDK agent entrypoint

The qualified product architecture is the installable `rapp-work` distribution
and `rapp_work` package. Start with `README.md`, `docs/ARCHITECTURE.md`, and
`protocols/rapp-work-sdk/1/SPEC.md`.

Public JSON operations are exactly `status`, `verify`, `discover`, `scaffold`,
`update`, and `migrate`. The first three are read-only. The latter three plan by
default and require explicit apply plus the exact canonical plan SHA-256.

Read the canonical `rapp-work/1` bytes named by `RAPP_WORK_PIN.json` before
changing business protocol behavior. RAPP/1 remains authoritative for
identity, canonical bytes, the eleven-key Frame, hashes, signatures, Eggs,
sealed artifacts, and registries. Change canonical pins only for an explicitly
accepted upstream revision. Never rewrite root `SPEC.md`, the historical
signed registry, or its signatures to make an SDK pin update appear activated.

Historical project skills are compatibility surfaces. Use `rapp_work.compat`
rather than creating another workspace-manager or Private Hive
implementation. Preserve their fixtures.

`CONSTITUTION.md` (lessons and pending amendments) and `ECOSYSTEM.md` (the
layer map) are experimental guidance; they never override RAPP/1 or `rapp-work/1`.
`ECOSYSTEM.md` is generated from the tree in `organism/`: edit its part files, then
run `python3 organism/tools/build.py`; never edit the generated files by hand.

No network or credential inheritance by default. Never execute discovered
neurons, plugins, or skills. DOGG must be PII-free; GODD remains private.
