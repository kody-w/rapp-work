"""Move plans: relocate existing files inside one root, reviewably and reversibly.

A move creates the destination as a second hard link to the verified source with a
descriptor-relative, no-follow, no-replace ``link``, makes it durable, verifies both
names are one file with the planned bytes, and only then removes the source name. The
file therefore always has at least one verified name. A recovery marker bound to the
exact plan makes an interrupted apply resumable; any other state is refused.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from collections.abc import Iterator
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
    MAX_MOVES,
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
    _unlink_regular,
    load_identity,
)

MOVE_RECOVERY_SCHEMA = "rapp-work-move-recovery/1"
MOVE_RECOVERY_NAME = "move-recovery.json"
MOVE_RECOVERY_PATH = ".rapp-work/" + MOVE_RECOVERY_NAME
MAX_MARKER_BYTES = 1024 * 1024
UPDATE_RECOVERY_PATH = ".rapp-work/update-recovery.json"
BOUNDARY_ENTRIES = ("rappid.json", ".git")
_NO_HARDLINK_ERRORS = {
    value
    for value in (
        errno.EPERM,
        errno.EMLINK,
        errno.ENOSYS,
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
    )
    if value is not None
}


@dataclass
class _Progress:
    effects: bool = False
    completed: int = 0


def _require_move_platform() -> None:
    require(
        hasattr(os, "O_NOFOLLOW")
        and os.link in os.supports_dir_fd
        and os.link in os.supports_follow_symlinks
        and os.unlink in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks,
        "REFUSE_PLATFORM",
        "descriptor-relative no-follow hard links are unavailable; moves are refused",
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


def _integration(root: Path, identity: dict[str, Any]) -> tuple[set[str], str]:
    """Require a verified SDK integration; return the folded SDK-owned paths and inventory hash."""
    managed, managed_sha256 = _read_managed(root)
    require(
        managed_sha256 is not None,
        "REFUSE_SDK_PROFILE",
        "moves require a qualified SDK integration; plan an ordinary update first",
    )
    assert managed_sha256 is not None
    sdk = strict_json_loads(read_regular(root / ".rapp-work/sdk.json"), where="SDK integration")
    require(
        sdk == _sdk_record(identity),
        "REFUSE_SDK_PROFILE",
        "SDK integration record differs from the qualified profile; plan an ordinary update first",
    )
    if identity["kind"] == "workspace":
        Workspace(root).verify()
    else:
        Organization(root).verify()
    owned = {fold_path(path) for path in managed} | {fold_path(".rapp-work/managed.json")}
    return owned, managed_sha256


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


def _preconditions(root: Path, managed_sha256: str) -> dict[str, Any]:
    return {
        "identity_sha256": file_sha256(root / "rappid.json"),
        "managed_sha256": managed_sha256,
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


def _hash_at(directory: int, name: str, expected: os.stat_result) -> str:
    try:
        descriptor = os.open(name, _nofollow_flags(nonblock=True), dir_fd=directory)
    except OSError as error:
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "move file could not be opened safely",
            {"errno": error.errno, "path": name},
        ) from error
    try:
        info = os.fstat(descriptor)
        require(
            stat.S_ISREG(info.st_mode)
            and (info.st_dev, info.st_ino) == (expected.st_dev, expected.st_ino)
            and 0 <= info.st_size <= MAX_FILE_BYTES,
            "REFUSE_FILE_RACE",
            "move file changed while it was inspected",
            path=name,
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
                path=name,
            )
            digest.update(chunk)
        after = os.fstat(descriptor)
        require(
            total == info.st_size
            and (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "REFUSE_FILE_RACE",
            "move file changed while it was read",
            path=name,
        )
        return digest.hexdigest()
    finally:
        os.close(descriptor)


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
        _require_movable(info, path=source, root_device=root_device)
        digest = _hash_at(source_directory, source_name, info)
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
    owned, managed_sha256 = _integration(root, identity)
    _require_no_pending(root)
    root_device = _root_device(root)
    return MovePlan(
        target=str(root),
        subject=_subject(identity),
        preconditions=_preconditions(root, managed_sha256),
        moves=tuple(
            _inspect(root, source, destination, owned=owned, root_device=root_device)
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
    return plan.inverse()


def _recovery_bytes(plan: MovePlan) -> bytes:
    return canonical_bytes(
        {
            "plan": plan.to_dict(),
            "plan_sha256": plan.sha256,
            "schema": MOVE_RECOVERY_SCHEMA,
        }
    )


def _matches(info: os.stat_result, move: FileMove, *, links: int, root_device: int) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == links
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == move.mode
        and info.st_size == move.size
        and info.st_dev == root_device
    )


def _state(
    source_directory: int,
    source_name: str,
    destination_directory: int,
    destination_name: str,
    move: FileMove,
    root_device: int,
) -> tuple[str, tuple[int, int] | None]:
    """Classify one move as pending, linked, moved, or foreign (anything else)."""
    source = _lstat_at(source_directory, source_name)
    destination = _lstat_at(destination_directory, destination_name)
    if source is not None and destination is None:
        if _matches(source, move, links=1, root_device=root_device) and (
            _hash_at(source_directory, source_name, source) == move.sha256
        ):
            return "pending", (source.st_dev, source.st_ino)
    elif source is not None and destination is not None:
        if (
            (source.st_dev, source.st_ino) == (destination.st_dev, destination.st_ino)
            and _matches(destination, move, links=2, root_device=root_device)
            and _hash_at(destination_directory, destination_name, destination) == move.sha256
        ):
            return "linked", (destination.st_dev, destination.st_ino)
    elif destination is not None:
        if _matches(destination, move, links=1, root_device=root_device) and (
            _hash_at(destination_directory, destination_name, destination) == move.sha256
        ):
            return "moved", (destination.st_dev, destination.st_ino)
    return "foreign", None


def _hardlink(
    source_directory: int,
    source_name: str,
    destination_directory: int,
    destination_name: str,
) -> None:
    os.link(
        source_name,
        destination_name,
        src_dir_fd=source_directory,
        dst_dir_fd=destination_directory,
        follow_symlinks=False,
    )


def _link_destination(
    source_directory: int,
    source_name: str,
    destination_directory: int,
    destination_name: str,
    *,
    path: str,
    progress: _Progress,
) -> None:
    try:
        _hardlink(source_directory, source_name, destination_directory, destination_name)
    except FileExistsError as error:
        raise Refusal(
            "REFUSE_MOVE_COLLISION",
            "move destination appeared before apply; moves never replace",
            {"path": path},
        ) from error
    except OSError as error:
        if error.errno == errno.EXDEV:
            raise Refusal(
                "REFUSE_MOVE_CROSS_DEVICE",
                "move crosses a filesystem boundary; atomicity would be lost",
                {"path": path},
            ) from error
        if error.errno in _NO_HARDLINK_ERRORS:
            raise Refusal(
                "REFUSE_PLATFORM",
                "this filesystem cannot create the no-replace hard link a move requires",
                {"errno": error.errno, "path": path},
            ) from error
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "move link failed",
            {"errno": error.errno, "path": path},
        ) from error
    progress.effects = True
    os.fsync(destination_directory)


def _unlink_source(source_directory: int, source_name: str, *, path: str) -> None:
    try:
        os.unlink(source_name, dir_fd=source_directory)
    except OSError as error:
        raise Refusal(
            "REFUSE_PATH_UNSAFE",
            "move source name could not be removed; both names are left in place",
            {"errno": error.errno, "path": path},
        ) from error
    os.fsync(source_directory)


def _apply_one(
    root: Path,
    move: FileMove,
    *,
    root_device: int,
    recovering: bool,
    progress: _Progress,
) -> None:
    source_parent, source_name = _split(move.source)
    destination_parent, destination_name = _split(move.destination)
    with (
        _parent_fd(root, source_parent, root_device) as source_directory,
        _parent_fd(root, destination_parent, root_device) as destination_directory,
    ):
        names = (source_directory, source_name, destination_directory, destination_name)
        state, identity = _state(*names, move, root_device)
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
        if state == "pending":
            _link_destination(
                source_directory,
                source_name,
                destination_directory,
                destination_name,
                path=move.destination,
                progress=progress,
            )
            state, linked = _state(*names, move, root_device)
            require(
                state == "linked" and linked == identity,
                "REFUSE_WRITE_VERIFY",
                "move link verification failed; both names are left in place",
                destination=move.destination,
                source=move.source,
            )
        if state == "linked":
            _unlink_source(source_directory, source_name, path=move.source)
            progress.effects = True
        state, moved = _state(*names, move, root_device)
        require(
            state == "moved" and moved == identity,
            "REFUSE_WRITE_VERIFY",
            "move verification failed",
            destination=move.destination,
            source=move.source,
        )


def _all_moved(root: Path, plan: MovePlan, root_device: int) -> bool:
    for move in plan.moves:
        source_parent, source_name = _split(move.source)
        destination_parent, destination_name = _split(move.destination)
        try:
            with (
                _parent_fd(root, source_parent, root_device) as source_directory,
                _parent_fd(root, destination_parent, root_device) as destination_directory,
            ):
                state, _ = _state(
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


def _create_locked_marker(root: Path, data: bytes) -> int:
    """Create the marker create-only and hold an exclusive lock on it for the whole apply."""
    with directory_fd(root / ".rapp-work") as parent:
        try:
            descriptor = os.open(
                MOVE_RECOVERY_NAME,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
        except FileExistsError as error:
            raise Refusal(
                "REFUSE_RECOVERY_PENDING",
                "another move apply created a recovery marker first",
                {"path": MOVE_RECOVERY_PATH},
            ) from error
        try:
            _flock(descriptor, blocking=True)
            try:
                os.fchmod(descriptor, 0o600)
                view = memoryview(data)
                while view:
                    view = view[os.write(descriptor, view) :]
                os.fsync(descriptor)
                os.fsync(parent)
            except OSError as error:
                raise Refusal(
                    "REFUSE_PATH_UNSAFE",
                    "move recovery marker could not be written; nothing was moved",
                    {"errno": error.errno, "path": MOVE_RECOVERY_PATH},
                ) from error
        except Exception:
            _discard_created_marker(parent, descriptor)
            os.close(descriptor)
            raise
        except BaseException:
            os.close(descriptor)
            raise
    return descriptor


def _discard_created_marker(parent: int, descriptor: int) -> None:
    """Remove a marker this apply just created when writing it failed; nothing has moved."""
    try:
        created = os.fstat(descriptor)
        entry = os.stat(MOVE_RECOVERY_NAME, dir_fd=parent, follow_symlinks=False)
        if (entry.st_dev, entry.st_ino) == (created.st_dev, created.st_ino):
            os.unlink(MOVE_RECOVERY_NAME, dir_fd=parent)
            os.fsync(parent)
    except OSError:
        pass


def _lock_existing_marker(root: Path, expected: bytes) -> int:
    """Lock a pending marker without waiting; refuse if another apply holds it."""
    with directory_fd(root / ".rapp-work") as parent:
        try:
            descriptor = os.open(
                MOVE_RECOVERY_NAME,
                _nofollow_flags(nonblock=True),
                dir_fd=parent,
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


def _remove_marker(marker: Path, expected: bytes) -> None:
    require(
        read_regular(marker) == expected,
        "REFUSE_RECOVERY_BINDING",
        "move recovery marker changed during apply",
    )
    _unlink_regular(marker)


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
    owned, managed_sha256 = _integration(root, identity)
    _require_no_pending(root, move_marker=False)
    require(
        plan.preconditions == _preconditions(root, managed_sha256),
        "REFUSE_PRECONDITION",
        "workspace identity, inventory, or root changed after the move plan was built",
    )
    root_device = _root_device(root)
    marker = root / MOVE_RECOVERY_PATH
    marker_bytes = _recovery_bytes(plan)
    recovering = _present(marker)
    if recovering:
        for move in plan.moves:
            _require_unowned(move.source, owned)
            _require_unowned(move.destination, owned)
        lock = _lock_existing_marker(root, marker_bytes)
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
        lock = _create_locked_marker(root, marker_bytes)
    progress = _Progress()
    try:
        try:
            for move in plan.moves:
                _apply_one(
                    root,
                    move,
                    root_device=root_device,
                    recovering=recovering,
                    progress=progress,
                )
                progress.completed += 1
        except Refusal as error:
            kept = recovering or progress.effects
            if not kept:
                _remove_marker(marker, marker_bytes)
            raise Refusal(
                error.code,
                error.message,
                {
                    **(error.details or {}),
                    "completed_moves": progress.completed,
                    "recovery": "pending" if kept else "none",
                },
            ) from error
        _remove_marker(marker, marker_bytes)
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
