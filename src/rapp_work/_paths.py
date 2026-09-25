from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import secrets
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .errors import Refusal, require

MAX_FILE_BYTES = 16 * 1024 * 1024


def absolute_path(value: str | os.PathLike[str]) -> Path:
    raw = os.fspath(value)
    require("\x00" not in raw, "REFUSE_PATH", "filesystem path contains NUL")
    path = Path(os.path.abspath(os.path.expanduser(raw)))
    require(".." not in path.parts, "REFUSE_PATH", "parent traversal is forbidden")
    return path


def safe_relative(value: str) -> str:
    require(
        isinstance(value, str) and 0 < len(value) <= 512,
        "REFUSE_PATH",
        "relative path must contain 1 to 512 characters",
    )
    path = PurePosixPath(value)
    require(
        not path.is_absolute()
        and "\\" not in value
        and ":" not in value
        and all(part not in {"", ".", ".."} for part in path.parts),
        "REFUSE_PATH",
        "relative path is unsafe",
        path=value,
    )
    require(
        all(32 <= ord(character) != 127 for character in value),
        "REFUSE_PATH",
        "relative path contains a control character",
        path=value,
    )
    return value


def _nofollow_flags(*, directory: bool = False, nonblock: bool = False) -> int:
    require(
        hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd,
        "REFUSE_PLATFORM",
        "safe descriptor-relative no-follow filesystem operations are unavailable",
    )
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    if nonblock:
        flags |= getattr(os, "O_NONBLOCK", 0)
    return flags


@contextmanager
def directory_fd(path: Path) -> Iterator[int]:
    path = absolute_path(path)
    flags = _nofollow_flags(directory=True)
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        require(stat.S_ISDIR(info.st_mode), "REFUSE_PATH_TYPE", "directory required")
        yield descriptor
    except OSError as error:
        raise Refusal("REFUSE_PATH_UNSAFE", "unsafe or missing directory path", {"path": str(path)}) from error
    finally:
        os.close(descriptor)


def assert_no_symlinks(path: Path, *, allow_missing_leaf: bool = False) -> Path:
    path = absolute_path(path)
    cursor = Path(path.anchor)
    for index, component in enumerate(path.parts[1:]):
        cursor /= component
        try:
            info = os.lstat(cursor)
        except FileNotFoundError:
            if allow_missing_leaf and index == len(path.parts[1:]) - 1:
                return path
            raise Refusal(
                "REFUSE_PATH_MISSING",
                "filesystem path is missing",
                {"path": str(cursor)},
            ) from None
        require(
            not stat.S_ISLNK(info.st_mode),
            "REFUSE_SYMLINK",
            "symlink traversal is forbidden",
            path=str(cursor),
        )
    return path


def read_regular_at(
    parent: int,
    name: str,
    *,
    display: str,
    limit: int = MAX_FILE_BYTES,
    require_private: bool = False,
) -> bytes:
    """Read one regular, single-link file relative to an open directory, never following links."""
    descriptor = os.open(
        name,
        _nofollow_flags(nonblock=True),
        dir_fd=parent,
    )
    try:
        info = os.fstat(descriptor)
        require(
            stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            "REFUSE_PATH_TYPE",
            "regular, non-hardlinked file required",
            path=display,
        )
        if require_private and os.name != "nt":
            require(
                info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
                "REFUSE_PERMISSIONS",
                "private file must be owner-only mode 0600",
                path=display,
            )
        require(
            0 <= info.st_size <= limit,
            "REFUSE_FILE_LIMIT",
            "file exceeds the allowed byte limit",
            path=display,
            limit=limit,
        )
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        require(
            len(data) <= limit,
            "REFUSE_FILE_LIMIT",
            "file exceeds the allowed byte limit",
            path=display,
            limit=limit,
        )
        after = os.fstat(descriptor)
        require(
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "REFUSE_FILE_RACE",
            "file changed while it was being read",
            path=display,
        )
        return data
    finally:
        os.close(descriptor)


def read_regular(
    path: Path,
    *,
    limit: int = MAX_FILE_BYTES,
    require_private: bool = False,
) -> bytes:
    path = absolute_path(path)
    try:
        with directory_fd(path.parent) as parent:
            return read_regular_at(
                parent,
                path.name,
                display=str(path),
                limit=limit,
                require_private=require_private,
            )
    except Refusal:
        raise
    except OSError as error:
        raise Refusal("REFUSE_PATH_UNSAFE", "safe file read failed", {"path": str(path)}) from error


def file_sha256(path: Path, *, limit: int = MAX_FILE_BYTES) -> str:
    return hashlib.sha256(read_regular(path, limit=limit)).hexdigest()


def private_directory(path: Path, *, create: bool = False) -> Path:
    path = absolute_path(path)
    if create and not path.exists():
        with directory_fd(path.parent) as parent:
            try:
                os.mkdir(path.name, 0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
    assert_no_symlinks(path)
    with directory_fd(path) as descriptor:
        info = os.fstat(descriptor)
    if os.name != "nt":
        require(
            info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
            "REFUSE_PERMISSIONS",
            "private directory must be owner-only mode 0700",
            path=str(path),
        )
    return path


def create_directories(root: Path, relative: str, *, mode: int = 0o700) -> Path:
    relative = safe_relative(relative)
    root = private_directory(root)
    cursor = root
    for component in PurePosixPath(relative).parts:
        with directory_fd(cursor) as parent:
            try:
                os.mkdir(component, mode, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                child = os.stat(component, dir_fd=parent, follow_symlinks=False)
                require(
                    stat.S_ISDIR(child.st_mode),
                    "REFUSE_PATH_TYPE",
                    "directory component collides with a non-directory",
                    path=str(cursor / component),
                )
        cursor /= component
    return cursor


def write_new(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    path = absolute_path(path)
    require(isinstance(data, bytes), "REFUSE_BYTES", "write payload must be bytes")
    with directory_fd(path.parent) as parent:
        try:
            descriptor = os.open(
                path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode,
                dir_fd=parent,
            )
        except FileExistsError as error:
            raise Refusal(
                "REFUSE_CREATE_COLLISION",
                "create-only write target already exists",
                {"path": str(path)},
            ) from error
        try:
            if os.name != "nt":
                os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent)


def replace_owned(path: Path, data: bytes, *, expected_sha256: str, mode: int = 0o600) -> None:
    path = absolute_path(path)
    current = read_regular(path)
    require(
        hashlib.sha256(current).hexdigest() == expected_sha256,
        "REFUSE_PRECONDITION",
        "managed file changed since the plan was built",
        path=str(path),
    )
    staging_name = f".{path.name}.rapp-work-{secrets.token_hex(12)}"
    with directory_fd(path.parent) as parent:
        descriptor = os.open(
            staging_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=parent,
        )
        try:
            if os.name != "nt":
                os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(descriptor)
            require(
                hashlib.sha256(read_regular(path)).hexdigest() == expected_sha256,
                "REFUSE_PRECONDITION",
                "managed file changed before replacement",
                path=str(path),
            )
            os.replace(staging_name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(staging_name, dir_fd=parent)
            except FileNotFoundError:
                pass
            os.close(descriptor)


def path_identity(path: Path) -> dict[str, int]:
    path = assert_no_symlinks(path)
    info = os.stat(path, follow_symlinks=False)
    return {
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mode": int(stat.S_IMODE(info.st_mode)),
    }


def fsync_directory(path: Path) -> None:
    with directory_fd(path) as descriptor:
        os.fsync(descriptor)


def _raise_noreplace_error(error_number: int, target: Path) -> None:
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise Refusal(
            "REFUSE_CREATE_COLLISION",
            "create-only directory activation target already exists",
            {"path": str(target)},
        )
    unsupported = {errno.EINVAL, errno.ENOSYS}
    for name in ("ENOTSUP", "EOPNOTSUPP"):
        value = getattr(errno, name, None)
        if value is not None:
            unsupported.add(value)
    if error_number in unsupported:
        raise Refusal(
            "REFUSE_PLATFORM",
            "atomic no-replace directory activation is unavailable",
            {"path": str(target)},
        )
    raise Refusal(
        "REFUSE_PATH_UNSAFE",
        "atomic no-replace directory activation failed",
        {"errno": error_number, "path": str(target)},
    )


def _rename_noreplace(parent: int, source_name: str, target_name: str, target: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_raw = os.fsencode(source_name)
    target_raw = os.fsencode(target_name)
    if sys.platform.startswith("linux"):
        function = getattr(libc, "renameat2", None)
        require(
            function is not None,
            "REFUSE_PLATFORM",
            "Linux renameat2(RENAME_NOREPLACE) is unavailable",
        )
        assert function is not None
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        ctypes.set_errno(0)
        result = function(parent, source_raw, parent, target_raw, 1)
    elif sys.platform == "darwin":
        function = getattr(libc, "renameatx_np", None)
        if function is not None:
            function.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            function.restype = ctypes.c_int
            ctypes.set_errno(0)
            result = function(parent, source_raw, parent, target_raw, 0x00000004)
        else:
            path_function = getattr(libc, "renamex_np", None)
            require(
                path_function is not None,
                "REFUSE_PLATFORM",
                "macOS renamex_np(RENAME_EXCL) is unavailable",
            )
            assert path_function is not None
            path_function.argtypes = [
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            path_function.restype = ctypes.c_int
            ctypes.set_errno(0)
            source_path = os.fsencode(target.parent / source_name)
            result = path_function(source_path, os.fsencode(target), 0x00000004)
    else:
        raise Refusal(
            "REFUSE_PLATFORM",
            "atomic no-replace directory activation is unsupported on this platform",
            {"platform": sys.platform},
        )
    if result != 0:
        _raise_noreplace_error(ctypes.get_errno(), target)


def activate_directory_noreplace(source: Path, target: Path) -> None:
    source = absolute_path(source)
    target = absolute_path(target)
    require(
        source.parent == target.parent and source.name != target.name,
        "REFUSE_PATH",
        "directory activation requires distinct siblings",
    )
    with directory_fd(source.parent) as parent:
        try:
            source_info = os.stat(source.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError as error:
            raise Refusal(
                "REFUSE_PATH_MISSING",
                "directory activation source is missing",
                {"path": str(source)},
            ) from error
        require(
            stat.S_ISDIR(source_info.st_mode),
            "REFUSE_PATH_TYPE",
            "directory activation source must be a directory",
            path=str(source),
        )
        _rename_noreplace(parent, source.name, target.name, target)
        target_info = os.stat(target.name, dir_fd=parent, follow_symlinks=False)
        require(
            stat.S_ISDIR(target_info.st_mode)
            and (target_info.st_dev, target_info.st_ino)
            == (source_info.st_dev, source_info.st_ino),
            "REFUSE_WRITE_VERIFY",
            "activated directory identity differs from staging",
            path=str(target),
        )
        os.fsync(parent)


@contextmanager
def locked_file(path: Path, *, create: bool = True) -> Iterator[None]:
    require(os.name == "posix", "REFUSE_PLATFORM", "safe advisory file locking is unavailable")
    import fcntl

    path = absolute_path(path)
    with directory_fd(path.parent) as parent:
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        if create:
            flags |= os.O_CREAT
        try:
            descriptor = os.open(
                path.name,
                flags,
                0o600,
                dir_fd=parent,
            )
        except FileNotFoundError as error:
            raise Refusal(
                "REFUSE_LOCK",
                "required lock file is missing",
                {"path": str(path)},
            ) from error
    try:
        info = os.fstat(descriptor)
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600,
            "REFUSE_LOCK",
            "unsafe lock file",
            path=str(path),
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
