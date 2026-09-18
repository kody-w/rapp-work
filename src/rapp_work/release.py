from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._json import canonical_bytes, canonical_sha256, closed_object, strict_json_loads
from ._paths import (
    absolute_path,
    activate_directory_noreplace,
    create_directories,
    directory_fd,
    fsync_directory,
    locked_file,
    private_directory,
    read_regular,
    replace_owned,
    write_new,
)
from .errors import require
from .rapp1 import utc_valid

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_RELEASE_OBSERVATIONS = 128


@dataclass(frozen=True)
class ReleaseObservation:
    release_sha256: str
    plan_sha256: str
    source: str
    transport: str
    observed_utc: str
    hive_vector_sha256: str | None = None

    SCHEMA = "rapp-work-release-observation/1"

    def __post_init__(self) -> None:
        require(
            bool(HEX64.fullmatch(self.release_sha256))
            and bool(HEX64.fullmatch(self.plan_sha256))
            and (
                self.hive_vector_sha256 is None
                or bool(HEX64.fullmatch(self.hive_vector_sha256))
            ),
            "REFUSE_RELEASE_OBSERVATION",
            "release observation contains an invalid SHA-256",
        )
        require(
            isinstance(self.source, str)
            and 0 < len(self.source) <= 1024
            and self.transport in {"filesystem", "private-git", "memory", "compatibility"},
            "REFUSE_RELEASE_OBSERVATION",
            "release observation source or transport is invalid",
        )
        require(
            utc_valid(self.observed_utc),
            "REFUSE_RELEASE_OBSERVATION",
            "release observation time is not a RAPP/1 millisecond UTC value",
        )

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "hive_vector_sha256": self.hive_vector_sha256,
            "observed_utc": self.observed_utc,
            "plan_sha256": self.plan_sha256,
            "release_sha256": self.release_sha256,
            "schema": self.SCHEMA,
            "source": self.source,
            "transport": self.transport,
        }

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseObservation:
        item = closed_object(
            value,
            required={
                "hive_vector_sha256",
                "observed_utc",
                "plan_sha256",
                "release_sha256",
                "schema",
                "source",
                "transport",
            },
            where="release observation",
        )
        require(
            item["schema"] == cls.SCHEMA,
            "REFUSE_RELEASE_OBSERVATION",
            "wrong release observation schema",
        )
        return cls(
            release_sha256=item["release_sha256"],
            plan_sha256=item["plan_sha256"],
            source=item["source"],
            transport=item["transport"],
            observed_utc=item["observed_utc"],
            hive_vector_sha256=item["hive_vector_sha256"],
        )


class ReleaseObservationStore:
    """Bounded immutable observations; reaching the bound refuses instead of pruning."""

    def __init__(self, root: Path, *, maximum: int = MAX_RELEASE_OBSERVATIONS) -> None:
        require(
            type(maximum) is int and 1 <= maximum <= MAX_RELEASE_OBSERVATIONS,
            "REFUSE_RELEASE_STORE",
            "release observation bound must be between 1 and 128",
        )
        self.root = absolute_path(root)
        self.maximum = maximum

    @property
    def observations(self) -> Path:
        return self.root / "observations"

    def _index(self, hashes: list[str] | tuple[str, ...]) -> dict[str, Any]:
        return {
            "maximum": self.maximum,
            "observations": list(hashes),
            "schema": "rapp-work-release-observation-index/1",
        }

    def _initialize(self) -> None:
        require(
            not self.root.exists() and not self.root.is_symlink(),
            "REFUSE_RELEASE_STORE",
            "release observation store already exists and must be validated",
        )
        staging = self.root.parent / (
            f".{self.root.name}.rapp-work-observations-{secrets.token_hex(12)}"
        )
        with directory_fd(self.root.parent) as parent:
            os.mkdir(staging.name, 0o700, dir_fd=parent)
            os.fsync(parent)
        try:
            private_directory(staging)
            create_directories(staging, "observations")
            write_new(staging / ".store.lock", b"")
            write_new(staging / "index.json", canonical_bytes(self._index(())))
            fsync_directory(staging / "observations")
            fsync_directory(staging)
            activate_directory_noreplace(staging, self.root)
        except BaseException:
            if staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging)
            raise

    def _validate(self) -> tuple[tuple[str, ...], bytes]:
        private_directory(self.root)
        with directory_fd(self.root) as descriptor:
            names = sorted(os.listdir(descriptor))
            require(
                names == [".store.lock", "index.json", "observations"],
                "REFUSE_RELEASE_STORE",
                "release observation store layout is not closed",
                entries=names,
            )
            lock_info = os.stat(".store.lock", dir_fd=descriptor, follow_symlinks=False)
            index_info = os.stat("index.json", dir_fd=descriptor, follow_symlinks=False)
            observations_info = os.stat(
                "observations",
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            require(
                stat.S_ISREG(lock_info.st_mode)
                and stat.S_ISREG(index_info.st_mode)
                and stat.S_ISDIR(observations_info.st_mode),
                "REFUSE_RELEASE_STORE",
                "release observation store contains unsafe entry types",
            )
        require(
            read_regular(self.root / ".store.lock", require_private=True) == b"",
            "REFUSE_RELEASE_STORE",
            "release observation store lock file is malformed",
        )
        private_directory(self.observations)
        values: list[str] = []
        with directory_fd(self.observations) as descriptor:
            for name in sorted(os.listdir(descriptor)):
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                require(
                    stat.S_ISREG(info.st_mode)
                    and name.endswith(".json")
                    and bool(HEX64.fullmatch(name[:-5])),
                    "REFUSE_RELEASE_STORE",
                    "release observation store contains an unmanaged entry",
                    entry=name,
                )
                raw = read_regular(self.observations / name, require_private=True)
                observation = ReleaseObservation.from_dict(
                    strict_json_loads(raw, where="release observation")
                )
                require(
                    observation.sha256 == name[:-5]
                    and hashlib.sha256(raw).hexdigest() == observation.sha256,
                    "REFUSE_RELEASE_STORE",
                    "release observation address mismatch",
                    entry=name,
                )
                values.append(observation.sha256)
        hashes = tuple(values)
        index_raw = read_regular(self.root / "index.json", require_private=True)
        index = closed_object(
            strict_json_loads(index_raw, where="release observation index"),
            required={"maximum", "observations", "schema"},
            where="release observation index",
        )
        require(
            index["schema"] == "rapp-work-release-observation-index/1"
            and type(index["maximum"]) is int
            and index["maximum"] == self.maximum
            and isinstance(index["observations"], list)
            and index["observations"] == list(hashes)
            and len(hashes) <= self.maximum
            and canonical_bytes(index) == index_raw,
            "REFUSE_RELEASE_STORE",
            "release observation index is malformed or inconsistent",
        )
        return hashes, index_raw

    def _hashes(self) -> tuple[str, ...]:
        if not self.root.exists() and not self.root.is_symlink():
            return ()
        return self._validate()[0]

    def status(self) -> dict[str, Any]:
        hashes = self._hashes()
        return {
            "count": len(hashes),
            "maximum": self.maximum,
            "observations": list(hashes),
            "status": "available",
        }

    def observe(
        self,
        observation: ReleaseObservation,
        *,
        expected_sha256: str,
    ) -> dict[str, Any]:
        require(
            observation.sha256 == expected_sha256,
            "REFUSE_PLAN_HASH",
            "exact release observation SHA-256 is required",
        )
        if not self.root.exists() and not self.root.is_symlink():
            self._initialize()
        else:
            self._validate()
        with locked_file(self.root / ".store.lock", create=False):
            validated, index_raw = self._validate()
            hashes = list(validated)
            path = self.observations / f"{observation.sha256}.json"
            raw = canonical_bytes(observation.to_dict())
            if observation.sha256 in hashes:
                require(
                    read_regular(path, require_private=True) == raw,
                    "REFUSE_RELEASE_STORE",
                    "immutable release observation changed",
                )
                return {
                    "count": len(hashes),
                    "observation_sha256": observation.sha256,
                    "status": "unchanged",
                }
            require(
                len(hashes) < self.maximum,
                "REFUSE_RELEASE_OBSERVATION_LIMIT",
                "bounded immutable release observation store is full",
                maximum=self.maximum,
            )
            write_new(path, raw)
            hashes.append(observation.sha256)
            hashes.sort()
            index_path = self.root / "index.json"
            try:
                replace_owned(
                    index_path,
                    canonical_bytes(self._index(hashes)),
                    expected_sha256=hashlib.sha256(index_raw).hexdigest(),
                )
            except BaseException:
                if path.exists() and not path.is_symlink():
                    require(
                        read_regular(path, require_private=True) == raw,
                        "REFUSE_RELEASE_STORE",
                        "new observation changed before rollback",
                    )
                    with directory_fd(self.observations) as descriptor:
                        os.unlink(path.name, dir_fd=descriptor)
                        os.fsync(descriptor)
                raise
            require(
                self._validate()[0] == tuple(hashes),
                "REFUSE_WRITE_VERIFY",
                "release observation store read-back failed",
            )
        return {
            "count": len(hashes),
            "observation_sha256": observation.sha256,
            "status": "recorded",
        }
