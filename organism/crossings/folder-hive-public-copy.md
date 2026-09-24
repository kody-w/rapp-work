---
from: folder-hive
to: public-copy
what: Exactly the files of an approved manifest
authorized_by: The approvals number; `check-public` verifies the copy
home: Hive folder convention; `rapp-hive/1` §2
health: experimental
arrow: out
label: approved files
---
Members approve a manifest of exact files and hashes. Exactly those files are copied into the separate public copy, and anyone can check it with `check-public`. A Private Hive never publishes: `rapp-hive/1` disables external publication.
