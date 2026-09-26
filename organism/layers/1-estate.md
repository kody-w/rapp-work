---
layer: 1
name: Estate
role: "An owner's signed registry: who may sign as whom, which protocols are pinned, which Grail kernel each release scope pins (RAPP/1 §§11.1, 13.3)"
decides: The estate owner
signed_with: RAPP/1 §13 registry entries
home: "Each owner's repository (`rappid.json`, `registry.json`); the kody-w estate's signed registry is `ecosystem-spec.json` in `kody-w/rapp-map`, anchored by the owner rappid in `kody-w/rapp-1`'s README"
health: in force; no estate declares the Brainstem's kernel yet (G15)
color: purple
check: "`python3 tools/check.py` (signed registry, plus `rapp-hive/1` and `rapp-federation/1` conformance), `python3 -m pytest` and `python3 tools/release_inventory.py --check` in `kody-w/rapp-work`; for the kody-w estate, `kody-w/rapp-map`'s registry verifier"
lines:
  - Who may sign as whom · which protocols are pinned · which Grail kernel each release scope pins
  - Append-only · rappid.json · a signed registry · an owner anchor out of band
---
An estate is one owner's signed list of what is theirs.

- It says which keys may sign as whom, which protocols are pinned, and which Grail kernel each release scope pins.
- It lives where its owner publishes it, usually the owner's own repository. Each signed version raises `registry_seq` and appends entries; an old entry is retired only by its `deprecated` flag, never removed.
- An organization's owner gets their authority from here.
- The kody-w estate's signed registry, `kody-w/rapp-map`'s `ecosystem-spec.json` at `registry_seq` 2, pins `rapp/1`, `rapp-cicd/1` and `rapp-deploy/1`.
- No estate declares the Brainstem's kernel yet. RAPP's unsigned `KERNEL_PIN.json` pins its LTS channel at `kody-w/rapp-installer@brainstem-v0.6.9`; the newest `brainstem-v*` tag, `brainstem-v0.6.16`, is what the installer's `main` ships, and nothing signed pins it yet (G15).
