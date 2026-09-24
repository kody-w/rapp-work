---
name: Hive Mind
column: across
beside: 3
order: 2
role: "The network of sovereign Hives: discovery through Hive Hub cards, and agreements between organizations"
home: "[`rapp-federation/1`](https://github.com/kody-w/rapp-work/blob/main/protocols/rapp-federation/1/SPEC.md) (candidate); [`kody-w/hive-hub`](https://github.com/kody-w/hive-hub/tree/experimental/organism-fit)"
health: candidate; folder Hives through Hive Hub cards (experimental, G12)
check:
  - "`python3 tools/check.py` (signed registry, plus `rapp-hive/1` and `rapp-federation/1` conformance), `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
  - "`python tools/build.py --check` and the tests in `kody-w/hive-hub`"
lines:
  - other organizations' Hives, by agreement only
  - rapp-federation/1 · Hive Hub cards
---
The Hive Mind is the network of sovereign Hives. Each stays its own.

- Hive Hub is a folder of markdown cards: one per protocol, organization and Hive. A seven-word chant finds a card; it is a locator, never a password.
- To join, you give a card to your own Brainstem. It checks the Hive's first commit and founder key, then sends one signed request.
- Organizations work together only by signed agreement. Membership is never shared.
