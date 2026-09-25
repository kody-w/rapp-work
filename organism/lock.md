---
name: "RAPP/1 LTS: what it takes to lock the whole thing"
definition:
  - "One LTS release of the whole stack: one estate release scope that pins every component"
  - Everything in it is in force, and nothing in it is experimental
  - Newest releases get their own successor scopes. Experiments live only there until they graduate
pins:
  - "the LTS kernel `brainstem-v0.6.9`"
  - "`rapp-hive/1`"
  - "`rapp-work/1`"
  - RAPP Workspace/1
  - "`rapp-work-sdk/1`"
  - "`rapp-registry/1.0`"
  - "`rapp-cicd/1`"
  - "`rapp-deploy/1`"
  - the agents and apps that ship with it
cite: "RAPP/1 §11.1: a release scope's pin is “a permanent compatibility anchor, not a moving release channel”, and “A successor uses a new `release_scope`”. §13.3: no two `grail-kernel` entries share a scope"
phases:
  - "Decide: you, about an hour"
  - "Zero drift, clean pull: engineering"
  - "Close the specification gaps: spec owner"
  - "Switch it on: estate owner"
  - "Graduate into RAPP/1: engineering, through the rings"
steps:
  - "1: merge RAPP proposal 0001 (G18), a documentation fix only: it is yours because RAPP reserves constitution merges for the maintainer (Articles XXVIII.4 and XXX.2)"
  - "1: accept or refuse RAPP proposal 0002 (G19), Tier 2 loading: a draft on `experimental/proposal-0002-tier2-parity`"
  - "1: ratify the RAPP Work Constitution and its Part V (G8, G9)"
  - "2: fix RAPP's and RAR's non-conformant eggs, and RAR's bounded scan"
  - "2: give rapp-model-hive's frames a trusted anchor"
  - "2: re-sweep until every repo of the RAPP/1 stack is certified (the dogfood)"
  - "2: keep the default pull clean: default branches and the LTS install carry only in-force parts; experiments stay on experimental branches or in newest"
  - "2: one front door keeps the network unified and tracked; pin the Windows LTS install (G23)"
  - "3: rapp-hive/1 (G1, G6)"
  - "3: rapp-work-sdk/1 (G2, G3, G4, G7)"
  - "3: rapp-work/1 (G5, G10, G11, G22)"
  - "3: a gap that cannot close in time waits for a later RAPP, with the owner's sign-off"
  - "4: sign the RAPP/1 LTS release scope: its LTS `grail-kernel` entry, plus a successor scope for the newest kernel (G15)"
  - "4: sign the protocol pins"
  - "4: activate `rapp-work/1` (G16): the Organization must be in force for RAPP/1 to be healthy throughout"
  - "4: give the Brainstem an SDK agent (G17)"
  - "5: graduate each newest part through the rings: Folder Hive, Hive copy and the Hive agent (G14), References (G13), Hub cards (G12), Public copy, the Brainstem app (G20)"
  - "5: then Hive Mind, once an estate accepts `rapp-federation/1`, and the Release rings, once phase 4 activates them and a graduation uses them"
  - "5: merge what graduated; the rest stays out of what people pull"
  - "5: tag the lock once the clean-pull check passes again; sweep for drift on a schedule"
---
RAPP/1 is the one LTS release people pull. Five phases lock it, in order, with the owner's decisions first.
