---
layer: 1
name: Estate
role: "An owner's signed registry: who may sign as whom, which protocols are pinned, which Grail kernel each release scope pins (RAPP/1 §§11.1, 13.3)"
decides: The estate owner
signed_with: RAPP/1 §13 registry entries
home: Each owner's repository (`rappid.json`, `registry.json`)
health: in force; no estate declares the Brainstem's kernel yet (G15)
color: purple
check: "`python3 tools/check.py` (signed registry, plus `rapp-hive/1` and `rapp-federation/1` conformance), `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`"
lines:
  - Who may sign as whom · which protocols are pinned · which Grail kernel each release scope pins
  - Append-only · rappid.json · registry.json · owner-anchor.json
---
An estate is one owner's signed list of what is theirs.

- It says which keys may sign as whom, which protocols are pinned, and which Grail kernel each release scope pins.
- It lives in the owner's own repository and only grows, one signed entry at a time.
- An organization's owner gets their authority from here.
- No estate declares the Brainstem's kernel yet. Its pin is the unsigned `KERNEL_PIN.json` in `kody-w/RAPP`, frozen at `kody-w/rapp-installer@brainstem-v0.6.9` (G15).
