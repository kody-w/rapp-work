---
name: Workspaces
layer: 4
order: 1
role: Your private, local-first workspaces (GODD); the SDK changes them only by exact plans, and never replaces your own files
home: "RAPP Workspace/1; `rapp-work-sdk/1` as specified in `kody-w/rapp-work` (`kody-w/rapp-workspace` carries a different document under the same id)"
health: specified; no estate activates RAPP Workspace/1 or `rapp-work-sdk/1` yet
check:
  - "`python3 tools/check.py` (signed registry, plus `rapp-hive/1` and `rapp-federation/1` conformance), `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
  - "For `rapp-hive/1` and Workspace/1: the `kody-w/rapp-workspace` CI jobs (core pins and conformance, Private Hive suite)"
lines:
  - private GODD
  - local-first
  - SDK plans
---
Your workspaces are private and local-first. They never go into a Hive unless you bring something by signed copy.

- The SDK plans every change it makes, and applies a plan only with that plan's exact hash (`plan_sha256`). It never replaces a file it does not own.
- RAPP Workspace/1 and the SDK are specified, but no estate activates them yet.
