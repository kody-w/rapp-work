---
layer: 3
name: Hive
role: "The organization's one shared folder: `HIVE.md`, `members/`, `requests/`, `shared/`, `former/`, with git underneath and no owner inside"
decides: The members, by the Hive's approvals number
signed_with: SSH-signed commits, each judged by the Hive as it stood just before
home: "Folder convention: [`kody-w/rapp-model-hive`](https://github.com/kody-w/rapp-model-hive/tree/experimental/hive-md) `HIVE-MD.md`. In force today: [`rapp-hive/1`](https://github.com/kody-w/rapp-work/blob/main/protocols/rapp-hive/1/SPEC.md)"
health: experimental (folder convention); in force (`rapp-hive/1`)
color: green
check:
  - "For the folder convention: `python agents/hive_agent.py check <hive>`, `check-public <copy>`, and `tools/build_example.py --check` with the tests (CI on macOS, Linux and Windows)"
  - "For `rapp-hive/1` and Workspace/1: the `kody-w/rapp-workspace` CI jobs (core pins and conformance, Private Hive suite)"
lines:
  - HIVE.md · members/ · requests/ · shared/ · former/ — markdown, git underneath, no owner inside
  - Every change is one signed commit, judged by the Hive as it stood just before · approvals ≥ 2
---
A Hive is a folder of markdown that people can read, with git underneath and no owner inside.

- `HIVE.md` holds its rules, including how many approvals a change needs.
- Every change is one signed commit. The Hive judges it by its rules as they stood just before.
- The folder convention is experimental. `rapp-hive/1` stays in force, unchanged.
