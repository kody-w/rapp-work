from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from ..common import MAX_ARTIFACT_BYTES, MAX_ARTIFACTS, MAX_BUNDLE_BYTES, canonical, digest, exact_keys, no_symlinks, now, private_directory, read_file, require, timestamp
from .filesystem import publication_path


OID = re.compile(r"^[0-9a-f]{40}$")


def validate_evidence(evidence: dict, config: dict) -> dict:
    exact_keys(evidence, {"schema", "checked_utc", "repository", "actor"}, "GitHub privacy evidence")
    require(evidence["schema"] == "rapp-private-hive-github-evidence/1", "wrong privacy evidence schema")
    checked = datetime.strptime(timestamp(evidence["checked_utc"]), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - checked).total_seconds()
    require(-30 <= age <= 300, "GitHub privacy evidence is stale or from the future")
    repository, actor = evidence["repository"], evidence["actor"]
    exact_keys(repository, {"id", "full_name", "owner_id", "private", "visibility", "fork", "archived", "disabled"},
               "GitHub repository evidence")
    exact_keys(actor, {"id", "login"}, "GitHub actor evidence")
    require(type(repository["id"]) is int and repository["id"] == config["repository_id"]
            and type(repository["owner_id"]) is int and repository["owner_id"] == config["owner_id"]
            and repository["full_name"] == config["repository"], "GitHub repository/owner identity mismatch")
    require(repository["private"] is True and repository["visibility"] == "private"
            and repository["fork"] is False and repository["archived"] is False and repository["disabled"] is False,
            "GitHub repository must be private, nonfork, nonarchived and enabled")
    require(type(actor["id"]) is int and actor["id"] == config["actor_id"]
            and actor["login"] == config["actor_login"], "GitHub authenticated actor mismatch")
    return evidence


class GitHubCLI:
    """Use gh's authenticated API, without accepting repository names as privacy evidence."""

    def __call__(self, config):
        def api(endpoint):
            try:
                process = subprocess.run(["gh", "api", "--hostname", "github.com", endpoint],
                                         check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            except (OSError, subprocess.SubprocessError) as error:
                raise ValueError("GitHub CLI privacy evidence unavailable") from error
            require(len(process.stdout) <= MAX_ARTIFACT_BYTES, "GitHub evidence byte limit")
            return json.loads(process.stdout)
        repo, actor = api("repos/" + config["repository"]), api("user")
        return {"schema": "rapp-private-hive-github-evidence/1", "checked_utc": now(),
                "repository": {"id": repo["id"], "full_name": repo["full_name"], "owner_id": repo["owner"]["id"],
                               "private": repo["private"], "visibility": repo["visibility"], "fork": repo["fork"],
                               "archived": repo["archived"], "disabled": repo["disabled"]},
                "actor": {"id": actor["id"], "login": actor["login"]}}

    def token(self):
        try:
            result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("GitHub CLI credential unavailable") from error
        token = result.stdout.strip().decode("ascii")
        require(token and len(token) <= 4096 and not any(char.isspace() for char in token), "invalid GitHub credential")
        return token


class GitSession:
    def __init__(self, root, remote, *, local=False, token=None):
        self.root, self.remote = root, remote
        self.env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM="/dev/null", GIT_CONFIG_GLOBAL="/dev/null",
                        GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1", GIT_ATTR_NOSYSTEM="1",
                        GIT_PAGER="cat", GIT_CEILING_DIRECTORIES=str(root.parent), LC_ALL="C")
        if token:
            authorization = base64.b64encode(("x-access-token:" + token).encode()).decode()
            self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                            GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + authorization)
        self.prefix = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                       "-c", "commit.gpgSign=false", "-c", "protocol.allow=never",
                       "-c", "protocol.https.allow=always", "-c", "credential.helper=",
                       "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "fetch.writeCommitGraph=false"]
        if local:
            self.prefix += ["-c", "protocol.file.allow=always"]
        self.run("init", "--quiet", "--bare", "--object-format=sha1", "--template=", "--initial-branch=hive", str(root),
                 bare=False)
        self.config_bytes = read_file(root / "config")

    def run(self, *args, data=None, bare=True, env=None, limit=MAX_BUNDLE_BYTES):
        if bare:
            require(read_file(self.root / "config") == self.config_bytes, "isolated Git config changed")
        command = self.prefix + (["--git-dir=" + str(self.root)] if bare else []) + list(args)
        try:
            result = subprocess.run(command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=self.root.parent, env=env or self.env, check=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("isolated Git operation refused or CAS failed") from error
        require(len(result.stdout) <= limit, "Git output byte limit")
        return result.stdout

    def ref(self, ref):
        output = self.run("ls-remote", "--refs", self.remote, ref).decode("ascii").strip()
        if not output:
            return None
        lines = output.splitlines()
        require(len(lines) == 1, "ambiguous Git ref")
        oid, name = lines[0].split("\t")
        require(OID.fullmatch(oid) and name == ref, "unexpected remote ref")
        return oid

    def fetch(self, oid):
        require(isinstance(oid, str) and OID.fullmatch(oid), "expected old Git OID is invalid")
        self.run("fetch", "--quiet", "--depth=1", "--no-tags", "--no-write-fetch-head", self.remote, oid)
        require(self.run("cat-file", "-t", oid).strip() == b"commit", "Git ref does not identify a commit")

    def tree(self, oid):
        raw = self.run("ls-tree", "-rz", "--full-tree", oid)
        entries = {}
        for record in raw.split(b"\0"):
            if not record:
                continue
            fields, name = record.split(b"\t", 1)
            mode, kind, address = fields.decode("ascii").split(" ")
            path = name.decode("utf-8")
            require(mode == "100644" and kind == "blob", "Git executable, symlink, tree anomaly or submodule refused")
            require(path == "refs/current.json" or publication_path(path), "unmanaged remote path")
            require(path not in entries, "duplicate Git tree path")
            entries[path] = address
        require(len(entries) <= MAX_ARTIFACTS + 1, "Git tree artifact limit")
        return entries

    def read(self, oid, path):
        require(path == "refs/current.json" or publication_path(path), "invalid Git artifact path")
        size = int(self.run("cat-file", "-s", oid + ":" + path, limit=64))
        require(0 <= size <= MAX_ARTIFACT_BYTES, "Git artifact byte limit")
        return self.run("cat-file", "blob", oid + ":" + path, limit=MAX_ARTIFACT_BYTES)

    def commit(self, files, parent, stamp):
        tree = {}
        for path, data in sorted(files.items()):
            address = self.run("hash-object", "-w", "--stdin", data=data, limit=128).strip().decode("ascii")
            node = tree
            parts = path.split("/")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
                require(isinstance(node, dict), "Git path collision")
            require(parts[-1] not in node, "Git duplicate path")
            node[parts[-1]] = address

        def make(node):
            rows = []
            for name, entry in node.items():
                folder = isinstance(entry, dict)
                oid = make(entry) if folder else entry
                rows.append((name + ("/" if folder else ""), ("040000 tree " if folder else "100644 blob ")
                             + oid + "\t" + name + "\0"))
            raw = "".join(row for _, row in sorted(rows)).encode("utf-8")
            return self.run("mktree", "-z", data=raw, limit=128).strip().decode("ascii")

        tree_oid = make(tree)
        epoch = int(datetime.strptime(timestamp(stamp), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp())
        env = {**self.env, "GIT_AUTHOR_NAME": "Private Hive owner", "GIT_AUTHOR_EMAIL": "private-hive@example.invalid",
               "GIT_COMMITTER_NAME": "Private Hive owner", "GIT_COMMITTER_EMAIL": "private-hive@example.invalid",
               "GIT_AUTHOR_DATE": f"{epoch} +0000", "GIT_COMMITTER_DATE": f"{epoch} +0000"}
        args = ["commit-tree", tree_oid] + (["-p", parent] if parent is not None else [])
        return self.run(*args, data=b"Approved immutable Private Hive release\n", env=env, limit=128).strip().decode()


class GitHubGit:
    def __init__(self, config: dict, state_directory: Path, *, evidence_provider=None, remote_override: Path | None = None):
        from ..authority import validate_channels
        validate_channels([{**config, "role": "authority"}])
        require(config["kind"] == "github", "private GitHub adapter only")
        self.config, self.state_directory = dict(config), no_symlinks(Path(state_directory))
        self.provider = evidence_provider or GitHubCLI()
        self.remote_override = no_symlinks(Path(remote_override)) if remote_override is not None else None
        require(remote_override is None or evidence_provider is not None, "local Git test transport requires explicit evidence injection")

    def privacy(self):
        return validate_evidence(self.provider(dict(self.config)), self.config)

    @contextmanager
    def session(self):
        self.privacy()
        root = private_directory(self.state_directory, create=True)
        working = root / ("git-session-" + uuid.uuid4().hex)
        working.mkdir(mode=0o700)
        try:
            token = self.provider.token() if hasattr(self.provider, "token") else None
            require(token is not None or self.remote_override is not None,
                    "real GitHub transport requires an authenticated credential provider")
            remote = str(self.remote_override) if self.remote_override is not None else (
                "https://github.com/" + self.config["repository"] + ".git")
            yield GitSession(working, remote, local=self.remote_override is not None, token=token)
        finally:
            shutil.rmtree(working)

    @contextmanager
    def snapshot(self):
        with self.session() as git:
            oid = git.ref(self.config["ref"])
            require(oid is not None, "GitHub channel has no published ref")
            git.fetch(oid)
            entries = git.tree(oid)
            require("refs/current.json" in entries, "GitHub channel has no current pointer")
            yield lambda path: git.read(oid, path), oid

    def publish(self, files, pointer, *, expected_pointer, expected_ref, intent=None, save_intent=None,
                fault=None, created_utc=None):
        require(expected_ref == "absent" or (isinstance(expected_ref, str) and OID.fullmatch(expected_ref)),
                "explicit expected old Git OID or 'absent' required")
        require(save_intent is not None, "durable Git CAS intent callback required")
        for path in files:
            publication_path(path)
        expected_oid = None if expected_ref == "absent" else expected_ref
        desired_files = {**files, "refs/current.json": pointer}
        with self.session() as git:
            actual_oid = git.ref(self.config["ref"])
            recovering = intent is not None and actual_oid == intent.get("ref")
            require(actual_oid == expected_oid or recovering, "Git expected ref CAS conflict")
            if actual_oid is not None:
                git.fetch(actual_oid)
                tree = git.tree(actual_oid)
                previous = git.read(actual_oid, "refs/current.json")
                if recovering:
                    require(previous == pointer and set(tree) == set(desired_files)
                            and all(git.read(actual_oid, path) == raw for path, raw in desired_files.items()),
                            "Git recovery read-back mismatch")
                    return {"pointer_sha256": digest(pointer), "ref": actual_oid}
                require(digest(previous) == expected_pointer, "Git current pointer does not match approved base")
                for path, oid in tree.items():
                    if path == "refs/current.json":
                        continue
                    require(path in files and hashlib.sha1(b"blob " + str(len(files[path])).encode() + b"\0" + files[path]).hexdigest() == oid,
                            "Git prior immutable content differs or would be lost")
            else:
                require(expected_pointer is None, "Git channel lost its existing authority")
            desired_oid = git.commit(desired_files, expected_oid, created_utc)
            save_intent({"ref": desired_oid, "pointer_sha256": digest(pointer)})
            if fault:
                fault("before-cas")
            self.privacy()
            git.run("push", "--quiet", "--porcelain",
                    "--force-with-lease=" + self.config["ref"] + ":" + (expected_oid or ""),
                    git.remote, desired_oid + ":" + self.config["ref"])
            if fault:
                fault("after-cas")
            require(git.ref(self.config["ref"]) == desired_oid, "Git publication ref read-back mismatch")
            return {"pointer_sha256": digest(pointer), "ref": desired_oid}
