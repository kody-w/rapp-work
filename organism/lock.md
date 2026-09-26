---
name: "RAPP/1 LTS: what it takes to lock the whole thing"
definition:
  - "One estate-signed `release_scope` whose Grail pin never moves; each release in it pins every component"
  - Everything in it is in force; nothing in it is experimental
  - "The newest channel holds experiments until they graduate: one successor scope per newer kernel"
pins:
  - "the LTS kernel `brainstem-v0.6.9`"
  - "`rapp-hive/1`"
  - "`rapp-work/1`"
  - RAPP Workspace/1
  - "`rapp-work-sdk/1`"
  - "`rapp-registry/1.1`"
  - "`rapp-cicd/1`"
  - "`rapp-deploy/1`"
  - the agents and apps that ship with it
cite: "RAPP/1 §11.1: the pin is “a permanent compatibility anchor”, and “A successor uses a new `release_scope`”. §13.3: at most one `grail-kernel` entry per scope, and a `protocol` entry per adopted protocol. `rapp-cicd/1` §2: a release lists every part"
phases:
  - "Decide: you, about an hour"
  - "Zero drift, clean pull: engineering"
  - "Close the specification gaps: spec owner"
  - "Switch it on: estate owner"
  - "Graduate into RAPP/1: engineering, through the rings"
steps:
  - "1: accept or refuse RAPP proposal 0002 (G19), Tier 2 loading: a draft on `experimental/proposal-0002-tier2-parity`"
  - "1: ratify the RAPP Work Constitution and its Part V (G8, G9)"
  - "1: done: RAPP proposal 0001 and its amendment are merged (`kody-w/RAPP#119`, `kody-w/RAPP#124`), so RAPP's Constitution says only top-level agents are live"
  - "2: fix RAPP's and RAR's non-conformant eggs and RAR's bounded scan (`kody-w/RAPP#121`, which only the maintainer merges, and `kody-w/RAR#1116`; both open)"
  - "2: give rapp-model-hive's frames a trusted anchor (`kody-w/rapp-model-hive#2`, open; it needs the owner's registry entries)"
  - "2: re-sweep until every repo of the RAPP/1 stack is certified (the dogfood)"
  - "2: keep the default pull clean: default branches and the LTS install carry only in-force parts"
  - "2: one front door keeps the network unified and tracked; pin the Windows LTS install (G23, which only the owner merges)"
  - "3: RAPP/1 core additions land before the estate signs: rev-17, a draft on `kody-w/rapp-1` `experimental/rapp1-core-*`, adds release pins, lifecycle notices and stream signers"
  - "3: rapp-hive/1 (G1, G6)"
  - "3: rapp-work-sdk/1 (G2, G3, G4, G7, G11)"
  - "3: rapp-work/1, by sibling profiles (G5, G10); RAPP's Constitution and RAPP Workspace/1 (G22, G24)"
  - "3: a gap that cannot close in time waits for a later RAPP, with the owner's sign-off"
  - "4: sign both kernel channels: a `grail-kernel` entry for the LTS scope, and one for a successor scope (G15)"
  - "4: sign the remaining protocol pins; that estate-activates the Workspaces and RAR"
  - "4: activate `rapp-work/1` (G16), so the Organization is in force"
  - "4: authorize the network pulse signer: pulses (experimental) version the map and the network's health"
  - "4: switch on the Distributed Hive: accept RAPP proposal 0020, then merge the drafts of beacon 1.1, `estate.json` and the operator's acceptance in RAPP's seed"
  - "5: graduate each newest part through the rings: Folder Hive, Hive copy and the Hive agent (G14), References (G13), Hub cards (G12), Public copy, the Brainstem app (G20), the Brainstem's SDK agent (G17), the Distributed Hive"
  - "5: then Hive Mind, once an estate accepts `rapp-federation/1`, and the Release rings, once a graduation uses them"
  - "5: merge what graduated; the rest stays out of what people pull"
  - "5: tag the lock once the clean-pull check passes again; sweep for drift on a schedule"
end: "distributed-hive: RAPP/1 LTS resolves as a distributed Hive, so a person pulls full RAPP/1 from static data"
---
RAPP/1 is the one LTS release people pull. Five phases lock it, in order, with the owner's decisions first; it ends as a distributed Hive.
