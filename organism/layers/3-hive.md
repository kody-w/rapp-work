---
layer: 3
name: Hive
role: "Where the members share work: a `rapp-hive/1` Private Hive (in force, and the only kind of Hive an organization can bind), a folder Hive (experimental), or a distributed Hive of many repositories (experimental)"
decides: The members, by the approvals number in a folder Hive; the one owner of a Private Hive
signed_with: SSH-signed commits in a folder Hive; signed RAPP/1 frames in a Private Hive
home: "Folder Hive: [`kody-w/rapp-model-hive`](https://github.com/kody-w/rapp-model-hive/tree/experimental/hive-md) `HIVE-MD.md`. Private Hive: [`rapp-hive/1`](https://github.com/kody-w/rapp-work/blob/main/protocols/rapp-hive/1/SPEC.md)"
health: in force (`rapp-hive/1` Private Hive); experimental (folder Hive, distributed Hive)
color: green
---
The Hive is where members share work. It comes in two kinds today, side by side, and a third is drafted:

- A **folder Hive** is markdown with git underneath and no owner inside. It is experimental, and an organization cannot bind one yet (G10).
- A **`rapp-hive/1` Private Hive** has one owner and signed RAPP/1 frames. It is in force, pinned by `kody-w/rapp-work`'s own signed registry, and it is the only kind of Hive an organization can bind, once an estate activates `rapp-work/1` (G16).
- A **distributed Hive** is the RAPP/1 network as one Hive: in the draft convention, each repository keeps its member space in `.rapp/`, and a Hive root keeps one pointer per repository, which pins its LTS commit when it has one. It is experimental, and it is the end goal, where RAPP/1 LTS ends. The views draw it beside the estate, whose `estate.json` is to pin its root (RAPP proposal 0020).
