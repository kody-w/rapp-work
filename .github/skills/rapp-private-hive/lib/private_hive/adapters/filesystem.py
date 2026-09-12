from __future__ import annotations

from pathlib import Path
import re

from ..common import MAX_ARTIFACT_BYTES, digest, locked, no_symlinks, private_directory, read_file, require, sync_directory, write_file


_HASH = r"[0-9a-f]{64}"
PUBLIC_PATH = re.compile(
    rf"(?:objects/(?:particle|wave|egg-manifest)/{_HASH}"
    rf"|manifests/(?:releases/)?{_HASH}|chains/{_HASH}"
    rf"|receipts/[a-z0-9][a-z0-9-]*/{_HASH}|registry-history/[1-9][0-9]*-{_HASH})\.json"
)


def publication_path(path: str) -> str:
    require(isinstance(path, str) and PUBLIC_PATH.fullmatch(path), "not an allowed publication artifact path")
    return path


class Filesystem:
    def __init__(self, root: Path):
        self.root = no_symlinks(Path(root))

    def _root(self, create=False):
        root = private_directory(self.root, create=create)
        allowed = {"objects", "manifests", "chains", "receipts", "registry-history", "refs", ".store.lock"}
        require(all(path.name in allowed for path in root.iterdir()), "channel contains unmanaged top-level entries")
        return root

    def read(self, path: str) -> bytes:
        require(path == "refs/current.json" or publication_path(path), "invalid store read")
        self._root()
        return read_file(self.root / path, private=True)

    def current(self) -> bytes | None:
        if not self.root.exists():
            return None
        try:
            return self.read("refs/current.json")
        except FileNotFoundError:
            return None

    def _parents(self, path: Path):
        for parent in reversed(path.parents):
            if parent == self.root or self.root in parent.parents:
                if not parent.exists():
                    private_directory(parent, create=True)
                    sync_directory(parent.parent)
                else:
                    private_directory(parent)

    def _put(self, path: str, data: bytes):
        publication_path(path)
        require(isinstance(data, bytes) and len(data) <= MAX_ARTIFACT_BYTES, "artifact byte limit")
        destination = self.root / path
        self._parents(destination)
        write_file(destination, data, immutable=True)
        require(self.read(path) == data, "immutable read-back mismatch")

    def put_immutable(self, path: str, data: bytes):
        publication_path(path)
        self._root(create=True)
        with locked(self.root / ".store.lock"):
            self._put(path, data)

    def _cas(self, expected: str | None, desired: bytes):
        current = self.current()
        current_hash = digest(current) if current is not None else None
        require(current_hash == expected, "current pointer CAS conflict")
        destination = self.root / "refs" / "current.json"
        self._parents(destination)
        write_file(destination, desired)
        require(self.current() == desired, "current pointer read-back mismatch")

    def compare_and_swap(self, expected: str | None, desired: bytes):
        self._root(create=True)
        with locked(self.root / ".store.lock"):
            self._cas(expected, desired)

    def publish(self, files: dict[str, bytes], pointer: bytes, *, expected_pointer: str | None,
                expected_ref=None, intent=None, save_intent=None, fault=None, created_utc=None):
        require(expected_ref is None, "filesystem does not accept a Git ref")
        for path in files:
            publication_path(path)
        root = self._root(create=True)
        with locked(root / ".store.lock"):
            current = self.current()
            desired_hash = digest(pointer)
            same = current == pointer
            require(same or (digest(current) if current is not None else None) == expected_pointer,
                    "current pointer CAS conflict")
            for path, data in sorted(files.items()):
                target = root / path
                if target.exists() or target.is_symlink():
                    # The immutable writer also recognizes and repairs the
                    # exact two-link state left by death after link(2).
                    write_file(target, data, immutable=True)
                    require(self.read(path) == data, "immutable write collision")
            for path, data in sorted(files.items()):
                self._put(path, data)
                if fault:
                    fault("after-object")
            if fault:
                fault("before-cas")
            if not same:
                self._cas(expected_pointer, pointer)
            if fault:
                fault("after-cas")
            require(self.current() == pointer and all(self.read(path) == data for path, data in files.items()),
                    "publication read-back mismatch")
            return {"pointer_sha256": desired_hash, "ref": None}
