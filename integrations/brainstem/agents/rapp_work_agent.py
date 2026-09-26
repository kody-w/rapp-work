"""RappWork: reach your private RAPP Work workspaces by talking to your Brainstem.

A single-file agent for the newest Brainstem channel (`brainstem-v0.6.16`; not in
the LTS `brainstem-v0.6.9` release scope; RAR Frontier tier). It calls only the
six public operations of the RAPP Work SDK (`rapp_work`, `rapp-work-sdk/1`) and
applies only a plan confirmed by its exact full SHA-256 in a later request.

Verbs (`action`)
  status    read-only: a folder's SDK status (`root`), one stored plan
            (`plan_sha256`), or an overview naming open plans by hash prefix only
  verify    read-only: the SDK's verification of a folder (`root`)
  discover  read-only and inert: skills, plugins and Portable Neurons under
            `roots`; nothing found is imported or run
  propose   scaffold, update or migrate (`operation`): stores the SDK's plan and
            returns an exact summary with the plan's full SHA-256; nothing changes
  confirm   the exact full hash, accepted only in a later request (below)
  apply     sends the stored plan and the confirmed hash to the SDK, which
            re-checks the hash and every precondition before its first write
  undo      withdraws a plan before apply; after apply it refuses and explains

Later requests: the newest Brainstem builds fresh agent instances for every
request and may run requests at once. Every event this agent records raises a
counter in its state, under the state lock; each instance reads the counter when
it is built. confirm is recorded only by an instance whose reading is at least
the number of the plan's latest event: a request that began after that event.
This proves order, not consent; the agent never sees the person's words.

Undo after apply is refused: RAPP Work SDK 1.0.0 effects are create-only writes
or exact-hash replacements of SDK-owned files, with no delete, so no SDK plan is
the inverse of a scaffold, update or migrate. This agent never deletes anything.

Safety: the model names a plan only by its hash and can never supply a plan or
a state folder. Nothing discovered is imported or run, and nothing is installed.
The top level imports only the standard library and BasicAgent; the SDK is
imported lazily, never from the Brainstem's own folders, so a missing SDK never
triggers the Brainstem's load-time auto-install. No network, credentials or
secrets. Outputs go to the Brainstem's model, so they name no home-folder path
or RAPPID and show found files relative to the folder searched.

Install the SDK into the Python that runs the Brainstem (for the installer,
`.brainstem/venv/bin/python` in the home folder), from its pinned source:
  <that python> -m pip install \\
    "rapp-work @ git+https://github.com/kody-w/rapp-work@29ead23b21645f8d7682ee00414930ffa9ce0ca6"
then copy this one file to the top of the Brainstem's `agents/` folder.

State: `.brainstem/rapp_work/` in the home folder, or BRAINSTEM_RAPP_WORK_PATH.
Folders 0700 and files 0600, owner-only, opened without following symlinks, and
bounded: one record per plan hash, a `lock` and a `clock`. Delete this file to
remove the agent; the state folder is plain data you can keep or remove.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import time
import unicodedata
from collections.abc import Iterable, Iterator
from typing import Any

try:
    from agents.basic_agent import BasicAgent
except Exception:
    try:
        from basic_agent import BasicAgent
    except Exception:

        class BasicAgent:  # type: ignore[no-redef]
            """Stand-in so this file always loads; a Brainstem provides the real base."""

            def __init__(
                self,
                name: str | None = None,
                metadata: dict[str, Any] | None = None,
            ) -> None:
                if name is not None:
                    self.name = name
                if metadata is not None:
                    self.metadata = metadata

            def perform(self, **kwargs: Any) -> str:
                return "Not implemented."

            def system_context(self) -> str | None:
                return None

            def to_tool(self) -> dict[str, Any]:
                return {
                    "type": "function",
                    "function": {
                        "name": self.name,
                        "description": self.metadata.get("description", ""),
                        "parameters": self.metadata.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    },
                }


__manifest__ = {
    "schema": "rapp-agent/1.0",
    "name": "@kody-w/rapp_work_agent",
    "version": "0.2.0",
    "display_name": "RappWork",
    "description": (
        "Reaches your private RAPP Work workspaces through the RAPP Work SDK: read-only "
        "status, verify and discover, plus scaffold, update and migrate plans that apply "
        "only after a later message confirms their exact SHA-256."
    ),
    "author": "kody-w",
    "tags": [
        "rapp-work",
        "workspaces",
        "sdk",
        "plan-hash",
        "propose-confirm-apply",
        "local-first",
        "brainstem",
    ],
    "category": "core",
    "quality_tier": "experimental",
    "requires_env": [],
    "dependencies": ["@rapp/basic_agent"],
}

AGENT_VERSION = "0.2.0"
SDK_SOURCE = "https://github.com/kody-w/rapp-work"
SDK_SOURCE_COMMIT = "29ead23b21645f8d7682ee00414930ffa9ce0ca6"
SDK_REQUIREMENT = f"rapp-work @ git+{SDK_SOURCE}@{SDK_SOURCE_COMMIT}"
STATE_ENV = "BRAINSTEM_RAPP_WORK_PATH"
RECORD_SCHEMA = "rapp-work-brainstem-agent-record/2"

SDK_OPERATIONS = ("status", "verify", "discover", "scaffold", "update", "migrate")
PLAN_OPERATIONS = ("scaffold", "update", "migrate")
ACTIONS = ("status", "verify", "discover", "propose", "confirm", "apply", "undo")
PLAN_INPUT_KEYS = {
    "scaffold": ("kind", "mode", "owner_label", "root", "slug", "world_id"),
    "update": ("root",),
    "migrate": ("source", "target"),
}
PLAN_PATH_KEYS = {"scaffold": ("root",), "update": ("root",), "migrate": ("source", "target")}

MAX_INPUT_CHARS = 4096
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 256
MAX_OPEN_PLANS = 16
MAX_APPLY_ATTEMPTS = 8
MAX_EVENTS = MAX_APPLY_ATTEMPTS + 3
MAX_STATE_ENTRIES = 1024
MAX_DISCOVER_ROOTS = 32
MAX_LISTED = 12
LOCK_WAIT_SECONDS = 10.0

_HEX64 = re.compile(r"[0-9a-f]{64}")
_CLOCK = re.compile(rb"(0|[1-9][0-9]{0,14})\n")
_RECORD_NAME = re.compile(r"([0-9a-f]{64})\.json")
_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp"})
# A record's history: its latest proposal, at most one confirmation, the refused applies since
# that confirmation, then at most one final event. Proposing again keeps nothing before the new
# proposal, and confirming again keeps only the proposal.
_EVENT_KEYS = {
    "proposed": {"event", "seq", "utc"},
    "confirmed": {"event", "plan_sha256", "refused", "seq", "utc"},
    "apply-refused": {"code", "event", "message", "seq", "utc"},
    "applied": {"event", "result", "seq", "utc"},
    "withdrawn": {"event", "seq", "utc"},
}
_EVENT_AFTER = {
    "proposed": {""},
    "confirmed": {"proposed"},
    "apply-refused": {"confirmed"},
    "applied": {"confirmed"},
    "withdrawn": {"proposed", "confirmed"},
}
RETRY_CODES = frozenset({"REFUSE_RUNTIME", "REFUSE_WRITE_VERIFY"})
_RECORD_KEYS = {
    "agent_version",
    "events",
    "inputs",
    "operation",
    "plan",
    "plan_sha256",
    "plan_storage_sha256",
    "schema",
}
_RESULT_KEYS = (
    "effects",
    "kind",
    "plan_sha256",
    "rappid",
    "receipt_sha256",
    "root",
    "source_preserved",
    "status",
    "target",
)


UNCHANGED = "Nothing was changed."
OUTCOME_UNKNOWN = (
    "This agent cannot tell whether anything changed; check the folder with status or verify "
    "before trying again."
)


class _Refusal(Exception):
    """A fail-closed refusal; unless its outcome says otherwise, no effect was requested."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        outcome: str = UNCHANGED,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}
        self.outcome = outcome


# -- text -----------------------------------------------------------------------------


def _clean(value: Any, limit: int = 300) -> str:
    """Render untrusted text on one line; control and invisible characters are escaped."""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            text = repr(value)
    pieces: list[str] = []
    for character in text[:limit]:
        if unicodedata.category(character) in _HIDDEN_CATEGORIES:
            pieces.append(character.encode("unicode_escape").decode("ascii"))
        else:
            pieces.append(character)
    if len(text) > limit:
        pieces.append("...")
    return "".join(pieces)


def _details_line(details: dict[str, Any]) -> str:
    parts = [f"{_clean(key, 60)}={_clean(value, 240)}" for key, value in sorted(details.items())]
    return "Details: " + "; ".join(parts)


def _refusal_text(refusal: _Refusal) -> str:
    lines = [f"RAPP Work: REFUSED [{refusal.code}] {refusal.message}"]
    if refusal.details:
        lines.append(_details_line(refusal.details))
    lines.append(refusal.outcome)
    return "\n".join(lines)


def _sdk_refusal(envelope: dict[str, Any]) -> dict[str, Any]:
    refusal = envelope.get("refusal")
    return refusal if isinstance(refusal, dict) else {}


def _sdk_refusal_text(envelope: dict[str, Any], lead: str) -> str:
    refusal = _sdk_refusal(envelope)
    lines = [
        f"RAPP Work: REFUSED by the RAPP Work SDK [{_clean(refusal.get('code'), 80)}] "
        f"{_clean(refusal.get('message'))}"
    ]
    details = refusal.get("details")
    if isinstance(details, dict) and details:
        lines.append(_details_line(details))
    lines.append(lead)
    return "\n".join(lines)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _usage() -> str:
    return "\n".join(
        [
            "RappWork (newest Brainstem channel): your private RAPP Work workspaces, through "
            "the RAPP Work SDK.",
            "Read-only: status (root, or plan_sha256, or nothing for an overview), verify "
            "(root), discover (roots).",
            "Changes: propose with operation scaffold, update or migrate, and show the person "
            "the summary. Only when the person replies in a later message with the full plan "
            "hash, confirm and apply exactly that hash. undo withdraws a plan before apply.",
            "Nothing changes until a confirmed plan is applied.",
        ]
    )


# -- inputs ---------------------------------------------------------------------------


def _present(arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop the empty values a model sends for properties it did not mean to use."""
    return {
        key: value
        for key, value in arguments.items()
        if value is not None and not (isinstance(value, (str, list)) and len(value) == 0)
    }


def _closed(arguments: dict[str, Any], allowed: Iterable[str], verb: str) -> None:
    permitted = set(allowed)
    unknown = sorted(str(key) for key in arguments if key not in permitted)
    if unknown:
        raise _Refusal(
            "AGENT_REFUSE_INPUT",
            f"{verb} does not take: {', '.join(_clean(key, 60) for key in unknown)}",
            {"allowed": sorted(permitted)},
        )


def _visible_text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_INPUT_CHARS:
        raise _Refusal(
            "AGENT_REFUSE_INPUT",
            f"{where} must be a non-empty string of at most {MAX_INPUT_CHARS} characters",
        )
    if any(unicodedata.category(character) in _HIDDEN_CATEGORIES for character in value):
        raise _Refusal(
            "AGENT_REFUSE_INPUT",
            f"{where} contains control or invisible formatting characters",
            {where: _clean(value)},
        )
    return value


def _path_input(value: Any, where: str) -> str:
    """An absolute path input; every verb refuses one inside this agent's own state folder."""
    text = os.path.expanduser(_visible_text(value, where))
    parts = text.replace("\\", "/").split("/")
    if not os.path.isabs(text) or ".." in parts:
        raise _Refusal(
            "AGENT_REFUSE_PATH",
            f"{where} must be an absolute folder path without '..' (this agent never guesses "
            "a folder from the Brainstem's working directory)",
            {where: _clean(value)},
        )
    path = os.path.abspath(text)
    base = _state_base()
    for spelling in {path, os.path.realpath(path)}:
        if any(_is_within(spelling, state) for state in {base, os.path.realpath(base)}):
            raise _Refusal(
                "AGENT_REFUSE_PATH",
                f"{where} lies inside this agent's own state folder",
                {where: _clean(value)},
            )
    return path


def _hash_input(value: Any) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise _Refusal(
            "AGENT_REFUSE_HASH_FORMAT",
            "plan_sha256 must be the exact full 64-character lowercase SHA-256 shown in the "
            "proposal; prefixes, other spellings and prefixed forms are never accepted",
            {"received_length": len(value) if isinstance(value, str) else type(value).__name__},
        )
    return value


def _is_within(path: str, root: str) -> bool:
    """Case-insensitively, so a differently cased spelling on such a filesystem is caught."""
    path, root = (os.path.normcase(os.path.normpath(value)).casefold() for value in (path, root))
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


# -- private state: descriptor-relative, no-follow, bounded -------------------------------


def _state_base() -> str:
    override = os.environ.get(STATE_ENV)
    if override:
        candidate = os.path.expanduser(override)
    else:
        candidate = os.path.join(os.path.expanduser("~"), ".brainstem", "rapp_work")
    parts = candidate.replace("\\", "/").split("/")
    if "\x00" in candidate or not os.path.isabs(candidate) or ".." in parts:
        raise _Refusal(
            "AGENT_REFUSE_STATE",
            f"the state folder must be an absolute path without '..' (set {STATE_ENV})",
            {"path": _clean(candidate)},
        )
    return os.path.normpath(candidate)


def _state_label() -> str:
    """Where the state is, without a home-folder path (outputs go to the model)."""
    if os.environ.get(STATE_ENV):
        return f"the folder named by {STATE_ENV}"
    return ".brainstem/rapp_work in your home folder"


def _require_platform() -> None:
    supported = (
        hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "geteuid")
        and hasattr(os, "fchmod")
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.rename in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.scandir in os.supports_fd
    )
    if not supported:
        raise _Refusal(
            "AGENT_REFUSE_STATE",
            "this platform lacks descriptor-relative no-follow file operations, so this agent "
            "keeps no state here and refuses changes",
        )


def _dir_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_directory(path: str, *, create: bool) -> tuple[int, bool]:
    """Open an absolute folder one component at a time, never following a symlink.

    Missing components are created with mode 0700 only when `create` is true.
    Returns the descriptor and whether the last component was created now.
    """
    _require_platform()
    flags = _dir_flags()
    descriptor = os.open(os.sep, flags)
    created = False
    try:
        for part in (component for component in path.split(os.sep) if component):
            created = False
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                with contextlib.suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                    created = True
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, created


def _make_private(descriptor: int, created: bool, where: str) -> None:
    if created:
        os.fchmod(descriptor, 0o700)
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise _Refusal(
            "AGENT_REFUSE_STATE",
            "the agent state folders must be directories owned by you with mode 0700",
            {"folder": _clean(where), "mode": oct(stat.S_IMODE(info.st_mode))},
        )


def _open_child_directory(parent: int, name: str, *, create: bool, where: str) -> int:
    flags = _dir_flags()
    created = False
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
    except FileNotFoundError:
        if not create:
            raise
        with contextlib.suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent)
            created = True
        descriptor = os.open(name, flags, dir_fd=parent)
    try:
        _make_private(descriptor, created, where)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _check_private_file(descriptor: int, what: str) -> os.stat_result:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise _Refusal(
            "AGENT_REFUSE_STORED_PLAN",
            f"the {what} is not a private regular file (owner-only 0600, one link)",
        )
    return info


def _read_private_file(directory: int, name: str, limit: int, what: str = "stored record") -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(name, flags, dir_fd=directory)
    try:
        info = _check_private_file(descriptor, what)
        if info.st_size > limit:
            raise _Refusal(
                "AGENT_REFUSE_STATE_BOUND",
                f"the {what} exceeds the size bound",
                {"limit_bytes": limit},
            )
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > limit:
            raise _Refusal("AGENT_REFUSE_STATE_BOUND", f"the {what} exceeds the size bound")
        return data
    finally:
        os.close(descriptor)


def _write_private_file(directory: int, name: str, data: bytes) -> None:
    """Replace `name` atomically: write a new 0600 file, then rename it into place."""
    temporary = f".{name}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600, dir_fd=directory)
    try:
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary, dir_fd=directory)
        raise
    os.fsync(directory)


def _acquire_lock(base: int) -> int:
    try:
        import fcntl
    except ImportError:
        raise _Refusal(
            "AGENT_REFUSE_STATE", "advisory file locking is unavailable on this platform"
        ) from None
    created = False
    try:
        descriptor = os.open(
            "lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=base
        )
        created = True
    except FileExistsError:
        descriptor = os.open(
            "lock", os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=base
        )
    try:
        if created:
            os.fchmod(descriptor, 0o600)
        _check_private_file(descriptor, "state lock")
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return descriptor
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise _Refusal(
                        "AGENT_REFUSE_STATE",
                        "another RAPP Work request holds the state lock; try again",
                    ) from None
                time.sleep(0.05)
    except BaseException:
        os.close(descriptor)
        raise


def _release_lock(descriptor: int) -> None:
    try:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except (ImportError, OSError):
        pass
    finally:
        os.close(descriptor)


def _unsafe_state(where: str, error: OSError) -> _Refusal:
    return _Refusal(
        "AGENT_REFUSE_STATE",
        "the state folder path is unsafe: every component must be a real directory, and "
        "symlinks are never followed",
        {"folder": where, "error": errno.errorcode.get(error.errno or 0, str(error.errno))},
    )


@contextlib.contextmanager
def _state(*, create: bool, lock: bool) -> Iterator[tuple[int, int] | None]:
    """Yield (state folder, records folder) descriptors, or None when no state exists.

    Callers that only read pass create=False and lock=False and never create anything.
    """
    base = _state_base()
    base_fd = lock_fd = records_fd = -1
    created = False
    value: tuple[int, int] | None = None
    try:
        try:
            base_fd, created = _open_directory(base, create=create)
        except FileNotFoundError:
            if create:
                raise _Refusal("AGENT_REFUSE_STATE", "the state folder could not be created") from None
        except OSError as error:
            raise _unsafe_state("state", error) from None
        if base_fd >= 0:
            _make_private(base_fd, created, "state")
            if lock:
                lock_fd = _acquire_lock(base_fd)
            try:
                records_fd = _open_child_directory(
                    base_fd, "records", create=create, where="records"
                )
            except FileNotFoundError:
                if create:
                    raise _Refusal(
                        "AGENT_REFUSE_STATE", "the records folder could not be created"
                    ) from None
            except OSError as error:
                raise _unsafe_state("records", error) from None
            if records_fd >= 0:
                value = (base_fd, records_fd)
        yield value
    finally:
        if records_fd >= 0:
            os.close(records_fd)
        if lock_fd >= 0:
            _release_lock(lock_fd)
        if base_fd >= 0:
            os.close(base_fd)


def _record_names(records: int) -> tuple[list[str], int]:
    names: list[str] = []
    others = 0
    seen = 0
    with os.scandir(records) as iterator:
        for entry in iterator:
            seen += 1
            if seen > MAX_STATE_ENTRIES:
                raise _Refusal(
                    "AGENT_REFUSE_STATE_BOUND",
                    "the records folder holds more entries than this agent will read",
                    {"limit": MAX_STATE_ENTRIES},
                )
            match = _RECORD_NAME.fullmatch(entry.name)
            if match:
                names.append(match.group(1))
            else:
                others += 1
    return sorted(names), others


# -- records --------------------------------------------------------------------------


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _plan_storage_sha256(plan: dict[str, Any]) -> str:
    """Tamper tripwire over this agent's own stored bytes. It is not the plan hash.

    The canonical plan SHA-256 is computed and enforced only by the SDK.
    """
    return hashlib.sha256(_json_bytes(plan)).hexdigest()


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate member {key!r}")
        value[key] = item
    return value


def _no_float(text: str) -> Any:
    raise ValueError("floating-point or non-finite value")


def _parse_json(raw: bytes) -> Any:
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_no_duplicates,
        parse_float=_no_float,
        parse_constant=_no_float,
    )


def _check_plan(operation: str, plan: Any, inputs: dict[str, str]) -> dict[str, Any]:
    """Shape checks on an SDK plan. The SDK itself re-verifies everything that matters."""
    problem = None
    if not isinstance(plan, dict):
        problem = "the plan is not an object"
    elif plan.get("operation") != operation or plan.get("network") is not False:
        problem = "the plan operation or network flag differs"
    elif operation == "migrate" and (
        plan.get("source") != inputs.get("source") or plan.get("target") != inputs.get("target")
    ):
        problem = "the plan source or target differs from its inputs"
    elif operation != "migrate" and plan.get("target") != inputs.get("root"):
        problem = "the plan target differs from its inputs"
    elif not isinstance(plan.get("actions"), list):
        problem = "the plan has no action list"
    else:
        for action in plan["actions"]:
            if not (
                isinstance(action, dict)
                and action.get("operation") in {"create", "replace"}
                and isinstance(action.get("path"), str)
                and type(action.get("bytes")) is int
                and isinstance(action.get("sha256"), str)
                and (action.get("expected_sha256") is None)
                == (action.get("operation") == "create")
            ):
                problem = "a plan action has an unexpected shape"
                break
    if problem is not None or not isinstance(plan, dict):
        raise _Refusal("AGENT_REFUSE_STORED_PLAN", problem or "the plan is not an object")
    return plan


def _record_state(record: dict[str, Any]) -> str:
    """Replay the event history; refuse any history this agent could not have written."""
    events = record.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise _Refusal("AGENT_REFUSE_STORED_PLAN", "the record history is missing or unbounded")
    state = ""
    seq = 0
    for event in events:
        kind = event.get("event") if isinstance(event, dict) else None
        if (
            not isinstance(event, dict)
            or not isinstance(kind, str)
            or kind not in _EVENT_KEYS
            or set(event) != _EVENT_KEYS[kind]
            or not isinstance(event.get("utc"), str)
            or type(event.get("seq")) is not int
            or not seq < event["seq"] < 10**15
        ):
            raise _Refusal("AGENT_REFUSE_STORED_PLAN", "the record history has a malformed event")
        if state not in _EVENT_AFTER[kind]:
            raise _Refusal("AGENT_REFUSE_STORED_PLAN", "the record history is out of order")
        if kind == "confirmed" and (
            event["plan_sha256"] != record.get("plan_sha256")
            or type(event["refused"]) is not int
            or event["refused"] < 0
        ):
            raise _Refusal(
                "AGENT_REFUSE_STORED_PLAN",
                "the record's confirmation is malformed or names a different plan hash",
            )
        seq = event["seq"]
        if kind != "apply-refused":
            state = kind
    return state


def _check_record(record: Any, digest: str) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
        raise _Refusal("AGENT_REFUSE_STORED_PLAN", "the stored record has an unexpected shape")
    operation = record.get("operation")
    inputs = record.get("inputs")
    if (
        record.get("schema") != RECORD_SCHEMA
        or record.get("plan_sha256") != digest
        or not isinstance(operation, str)
        or operation not in PLAN_INPUT_KEYS
        or not isinstance(inputs, dict)
        or set(inputs) != set(PLAN_INPUT_KEYS[operation])
        or not all(isinstance(value, str) for value in inputs.values())
    ):
        raise _Refusal(
            "AGENT_REFUSE_STORED_PLAN",
            "the stored record does not match its file name, schema or inputs",
        )
    plan = _check_plan(operation, record.get("plan"), inputs)
    if record.get("plan_storage_sha256") != _plan_storage_sha256(plan):
        raise _Refusal(
            "AGENT_REFUSE_STORED_PLAN",
            "the stored plan was edited after it was proposed; it will not be sent to the SDK",
            {"plan_sha256": digest},
        )
    _record_state(record)
    return record


def _load_record(records: int, digest: str) -> dict[str, Any] | None:
    name = digest + ".json"
    try:
        raw = _read_private_file(records, name, MAX_RECORD_BYTES)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _Refusal(
            "AGENT_REFUSE_STORED_PLAN",
            "the stored record could not be read safely (a symlink or an unreadable file)",
            {"record": name, "error": errno.errorcode.get(error.errno or 0, str(error.errno))},
        ) from None
    try:
        record = _parse_json(raw)
    except (UnicodeDecodeError, ValueError):
        raise _Refusal(
            "AGENT_REFUSE_STORED_PLAN", "the stored record is not valid JSON", {"record": name}
        ) from None
    return _check_record(record, digest)


def _save_record(records: int, record: dict[str, Any]) -> None:
    data = _json_bytes(record) + b"\n"
    if len(data) > MAX_RECORD_BYTES:
        raise _Refusal(
            "AGENT_REFUSE_STATE_BOUND",
            "this plan is too large for the Brainstem agent to keep; use the rapp-work CLI",
            {"limit_bytes": MAX_RECORD_BYTES},
        )
    try:
        _write_private_file(records, str(record["plan_sha256"]) + ".json", data)
    except OSError as error:
        raise _Refusal(
            "AGENT_REFUSE_STATE",
            "the plan record could not be written safely",
            {"error": errno.errorcode.get(error.errno or 0, str(error.errno))},
        ) from None


def _read_clock(base: int) -> int:
    """The state's logical clock: the sequence number of the latest recorded event."""
    try:
        raw = _read_private_file(base, "clock", 32, "state clock")
    except FileNotFoundError:
        return 0
    except OSError as error:
        raise _unsafe_state("clock", error) from None
    match = _CLOCK.fullmatch(raw)
    if match is None:
        raise _Refusal("AGENT_REFUSE_STATE", "the state clock is not a decimal counter")
    return int(match.group(1))


def _clock_now() -> int | None:
    """The clock as an instance is built, read without the lock; None if it is unreadable."""
    try:
        with _state(create=False, lock=False) as handles:
            clock = 0 if handles is None else _read_clock(handles[0])
    except Exception:
        return None
    return clock


def _commit(
    handles: tuple[int, int],
    record: dict[str, Any],
    kind: str,
    keep: int | None = None,
    **fields: Any,
) -> None:
    """Under the state lock: record one event, then advance the clock to its number.

    The record is written first, so an instance that reads the new clock value was
    built after the event was stored. `keep` drops the events after the first `keep`.
    """
    base, records = handles
    seq = max([_read_clock(base), *(event["seq"] for event in record["events"])]) + 1
    record["events"] = [
        *record["events"][:keep],
        {"event": kind, "seq": seq, "utc": _now(), **fields},
    ]
    _save_record(records, record)
    try:
        _write_private_file(base, "clock", b"%d\n" % seq)
    except OSError as error:
        raise _Refusal(
            "AGENT_REFUSE_STATE",
            "the state clock could not be written safely",
            {"error": errno.errorcode.get(error.errno or 0, str(error.errno))},
            outcome="The plan's record was updated but the state clock was not; check it with "
            "status before trying again.",
        ) from None


def _refused_count(record: dict[str, Any]) -> tuple[int, int]:
    """Refused applies since the latest confirmation, and since the latest proposal."""
    recent = sum(1 for event in record["events"] if event["event"] == "apply-refused")
    return recent, recent + int(_last_event(record, "confirmed").get("refused", 0))


def _last_event(record: dict[str, Any], kind: str) -> dict[str, Any]:
    for event in reversed(record["events"]):
        if isinstance(event, dict) and event.get("event") == kind:
            return event
    return {}


# -- the SDK: imported lazily, and never from the Brainstem's own folders ------------------


def _install_text() -> str:
    return (
        "Install it into the Python that runs this Brainstem (for the Brainstem installer, "
        ".brainstem/venv/bin/python in your home folder), from its source at a pinned commit "
        f'and never from a package index name: <that python> -m pip install "{SDK_REQUIREMENT}". '
        "The Brainstem loads agents again for every message, so no restart is needed. This "
        "agent never installs anything itself."
    )


def _import_root(location: str) -> str:
    if os.path.isdir(location):
        return os.path.dirname(location)
    if os.path.basename(location).startswith("__init__."):
        return os.path.dirname(os.path.dirname(location))
    return os.path.dirname(location)


def _shadow_reason(spec: Any) -> str | None:
    """Explain why a `rapp_work` that was found must not be imported, or return None."""
    locations: list[str] = []
    origin = getattr(spec, "origin", None)
    if isinstance(origin, str) and os.path.isabs(origin):
        locations.append(origin)
    for entry in getattr(spec, "submodule_search_locations", None) or []:
        if isinstance(entry, str):
            locations.append(entry)
    if not locations:
        return "the name rapp_work resolves to a namespace folder or a built-in, not the SDK"
    trees: list[tuple[str, str]] = []
    roots: list[str] = []
    for variant in {os.path.abspath(__file__), os.path.realpath(__file__)}:
        agents_folder = os.path.dirname(variant)
        trees.append((agents_folder, "this Brainstem's agents folder"))
        roots.append(os.path.normcase(os.path.dirname(agents_folder)))
    with contextlib.suppress(OSError):
        roots.append(os.path.normcase(os.path.realpath(os.getcwd())))
    with contextlib.suppress(_Refusal):
        trees.append((_state_base(), "this agent's state folder"))
    for location in locations:
        for variant in {os.path.abspath(location), os.path.realpath(location)}:
            for tree, label in trees:
                if _is_within(variant, tree):
                    return (
                        f"a module named rapp_work was found inside {label}, where folders are "
                        "organization or agent state, never live code"
                    )
            if os.path.normcase(os.path.normpath(_import_root(variant))) in roots:
                return (
                    "a module named rapp_work was found directly in the Brainstem folder or "
                    "its working folder"
                )
    return None


def _sdk() -> Any:
    try:
        spec = importlib.util.find_spec("rapp_work")
    except (ImportError, ValueError, AttributeError):
        spec = None
    if spec is None:
        raise _Refusal(
            "AGENT_REFUSE_SDK_MISSING",
            "the RAPP Work SDK (rapp_work) is not installed in this Brainstem's Python. "
            + _install_text(),
        )
    reason = _shadow_reason(spec)
    if reason is not None:
        raise _Refusal(
            "AGENT_REFUSE_SDK_SHADOWED",
            reason + "; it was not imported. Remove it, then install the SDK. " + _install_text(),
        )
    try:
        import rapp_work
    except Exception as error:
        raise _Refusal(
            "AGENT_REFUSE_SDK_MISSING",
            f"the RAPP Work SDK was found but could not be imported ({type(error).__name__}). "
            + _install_text(),
        ) from None
    return rapp_work


def _call_sdk(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Call exactly one of the six public SDK operations and check its envelope."""
    if operation not in SDK_OPERATIONS:
        raise _Refusal("AGENT_REFUSE_INTERNAL", "not one of the six public SDK operations")
    sdk = _sdk()
    function = getattr(sdk, operation, None)
    if not callable(function):
        raise _Refusal(
            "AGENT_REFUSE_SDK_RESPONSE",
            f"the installed rapp_work has no {operation} operation. " + _install_text(),
        )
    envelope = function(dict(inputs))
    if (
        not isinstance(envelope, dict)
        or envelope.get("operation") != operation
        or envelope.get("status") not in {"ok", "planned", "applied", "refused"}
        or (envelope["status"] != "refused" and not isinstance(envelope.get("result"), dict))
    ):
        raise _Refusal(
            "AGENT_REFUSE_SDK_RESPONSE",
            "the SDK returned an envelope this agent does not recognize; nothing was recorded",
            outcome=OUTCOME_UNKNOWN if inputs.get("apply") is True else UNCHANGED,
        )
    return envelope


# -- summaries ------------------------------------------------------------------------


def _short(digest: Any) -> str:
    return _clean(digest[:12], 12) if isinstance(digest, str) else "?"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _subject_line(subject: Any) -> str:
    items = sorted(
        (key, value) for key, value in _mapping(subject).items() if key not in {"rappid", "root"}
    )
    return "Subject: " + ", ".join(f"{_clean(key, 40)} {_clean(value, 200)}" for key, value in items)


def _action_lines(actions: list[dict[str, Any]], *, past: bool) -> list[str]:
    lines: list[str] = []
    for action in actions[:MAX_LISTED]:
        path = _clean(action["path"], 200)
        if action["operation"] == "replace":
            if past:
                lines.append(
                    f"  replaced {path} (was sha256 {_short(action.get('expected_sha256'))}..., "
                    f"now {_short(action.get('sha256'))}...)"
                )
            else:
                lines.append(
                    f"  replace {path} ({action['bytes']} bytes) only if it is still sha256 "
                    f"{_short(action.get('expected_sha256'))}..."
                )
        else:
            verb = "created " if past else "create  "
            lines.append(
                f"  {verb}{path} ({action['bytes']} bytes, sha256 {_short(action.get('sha256'))}...)"
            )
    if len(actions) > MAX_LISTED:
        lines.append(f"  ... and {len(actions) - MAX_LISTED} more, all in the stored plan")
    return lines


def _plan_lines(operation: str, plan: dict[str, Any]) -> list[str]:
    actions = plan["actions"]
    creates = sum(1 for action in actions if action["operation"] == "create")
    replaces = len(actions) - creates
    lines: list[str] = []
    if operation == "scaffold":
        subject = _mapping(plan.get("subject"))
        lines.append(
            f"Operation: scaffold - create a new {_clean(subject.get('kind'), 40)} "
            f"'{_clean(subject.get('slug'), 100)}' (owner label "
            f"'{_clean(subject.get('owner_label'), 60)}', world "
            f"'{_clean(subject.get('world_id'), 80)}', mode '{_clean(subject.get('mode'), 20)}')."
        )
        lines.append(
            f"Target folder: {_clean(plan.get('target'), 400)} (must not exist; the SDK creates "
            "it in one atomic step)"
        )
    elif operation == "update":
        subject = _mapping(plan.get("subject"))
        lines.append(
            "Operation: update - adopt or refresh the RAPP Work SDK "
            f"{_clean(subject.get('sdk_version'), 20)} integration files of the "
            f"{_clean(subject.get('kind'), 40)} in world '{_clean(subject.get('world_id'), 80)}'."
        )
        lines.append(
            f"Folder: {_clean(plan.get('target'), 400)} (only SDK-owned files are ever replaced, "
            "and only if their current SHA-256 still equals the plan's)"
        )
    else:
        binding = _mapping(plan.get("source_binding"))
        authority = binding.get("authority_files")
        count = len(authority) if isinstance(authority, list) else 0
        lines.append(
            f"Operation: migrate - create a successor of the {_clean(binding.get('kind'), 40)} "
            f"in world '{_clean(binding.get('world_id'), 80)}'."
        )
        lines.append(
            f"Source: {_clean(plan.get('source'), 400)} (preserved byte for byte; {count} "
            "authority files are bound by SHA-256 and re-checked at apply)"
        )
        lines.append(f"Target folder: {_clean(plan.get('target'), 400)} (must not exist)")
    lines.append(
        f"Effects: {creates} file(s) created, {replaces} replaced, 0 deleted. Network: none."
    )
    lines.extend(_action_lines(actions, past=False))
    return lines


def _undo_note(operation: str) -> str:
    return (
        "Undo after apply: not possible for this plan with RAPP Work SDK 1.0.0 (its effects are "
        f"create-only or exact-hash replacements, and it has no delete). A {operation} plan can "
        "be undone only before apply, which withdraws it."
    )


def _after_refused_apply(code: str, digest: str) -> str:
    """After an SDK apply refusal, which may have stopped part-way: what to do next."""
    if code in RETRY_CODES:
        step = (
            f"fix the cause (for example free space or permissions), then apply {digest} "
            "again: the SDK finishes this same plan. Do not withdraw it, because only this plan "
            "can finish a partly applied update or migration."
        )
    elif code == "REFUSE_RECOVERY_BINDING":
        step = (
            "an earlier plan's apply stopped part-way in this folder, and the SDK lets only that "
            "plan finish: apply it again with the full hash from its proposal. This plan stays "
            "confirmed."
        )
    else:
        step = (
            "check the folder with verify. If it changed on purpose after the proposal, withdraw "
            "this plan with undo and propose again; if not, put it back as it was and apply "
            f"{digest} again."
        )
    return (
        "The SDK stopped this apply. An apply can stop part-way, so part of the plan may already "
        "be in the folder. Next: " + step
    )


def _record_line(digest: str, record: dict[str, Any]) -> str:
    """One open plan, named by a hash prefix: only a proposal shows a full hash."""
    inputs = record["inputs"]
    where = inputs.get("root") or f"{inputs.get('source')} -> {inputs.get('target')}"
    return (
        f"  {_short(digest)}... {_record_state(record)} {record['operation']} "
        f"{_clean(where, 200)} (proposed {_clean(record['events'][0].get('utc'), 30)})"
    )


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {key: result[key] for key in _RESULT_KEYS if key in result}
    verification = result.get("verification")
    if isinstance(verification, dict) and isinstance(verification.get("status"), str):
        summary["verification"] = verification["status"]
    parsed = _parse_json(_json_bytes(summary))
    return parsed if isinstance(parsed, dict) else {}


def _verify_line(root: Any) -> str:
    if not isinstance(root, str):
        return "SDK verify: not run (no folder in the SDK result)."
    try:
        envelope = _call_sdk("verify", {"root": root})
    except _Refusal as error:
        return f"SDK verify: not run ({error.code})."
    if envelope["status"] == "refused":
        refused = _sdk_refusal(envelope)
        return (
            f"SDK verify (read-only): REFUSED [{_clean(refused.get('code'), 80)}] "
            f"{_clean(refused.get('message'))}"
        )
    result = envelope["result"]
    subject = _mapping(result.get("subject"))
    return (
        f"SDK verify (read-only): {_clean(subject.get('status') or result.get('status'), 60)} - "
        f"{_clean(subject.get('kind'), 40)}, {_clean(subject.get('managed_files'), 20)} "
        "managed file(s)."
    )


def _format_status(envelope: dict[str, Any], root: str) -> str:
    if envelope["status"] == "refused":
        return _sdk_refusal_text(envelope, "This was a read-only request; nothing was changed.")
    result = envelope["result"]
    lines = [
        f"RAPP Work SDK status (read-only) of {_clean(result.get('root', root), 400)}",
        f"Classification: {_clean(result.get('classification'), 60)}",
    ]
    if isinstance(result.get("subject"), dict):
        lines.append(_subject_line(result["subject"]))
    profiles = result.get("profiles")
    if isinstance(profiles, list):
        lines.append("Profiles: " + ", ".join(_clean(value, 60) for value in profiles))
    network = "off" if result.get("network") is False else _clean(result.get("network"), 20)
    lines.append(f"SDK version {_clean(result.get('sdk_version'), 20)}; network {network}.")
    return "\n".join(lines)


def _format_verify(envelope: dict[str, Any], root: str) -> str:
    if envelope["status"] == "refused":
        return _sdk_refusal_text(
            envelope,
            "This was a read-only request; nothing was changed. A workspace without SDK "
            "integration files can adopt them through a proposed update.",
        )
    result = envelope["result"]
    lines = [
        f"RAPP Work SDK verify (read-only) of {_clean(result.get('root', root), 400)}: "
        f"{_clean(result.get('status'), 40)}"
    ]
    if isinstance(result.get("subject"), dict):
        lines.append(_subject_line(result["subject"]))
    profiles = _mapping(result.get("profiles"))
    if profiles:
        lines.append(f"Pinned profiles: {_clean(profiles.get('status'), 40)}")
    return "\n".join(lines)


def _found(path: Any, roots: list[Any]) -> str:
    """A discovered path under the name of the folder searched, not the whole device path."""
    if isinstance(path, str):
        for root in roots:
            prefix = root.rstrip(os.sep) + os.sep if isinstance(root, str) else None
            if prefix and path.startswith(prefix):
                name = os.path.basename(prefix[:-1]) or os.sep
                return _clean(os.path.join(name, path[len(prefix) :]), 300)
    return _clean(path, 300)


def _format_discover(envelope: dict[str, Any]) -> str:
    if envelope["status"] == "refused":
        return _sdk_refusal_text(envelope, "This was a read-only request; nothing was changed.")
    result = envelope["result"]
    groups = {
        name: result.get(name) if isinstance(result.get(name), list) else []
        for name in ("skills", "plugins", "neurons", "refusals")
    }
    roots = result.get("roots") if isinstance(result.get("roots"), list) else []
    lines = [
        "RAPP Work SDK discover (read-only and inert: nothing was imported or run) over "
        f"{len(roots)} root(s): {len(groups['skills'])} skill(s), {len(groups['plugins'])} "
        f"plugin(s), {len(groups['neurons'])} Portable Neuron(s); {len(groups['refusals'])} "
        "entry(ies) refused or ignored."
    ]
    shown = 10
    for name, key, label in (
        ("skills", "name", "Skill"),
        ("plugins", "name", "Plugin"),
        ("neurons", "declared_name", "Neuron"),
    ):
        entries = groups[name]
        for entry in entries[:shown]:
            item = _mapping(entry)
            where = _found(item.get("manifest") or item.get("path"), roots)
            digest = item.get("sha256") or item.get("manifest_sha256")
            lines.append(
                f"  {label}: {_clean(item.get(key), 100)} at {where} "
                f"(sha256 {_short(digest)}..., never run)"
            )
        if len(entries) > shown:
            lines.append(f"  ... and {len(entries) - shown} more {name}")
    for entry in groups["refusals"][:shown]:
        item = _mapping(entry)
        lines.append(
            f"  Ignored: [{_clean(item.get('code'), 60)}] {_found(item.get('path'), roots)}"
        )
    lines.append(
        "Paths are shown under the name of the folder searched. Single-file *_agent.py agents "
        "are not listed, and this agent never opens or runs them."
    )
    return "\n".join(lines)


class RappWorkAgent(BasicAgent):  # type: ignore[misc]
    """Brainstem agent over the six RAPP Work SDK operations, with an exact-hash gate."""

    def __init__(self) -> None:
        self.name = "RappWork"
        self.metadata = {
            "name": self.name,
            "description": (
                "Reach the person's private RAPP Work workspaces through the RAPP Work SDK. "
                "Read-only: status, verify, discover. Changes: propose builds an SDK plan "
                "(scaffold a new workspace or organization, update a workspace's SDK "
                "integration files, or migrate a workspace to a new successor folder) and "
                "returns an exact summary with the full plan SHA-256; show it to the person "
                "verbatim. Nothing changes until the person replies in a later message with "
                "that full hash; only then call confirm, then apply, with exactly that hash. "
                "Never shorten, guess or invent a hash. undo withdraws a plan before apply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(ACTIONS),
                        "description": (
                            "status, verify and discover only read. propose asks the SDK for "
                            "a plan. confirm records a yes to one exact plan hash, given by the "
                            "person in a later message. apply runs a confirmed plan. undo "
                            "withdraws a plan that was not applied."
                        ),
                    },
                    "operation": {
                        "type": "string",
                        "enum": list(PLAN_OPERATIONS),
                        "description": "propose only: which SDK plan to build.",
                    },
                    "root": {
                        "type": "string",
                        "description": (
                            "Absolute folder path. status and verify: the folder to inspect. "
                            "propose scaffold: the new folder to create (it must not exist). "
                            "propose update: the workspace folder."
                        ),
                    },
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "discover: absolute folders to inventory as inert data.",
                    },
                    "max_entries": {
                        "type": "integer",
                        "description": "discover: optional bound on entries scanned (1-10000).",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["workspace", "organization"],
                        "description": "propose scaffold: what to create (default workspace).",
                    },
                    "owner_label": {
                        "type": "string",
                        "description": "propose scaffold: lowercase owner label, like example.",
                    },
                    "slug": {
                        "type": "string",
                        "description": "propose scaffold: lowercase name, like finance.",
                    },
                    "world_id": {
                        "type": "string",
                        "description": "propose scaffold: lowercase world id, like example-world.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["solo", "hive"],
                        "description": "propose scaffold: solo (default) or hive.",
                    },
                    "source": {
                        "type": "string",
                        "description": (
                            "propose migrate: absolute path of the existing workspace; it is "
                            "never changed."
                        ),
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "propose migrate: absolute path of the new successor folder; it "
                            "must not exist."
                        ),
                    },
                    "plan_sha256": {
                        "type": "string",
                        "description": (
                            "confirm, apply, undo and status: the exact full 64-character plan "
                            "hash from the proposal, as the person gave it."
                        ),
                    },
                },
                "required": ["action"],
            },
        }
        # When this request began, in the state's own event order (see "Later requests").
        self._clock = _clock_now()
        super().__init__(name=self.name, metadata=self.metadata)

    def perform(self, **kwargs: Any) -> str:
        try:
            arguments = _present(kwargs)
            action = arguments.pop("action", None)
            if action is None:
                return _usage()
            handlers = {
                "status": self._status,
                "verify": self._verify,
                "discover": self._discover,
                "propose": self._propose,
                "confirm": self._confirm,
                "apply": self._apply,
                "undo": self._undo,
            }
            if not isinstance(action, str) or action not in handlers:
                raise _Refusal(
                    "AGENT_REFUSE_ACTION",
                    f"unknown action {_clean(action, 60)}",
                    {"allowed": list(ACTIONS)},
                )
            return handlers[action](arguments)
        except _Refusal as refusal:
            return _refusal_text(refusal)
        except Exception as error:
            return _refusal_text(
                _Refusal(
                    "AGENT_REFUSE_INTERNAL",
                    f"unexpected {type(error).__name__}; this agent stopped before any further "
                    "step",
                    outcome=OUTCOME_UNKNOWN,
                )
            )

    # -- read-only ------------------------------------------------------------------------

    def _status(self, arguments: dict[str, Any]) -> str:
        _closed(arguments, ("root", "plan_sha256"), "status")
        if "root" in arguments and "plan_sha256" in arguments:
            raise _Refusal("AGENT_REFUSE_INPUT", "status takes a root or a plan_sha256, not both")
        if "plan_sha256" in arguments:
            return self._describe(_hash_input(arguments["plan_sha256"]))
        if "root" in arguments:
            root = _path_input(arguments["root"], "root")
            return _format_status(_call_sdk("status", {"root": root}), root)
        return self._overview()

    def _verify(self, arguments: dict[str, Any]) -> str:
        _closed(arguments, ("root",), "verify")
        if "root" not in arguments:
            raise _Refusal("AGENT_REFUSE_INPUT", "verify needs root, an absolute folder path")
        root = _path_input(arguments["root"], "root")
        return _format_verify(_call_sdk("verify", {"root": root}), root)

    def _discover(self, arguments: dict[str, Any]) -> str:
        _closed(arguments, ("roots", "root", "max_entries"), "discover")
        raw = arguments.get("roots", [])
        if "root" in arguments and isinstance(raw, list):
            raw = [*raw, arguments["root"]]
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_DISCOVER_ROOTS:
            raise _Refusal(
                "AGENT_REFUSE_INPUT",
                f"discover needs roots: 1 to {MAX_DISCOVER_ROOTS} absolute folder paths",
            )
        inputs: dict[str, Any] = {"roots": [_path_input(value, "roots") for value in raw]}
        if "max_entries" in arguments:
            maximum = arguments["max_entries"]
            if type(maximum) is not int or not 1 <= maximum <= 10_000:
                raise _Refusal(
                    "AGENT_REFUSE_INPUT", "max_entries must be an integer from 1 to 10000"
                )
            inputs["max_entries"] = maximum
        return _format_discover(_call_sdk("discover", inputs))

    def _overview(self) -> str:
        found = "not found"
        with contextlib.suppress(ImportError, ValueError, AttributeError):
            spec = importlib.util.find_spec("rapp_work")
            if spec is not None:
                reason = _shadow_reason(spec)
                found = "found (imported only when a verb needs it)"
                if reason is not None:
                    found = "REFUSED: " + reason
        lines = [f"RappWork agent {AGENT_VERSION} (newest Brainstem channel). RAPP Work SDK: {found}."]
        if found == "not found":
            lines.append(_install_text())
        where = _state_label()
        counts: dict[str, int] = {}
        open_lines: list[str] = []
        unreadable = others = 0
        with _state(create=False, lock=False) as handles:
            if handles is None:
                lines.append(f"State: {where} (nothing stored yet).")
                return "\n".join(lines)
            names, others = _record_names(handles[1])
            for digest in names:
                try:
                    record = _load_record(handles[1], digest)
                except _Refusal:
                    unreadable += 1
                    continue
                if record is None:
                    continue
                state = _record_state(record)
                counts[state] = counts.get(state, 0) + 1
                if state in {"proposed", "confirmed"} and len(open_lines) < MAX_LISTED:
                    open_lines.append(_record_line(digest, record))
        summary = ", ".join(f"{count} {state}" for state, count in sorted(counts.items()))
        lines.append(f"State: {where} - plans: {summary or 'none'}.")
        if unreadable or others:
            lines.append(f"Also ignored: {unreadable} unreadable record(s), {others} other entr(ies).")
        if open_lines:
            lines.append(
                "Open plans (not applied), by hash prefix only; a plan's full hash is shown only "
                "in its proposal:"
            )
            lines.extend(open_lines)
        return "\n".join(lines)

    def _describe(self, digest: str) -> str:
        with _state(create=False, lock=False) as handles:
            record = None if handles is None else _load_record(handles[1], digest)
        if record is None:
            raise _Refusal("AGENT_REFUSE_UNKNOWN_PLAN", "no stored plan has exactly this hash")
        lines = [f"RAPP Work plan {digest}: {_record_state(record)} ({record['operation']})."]
        lines.extend(_plan_lines(record["operation"], record["plan"]))
        for event in record["events"]:
            code = f" [{_clean(event['code'], 80)}]" if event["event"] == "apply-refused" else ""
            lines.append(f"  {_clean(event['utc'], 30)} {event['event']}{code}")
        return "\n".join(lines)

    # -- propose, confirm, apply, undo -----------------------------------------------------

    def _plan_inputs(self, operation: str, arguments: dict[str, Any]) -> dict[str, str]:
        _closed(arguments, ("operation", *PLAN_INPUT_KEYS[operation]), f"propose {operation}")
        inputs: dict[str, str] = {}
        if operation == "scaffold":
            missing = [key for key in ("root", "owner_label", "slug", "world_id") if key not in arguments]
            if missing:
                raise _Refusal(
                    "AGENT_REFUSE_INPUT",
                    "propose scaffold needs root, owner_label, slug and world_id",
                    {"missing": missing},
                )
            inputs["kind"] = _visible_text(arguments.get("kind", "workspace"), "kind")
            inputs["mode"] = _visible_text(arguments.get("mode", "solo"), "mode")
            for key in ("owner_label", "slug", "world_id"):
                inputs[key] = _visible_text(arguments[key], key)
        for key in PLAN_PATH_KEYS[operation]:
            if key not in arguments:
                raise _Refusal(
                    "AGENT_REFUSE_INPUT",
                    f"propose {operation} needs {' and '.join(PLAN_PATH_KEYS[operation])}",
                )
            inputs[key] = _path_input(arguments[key], key)
        return inputs

    def _propose(self, arguments: dict[str, Any]) -> str:
        operation = arguments.get("operation")
        if not isinstance(operation, str) or operation not in PLAN_OPERATIONS:
            raise _Refusal(
                "AGENT_REFUSE_INPUT",
                "propose needs operation: scaffold, update or migrate",
                {"allowed": list(PLAN_OPERATIONS)},
            )
        inputs = self._plan_inputs(operation, arguments)
        envelope = _call_sdk(operation, inputs)
        if envelope["status"] == "refused":
            return _sdk_refusal_text(envelope, "No plan was stored and nothing was changed.")
        result = envelope["result"]
        digest = result.get("plan_sha256")
        if (
            envelope["status"] != "planned"
            or result.get("effects") is not False
            or not isinstance(digest, str)
            or not _HEX64.fullmatch(digest)
        ):
            raise _Refusal("AGENT_REFUSE_SDK_RESPONSE", "the SDK did not return a plan and its hash")
        plan = _check_plan(operation, result.get("plan"), inputs)
        if not plan["actions"]:
            where = inputs.get("root") or inputs.get("target")
            return (
                "RAPP Work: nothing to propose. The SDK planned no file changes for "
                f"{_clean(where, 400)} (plan {digest}); nothing was stored or changed."
            )
        with _state(create=True, lock=True) as handles:
            if handles is None:
                raise _Refusal("AGENT_REFUSE_STATE", "the state folder could not be opened")
            records = handles[1]
            record = _load_record(records, digest)
            if record is not None and _record_state(record) == "applied":
                applied = _last_event(record, "applied")
                return (
                    f"RAPP Work: this exact plan ({digest}) was already applied at "
                    f"{_clean(applied.get('utc'), 30)}; nothing was stored or changed."
                )
            if record is None:
                self._check_bounds(records)
                record = {
                    "agent_version": AGENT_VERSION,
                    "events": [],
                    "inputs": inputs,
                    "operation": operation,
                    "plan": plan,
                    "plan_sha256": digest,
                    "plan_storage_sha256": _plan_storage_sha256(plan),
                    "schema": RECORD_SCHEMA,
                }
            _commit(handles, record, "proposed", keep=0)
        lines = ["RAPP Work: plan proposed by the RAPP Work SDK. Nothing has changed yet."]
        lines.extend(_plan_lines(operation, plan))
        lines.append(f"Plan SHA-256 (full): {digest}")
        lines.append(
            "Next: show this summary to the person. Only if they approve, they reply in a NEW "
            f"message: confirm {digest}"
        )
        lines.append(
            "After that reply, call confirm and then apply with that exact hash. To drop the "
            f"plan instead: undo {digest}"
        )
        lines.append(_undo_note(operation))
        return "\n".join(lines)

    @staticmethod
    def _check_bounds(records: int) -> None:
        names, _ = _record_names(records)
        if len(names) >= MAX_RECORDS:
            raise _Refusal(
                "AGENT_REFUSE_STATE_BOUND",
                "this agent already keeps the maximum number of plan records; records of applied "
                "or withdrawn plans are plain data you may delete from its state folder",
                {"limit": MAX_RECORDS},
            )
        open_plans = 0
        for name in names:
            try:
                other = _load_record(records, name)
            except _Refusal:
                continue
            if other is not None and _record_state(other) in {"proposed", "confirmed"}:
                open_plans += 1
        if open_plans >= MAX_OPEN_PLANS:
            raise _Refusal(
                "AGENT_REFUSE_STATE_BOUND",
                "too many plans are open; apply or withdraw some first (undo takes the full hash "
                "from a plan's proposal, and proposing an update or migration again shows it)",
                {"limit": MAX_OPEN_PLANS},
            )

    def _confirm(self, arguments: dict[str, Any]) -> str:
        _closed(arguments, ("plan_sha256",), "confirm")
        digest = _hash_input(arguments.get("plan_sha256"))
        with _state(create=False, lock=True) as handles:
            record = None if handles is None else _load_record(handles[1], digest)
            if handles is None or record is None:
                raise _Refusal("AGENT_REFUSE_UNKNOWN_PLAN", "no stored plan has exactly this hash")
            state = _record_state(record)
            if state == "applied":
                raise _Refusal("AGENT_REFUSE_ALREADY_APPLIED", "this plan was already applied")
            if state == "withdrawn":
                raise _Refusal(
                    "AGENT_REFUSE_WITHDRAWN", "this plan was withdrawn; propose it again first"
                )
            recent, total = _refused_count(record)
            if state == "confirmed" and not recent:
                return f"RAPP Work: plan {digest} is already confirmed. Next: apply {digest}"
            if self._clock is None:
                raise _Refusal(
                    "AGENT_REFUSE_STATE",
                    "this request could not read the state clock safely when it began, so it "
                    "cannot order a confirmation; check the state folder, then reply in a new "
                    "message",
                )
            if self._clock < record["events"][-1]["seq"]:
                latest = "refused apply" if recent else "proposal"
                raise _Refusal(
                    "AGENT_REFUSE_NOT_LATER_TURN",
                    f"this request began before the plan's latest {latest} was recorded, so it "
                    "cannot confirm it; the person must read the plan and reply in a new message "
                    "with the full hash",
                )
            _commit(handles, record, "confirmed", keep=1, plan_sha256=digest, refused=total)
        again = f" again ({recent} refused apply attempt(s) no longer count)" if recent else ""
        return (
            f"RAPP Work: plan {digest} confirmed{again}. Nothing has changed yet.\n"
            f"Next: apply {digest}. The SDK re-checks the whole plan, its exact hash and every "
            "precondition before its first write."
        )

    def _apply(self, arguments: dict[str, Any]) -> str:
        _closed(arguments, ("plan_sha256",), "apply")
        digest = _hash_input(arguments.get("plan_sha256"))
        warning = ""
        with _state(create=False, lock=True) as handles:
            record = None if handles is None else _load_record(handles[1], digest)
            if handles is None or record is None:
                raise _Refusal("AGENT_REFUSE_UNKNOWN_PLAN", "no stored plan has exactly this hash")
            state = _record_state(record)
            if state == "applied":
                raise _Refusal(
                    "AGENT_REFUSE_ALREADY_APPLIED",
                    "this plan was already applied; a plan is never applied twice",
                    {"applied_utc": _last_event(record, "applied").get("utc")},
                )
            if state == "withdrawn":
                raise _Refusal("AGENT_REFUSE_WITHDRAWN", "this plan was withdrawn with undo")
            if state != "confirmed":
                raise _Refusal(
                    "AGENT_REFUSE_NOT_CONFIRMED",
                    "this plan has not been confirmed; the person must reply in a later message "
                    "with its full hash first",
                )
            if (
                _last_event(record, "confirmed").get("plan_sha256") != digest
                or record["plan_sha256"] != digest
            ):
                raise _Refusal("AGENT_REFUSE_NOT_CONFIRMED", "the confirmation names another hash")
            recent, _ = _refused_count(record)
            if recent >= MAX_APPLY_ATTEMPTS:
                raise _Refusal(
                    "AGENT_REFUSE_ATTEMPTS",
                    f"the SDK refused this plan {recent} times since it was last confirmed. Check "
                    "the folder with status or verify and fix the cause; the person can then "
                    "confirm it again in a new message, which allows more attempts, or withdraw "
                    "it with undo",
                    {"limit": MAX_APPLY_ATTEMPTS},
                )
            operation = record["operation"]
            request = {
                **record["inputs"],
                "apply": True,
                "plan": _parse_json(_json_bytes(record["plan"])),
                "plan_sha256": digest,
            }
            envelope = _call_sdk(operation, request)
            if envelope["status"] == "refused":
                refusal = _sdk_refusal(envelope)
                code = _clean(refusal.get("code"), 80)
                try:
                    _commit(
                        handles,
                        record,
                        "apply-refused",
                        code=code,
                        message=_clean(refusal.get("message"), 300),
                    )
                except _Refusal as error:
                    warning = (
                        "\nWarning: this agent's record of the refusal may be incomplete "
                        f"({error.code})."
                    )
                return _sdk_refusal_text(envelope, _after_refused_apply(code, digest)) + warning
            result = envelope["result"]
            try:
                _commit(handles, record, "applied", result=_result_summary(result))
            except _Refusal as refusal:
                warning = (
                    "\nWarning: the SDK applied the plan, but this agent's record of it may be "
                    f"incomplete ({refusal.code}); check the folder with verify."
                )
        root = result.get("root") or result.get("target")
        lines = [
            f"RAPP Work: plan {digest} applied by the RAPP Work SDK "
            f"(status {_clean(result.get('status'), 40)}).",
            f"Folder: {_clean(root, 400)}",
            _verify_line(root),
            _undo_note(operation),
        ]
        return "\n".join(lines) + warning

    def _undo(self, arguments: dict[str, Any]) -> str:
        _closed(arguments, ("plan_sha256",), "undo")
        digest = _hash_input(arguments.get("plan_sha256"))
        with _state(create=False, lock=False) as handles:
            record = None if handles is None else _load_record(handles[1], digest)
        if record is None:
            raise _Refusal("AGENT_REFUSE_UNKNOWN_PLAN", "no stored plan has exactly this hash")
        if _record_state(record) == "applied":
            return self._undo_refusal(digest, record)
        with _state(create=False, lock=True) as handles:
            current = None if handles is None else _load_record(handles[1], digest)
            if handles is None or current is None:
                raise _Refusal("AGENT_REFUSE_UNKNOWN_PLAN", "no stored plan has exactly this hash")
            state = _record_state(current)
            if state == "withdrawn":
                return f"RAPP Work: plan {digest} was already withdrawn; nothing was changed."
            if state in {"proposed", "confirmed"}:
                _, total = _refused_count(current)
                _commit(handles, current, "withdrawn")
                text = (
                    f"RAPP Work: plan {digest} withdrawn. It can no longer be confirmed or "
                    "applied, and its record is kept."
                )
                if total:
                    text += (
                        f" The SDK refused {total} apply attempt(s) of it since its latest "
                        "proposal, and a refused apply can stop part-way; check the folder with "
                        "verify."
                    )
                return text
        return self._undo_refusal(digest, current)

    @staticmethod
    def _undo_refusal(digest: str, record: dict[str, Any]) -> str:
        operation = record["operation"]
        plan = record["plan"]
        actions = plan["actions"]
        creates = sum(1 for action in actions if action["operation"] == "create")
        replaces = len(actions) - creates
        lines = [
            "RAPP Work: REFUSED [AGENT_REFUSE_UNDO_AFTER_APPLY] this applied plan cannot be undone "
            "with RAPP Work SDK 1.0.0, and this agent never deletes or rewrites files.",
            f"Plan {digest} ({operation}) was applied at "
            f"{_clean(_last_event(record, 'applied').get('utc'), 30)}.",
        ]
        if operation == "scaffold":
            lines.append(
                f"What apply created: the folder {_clean(plan.get('target'), 400)} with "
                f"{creates} files:"
            )
        elif operation == "update":
            lines.append(
                f"What apply did in {_clean(plan.get('target'), 400)}: created {creates} and "
                f"replaced {replaces} SDK-owned file(s):"
            )
        else:
            lines.append(
                f"What apply created: the successor folder {_clean(plan.get('target'), 400)} with "
                f"{creates} planned files plus the SDK's migration receipt and recovery record. "
                f"The source {_clean(plan.get('source'), 400)} was not changed."
            )
        lines.extend(_action_lines(actions, past=True))
        lines.append(
            "Why it cannot be reversed: the SDK's only effects are create-only writes and "
            "exact-hash replacements of SDK-owned files (rapp-work-sdk/1 section 4); it has no "
            "delete operation, and source deletion is an explicit refusal (section 12). No SDK "
            "plan can express the inverse of this one."
        )
        if replaces:
            lines.append(
                "Restoring replaced files would need a plan the SDK does not build: update plans "
                "carry only the SDK's own current integration bytes, and the prior bytes of a "
                "replaced file are recorded only as a hash."
            )
        lines.append(
            "Nothing was changed by this undo request. Removing created files is a decision for "
            "you to make outside this agent; it never removes files."
        )
        lines.append(_verify_line(plan.get("target")))
        return "\n".join(lines)


if __name__ == "__main__":
    print(RappWorkAgent().perform())
