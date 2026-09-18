from __future__ import annotations

from importlib import resources
from pathlib import Path

from .errors import refuse


def source_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file() and (candidate / "RAPP1_PIN.json").is_file():
        return candidate
    return None


def vendor_root() -> Path:
    checkout = source_root()
    if checkout is not None:
        return checkout / "vendor" / "rapp-1"
    try:
        return Path(str(resources.files("rapp_work._vendor_rapp1")))
    except (ModuleNotFoundError, TypeError) as error:
        raise RuntimeError("packaged RAPP/1 reference is unavailable") from error


def protocols_root() -> Path:
    checkout = source_root()
    if checkout is not None:
        return checkout / "protocols"
    try:
        return Path(str(resources.files("rapp_work._protocols")))
    except (ModuleNotFoundError, TypeError) as error:
        raise RuntimeError("packaged protocol profiles are unavailable") from error


def skill_root(name: str) -> Path:
    checkout = source_root()
    if checkout is not None:
        candidate = checkout / ".github" / "skills" / name
    else:
        try:
            candidate = Path(str(resources.files("rapp_work._legacy_skills"))) / name
        except (ModuleNotFoundError, TypeError) as error:
            raise RuntimeError("packaged compatibility skills are unavailable") from error
    if not candidate.is_dir():
        refuse("REFUSE_COMPATIBILITY_MISSING", "packaged compatibility skill is missing", skill=name)
    return candidate


def data_file(relative: str) -> Path:
    candidate = Path(str(resources.files("rapp_work.data"))) / relative
    if not candidate.is_file():
        raise RuntimeError(f"packaged SDK data is missing: {relative}")
    return candidate
