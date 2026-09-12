from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .common import R, b64, canonical, digest, exact_keys, no_symlinks, parse, private_directory, read_file, require, sync_directory, unb64, write_file


@dataclass(frozen=True)
class OwnerKey:
    rappid: str
    private: Ed25519PrivateKey
    directory: Path | None = None

    @property
    def spki(self) -> bytes:
        return self.private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    def sign(self, value: dict) -> str:
        header = canonical({"alg": "EdDSA", "b64": False, "crit": ["b64"], "kid": self.rappid})
        protected = base64.urlsafe_b64encode(header).rstrip(b"=")
        signature = self.private.sign(protected + b"." + canonical(value))
        return protected.decode("ascii") + ".." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    def signed(self, value: dict) -> dict:
        require("sig" not in value, "refuse signing an already signed document")
        return {**value, "sig": self.sign(value)}


def create(directory: Path, owner_label: str, slug: str = "owner") -> OwnerKey:
    # Validate labels before creating custody. Never generate into an existing directory.
    require(os.name == "posix", "POSIX custody is required; unsupported host refused before effects")
    require(isinstance(owner_label, str) and isinstance(slug, str)
            and R.rappid_valid(f"rappid:@{owner_label}/{slug}:" + "0" * 64), "invalid owner label or slug")
    directory = no_symlinks(Path(directory))
    require(not directory.exists(), "key directory already exists; load it, never remint")
    require(directory.parent.is_dir(), "key parent must already exist")
    directory.mkdir(mode=0o700)
    private_directory(directory)
    private = Ed25519PrivateKey.generate()
    spki = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    key = OwnerKey(R.mint_rappid(owner_label, slug, spki), private)
    pkcs8 = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption())
    write_file(directory / "owner.pk8.pem", pkcs8, immutable=True)
    record = {"schema": "rapp-private-hive-key/1", "owner_rappid": key.rappid,
              "spki_der_b64": b64(spki), "spki_sha256": digest(spki)}
    write_file(directory / "identity.json", canonical(record), immutable=True)
    sync_directory(directory)
    return load(directory, expected_rappid=key.rappid)


def load(directory: Path, *, expected_rappid: str | None = None) -> OwnerKey:
    directory = private_directory(Path(directory))
    require({path.name for path in directory.iterdir()} == {"owner.pk8.pem", "identity.json"},
            "incomplete or ambiguous custody; refusing key creation or repair")
    record = parse(read_file(directory / "identity.json", private=True))
    exact_keys(record, {"schema", "owner_rappid", "spki_der_b64", "spki_sha256"}, "key identity")
    require(record["schema"] == "rapp-private-hive-key/1", "wrong key identity schema")
    encoded = read_file(directory / "owner.pk8.pem", private=True, limit=4096)
    require(encoded.startswith(b"-----BEGIN PRIVATE KEY-----\n"), "unencrypted PKCS8 PEM required")
    private = serialization.load_pem_private_key(encoded, password=None)
    require(isinstance(private, Ed25519PrivateKey), "only explicit Ed25519 owner custody is supported")
    key = OwnerKey(record["owner_rappid"], private, directory)
    require(R.rappid_valid(key.rappid), "invalid owner RAPPID")
    require(unb64(record["spki_der_b64"]) == key.spki and record["spki_sha256"] == digest(key.spki),
            "owner identity/SPKI mismatch")
    require(R.rappid_parts(key.rappid)["hash"] == R.Hb("rapp/1:rappid", key.spki),
            "owner key does not bind the existing RAPPID")
    if expected_rappid is not None:
        require(key.rappid == expected_rappid, "owner mismatch; rotation is unsupported")
    return key


def verify_signed(value: dict, owner_rappid: str, spki: bytes):
    require(isinstance(value, dict) and "sig" in value, "signed document required")
    require(isinstance(serialization.load_der_public_key(spki), Ed25519PublicKey), "Ed25519 anchor required")
    ok, why = R.verify_detached_jws({key: item for key, item in value.items() if key != "sig"},
                                   value["sig"], spki, owner_rappid)
    require(ok, "signature refused: " + why)


def verify_anchor(raw: bytes) -> dict:
    anchor = parse(raw, "owner anchor")
    exact_keys(anchor, {"schema", "owner_rappid", "spki_der_b64", "spki_sha256", "hive_rappid",
                        "world_id", "genesis_frame_hash", "registry_seq", "registry_hash", "sig"},
               "owner anchor")
    require(anchor["schema"] == "rapp-private-hive-owner-anchor/1", "wrong owner anchor schema")
    require(R.rappid_valid(anchor["hive_rappid"]), "invalid anchored Hive identity")
    spki = unb64(anchor["spki_der_b64"])
    require(digest(spki) == anchor["spki_sha256"], "anchor SPKI hash mismatch")
    require(anchor["registry_seq"] == 1 and not isinstance(anchor["registry_seq"], bool),
            "direct-owner MVP anchors start at registry sequence 1")
    from .common import H, hex64
    H.label(anchor["world_id"], "anchor world")
    hex64(anchor["genesis_frame_hash"])
    hex64(anchor["registry_hash"])
    verify_signed(anchor, anchor["owner_rappid"], spki)
    return anchor
