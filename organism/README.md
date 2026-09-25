# The RAPP/1 organism

The anatomy of the RAPP/1 ecosystem as a tree of small markdown files, one fact per file, and a builder that draws every view from them. The tree is the single source of truth. The views are generated, so they cannot drift from it.

It is experimental. Specifications decide; the organism only points at them.

It also says what it takes to lock RAPP/1, the one LTS release of the whole stack that people pull. Only parts in force are in RAPP/1; every other part is newest, until it graduates.

| Path | What it holds |
|---|---|
| [`ORGANISM.md`](ORGANISM.md) | The genome: the whole organism on one page. Generated. |
| `layers/` | The seven layers, from 0 (RAPP/1) to 6 (you), one file each |
| `parts/` | Parts inside a layer, and parts beside the stack |
| `crossings/` | How anything moves between layers, one crossing per file |
| `journeys/` | E1 to E7: end to end, through every layer |
| `gaps/` | One file per gap, G01 to G24: what is still open, and which lock-in phase closes each. A dropped gap leaves its number unused (G21). |
| `invariants.md` | What holds everywhere |
| `dogfood.md` | The RAPP Hive, where the organism is tried for real |
| `health.md` | The health words every `health` and `status` starts with |
| `glossary.md` | The other words this map uses, one per line |
| `lock.md` | RAPP/1 LTS: what it is and pins, five phases of steps that lock it, and the part where it ends |
| `clean-pull.md` | The clean-pull check: files on each default branch that mention “experimental”, and the front door where people find RAPP/1 |
| `views/` | Generated: `graph.txt`, `organism.svg`, `organism.excalidraw`, `one-page.html`, `lock-in.html`, and their printed `one-page.pdf`, `lock-in.pdf` and `rapp-lock-in.pdf` (both pages) |
| `tools/build.py` | The builder: Python 3.10 or newer, standard library only |

## Pull a fresh copy

Each of these gets you this folder from the `experimental/rapp-work-constitution` branch of [`kody-w/rapp-work`](https://github.com/kody-w/rapp-work).

1. With degit (needs Node.js):

   ```bash
   npx degit kody-w/rapp-work/organism#experimental/rapp-work-constitution my-organism
   ```

2. With git, as a shallow sparse clone:

   ```bash
   git clone --depth 1 --filter=blob:none --sparse -b experimental/rapp-work-constitution https://github.com/kody-w/rapp-work.git
   cd rapp-work
   git sparse-checkout set organism
   ```

   Later, `git pull` in that folder brings the newest version.

3. Without tools: download the [branch ZIP](https://github.com/kody-w/rapp-work/archive/refs/heads/experimental/rapp-work-constitution.zip) and keep its `organism/` folder.

## View it

- Open `views/one-page.html` in a browser. It prints on one US Letter landscape page.
- Open `views/lock-in.html` for what it takes to lock RAPP/1 LTS: the owner's decisions first, what RAPP/1 pins, five phases, each layer's status and every gap. Each gap a step names is drawn as a chip in the colors of its status. The page ends where RAPP/1 LTS ends: the Distributed Hive, which a person pulls from static data. `views/rapp-lock-in.pdf` holds both pages.
- In every view, plain boxes in force are RAPP/1, and striped boxes (in the text graph, the word `newest`) are not in RAPP/1 yet. Inside each layer the RAPP/1 cells come first and the newest cells after them, so newest parts read as their own lane. You and outside knowledge ship in neither, and are drawn dotted and white. Square chips say what each layer still needs to graduate.
- Read `views/graph.txt` in a terminal, or `ORGANISM.md` for the graph with every table.
- Open `views/organism.svg` for the drawing, or load `views/organism.excalidraw` in [Excalidraw](https://excalidraw.com).

## Copy and tweak

Each file starts with a short frontmatter block, the facts the builder needs, then a few plain words: the anatomy page.

```markdown
---
name: Public copy
column: out
beside: 3
order: 1
role: A separate, reviewed repository holding exactly the approved files, plus `PUBLISHED.md`
home: The Hive folder convention; DOGG rules of `rapp-hive/1` §2
health: experimental
lines:
  - exactly the approved files
  - PUBLISHED.md · check-public
---
A public copy is a separate repository. It holds exactly the files the members approved.
```

- **Change a fact:** edit the one file that holds it.
- **Reorganize:** move a part with `beside` or `layer`, or add, rename and remove files. The views follow.
- **Add a crossing:** add a file to `crossings/` that names its `from`, `to`, `arrow` and `label`. Name the file `<from>-<to>.md`.
- **Rebuild:**

  ```bash
  python3 tools/build.py          # writes ORGANISM.md and views/
  python3 tools/build.py --pdf    # also prints the PDFs in views/, when Chrome or Chromium is installed
  ```

The builder refuses with the file and the fix when something is wrong: an unknown or missing field, a duplicate id, layers other than exactly 0 to 6, a crossing with an unknown end or an arrow against its direction, a health word that `health.md` does not define, a gap with a bad `phase`, `who` or `blocks`, a gap that no `lock.md` step of its phase names, a newest part that no `lock.md` step graduates, a part in force whose health names something experimental, a bad clean-pull count, an `end` that names no part, a page that prints on more than one sheet, or a value that would break the frontmatter.

| File | Fields (optional ones in brackets) |
|---|---|
| `layers/<n>-<id>.md` | `layer`, `name`, `role`, `decides`, `signed_with`, `home`, `health`, `color`, [`span`, `lines`, `check`] |
| `parts/<id>.md` | `name`, `role`, `home`, `health`, and either `layer` or `column` with `beside`; [`order`, `span`, `lines`, `check`] |
| `crossings/<id>.md` | `from`, `to`, `what`, `authorized_by`, `home`, `health`, `arrow`, `label` |
| `gaps/G<nn>.md` | `id`, `gap`, `home`, `fix`, `status`, `phase`, `who`, `blocks` |
| `journeys/E<n>.md` | `id`, `title`; the steps are the body's `- ` lines |
| `invariants.md` | `healthy`, `upstream`; each rule is a body line `- **Lead.** More words.` |
| `dogfood.md` | `name`, `health`, `tree`, `loop` |
| `health.md`, `glossary.md` | `name`; each word is a body line `- **word:** meaning` |
| `lock.md` | `name`, `definition`, `pins`, `cite`, `phases` (`Title: who` or `Title: who, note`), `steps` (`<phase>: words`), [`end` (`<part id>: words`)] |
| `clean-pull.md` | `name`, `phase`, `command`, `measured` (YYYY-MM-DD), `mentions` (`<repository>: <files>`), [`door` (`<health word>: words`)] |

- `health` and `status` start with a word from `health.md`: in force, specified, experimental, candidate, planned, gap, idea, open, proposed or own shape. Words after it are notes. `—` means none.
- `color` is an Open Color family: gray, orange, green, blue or purple.
- `column` is in, out or across. `beside` and `layer` are layer numbers.
- `arrow` is down, up or both inside the stack; in, out or both beside it. It must point from `from` to `to`, so every arrow reads like its row.
- Inside a layer, RAPP/1 cells come first and newest cells after them; `order` sorts the parts within each lane.
- `span` sets how much of its layer's width a part inside it takes (default 1). A layer with parts and its own `lines` is drawn as one more cell; its `span` sizes that cell.
- A part's channel follows its health, and is never set by hand: RAPP/1 (the LTS release) when it is in force; newest, not in RAPP/1 yet, for any other word; outside knowledge (own shape) ships in neither.
- `phase` is the lock-in phase that closes a gap, 1 to 5, and `who` acts on it: you, engineering, spec owner or estate owner. `blocks` names the layer or part the gap holds back. Each layer's status is `in RAPP/1`, `N to graduate` (those gaps, plus its newest parts that no gap covers) or `nothing to graduate`.
- Every gap must be named by a `lock.md` step of its own phase, every newest part by some `lock.md` step, and every phase needs a step. The clean-pull check needs a step of its `phase` that says its `name`.
- `end` names the part where the lock-in ends, and what reaching it means. The lock-in page ends with it, its role drawn as a route when the role reads `lead: a → b → c`.
- `lines` are the words drawn in a box. A layer `role` that starts with a short phrase and a colon gives the box its title.
- Wrap a value in double quotes when it holds `: ` or starts with a sign such as `` ` ``, `[` or `"`, so the frontmatter stays valid YAML.

## Check it

```bash
python3 tools/build.py --check
```

It rebuilds every view in memory and exits 1 if any generated file differs from the tree. The PDFs are left out, because Chrome stamps the time into them. `--pdf` checks their page counts instead: one sheet for each page.

Inside `kody-w/rapp-work`, the builder also keeps `../ECOSYSTEM.md`, the long-form map, generated from the same tree. It touches that file only when it already starts with the generated-file marker, so a copy anywhere else never writes outside its own folder.

## Make it your own

The folder stands alone: the builder needs only Python, and every link out of the tree is a full URL. It can become its own template repository later, unchanged. To grow your own organism, copy the folder, change the facts, and keep `tools/build.py`.
