---
name: Hive copy
layer: 4
order: 2
role: Your copy of each Hive, with your own `members/<you>/` space and one key
home: The Hive agent's private state (`<hive>/.git/rapp-hive/`)
health: experimental
lines:
  - your space
  - one key per device
  - verified
---
Your Hive copy is your checkout of a Hive, with your own `members/<you>/` space inside it.

- Your device holds one key for this Hive, and it signs your commits.
- Your device verifies every change before it checks anything out.
