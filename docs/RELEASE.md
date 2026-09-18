# Release qualification

## Inventory

`RELEASE-INVENTORY.json` commits to every release source byte except itself.
The sdist must contain every inventoried path at its exact size and SHA-256.
Only the fixed deterministic setuptools metadata set may appear in addition.

```bash
python3 tools/release_inventory.py --write
python3 tools/release_inventory.py --check
```

The inventory is canonical JSON and records path, byte length, and SHA-256.
In a clean sdist extraction, `--check` verifies those committed files directly
without requiring Git; `--write` remains source-checkout-only.

## Required gates

```bash
python3 tools/check.py
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy
python3 tools/release_inventory.py --check
python3 -m build
python3 tools/verify_package.py dist/*.whl dist/*.tar.gz
```

Then install the wheel into a new repository-local virtual environment and
smoke both entrypoints:

```bash
python3 -m venv .clean-install
.clean-install/bin/python -m pip install dist/rapp_work-1.0.0-py3-none-any.whl
.clean-install/bin/rapp-work status
.clean-install/bin/python -m rapp_work verify --root .
```

Remove the qualification environment afterward. Do not use system temporary
directories for release work.

## Package checks

`tools/verify_package.py` checks:

- distribution name/version and console entrypoint;
- typed marker and static API/profile metadata;
- exact root/package mirrors of `RAPP1_PIN.json` and `RAPP_WORK_PIN.json`;
- exact vendored RAPP/1 implementation and packaged canonical RAPP Work
  specification/schema;
- Hive/Federation profile fixtures;
- legacy workspace-manager and Private Hive compatibility payloads;
- exact sdist equality with `RELEASE-INVENTORY.json`, apart from validated
  deterministic packaging metadata;
- archive path normalization; and
- absence of links/devices in wheel and sdist.

## Authority statement

Building a package does not activate a profile in another estate, publish a
Private Hive, accept a Federation agreement, or mutate signed parent authority.
The canonical SDK parent pin and the historical root signed-estate pin are
verified independently; packaging never rewrites the latter.
