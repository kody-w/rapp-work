---
from: estate
to: distributed-hive
what: "The estate's pin of the Hive root: a `hives[]` entry in `estate.json` naming the public copy's commit and the hash of its `PUBLISHED.md`"
authorized_by: "The estate owner's choice of commit. Hashes prove integrity; authenticity needs the estate owner's signed registry"
home: "RAPP proposal 0020 (§§1, 3, 6), a draft; RAPP Constitution Article XLVI"
health: candidate; `estate.json` is a placeholder today, and its draft entry does not match the convention yet
arrow: out
label: pins its root
---
An estate's `estate.json` pins the Hive roots it keeps, and its beacon leads to that `estate.json`, so a walk from RAPP's seed reaches every station. RAPP proposal 0020 drafts the optional `hives[]` field that carries this pin. It is a candidate: no estate has accepted it, and today's `estate.json` is a placeholder status document. The estate kit's draft on `kody-w/rapp-estate` branch `experimental/rapp1-distributed-hive` carries one `hives[]` entry for the RAPP Hive's root, unsigned, with an extra `lts_pins` member that the revised convention (`DISTRIBUTED-HIVE.md` §10) skips.
