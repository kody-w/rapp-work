---
name: Distributed Hive
column: across
beside: 1
role: "The RAPP/1 network as one Hive, found by raw URL: RAPP's seed → beacon → `estate.json` → Hive root → a pointer per repository → its `.rapp/member.md`, at its LTS commit"
home: "`DISTRIBUTED-HIVE.md`, HIVE-MD “Remote member spaces” and the Hive agent's `resolve`, in [`kody-w/rapp-model-hive`](https://github.com/kody-w/rapp-model-hive/tree/experimental/hive-md-distributed) (branch `experimental/hive-md-distributed`); RAPP proposal 0020, a draft on branch `experimental/proposal-0020-distributed-hive`"
health: experimental; the seed does not reach it yet
lines:
  - the RAPP/1 network as one Hive
  - each repo's .rapp/ · found from RAPP's seed
---
The distributed Hive is the RAPP/1 network as one Hive of plain folders and files. It is where RAPP/1 LTS ends: a person pulls full RAPP/1 from static data.

- Each repository, a station, keeps its own member space: its card `.rapp/member.md` and what it shares under `.rapp/shared/`, changed by its own commits.
- A Hive root is a Hive's public copy; for the RAPP Hive, `kody-w/rapp-hive-public`. In the draft convention it keeps one pointer per station, `members/<station>.md`, which pins the station's LTS commit and the hash of each file read there. None is published yet.
- It is all found by raw URL, with no server: RAPP's seed, then the operator's beacon, then `estate.json`, then the Hive root, then each station (RAPP Constitution Articles XLVI and XLVII, and proposal 0020).
- LTS, the default, reads each station at its pinned commit and checks every hash. Newest reads each at `HEAD`. The Hive agent's `resolve` reads only the LTS way: each station at its pinned commit, every file checked, into a local copy.
- Hashes prove integrity only. Authenticity needs one signature at the top: the estate owner's signed registry.
- Today the seed's one operator is not accepted, and the beacon and `estate.json` are placeholder status documents, so a walk from the seed stops at the estate. The estate kit drafted a real beacon 1.1 and an `estate.json` that pins the Hive root, on `kody-w/rapp-estate` branch `experimental/rapp1-distributed-hive`, and RAPP's branch `experimental/rapp1-network-seed-acceptance` pins that beacon in the seed, then accepts the operator once the owner allows it. Nothing there is signed or merged.
