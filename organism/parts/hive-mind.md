---
name: Hive Mind
column: across
beside: 3
order: 2
role: "The network of sovereign Hives: discovery, dial records and join cards, agreements between organizations"
home: "[`rapp-federation/1`](https://github.com/kody-w/rapp-work/blob/main/protocols/rapp-federation/1/SPEC.md) (candidate); [`kody-w/hive-hub`](https://github.com/kody-w/hive-hub)"
health: candidate; folder Hives unmapped (G12)
check:
  - "`python3 tools/check.py` (signed registry, plus `rapp-hive/1` and `rapp-federation/1` conformance), `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
  - Each repository's own test suite and runner
lines:
  - other organizations' Hives, by agreement only
  - rapp-federation/1 · Hive Hub
---
The Hive Mind is the network of sovereign Hives. Each stays its own.

- Hive Hub helps one organization find and dial another.
- Organizations work together only by signed agreement. Membership is never shared.
- Dial records do not describe folder Hives yet. That is gap G12.
