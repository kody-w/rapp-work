"""Move plans: relocate existing files inside one root, reviewably and reversibly.

Each move is one descriptor-relative, no-replace rename: Linux ``renameat2`` with
``RENAME_NOREPLACE`` or macOS ``renameatx_np`` with ``RENAME_EXCL``. A rename moves
exactly the file its source name holds at that instant and refuses an existing
destination, so no step of a move can make any file unreachable: the SDK never unlinks or
replaces a name of a file it moves. The source is verified through an open descriptor
before the rename and that same file must arrive at the destination; if another process
changed or replaced the source in between, the rename is undone the same way and the apply
refuses. A recovery marker bound to the exact plan makes an interrupted apply resumable;
any other state is refused. Where no no-replace rename exists, moves are refused.
"""

from __future__ import annotations

import ctypes
import errno
import functools
import hashlib
import os
import secrets
import stat
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ._json import canonical_bytes, closed_object, strict_json_loads
from ._paths import (
    MAX_FILE_BYTES,
    _nofollow_flags,
    absolute_path,
    assert_no_symlinks,
    directory_fd,
    file_sha256,
    path_identity,
    read_regular,
)
from .errors import Refusal, refuse, require
from .plans import (
    IDENTITY_NAME,
    INSTRUCTION_NAMES,
    KERNEL_NAMES,
    MAX_MOVES,
    ROOT_AUTHORITY_NAMES,
    FileMove,
    MovePlan,
    fold_path,
    require_disjoint_moves,
    require_movable_path,
)
from .workspace import (
    Organization,
    Workspace,
    _read_managed,
    _sdk_record,
    load_identity,
)

MOVE_RECOVERY_SCHEMA = "rapp-work-move-recovery/1"
MOVE_RECOVERY_NAME = "move-recovery.json"
MOVE_RECOVERY_PATH = ".rapp-work/" + MOVE_RECOVERY_NAME
MAX_MARKER_BYTES = 1024 * 1024
UPDATE_RECOVERY_PATH = ".rapp-work/update-recovery.json"
BOUNDARY_ENTRIES = ("rappid.json", ".git")
MAX_LISTED_ENTRIES = 100_000
NAMED_ANYWHERE = (IDENTITY_NAME, *INSTRUCTION_NAMES, *KERNEL_NAMES)
LINUX_RENAME_NOREPLACE = 1
DARWIN_RENAME_EXCL = 0x00000004
_COLLISION_ERRORS = {errno.EEXIST, errno.ENOTEMPTY}
_UNSUPPORTED_RENAME_ERRORS = {
    value
    for value in (
        errno.EINVAL,
        errno.ENOSYS,
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
    )
    if value is not None
}

Identity = tuple[int, int]


@dataclass
class _Progress:
    completed: int = 0
    # A rename happened whose result is neither verified nor undone.
    dirty: bool = False


@functools.cache
def _exclusive_rename() -> tuple[Any, int] | None:
    """The platform's descriptor-relative no-replace rename and its flag, or ``None``."""
    if sys.platform.startswith("linux"):
        name, flag = "renameat2", LINUX_RENAME_NOREPLACE
    elif sys.platform == "darwin":
        name, flag = "renameatx_np", DARWIN_RENAME_EXCL
    else:
        return None
    try:
        function = getattr(ctypes.CDLL(None, use_errno=True), name, None)
    except (OSError, TypeError):
        return None
    if function is None:
        return None
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    return function, flag


def _rename_exclusive(
    source_directory: int,
    source_name: str,
    destination_directory: int,
    destination_name: str,
) -> None:
    """Rename one entry between two directory descriptors; never replace, never follow links."""
    primitive = _exclusive_rename()
    if primitive is None:
        raise OSError(errno.ENOSYS, "a no-replace rename is unavailable")
    function, flag = primitive
    ctypes.set_errno(0)
    result = function(
        source_directory,
        os.fsencode(source_name),
        destination_directory,
        os.fsencode(destination_name),
        flag,
    )
    if result != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


def _require_move_platform() -> None:
    require(
        hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
        and os.unlink in os.supports_dir_fd
        and _exclusive_rename() is not None,
        "REFUSE_PLATFORM",
        "descriptor-relative no-replace renames are unavailable; moves are refused",
    )


def _present(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _split(path: str) -> tuple[str, str]:
    pure = PurePosixPath(path)
    return pure.parent.as_posix(), pure.name


def _subject(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": identity["kind"],
        "rappid": identity["rappid"],
        "world_id": identity["world_id"],
    }


def _load_root(root: Path) -> tuple[Path, dict[str, Any]]:
    _require_move_platform()
    root = assert_no_symlinks(absolute_path(root))
    identity = load_identity(root)
    require(
        identity["kind"] in {"workspace", "organization"},
        "REFUSE_KIND",
        "only Workspaces and pointer-only Organizations accept move plans",
    )
    return root, identity


def _integration(root: Path, identity: dict[str, Any]) -> tuple[set[str], tuple[str, ...]]:
    """Require a verified SDK integration; return the folded and exact SDK-owned paths."""
    managed, managed_sha256 = _read_managed(root)
    require(
        managed_sha256 is not None,
        "REFUSE_SDK_PROFILE",
        "moves require a qualified SDK integration; plan an ordinary update first",
    )
    sdk = strict_json_loads(read_regular(root / ".rapp-work/sdk.json"), where="SDK integration")
    require(
        sdk == _sdk_record(identity),
        "REFUSE_SDK_PROFILE",
        "SDK integration record differs from the qualified profile; plan and apply an ordinary "
        "update first (it may run while a move is pending)",
    )
    if identity["kind"] == "workspace":
        Workspace(root).verify()
    else:
        Organization(root).verify()
    paths = (*sorted(managed), ".rapp-work/managed.json")
    return {fold_path(path) for path in paths}, paths


def _marker_plan(raw: bytes) -> str | None:
    try:
        value = strict_json_loads(raw, where="recovery marker")
    except Refusal:
        return None
    if isinstance(value, dict) and isinstance(value.get("plan_sha256"), str):
        return str(value["plan_sha256"])
    return None


def _pending_plan(path: Path) -> str | None:
    try:
        return _marker_plan(read_regular(path))
    except Refusal:
        return None


def _require_no_pending(root: Path, *, move_marker: bool = True) -> None:
    require(
        not _present(root / UPDATE_RECOVERY_PATH),
        "REFUSE_RECOVERY_PENDING",
        "an interrupted SDK update must be resumed before moving files",
        path=UPDATE_RECOVERY_PATH,
    )
    if move_marker and _present(root / MOVE_RECOVERY_PATH):
        refuse(
            "REFUSE_RECOVERY_PENDING",
            "an interrupted move plan must be resumed before planning another",
            path=MOVE_RECOVERY_PATH,
            plan_sha256=_pending_plan(root / MOVE_RECOVERY_PATH),
        )


def _preconditions(root: Path) -> dict[str, Any]:
    return {
        "identity_sha256": file_sha256(root / "rappid.json"),
        "root_identity": path_identity(root),
    }


def _root_device(root: Path) -> int:
    return int(os.stat(root, follow_symlinks=False).st_dev)


def _lstat_at(directory: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "safe move inspection failed",
            {"errno": error.errno, "path": name},
        ) from error


def _stored(directory: int, name: str, *, path: str) -> bool:
    """Whether ``name`` is spelled exactly as one of the directory's entries.

    A case-, width-, or normalization-insensitive filesystem resolves other spellings of a
    stored name to it; a move names every existing entry by its stored spelling, so applying a
    plan and then its inverse restores every name exactly.
    """
    listed = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name == name:
                    return True
                listed += 1
                require(
                    listed < MAX_LISTED_ENTRIES,
                    "REFUSE_FILE_LIMIT",
                    "a move directory lists more than 100,000 entries",
                    path=path,
                )
    except OSError as error:
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "a move directory could not be listed",
            {"errno": error.errno, "path": path},
        ) from error
    return False


def _require_stored(directory: int, name: str, *, path: str) -> None:
    require(
        _stored(directory, name, path=path),
        "REFUSE_PATH_SPELLING",
        "move path spells an existing entry differently from its stored name",
        path=path,
        reason="stored-spelling",
    )


def _fsync(descriptor: int, *, path: str) -> None:
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "a move effect could not be made durable",
            {"errno": error.errno, "path": path},
        ) from error


@contextmanager
def _parent_fd(root: Path, parent: str, root_device: int) -> Iterator[int]:
    """Walk from the root without following links; refuse missing, foreign, or nested roots."""
    with directory_fd(root) as root_descriptor:
        descriptor = os.dup(root_descriptor)
        try:
            if parent != ".":
                for component in PurePosixPath(parent).parts:
                    info = _lstat_at(descriptor, component)
                    require(
                        info is not None,
                        "REFUSE_MOVE_PARENT",
                        "move parent directory is missing; moves never create directories",
                        path=parent,
                    )
                    assert info is not None
                    _require_stored(descriptor, component, path=parent)
                    require(
                        not stat.S_ISLNK(info.st_mode),
                        "REFUSE_SYMLINK",
                        "move parent traverses a symlink",
                        path=parent,
                    )
                    require(
                        stat.S_ISDIR(info.st_mode),
                        "REFUSE_MOVE_PARENT",
                        "move parent component is not a directory",
                        path=parent,
                    )
                    require(
                        info.st_dev == root_device,
                        "REFUSE_MOVE_CROSS_DEVICE",
                        "move parent is on another filesystem",
                        path=parent,
                    )
                    try:
                        child = os.open(
                            component,
                            _nofollow_flags(directory=True),
                            dir_fd=descriptor,
                        )
                    except OSError as error:
                        raise Refusal(
                            "REFUSE_PATH_UNSAFE",
                            "move parent could not be opened safely",
                            {"errno": error.errno, "path": parent},
                        ) from error
                    os.close(descriptor)
                    descriptor = child
                    opened = os.fstat(descriptor)
                    require(
                        (opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino),
                        "REFUSE_FILE_RACE",
                        "move parent changed while it was opened",
                        path=parent,
                    )
                    require(
                        all(_lstat_at(descriptor, name) is None for name in BOUNDARY_ENTRIES),
                        "REFUSE_MOVE_BOUNDARY",
                        "move path enters a nested identity or repository root",
                        path=parent,
                    )
            yield descriptor
        finally:
            os.close(descriptor)


def _hash_descriptor(descriptor: int, expected: os.stat_result, *, path: str) -> str:
    """SHA-256 of an open regular file that must stay the expected, unchanged file."""
    os.lseek(descriptor, 0, os.SEEK_SET)
    info = os.fstat(descriptor)
    require(
        stat.S_ISREG(info.st_mode)
        and (info.st_dev, info.st_ino) == (expected.st_dev, expected.st_ino)
        and 0 <= info.st_size <= MAX_FILE_BYTES,
        "REFUSE_FILE_RACE",
        "move file changed while it was inspected",
        path=path,
    )
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        require(
            total <= MAX_FILE_BYTES,
            "REFUSE_FILE_LIMIT",
            "move file exceeds the sixteen MiB limit",
            path=path,
        )
        digest.update(chunk)
    after = os.fstat(descriptor)
    require(
        total == info.st_size
        and (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "REFUSE_FILE_RACE",
        "move file changed while it was read",
        path=path,
    )
    return digest.hexdigest()


def _open_at(directory: int, name: str, *, code: str, path: str) -> int:
    try:
        return os.open(name, _nofollow_flags(nonblock=True), dir_fd=directory)
    except OSError as error:
        raise Refusal(
            code,
            "move file could not be opened safely",
            {"errno": error.errno, "path": path},
        ) from error


def _hash_at(directory: int, name: str, expected: os.stat_result) -> str:
    descriptor = _open_at(directory, name, code="REFUSE_PATH_UNSAFE", path=name)
    try:
        return _hash_descriptor(descriptor, expected, path=name)
    finally:
        os.close(descriptor)


def _named_identities(directory: int, *, at_root: bool) -> set[Identity]:
    """Identities of the protected names that exist in one directory."""
    found: set[Identity] = set()
    for name in NAMED_ANYWHERE + (ROOT_AUTHORITY_NAMES if at_root else ()):
        info = _lstat_at(directory, name)
        if info is not None:
            found.add((info.st_dev, info.st_ino))
    return found


def _protected_identities(root: Path, owned_paths: Iterable[str]) -> set[Identity]:
    """Identities of the root's authority files and every SDK-owned file."""
    with directory_fd(root) as root_directory:
        found = _named_identities(root_directory, at_root=True)
    for relative in owned_paths:
        pure = PurePosixPath(relative)
        try:
            with directory_fd(root / pure.parent) as parent:
                info = _lstat_at(parent, pure.name)
        except Refusal:
            continue
        if info is not None:
            found.add((info.st_dev, info.st_ino))
    return found


def _require_not_alias(info: os.stat_result, protected: set[Identity], *, path: str) -> None:
    require(
        (info.st_dev, info.st_ino) not in protected,
        "REFUSE_MOVE_PROTECTED",
        "move source is another name of a protected file",
        path=path,
        reason="protected-file-alias",
    )


def _require_movable(info: os.stat_result, *, path: str, root_device: int) -> None:
    require(
        not stat.S_ISLNK(info.st_mode),
        "REFUSE_SYMLINK",
        "move source is a symlink",
        path=path,
    )
    require(
        stat.S_ISREG(info.st_mode),
        "REFUSE_PATH_TYPE",
        "move source must be a regular file",
        path=path,
    )
    require(
        info.st_nlink == 1,
        "REFUSE_PATH_TYPE",
        "move source must be a regular, non-hardlinked file",
        path=path,
    )
    require(
        info.st_uid == os.geteuid(),
        "REFUSE_PERMISSIONS",
        "move source must be owned by the effective user",
        path=path,
    )
    require(
        stat.S_IMODE(info.st_mode) <= 0o777,
        "REFUSE_PERMISSIONS",
        "move source must not carry setuid, setgid, or sticky bits",
        path=path,
    )
    require(
        info.st_dev == root_device,
        "REFUSE_MOVE_CROSS_DEVICE",
        "move source is on another filesystem",
        path=path,
    )
    require(
        info.st_size <= MAX_FILE_BYTES,
        "REFUSE_FILE_LIMIT",
        "move source exceeds the sixteen MiB limit",
        path=path,
    )


def _requests(value: Any) -> list[tuple[str, str]]:
    require(
        isinstance(value, list) and 1 <= len(value) <= MAX_MOVES,
        "REFUSE_INPUT_SHAPE",
        "update moves must be an array of one to sixty-four moves",
    )
    pairs: list[tuple[str, str]] = []
    for raw in value:
        item = closed_object(raw, required={"destination", "source"}, where="update move")
        pairs.append((require_movable_path(item["source"]), require_movable_path(item["destination"])))
    pairs.sort()
    require_disjoint_moves(pairs)
    return pairs


def _require_unowned(path: str, owned: set[str]) -> None:
    require(
        fold_path(path) not in owned,
        "REFUSE_MOVE_PROTECTED",
        "move path names an SDK-owned file",
        path=path,
        reason="sdk-managed-file",
    )


def _inspect(
    root: Path,
    source: str,
    destination: str,
    *,
    owned: set[str],
    protected: set[Identity],
    root_device: int,
) -> FileMove:
    _require_unowned(source, owned)
    _require_unowned(destination, owned)
    source_parent, source_name = _split(source)
    destination_parent, destination_name = _split(destination)
    with _parent_fd(root, source_parent, root_device) as source_directory:
        info = _lstat_at(source_directory, source_name)
        require(info is not None, "REFUSE_MOVE_SOURCE", "move source is missing", path=source)
        assert info is not None
        _require_stored(source_directory, source_name, path=source)
        _require_movable(info, path=source, root_device=root_device)
        digest = _hash_at(source_directory, source_name, info)
        local = _named_identities(source_directory, at_root=source_parent == ".")
        _require_not_alias(info, protected | local, path=source)
    with _parent_fd(root, destination_parent, root_device) as destination_directory:
        require(
            _lstat_at(destination_directory, destination_name) is None,
            "REFUSE_MOVE_COLLISION",
            "move destination already exists; moves never replace",
            path=destination,
        )
    return FileMove(
        source=source,
        destination=destination,
        sha256=digest,
        size=int(info.st_size),
        mode=stat.S_IMODE(info.st_mode),
    )


def plan_moves(root: Path, moves: Any) -> MovePlan:
    """Plan moves read-only; every precondition is replayed again before the first write."""
    pairs = _requests(moves)
    root, identity = _load_root(root)
    owned, owned_paths = _integration(root, identity)
    _require_no_pending(root)
    root_device = _root_device(root)
    protected = _protected_identities(root, owned_paths)
    return MovePlan(
        target=str(root),
        subject=_subject(identity),
        preconditions=_preconditions(root),
        moves=tuple(
            _inspect(
                root,
                source,
                destination,
                owned=owned,
                protected=protected,
                root_device=root_device,
            )
            for source, destination in pairs
        ),
    )


def invert_move_plan(root: Path, plan: MovePlan) -> MovePlan:
    """Return the exact inverse plan without effects and without reading the moved files."""
    root, identity = _load_root(root)
    require(plan.target == str(root), "REFUSE_PLAN_TARGET", "move plan target differs from request")
    require(
        plan.subject == _subject(identity),
        "REFUSE_PLAN",
        "move plan subject differs from the workspace identity",
    )
    _require_no_pending(root)
    return plan.inverse()


def _recovery_bytes(plan: MovePlan) -> bytes:
    return canonical_bytes(
        {
            "plan": plan.to_dict(),
            "plan_sha256": plan.sha256,
            "schema": MOVE_RECOVERY_SCHEMA,
        }
    )


def _matches(info: os.stat_result, move: FileMove, root_device: int) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == move.mode
        and info.st_size == move.size
        and info.st_dev == root_device
    )


def _classify(
    source_directory: int,
    source_name: str,
    destination_directory: int,
    destination_name: str,
    move: FileMove,
    root_device: int,
) -> tuple[str, os.stat_result | None]:
    """Classify one move as pending, moved, or foreign (anything else).

    Pending needs the planned source metadata and no destination; its bytes are verified
    through the pinned descriptor just before the rename. Moved needs no source and the
    planned destination, bytes included.
    """
    source = _lstat_at(source_directory, source_name)
    destination = _lstat_at(destination_directory, destination_name)
    if (
        source is not None
        and destination is None
        and _matches(source, move, root_device)
        and _stored(source_directory, source_name, path=move.source)
    ):
        return "pending", source
    if (
        source is None
        and destination is not None
        and _matches(destination, move, root_device)
        and _stored(destination_directory, destination_name, path=move.destination)
        and _hash_at(destination_directory, destination_name, destination) == move.sha256
    ):
        return "moved", destination
    return "foreign", None


def _pin_source(
    source_directory: int,
    source_name: str,
    listed: os.stat_result,
    move: FileMove,
    *,
    root_device: int,
    code: str,
) -> int:
    """Open and verify the planned source; the open descriptor keeps its identity unique."""
    descriptor = _open_at(source_directory, source_name, code=code, path=move.source)
    try:
        info = os.fstat(descriptor)
        require(
            (info.st_dev, info.st_ino) == (listed.st_dev, listed.st_ino)
            and _matches(info, move, root_device),
            code,
            "move source changed before apply",
            source=move.source,
        )
        require(
            _hash_descriptor(descriptor, info, path=move.source) == move.sha256,
            code,
            "move source bytes differ from the plan",
            source=move.source,
        )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _flip(
    source_directory: int,
    source_name: str,
    destination_directory: int,
    destination_name: str,
    *,
    move: FileMove,
    recovering: bool,
) -> None:
    try:
        _rename_exclusive(source_directory, source_name, destination_directory, destination_name)
    except OSError as error:
        details = {"destination": move.destination, "errno": error.errno, "source": move.source}
        if error.errno in _COLLISION_ERRORS:
            raise Refusal(
                "REFUSE_MOVE_COLLISION",
                "move destination appeared before apply; moves never replace",
                details,
            ) from error
        if error.errno == errno.EXDEV:
            raise Refusal(
                "REFUSE_MOVE_CROSS_DEVICE",
                "move crosses a filesystem boundary",
                details,
            ) from error
        if error.errno in _UNSUPPORTED_RENAME_ERRORS:
            raise Refusal(
                "REFUSE_PLATFORM",
                "this filesystem cannot rename without replacing; moves are refused",
                details,
            ) from error
        if error.errno == errno.ENOENT:
            raise Refusal(
                "REFUSE_RECOVERY_STATE" if recovering else "REFUSE_PRECONDITION",
                "move source disappeared before apply",
                details,
            ) from error
        raise Refusal("REFUSE_PATH_UNSAFE", "move rename failed", details) from error


def _arrival_problem(
    arrived: os.stat_result | None,
    pin: int,
    pinned: os.stat_result,
    move: FileMove,
    destination_directory: int,
    destination_name: str,
    *,
    at_root: bool,
    root_device: int,
) -> str | None:
    """Why the file at the destination is not exactly the verified source, or ``None``."""
    if arrived is None:
        return "destination-missing"
    if (arrived.st_dev, arrived.st_ino) != (pinned.st_dev, pinned.st_ino):
        return "source-replaced"
    try:
        if not _stored(destination_directory, destination_name, path=move.destination):
            return "destination-spelling"
        current = os.fstat(pin)
        if not _matches(current, move, root_device) or (
            _hash_descriptor(pin, current, path=move.destination) != move.sha256
        ):
            return "source-changed"
        if (arrived.st_dev, arrived.st_ino) in _named_identities(
            destination_directory, at_root=at_root
        ):
            return "protected-name-alias"
    except (OSError, Refusal):
        return "verification-failed"
    return None


def _undo(
    destination_directory: int,
    destination_name: str,
    source_directory: int,
    source_name: str,
    arrived: os.stat_result,
) -> bool:
    """Rename the arrived file back, without replacing; true only when verified."""
    try:
        _rename_exclusive(destination_directory, destination_name, source_directory, source_name)
        os.fsync(source_directory)
        os.fsync(destination_directory)
        back = _lstat_at(source_directory, source_name)
    except (OSError, Refusal):
        return False
    return back is not None and (back.st_dev, back.st_ino) == (arrived.st_dev, arrived.st_ino)


def _apply_one(
    root: Path,
    move: FileMove,
    *,
    root_device: int,
    recovering: bool,
    protected: set[Identity],
    progress: _Progress,
) -> None:
    source_parent, source_name = _split(move.source)
    destination_parent, destination_name = _split(move.destination)
    with (
        _parent_fd(root, source_parent, root_device) as source_directory,
        _parent_fd(root, destination_parent, root_device) as destination_directory,
    ):
        state, listed = _classify(
            source_directory,
            source_name,
            destination_directory,
            destination_name,
            move,
            root_device,
        )
        if not recovering:
            require(
                state == "pending",
                "REFUSE_PRECONDITION",
                "move source or destination changed before apply",
                destination=move.destination,
                source=move.source,
            )
        require(
            state != "foreign",
            "REFUSE_RECOVERY_STATE",
            "interrupted move is in an unrecognized state; it is left for the owner",
            destination=move.destination,
            source=move.source,
        )
        if state == "moved":
            return
        assert listed is not None
        pin = _pin_source(
            source_directory,
            source_name,
            listed,
            move,
            root_device=root_device,
            code="REFUSE_RECOVERY_STATE" if recovering else "REFUSE_PRECONDITION",
        )
        try:
            pinned = os.fstat(pin)
            local = _named_identities(source_directory, at_root=source_parent == ".")
            _require_not_alias(pinned, protected | local, path=move.source)
            _flip(
                source_directory,
                source_name,
                destination_directory,
                destination_name,
                move=move,
                recovering=recovering,
            )
            progress.dirty = True
            _fsync(destination_directory, path=move.destination)
            _fsync(source_directory, path=move.source)
            arrived = _lstat_at(destination_directory, destination_name)
            problem = _arrival_problem(
                arrived,
                pin,
                pinned,
                move,
                destination_directory,
                destination_name,
                at_root=destination_parent == ".",
                root_device=root_device,
            )
            if problem is None:
                progress.dirty = False
                return
            undone = arrived is not None and _undo(
                destination_directory,
                destination_name,
                source_directory,
                source_name,
                arrived,
            )
            if undone:
                progress.dirty = False
            outcome = "the move was undone" if undone else "every name is left for the owner"
            details = {
                "destination": move.destination,
                "reason": problem,
                "source": move.source,
                "undone": undone,
            }
            if problem == "protected-name-alias":
                raise Refusal(
                    "REFUSE_MOVE_PROTECTED",
                    "move destination is another name of a protected file; " + outcome,
                    details,
                )
            if problem == "destination-spelling":
                raise Refusal(
                    "REFUSE_PATH_SPELLING",
                    "the filesystem stores the destination under another spelling; " + outcome,
                    details,
                )
            raise Refusal(
                "REFUSE_FILE_RACE",
                "the source changed while it was moved; " + outcome,
                details,
            )
        finally:
            os.close(pin)


def _all_moved(root: Path, plan: MovePlan, root_device: int) -> bool:
    for move in plan.moves:
        source_parent, source_name = _split(move.source)
        destination_parent, destination_name = _split(move.destination)
        try:
            with (
                _parent_fd(root, source_parent, root_device) as source_directory,
                _parent_fd(root, destination_parent, root_device) as destination_directory,
            ):
                state, _ = _classify(
                    source_directory,
                    source_name,
                    destination_directory,
                    destination_name,
                    move,
                    root_device,
                )
        except Refusal:
            return False
        if state != "moved":
            return False
    return True


def _read_locked(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = MAX_MARKER_BYTES + 1
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _flock(descriptor: int, *, blocking: bool) -> None:
    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise Refusal(
            "REFUSE_RECOVERY_BUSY",
            "another apply holds this move recovery; nothing was changed",
            {"path": MOVE_RECOVERY_PATH},
        ) from error
    except OSError as error:
        raise Refusal(
            "REFUSE_PLATFORM",
            "advisory locking of the move recovery marker is unavailable",
            {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
        ) from error


def _same_entry(directory: int, name: str, descriptor: int) -> bool:
    """Whether ``name`` still names the open file (a file with no name has no links)."""
    try:
        entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError:
        return False
    return opened.st_nlink >= 1 and (entry.st_dev, entry.st_ino) == (opened.st_dev, opened.st_ino)


def _discard_own(directory: int, name: str, descriptor: int) -> None:
    """Remove a marker or temporary file this apply created while the name is still it."""
    try:
        if _same_entry(directory, name, descriptor):
            os.unlink(name, dir_fd=directory)
            os.fsync(directory)
    except OSError:
        pass


def _create_locked_marker(marker_directory: int, data: bytes) -> int:
    """Write the marker under a private name, lock it, then rename it into place.

    The marker appears complete and already locked or not at all, and never replaces a
    marker another apply placed first.
    """
    temporary = f".move-recovery-{secrets.token_hex(16)}.tmp"
    try:
        descriptor = os.open(
            temporary,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=marker_directory,
        )
    except OSError as error:
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "move recovery marker could not be created; nothing was moved",
            {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
        ) from error
    placed = False
    try:
        _flock(descriptor, blocking=False)
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(data)
            while view:
                view = view[os.write(descriptor, view) :]
            os.fsync(descriptor)
        except OSError as error:
            raise Refusal(
                "REFUSE_PATH_UNSAFE",
                "move recovery marker could not be written; nothing was moved",
                {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
            ) from error
        try:
            _rename_exclusive(marker_directory, temporary, marker_directory, MOVE_RECOVERY_NAME)
        except OSError as error:
            if error.errno in _COLLISION_ERRORS:
                raise Refusal(
                    "REFUSE_RECOVERY_PENDING",
                    "another move apply created a recovery marker first",
                    {"path": MOVE_RECOVERY_PATH},
                ) from error
            if error.errno in _UNSUPPORTED_RENAME_ERRORS:
                raise Refusal(
                    "REFUSE_PLATFORM",
                    "this filesystem cannot rename without replacing; moves are refused",
                    {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
                ) from error
            raise Refusal(
                "REFUSE_PATH_UNSAFE",
                "move recovery marker could not be placed; nothing was moved",
                {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
            ) from error
        placed = True
        _fsync(marker_directory, path=MOVE_RECOVERY_PATH)
        require(
            _same_entry(marker_directory, MOVE_RECOVERY_NAME, descriptor),
            "REFUSE_RECOVERY_BINDING",
            "move recovery marker changed while it was created; nothing was moved",
            path=MOVE_RECOVERY_PATH,
        )
    except BaseException:
        _discard_own(marker_directory, MOVE_RECOVERY_NAME if placed else temporary, descriptor)
        os.close(descriptor)
        raise
    return descriptor


def _lock_existing_marker(marker_directory: int, expected: bytes) -> int:
    """Lock a pending marker without waiting, then prove it is still the named marker."""
    try:
        descriptor = os.open(
            MOVE_RECOVERY_NAME,
            _nofollow_flags(nonblock=True),
            dir_fd=marker_directory,
        )
    except OSError as error:
        raise Refusal(
            "REFUSE_RECOVERY_BINDING",
            "move recovery marker cannot be opened safely",
            {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
        ) from error
    try:
        info = os.fstat(descriptor)
        require(
            stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            "REFUSE_PATH_TYPE",
            "move recovery marker must be a regular, non-hardlinked file",
            path=MOVE_RECOVERY_PATH,
        )
        _flock(descriptor, blocking=False)
        require(
            _same_entry(marker_directory, MOVE_RECOVERY_NAME, descriptor),
            "REFUSE_RECOVERY_BUSY",
            "the move recovery marker was finished or replaced before its lock was taken; "
            "nothing was changed",
            path=MOVE_RECOVERY_PATH,
        )
        current = _read_locked(descriptor)
        require(
            current == expected,
            "REFUSE_RECOVERY_BINDING",
            "move recovery belongs to another plan",
            plan_sha256=_marker_plan(current),
        )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _remove_marker(marker_directory: int, descriptor: int, expected: bytes) -> None:
    require(
        _read_locked(descriptor) == expected
        and _same_entry(marker_directory, MOVE_RECOVERY_NAME, descriptor),
        "REFUSE_RECOVERY_BINDING",
        "move recovery marker changed during apply",
        path=MOVE_RECOVERY_PATH,
    )
    try:
        os.unlink(MOVE_RECOVERY_NAME, dir_fd=marker_directory)
    except OSError as error:
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "move recovery marker could not be removed",
            {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
        ) from error
    _fsync(marker_directory, path=MOVE_RECOVERY_PATH)


def _marker_present(marker_directory: int) -> bool:
    return _lstat_at(marker_directory, MOVE_RECOVERY_NAME) is not None


def apply_move_plan(plan: MovePlan, *, root: Path, plan_sha256: str) -> dict[str, Any]:
    require(
        isinstance(plan_sha256, str) and plan.sha256 == plan_sha256,
        "REFUSE_PLAN_HASH",
        "exact canonical plan SHA-256 is required",
        actual=plan.sha256,
        supplied=plan_sha256,
    )
    root, identity = _load_root(root)
    require(plan.target == str(root), "REFUSE_PLAN_TARGET", "move plan target differs from request")
    require(
        plan.subject == _subject(identity),
        "REFUSE_PLAN",
        "move plan subject differs from the workspace identity",
    )
    owned, owned_paths = _integration(root, identity)
    _require_no_pending(root, move_marker=False)
    require(
        plan.preconditions == _preconditions(root),
        "REFUSE_PRECONDITION",
        "workspace identity or root changed after the move plan was built",
    )
    root_device = _root_device(root)
    protected = _protected_identities(root, owned_paths)
    marker_bytes = _recovery_bytes(plan)
    with directory_fd(root / ".rapp-work") as marker_directory:
        recovering = _marker_present(marker_directory)
        if recovering:
            for move in plan.moves:
                _require_unowned(move.source, owned)
                _require_unowned(move.destination, owned)
            lock = _lock_existing_marker(marker_directory, marker_bytes)
        else:
            if _all_moved(root, plan, root_device):
                refuse(
                    "REFUSE_PLAN_APPLIED",
                    "move plan postconditions already hold; nothing was changed",
                    plan_sha256=plan.sha256,
                )
            current = plan_moves(
                root,
                [{"destination": move.destination, "source": move.source} for move in plan.moves],
            )
            require(
                current.to_dict() == plan.to_dict(),
                "REFUSE_PRECONDITION",
                "workspace changed after the move plan was built",
            )
            lock = _create_locked_marker(marker_directory, marker_bytes)
        progress = _Progress()
        try:
            try:
                for move in plan.moves:
                    _apply_one(
                        root,
                        move,
                        root_device=root_device,
                        recovering=recovering,
                        protected=protected,
                        progress=progress,
                    )
                    progress.completed += 1
            except Refusal as error:
                kept = recovering or progress.completed > 0 or progress.dirty
                if not kept:
                    _remove_marker(marker_directory, lock, marker_bytes)
                raise Refusal(
                    error.code,
                    error.message,
                    {
                        **(error.details or {}),
                        "completed_moves": progress.completed,
                        "recovery": "pending" if kept else "none",
                    },
                ) from error
            _remove_marker(marker_directory, lock, marker_bytes)
        finally:
            os.close(lock)
    verification = (
        Workspace(root).verify() if identity["kind"] == "workspace" else Organization(root).verify()
    )
    return {
        "effects": True,
        "moves": len(plan.moves),
        "plan_sha256": plan.sha256,
        "recovered": recovering,
        "root": str(root),
        "status": "moved",
        "verification": verification,
    }
