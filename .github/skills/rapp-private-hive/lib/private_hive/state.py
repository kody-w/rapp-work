from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat

from .common import canonical, locked, no_symlinks, parse, private_directory, require


class State:
    def __init__(self, directory: Path, role: str, *, create=False):
        require(role in {"publisher", "client"}, "unknown state role")
        self.root = private_directory(Path(directory), create=create)
        self.role = role
        self.path = self.root / "state.sqlite3"
        for suffix in ("", "-journal", "-wal", "-shm"):
            file = no_symlinks(Path(str(self.path) + suffix))
            if file.exists():
                info = file.stat()
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                        and stat.S_IMODE(info.st_mode) == 0o600, "unsafe SQLite state")
        if not self.path.exists():
            require(create, "state database is missing; explicit initialization is required")
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS releases (
                    plan_hash TEXT PRIMARY KEY, input_hash TEXT NOT NULL UNIQUE, plan BLOB NOT NULL,
                    pointer BLOB NOT NULL, approval BLOB, complete INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS release_files (
                    plan_hash TEXT NOT NULL, path TEXT NOT NULL, content BLOB NOT NULL,
                    PRIMARY KEY(plan_hash, path)
                );
                CREATE TABLE IF NOT EXISTS publications (
                    plan_hash TEXT NOT NULL, channel TEXT NOT NULL, receipt BLOB NOT NULL,
                    PRIMARY KEY(plan_hash, channel)
                );
                CREATE TABLE IF NOT EXISTS intents (
                    plan_hash TEXT NOT NULL, channel TEXT NOT NULL, value BLOB NOT NULL,
                    PRIMARY KEY(plan_hash, channel)
                );
            """)
            present = self.get(db, "role")
            require(present is None or present == {"role": role}, "state belongs to a different role")
            self.set(db, "role", {"role": role})

    @contextmanager
    def transaction(self):
        with locked(self.root / ".state.lock"):
            db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            try:
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("BEGIN IMMEDIATE")
                yield db
                if db.in_transaction:
                    db.commit()
            except BaseException:
                if db.in_transaction:
                    db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def get(db, key):
        row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return parse(bytes(row[0])) if row else None

    @staticmethod
    def set(db, key, value):
        db.execute("INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, canonical(value)))

    def snapshot(self):
        with self.transaction() as db:
            return {key: parse(bytes(value)) for key, value in db.execute("SELECT key,value FROM metadata")}

    @staticmethod
    def readonly_snapshot(directory: Path):
        root = private_directory(Path(directory))
        path = no_symlinks(root / "state.sqlite3")
        from .common import read_file
        read_file(path, private=True, limit=512 * 1024 * 1024)
        # A process may die with a hot rollback journal. SQLite must open the
        # existing database read-write to recover it before any read-only view.
        # The state lock serializes recovery; missing state is never created.
        with locked(root / ".state.lock"):
            db = sqlite3.connect(path, timeout=30, isolation_level=None)
            try:
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("BEGIN IMMEDIATE")
                values = {
                    key: parse(bytes(value))
                    for key, value in db.execute("SELECT key,value FROM metadata")
                }
                db.rollback()
                return values
            finally:
                db.close()

    @staticmethod
    def release(db, plan_hash):
        row = db.execute("SELECT plan,pointer,approval,complete FROM releases WHERE plan_hash=?", (plan_hash,)).fetchone()
        require(row is not None, "unknown frozen release plan")
        files = {path: bytes(content) for path, content in
                 db.execute("SELECT path,content FROM release_files WHERE plan_hash=? ORDER BY path", (plan_hash,))}
        return {"plan": parse(bytes(row[0])), "pointer": bytes(row[1]),
                "approval": parse(bytes(row[2])) if row[2] is not None else None,
                "complete": bool(row[3]), "files": files}
