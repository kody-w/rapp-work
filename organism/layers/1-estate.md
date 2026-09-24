---
layer: 1
name: Estate
role: "An owner's signed registry: who may sign as whom, which protocols are pinned, which Brainstem kernel (Grail) is declared"
decides: The estate owner
signed_with: RAPP/1 §13 registry entries
home: Each owner's repository (`rappid.json`, `registry.json`)
health: in force
color: purple
check: "`python3 tools/check.py`, `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
lines:
  - Who may sign as whom · which protocols are pinned · which Brainstem kernel (Grail) is declared
  - Append-only · rappid.json · registry.json · owner-anchor.json
---
An estate is one owner's signed list of what is theirs.

- It says which keys may sign as whom, which protocols are pinned, and which Brainstem kernel (the Grail) is declared.
- It lives in the owner's own repository and only grows, one signed entry at a time.
- An organization's owner gets their authority from here.
