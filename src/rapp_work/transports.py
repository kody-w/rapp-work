from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ._json import bytes_sha256
from ._paths import (
    absolute_path,
    assert_no_symlinks,
    create_directories,
    locked_file,
    private_directory,
    read_regular,
    replace_owned,
    safe_relative,
    write_new,
)
from .errors import Refusal, require
from .plans import FileAction, ReleasePlan, SignedRelease
from .rapp1 import utc_valid

HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_REF = re.compile(r"^refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
MAX_TRANSPORT_FILES = 8192
MAX_TRANSPORT_BYTES = 64 * 1024 * 1024


def _validated_files(files: dict[str, bytes]) -> tuple[str, ...]:
    require(
        isinstance(files, dict)
        and all(isinstance(path, str) and isinstance(content, bytes) for path, content in files.items()),
        "REFUSE_TRANSPORT",
        "transport files must map relative paths to bytes",
    )
    paths = tuple(sorted(safe_relative(path) for path in files))
    require(
        len(paths) == len(set(paths))
        and len(paths) <= MAX_TRANSPORT_FILES
        and sum(len(files[path]) for path in paths) <= MAX_TRANSPORT_BYTES,
        "REFUSE_TRANSPORT_LIMIT",
        "transport release exceeds file or byte bounds",
    )
    return paths


def _snapshot_files(files: dict[str, bytes]) -> dict[str, bytes]:
    paths = _validated_files(files)
    return {path: files[path] for path in paths}


def _publication_plan(value: ReleasePlan | SignedRelease | dict[str, Any] | None) -> ReleasePlan:
    if isinstance(value, SignedRelease):
        return value.plan
    if isinstance(value, ReleasePlan):
        return value
    require(
        isinstance(value, dict),
        "REFUSE_PLAN",
        "transport publication requires a complete canonical plan or SignedRelease",
    )
    assert isinstance(value, dict)
    if value.get("schema") == SignedRelease.SCHEMA:
        return SignedRelease.from_dict(value).plan
    return ReleasePlan.from_dict(value)


def _bind_publication_plan(
    supplied: ReleasePlan | SignedRelease | dict[str, Any] | None,
    expected: ReleasePlan,
    plan_sha256: str,
) -> ReleasePlan:
    plan = _publication_plan(supplied)
    require(
        plan.to_dict() == expected.to_dict(),
        "REFUSE_PLAN",
        "transport publication inputs differ from the complete canonical plan",
    )
    require(
        isinstance(plan_sha256, str) and plan.sha256 == plan_sha256,
        "REFUSE_PLAN_HASH",
        "transport publication requires the exact canonical plan SHA-256",
        actual=plan.sha256,
        supplied=plan_sha256,
    )
    return plan


class FilesystemTransport:
    """Private local immutable objects plus one compare-and-swap pointer."""

    def __init__(self, root: Path) -> None:
        self.root = absolute_path(root)

    @property
    def objects(self) -> Path:
        return self.root / "objects"

    @property
    def pointer(self) -> Path:
        return self.root / "current.json"

    def _ensure(self) -> None:
        if not self.root.exists():
            private_directory(self.root, create=True)
        private_directory(self.root)
        if not self.objects.exists():
            create_directories(self.root, "objects")
        allowed = {"objects", "current.json", ".transport.lock"}
        require(
            all(path.name in allowed and not path.is_symlink() for path in self.root.iterdir()),
            "REFUSE_TRANSPORT",
            "filesystem transport contains an unmanaged top-level entry",
        )

    def current(self) -> bytes | None:
        if not self.root.exists():
            return None
        private_directory(self.root)
        if not self.pointer.exists() and not self.pointer.is_symlink():
            return None
        return read_regular(self.pointer, require_private=True)

    def read(self, relative: str) -> bytes:
        relative = safe_relative(relative)
        return read_regular(self.objects / relative, require_private=True)

    def publication_plan(
        self,
        files: dict[str, bytes],
        pointer: bytes,
        *,
        expected_pointer_sha256: str | None,
    ) -> ReleasePlan:
        require(
            isinstance(pointer, bytes),
            "REFUSE_TRANSPORT",
            "transport pointer must be bytes",
        )
        files = _snapshot_files(files)
        require(
            expected_pointer_sha256 is None
            or (
                isinstance(expected_pointer_sha256, str)
                and bool(HEX64.fullmatch(expected_pointer_sha256))
            ),
            "REFUSE_TRANSPORT_CAS",
            "filesystem transport expected pointer hash is invalid",
        )
        paths = tuple(files)
        actions = [
            FileAction("create", f"objects/{path}", files[path], 0o600)
            for path in paths
        ]
        actions.append(
            FileAction(
                "create" if expected_pointer_sha256 is None else "replace",
                "current.json",
                pointer,
                0o600,
                expected_pointer_sha256,
            )
        )
        return ReleasePlan(
            operation="update",
            target=str(self.root),
            subject={
                "kind": "transport-publication",
                "pointer_sha256": bytes_sha256(pointer),
                "transport": "filesystem",
            },
            actions=tuple(sorted(actions, key=lambda action: action.path)),
            preconditions=(
                {
                    "expected_pointer_sha256": expected_pointer_sha256,
                    "pointer_path": "current.json",
                },
            ),
        )

    def publish(
        self,
        files: dict[str, bytes],
        pointer: bytes,
        *,
        expected_pointer_sha256: str | None,
        apply: bool,
        plan_sha256: str,
        plan: ReleasePlan | SignedRelease | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        require(apply, "REFUSE_APPLY_REQUIRED", "transport publication requires explicit apply")
        files = _snapshot_files(files)
        bound = _bind_publication_plan(
            plan,
            self.publication_plan(
                files,
                pointer,
                expected_pointer_sha256=expected_pointer_sha256,
            ),
            plan_sha256,
        )
        paths = tuple(files)
        self._ensure()
        with locked_file(self.root / ".transport.lock"):
            current = self.current()
            current_hash = bytes_sha256(current) if current is not None else None
            require(
                current_hash == expected_pointer_sha256,
                "REFUSE_TRANSPORT_CAS",
                "filesystem transport pointer changed",
                current=current_hash,
                expected=expected_pointer_sha256,
            )
            for relative in paths:
                destination = self.objects / relative
                parent = Path(relative).parent.as_posix()
                if parent != ".":
                    create_directories(self.objects, parent)
                content = files[relative]
                if destination.exists() or destination.is_symlink():
                    require(
                        read_regular(destination, require_private=True) == content,
                        "REFUSE_IMMUTABLE_COLLISION",
                        "filesystem transport immutable object differs",
                        path=relative,
                    )
                else:
                    write_new(destination, content)
            desired_hash = bytes_sha256(pointer)
            if current is None:
                write_new(self.pointer, pointer)
            elif current != pointer:
                require(
                    expected_pointer_sha256 is not None,
                    "REFUSE_TRANSPORT_CAS",
                    "existing pointer requires an exact expected hash",
                )
                assert expected_pointer_sha256 is not None
                replace_owned(
                    self.pointer,
                    pointer,
                    expected_sha256=expected_pointer_sha256,
                )
            require(
                self.current() == pointer
                and all(self.read(path) == files[path] for path in paths),
                "REFUSE_WRITE_VERIFY",
                "filesystem transport read-back failed",
            )
        return {
            "network": False,
            "plan_sha256": bound.sha256,
            "pointer_sha256": desired_hash,
            "status": "published",
            "transport": "filesystem",
        }


class PrivateGitTransport:
    """Local private-Git CAS adapter with a credential-free environment."""

    def __init__(self, repository: Path, *, ref: str = "refs/heads/rapp-work") -> None:
        raw = os.fspath(repository)
        require(
            "://" not in raw
            and not raw.startswith("git@")
            and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:/", raw) is None,
            "REFUSE_NETWORK",
            "core private-Git transport is local-only",
        )
        self.repository = assert_no_symlinks(absolute_path(repository))
        require(
            SAFE_REF.fullmatch(ref) is not None
            and ".." not in ref
            and "//" not in ref
            and not ref.endswith(("/", ".")),
            "REFUSE_GIT_REF",
            "unsafe private-Git ref",
        )
        self.ref = ref
        executable = shutil.which("git")
        require(executable is not None, "REFUSE_GIT", "git executable is unavailable")
        assert executable is not None
        self.git = absolute_path(executable)
        require(self.repository.is_dir(), "REFUSE_GIT", "private Git repository is missing")
        read_regular(self.repository / "config", limit=1024 * 1024)
        read_regular(self.repository / "HEAD", limit=4096)
        assert_no_symlinks(self.repository / "objects")
        assert_no_symlinks(self.repository / "refs")
        alternates = self.repository / "objects/info/alternates"
        require(
            not alternates.exists() and not alternates.is_symlink(),
            "REFUSE_GIT",
            "private-Git object alternates are unsupported",
        )
        packed_refs = self.repository / "packed-refs"
        if packed_refs.exists() or packed_refs.is_symlink():
            read_regular(packed_refs, limit=16 * 1024 * 1024)
        require(
            self._run("rev-parse", "--is-bare-repository").strip() == b"true",
            "REFUSE_GIT",
            "core private-Git transport requires an explicit bare repository",
        )
        object_format = self._run("rev-parse", "--show-object-format").decode("ascii").strip()
        require(object_format in {"sha1", "sha256"}, "REFUSE_GIT", "unsupported Git object format")
        self.oid_length = 40 if object_format == "sha1" else 64

    def sanitized_environment(self) -> dict[str, str]:
        return {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }

    def _run(
        self,
        *arguments: str,
        data: bytes | None = None,
        check: bool = True,
        environment: dict[str, str] | None = None,
        max_output: int = MAX_TRANSPORT_BYTES,
    ) -> bytes:
        command = [
            str(self.git),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "credential.helper=",
            "-c",
            "protocol.allow=never",
            "-c",
            "gc.auto=0",
            "--git-dir=" + str(self.repository),
            *arguments,
        ]
        env = self.sanitized_environment()
        if environment:
            env.update(environment)
        try:
            result = subprocess.run(
                command,
                input=data,
                capture_output=True,
                cwd=self.repository.parent,
                env=env,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise Refusal("REFUSE_GIT", "isolated private-Git operation failed") from error
        if check and result.returncode != 0:
            raise Refusal(
                "REFUSE_GIT",
                "isolated private-Git operation refused",
                {"stderr": result.stderr.decode("utf-8", "replace")[:1000]},
            )
        require(
            len(result.stdout) <= max_output,
            "REFUSE_TRANSPORT_LIMIT",
            "private-Git command output exceeds the fixed bound",
        )
        return result.stdout

    def current_ref(self) -> str | None:
        output = self._run("show-ref", "--verify", "--hash", self.ref, check=False).strip()
        if not output:
            return None
        value = output.decode("ascii")
        require(
            len(value) == self.oid_length and all(character in "0123456789abcdef" for character in value),
            "REFUSE_GIT",
            "private-Git ref returned an invalid object ID",
        )
        return value

    def _tree(self, node: dict[str, Any]) -> str:
        rows: list[tuple[str, bytes]] = []
        for name, value in node.items():
            if isinstance(value, dict):
                oid = self._tree(value)
                row = f"040000 tree {oid}\t{name}\0".encode()
            else:
                row = f"100644 blob {value}\t{name}\0".encode()
            rows.append((name, row))
        raw = b"".join(row for _, row in sorted(rows))
        return self._run("mktree", "-z", data=raw).strip().decode("ascii")

    def _commit(self, files: dict[str, bytes], parent: str | None, created_utc: str) -> str:
        tree: dict[str, Any] = {}
        for relative, content in sorted(files.items()):
            oid = self._run("hash-object", "-w", "--stdin", data=content).strip().decode("ascii")
            node = tree
            parts = relative.split("/")
            for part in parts[:-1]:
                existing = node.setdefault(part, {})
                require(isinstance(existing, dict), "REFUSE_GIT", "Git path collision")
                node = existing
            require(parts[-1] not in node, "REFUSE_GIT", "duplicate Git path")
            node[parts[-1]] = oid
        tree_oid = self._tree(tree)
        from datetime import datetime, timezone

        epoch = int(
            datetime.strptime(created_utc, "%Y-%m-%dT%H:%M:%S.%fZ")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        env = {
            "GIT_AUTHOR_DATE": f"{epoch} +0000",
            "GIT_AUTHOR_EMAIL": "rapp-work@example.invalid",
            "GIT_AUTHOR_NAME": "RAPP Work",
            "GIT_COMMITTER_DATE": f"{epoch} +0000",
            "GIT_COMMITTER_EMAIL": "rapp-work@example.invalid",
            "GIT_COMMITTER_NAME": "RAPP Work",
        }
        arguments = ["commit-tree", tree_oid]
        if parent is not None:
            arguments.extend(["-p", parent])
        return self._run(
            *arguments,
            data=b"Approved offline RAPP Work release\n",
            environment=env,
        ).strip().decode("ascii")

    def publication_plan(
        self,
        files: dict[str, bytes],
        *,
        expected_ref: str | None,
        created_utc: str,
    ) -> ReleasePlan:
        require(utc_valid(created_utc), "REFUSE_GIT", "private-Git commit time is invalid")
        files = _snapshot_files(files)
        require(
            expected_ref is None
            or (
                isinstance(expected_ref, str)
                and len(expected_ref) == self.oid_length
                and all(character in "0123456789abcdef" for character in expected_ref)
            ),
            "REFUSE_GIT",
            "private-Git expected ref is invalid",
        )
        paths = tuple(files)
        return ReleasePlan(
            operation="update",
            target=str(self.repository),
            subject={
                "created_utc": created_utc,
                "kind": "transport-publication",
                "ref": self.ref,
                "transport": "private-git",
            },
            actions=tuple(
                FileAction("create", path, files[path], 0o644)
                for path in paths
            ),
            preconditions=(
                {
                    "expected_ref": expected_ref,
                    "ref": self.ref,
                },
            ),
        )

    def publish(
        self,
        files: dict[str, bytes],
        *,
        expected_ref: str | None,
        created_utc: str,
        apply: bool,
        plan_sha256: str,
        plan: ReleasePlan | SignedRelease | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        require(apply, "REFUSE_APPLY_REQUIRED", "private-Git publication requires explicit apply")
        files = _snapshot_files(files)
        bound = _bind_publication_plan(
            plan,
            self.publication_plan(
                files,
                expected_ref=expected_ref,
                created_utc=created_utc,
            ),
            plan_sha256,
        )
        current = self.current_ref()
        require(
            current == expected_ref,
            "REFUSE_TRANSPORT_CAS",
            "private-Git ref changed",
            current=current,
            expected=expected_ref,
        )
        commit = self._commit(files, current, created_utc)
        old = current or ("0" * self.oid_length)
        self._run("update-ref", self.ref, commit, old)
        require(self.current_ref() == commit, "REFUSE_WRITE_VERIFY", "private-Git ref read-back failed")
        return {
            "commit": commit,
            "network": False,
            "plan_sha256": bound.sha256,
            "status": "published",
            "transport": "private-git",
        }

    def snapshot(self) -> dict[str, bytes]:
        current = self.current_ref()
        require(current is not None, "REFUSE_GIT", "private-Git ref is absent")
        assert current is not None
        output = self._run("ls-tree", "-rz", "-r", "--full-tree", current)
        files: dict[str, bytes] = {}
        for record in output.split(b"\0"):
            if not record:
                continue
            fields, raw_name = record.split(b"\t", 1)
            mode, kind, _ = fields.decode("ascii").split(" ")
            require(
                mode == "100644" and kind == "blob",
                "REFUSE_GIT",
                "private-Git tree contains executable, symlink, tree, or submodule entries",
            )
            name = raw_name.decode("utf-8")
            safe_relative(name)
            files[name] = self._run("show", f"{current}:{name}")
        require(
            len(files) <= MAX_TRANSPORT_FILES
            and sum(map(len, files.values())) <= MAX_TRANSPORT_BYTES,
            "REFUSE_TRANSPORT_LIMIT",
            "private-Git snapshot exceeds bounds",
        )
        return files
