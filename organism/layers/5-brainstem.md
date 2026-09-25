---
layer: 5
name: Brainstem
role: "The one surface you talk to: your own AI. Frozen Grail kernel, hot-loaded agents (the Hive agent is one file), soul and memory"
decides: You, in conversation
signed_with: "Nothing by itself: it proposes, you confirm"
home: "[`kody-w/RAPP`](https://github.com/kody-w/RAPP), with the LTS kernel pinned to `kody-w/rapp-installer@brainstem-v0.6.9`"
health: in force
color: orange
span: 2
check: Each repository's own test suite and runner
lines:
  - "Your own AI: frozen Grail kernel · hot-loaded agents · soul · memory"
  - "kernel: LTS `brainstem-v0.6.9` (RAPP's pin) · newest release `brainstem-v0.6.16`"
  - It proposes; you decide. A Hive is never its agents folder or soul.
---
The Brainstem is your own AI, and the one surface you talk to. Every other layer is plumbing.

- Its kernel, the Grail, is frozen. Agents are single files it loads while it runs; the Hive agent is one of them, and it never goes into the kernel.
- The kernel has two channels, by design: LTS, which RAPP pins in `KERNEL_PIN.json` (`brainstem-v0.6.9` today), and the newest release (`brainstem-v0.6.16` today, the newest `kody-w/rapp-installer` tag).
- It keeps a soul and a memory.
- It proposes; you decide.
