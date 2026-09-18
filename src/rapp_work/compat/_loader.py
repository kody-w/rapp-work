from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from .._resources import skill_root

_MODULES: dict[str, ModuleType] = {}


def load_file(name: str, path: Path, *, package: bool = False) -> ModuleType:
    existing = _MODULES.get(name)
    if existing is not None:
        return existing
    locations = [str(path.parent)] if package else None
    spec = importlib.util.spec_from_file_location(
        name,
        path,
        submodule_search_locations=locations,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load compatibility implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _MODULES[name] = module
    return module


def workspace_manager_module() -> ModuleType:
    return load_file(
        "rapp_work._compat_workspace_manager",
        skill_root("rapp-workspace-manager") / "scripts" / "manage.py",
    )


def private_hive_prepare_module() -> ModuleType:
    return load_file(
        "rapp_work._compat_private_hive_prepare",
        skill_root("rapp-private-hive") / "scripts" / "prepare_workspace.py",
    )


def private_hive_package() -> ModuleType:
    package = load_file(
        "rapp_work._compat_private_hive",
        skill_root("rapp-private-hive") / "lib" / "private_hive" / "__init__.py",
        package=True,
    )
    for child in ("authority", "bundle", "client", "common", "keys", "release", "state"):
        setattr(package, child, importlib.import_module(f"{package.__name__}.{child}"))
    return package


def private_hive_cli_module() -> ModuleType:
    return load_file(
        "rapp_work._compat_private_hive_cli",
        skill_root("rapp-private-hive") / "scripts" / "deploy_hive.py",
    )
