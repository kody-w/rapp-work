---
name: Private Hive
layer: 3
order: 2
role: "The `rapp-hive/1` Private Hive: the only kind of Hive an organization can bind (one `hive_rappid`), with one owner"
home: "[`rapp-hive/1`](https://github.com/kody-w/rapp-work/blob/main/protocols/rapp-hive/1/SPEC.md)"
health: in force; pinned by `kody-w/rapp-work`'s own signed registry, and the kody-w estate's registry does not pin it yet
check:
  - "`python3 tools/check.py` (signed registry, plus `rapp-hive/1` and `rapp-federation/1` conformance), `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
  - "For `rapp-hive/1` and Workspace/1: the `kody-w/rapp-workspace` CI jobs (core pins and conformance, Private Hive suite)"
lines:
  - rapp-hive/1
  - one owner
  - bound by hive_rappid
---
A Private Hive is the `rapp-hive/1` profile, in force today: `kody-w/rapp-work`'s own signed registry (`registry_seq` 0) pins it at today's bytes, though that registry's `rapp-work/1` pin, the historical root `SPEC.md`, is history, not an adoption. The kody-w estate's registry does not pin it yet; phase 4 signs that pin.

- Its declaration names one Hive, its world, one owner, its members, rooms and channels.
- An organization binds exactly one of them by its `hive_rappid`.
- It never publishes: external publication is disabled by its declaration.
