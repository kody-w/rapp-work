---
name: Private Hive
layer: 3
order: 2
role: "The `rapp-hive/1` Private Hive: the organization's one Hive today (one `hive_rappid`), with one owner"
home: "[`rapp-hive/1`](https://github.com/kody-w/rapp-work/blob/main/protocols/rapp-hive/1/SPEC.md)"
health: in force
check:
  - "`python3 tools/check.py` (signed registry, plus `rapp-hive/1` and `rapp-federation/1` conformance), `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
  - "For `rapp-hive/1` and Workspace/1: the `kody-w/rapp-workspace` CI jobs (core pins and conformance, Private Hive suite)"
lines:
  - rapp-hive/1
  - one owner
  - bound by hive_rappid
---
A Private Hive is the `rapp-hive/1` profile, in force today.

- Its declaration names one Hive, its world, one owner, its members, rooms and channels.
- An organization binds exactly one of them by its `hive_rappid`.
- It never publishes: external publication is disabled by its declaration.
