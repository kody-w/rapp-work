---
from: private-hive
to: organization
what: A signed Hive vector (`work.vector`) naming the accepted checkpoint
authorized_by: The organization's signer; a consumer accepts it only after verifying the checkpoint under `rapp-hive/1`
home: Canonical `rapp-work/1` §§2, 4
health: specified (G16)
arrow: down
label: "work.vector: the accepted Hive checkpoint"
---
An organization binds exactly one Private Hive by its `hive_rappid`. Each signed `work.vector` records which authenticated Hive checkpoint it accepted, and consumers keep it as a high-water mark: a lower sequence is rollback, and different hashes at one sequence are a fork. No estate has activated this yet (G16).
