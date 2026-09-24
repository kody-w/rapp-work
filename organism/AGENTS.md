# The organism: instructions for AI assistants

1. Read `ORGANISM.md` first. It holds the whole organism on one page: the graph, every layer, part, crossing, gap and journey, and what holds everywhere.
2. Change the organism only through its part files: `layers/`, `parts/`, `crossings/`, `gaps/`, `journeys/`, `invariants.md` and `dogfood.md`. Keep one fact per file. To reorganize, move, add, rename or remove files.
3. Then run `python3 tools/build.py`, and `python3 tools/build.py --check` before you finish.
4. Never edit generated files by hand: `ORGANISM.md`, everything in `views/`, and `../ECOSYSTEM.md` when this folder lives in `kody-w/rapp-work`.
5. If the builder refuses, fix the file it names. Do not work around the check.
6. Keep every fact public or synthetic: no personal data, no private Hive names, no local paths. Write plain, short sentences.
7. Specifications decide. When the organism disagrees with a specification, fix the organism, or propose the change to the specification's owner.
