---
name: Folder Hive
layer: 3
order: 1
span: 2
role: "A folder of markdown with git underneath: `HIVE.md`, `members/`, `requests/`, `shared/`, `former/`, and no owner inside"
home: "[`kody-w/rapp-model-hive`](https://github.com/kody-w/rapp-model-hive/tree/experimental/hive-md) `HIVE-MD.md`"
health: experimental; not bindable to an organization yet (G10)
check: "For the folder convention: `python agents/hive_agent.py check <hive>`, `check-public <copy>`, and `tools/build_example.py --check` with the tests (CI on macOS, Linux and Windows)"
lines:
  - HIVE.md · members/ · requests/ · shared/ · former/ · no owner inside
  - new Hives start at 2 approvals · not bindable yet (G10)
---
A folder Hive is markdown that people can read, with git underneath and no owner inside.

- `HIVE.md` holds its rules, including how many approvals a change needs. New Hives start at 2.
- Every change is one signed commit. The Hive judges it by its rules as they stood just before.
- It is experimental. No specification lets an organization bind it yet (G10).
