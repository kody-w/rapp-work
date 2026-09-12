from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unicodedata
import uuid


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "vendor" / "hive" / "reference"
sys.path.insert(0, str(REFERENCE))
import rapp as R
import rapp_hive as H
from hive_acceptance import HiveAcceptance, RegistryAuthority
from rapp_profile import exact_keys, require

HEX = re.compile(r"^[0-9a-f]{64}$")
MAX_FILE_BYTES = 700 * 1024
MAX_ARTIFACT_BYTES = R.MAX_CANONICAL_BYTES
MAX_FILES = 256
MAX_ARTIFACTS = 8192
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


def canonical(value) -> bytes:
    data = R.canonical(value).encode("utf-8")
    require(len(data) <= MAX_ARTIFACT_BYTES, "canonical artifact exceeds the RAPP/1 1 MiB limit")
    return data


def parse(data: bytes, where="document") -> dict:
    require(isinstance(data, bytes) and len(data) <= MAX_ARTIFACT_BYTES, f"{where}: byte limit")
    value = R._strict_json(data)
    require(isinstance(value, dict), f"{where}: expected object")
    require(canonical(value) == data, f"{where}: noncanonical bytes")
    return value


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def particle(value: dict) -> str:
    canonical(value)
    return R.H("rapp/1:particle", value)


def now() -> str:
    value = datetime.now(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def timestamp(value: str) -> str:
    require(R.utc_valid(value), "expected a RAPP/1 UTC millisecond timestamp")
    return value


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(value: str) -> bytes:
    require(isinstance(value, str), "base64: expected string")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("invalid base64") from error
    require(b64(data) == value, "noncanonical base64")
    return data


def hex64(value, where="hash"):
    require(isinstance(value, str) and HEX.fullmatch(value), f"{where}: expected SHA-256")
    return value


def relative(value: str) -> str:
    require(isinstance(value, str) and 0 < len(value) <= 512, "invalid relative path")
    parts = value.split("/")
    require(not value.startswith("/") and all(part not in {"", ".", ".."} for part in parts),
            "unsafe relative path")
    require("\\" not in value and ":" not in value
            and all(32 <= ord(char) != 127 for char in value), "unsafe relative path characters")
    require(all(part.casefold() not in {".git", ".rapp-hive", ".hive-inventory.json"}
                and not part.endswith((".", " ")) for part in parts), "reserved control path")
    require(all(not re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
                for part in parts), "reserved device path")
    return value


def paths_disjoint(*paths: Path):
    resolved = [path.absolute() for path in paths]
    require(all(a != b and a not in b.parents and b not in a.parents
                for index, a in enumerate(resolved) for b in resolved[index + 1:]),
            "workspace, custody, publisher, channel and client locations must not overlap")


def no_symlinks(path: Path):
    path = path.absolute()
    require(".." not in path.parts, "parent traversal in filesystem location refused")
    for item in (*reversed(path.parents), path):
        require(not item.is_symlink(), "symlinked path refused")
    return path.resolve(strict=False)


def private_directory(path: Path, *, create=False) -> Path:
    require(os.name == "posix", "this deployment requires POSIX custody, flock and atomic filesystem semantics")
    path = no_symlinks(Path(path))
    if create and not path.exists():
        require(path.parent.is_dir(), "parent directory must already exist")
        with directory_fd(path.parent) as parent:
            try:
                os.mkdir(path.name, mode=0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
    require(path.is_dir(), "private directory is missing")
    with directory_fd(path) as descriptor:
        info = os.fstat(descriptor)
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
            "private directory must be owned by this user and mode 0700")
    return path


@contextmanager
def directory_fd(path: Path):
    path = no_symlinks(Path(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _read_at(parent: int, name: str, *, private=False, limit=MAX_ARTIFACT_BYTES):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "regular, non-hardlinked file required")
        if private:
            require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
                    "private file must be owned by this user and mode 0600")
        require(info.st_size <= limit, "file byte limit")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        require(len(data) <= limit, "file byte limit")
        return data
    finally:
        os.close(descriptor)


def read_file(path: Path, *, private=False, limit=MAX_ARTIFACT_BYTES) -> bytes:
    path = no_symlinks(Path(path))
    with directory_fd(path.parent) as parent:
        return _read_at(parent, path.name, private=private, limit=limit)


def sync_directory(path: Path):
    with directory_fd(path) as descriptor:
        os.fsync(descriptor)


def _recover_interrupted_immutable(parent: int, name: str, data: bytes) -> None:
    """Remove our sole orphaned staging link after an abrupt immutable put."""
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError:
        return
    try:
        info = os.fstat(descriptor)
        if not (stat.S_ISREG(info.st_mode) and info.st_nlink == 2
                and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600):
            return
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            current = stream.read(max(MAX_ARTIFACT_BYTES, len(data)) + 1)
        if current != data:
            return
        staging = []
        for candidate in os.listdir(parent):
            if not candidate.startswith(".write-"):
                continue
            try:
                candidate_info = os.stat(candidate, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if (
                stat.S_ISREG(candidate_info.st_mode)
                and candidate_info.st_dev == info.st_dev
                and candidate_info.st_ino == info.st_ino
            ):
                staging.append(candidate)
        if len(staging) == 1:
            os.unlink(staging[0], dir_fd=parent)
            os.fsync(parent)
    finally:
        os.close(descriptor)


def write_file(path: Path, data: bytes, *, immutable=False):
    path = no_symlinks(Path(path))
    require(path.parent.is_dir(), "write parent is missing")
    with directory_fd(path.parent) as parent:
        if immutable:
            _recover_interrupted_immutable(parent, path.name, data)
        try:
            previous = _read_at(parent, path.name, private=True, limit=max(MAX_ARTIFACT_BYTES, len(data)))
        except FileNotFoundError:
            previous = None
        if previous is not None and immutable:
            require(previous == data, "immutable write collision")
            return
        staging = ".write-" + uuid.uuid4().hex
        descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if immutable:
                try:
                    os.link(staging, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                except FileExistsError:
                    require(_read_at(parent, path.name, private=True, limit=max(MAX_ARTIFACT_BYTES, len(data))) == data,
                            "immutable write collision")
                os.unlink(staging, dir_fd=parent)
            else:
                os.replace(staging, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(staging, dir_fd=parent)
            except FileNotFoundError:
                pass


@contextmanager
def locked(path: Path):
    import fcntl
    no_symlinks(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600, "unsafe lock file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def preparation():
    spec = importlib.util.spec_from_file_location("private_hive_preparation", ROOT / "scripts" / "prepare_workspace.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifact_path(space: str, address: str) -> str:
    require(space in {"rapp/1:particle", "rapp/1:wave", "rapp/1:egg-manifest"}, "unsupported artifact space")
    return f"objects/{space.split(':')[1]}/{hex64(address)}.json"


def chain_path(address: str) -> str:
    return f"chains/{hex64(address)}.json"


def safe_path_set(paths):
    values = sorted(relative(path) for path in paths)
    folded = [unicodedata.normalize("NFC", path).casefold() for path in values]
    require(len(folded) == len(set(folded)), "case-colliding paths")
    occupied = set(folded)
    require(all(parent.as_posix() not in occupied
                for name in folded for parent in PurePosixPath(name).parents if parent.as_posix() != "."),
            "file/directory path collision")
    return values
