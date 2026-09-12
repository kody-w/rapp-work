from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "lib"))
from private_hive import client, keys, release
from private_hive.common import R, b64, canonical, digest, now, preparation
from private_hive.state import State

P = preparation()


class Fixture:
    def __init__(self, *, keyless_owner=False):
        parent = Path.cwd() / ".hive-test-work"
        parent.mkdir(exist_ok=True, mode=0o700)
        self.root = parent / ("case-" + uuid.uuid4().hex)
        self.root.mkdir(mode=0o700)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(mode=0o700)
        self.publisher = self.root / "publisher"
        self.channel_root = self.root / "publication"
        self.client = self.root / "client"
        self.output = self.root / "materialized"
        self.custody = self.root / "keys"
        self.key = keys.create(self.custody, "fictional-owner")
        scanner_key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"PUBLIC FICTIONAL SCANNER TEST VECTOR").digest())
        scanner = keys.OwnerKey("unused", scanner_key)
        self.scanner = keys.OwnerKey(R.mint_rappid("fictional-scanner", "pii", scanner.spki), scanner_key)
        self.member = R.mint_rappid("fictional-owner", "legacy-member") if keyless_owner else self.key.rappid
        self.workspace_id = R.mint_rappid("fictional-owner", "legacy-workspace")
        self.data = {
            "rappid.json": json.dumps({"rappid": self.workspace_id, "workspace_spec": "legacy-local/1", "mode": "solo"}).encode(),
            "safe/guide.txt": b"Generic fictional public instruction sheet.\n",
            "safe/tool.py": b"raise RuntimeError('Published data MUST NOT execute')\n",
            "private/GODD-secret.txt": b"FICTIONAL PRIVATE SENTINEL: do not publish this selected sealed slice.\n",
        }
        for name, raw in self.data.items():
            path = self.workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        P.command_migrate(self.args(workspace=str(self.workspace), member_rappid=self.member,
                                   hive_name="fixture-hive", world_id="fictional-world"))
        P.command_trust_scanner(self.args(workspace=str(self.workspace), scanner_rappid=self.scanner.rappid,
                                         spki_sha256=digest(self.scanner.spki)))
        self.prepared = P.read_json(self.workspace / ".rapp-hive" / "state.json")
        self.channels = [{"id": "fixture-store", "kind": "filesystem", "role": "authority", "path": str(self.channel_root)}]

    @staticmethod
    def args(**values):
        return SimpleNamespace(**values)

    def close(self):
        shutil.rmtree(self.root)

    def receipt(self, path, *, stamp=None):
        unsigned = {"schema": "rapp-pii-scan/1", "file_sha256": digest((self.workspace / path).read_bytes()),
                    "result": "none", "scanner_rappid": self.scanner.rappid, "scanner_version": "fictional-fixture/1",
                    "scanned_utc": stamp or now(), "spki_der_b64": b64(self.scanner.spki)}
        receipt = self.scanner.signed(unsigned)
        destination = self.root / ("scan-" + uuid.uuid4().hex + ".json")
        destination.write_bytes(canonical(receipt))
        return destination

    def select(self, path="safe/guide.txt", *, data_class="dogg", stamp=None):
        sealed = data_class == "godd"
        receipt = None if sealed else self.receipt(path, stamp=stamp)
        return P.command_select(self.args(workspace=str(self.workspace), path=path, data_class=data_class,
                                          room="private" if sealed else "general", protection=None,
                                          pii_evidence=str(receipt) if receipt is not None else None))

    def stage(self):
        result = P.command_stage(self.args(workspace=str(self.workspace), outbox=str(self.root / "outbox")))
        self.stage_root = Path(result["outbox"])
        return result

    def init(self, directory=None):
        return release.initialize(self.workspace, directory or self.publisher, self.key, self.channels,
                                  adopt_prepared_owner=self.member if self.member != self.key.rappid else None)

    def build(self, directory=None, **kwargs):
        return release.build(directory or self.publisher, self.key, self.stage_root, **kwargs)

    def frozen(self, plan_hash, directory=None):
        state = State(directory or self.publisher, "publisher")
        with state.transaction() as db:
            return State.release(db, plan_hash)

    def publish(self, plan_hash, directory=None, **kwargs):
        directory = directory or self.publisher
        release.approve(directory, self.key, plan_hash)
        return release.publish(directory, self.key, plan_hash, **kwargs)

    def init_client(self, directory=None):
        anchor = release.export_anchor(self.publisher)
        return client.initialize(directory or self.client, canonical(anchor), expected_spki_sha256=digest(self.key.spki))

    def original_bytes(self):
        return {name: (self.workspace / name).read_bytes() for name in self.data}

    def first_release(self, *, selected=True, pending=False):
        if selected:
            self.select()
        if pending:
            self.select("private/GODD-secret.txt", data_class="godd")
        self.stage()
        self.init()
        return self.build()


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.close)
