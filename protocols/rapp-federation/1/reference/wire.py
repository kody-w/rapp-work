"""Bounded RAPP/1 wire and Ed25519 primitives; no network or sibling imports."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature, InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


UINT53 = (1 << 53) - 1
MAX_BYTES = 1 << 20
MAX_PLAINTEXT = 65536
FRAME_KEYS = frozenset({
    "spec", "kind", "stream_id", "seq", "utc", "payload", "payload_hash",
    "frame_hash", "prev", "prev_wave", "sig",
})
RAPPID = re.compile(
    r"rappid:@([a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"([a-z0-9]+(?:-[a-z0-9]+)*):([0-9a-f]{64})"
)
HEX = re.compile(r"[0-9a-f]{64}")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


class Refusal(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(code + (": " + detail if detail else ""))


def require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise Refusal(code, detail)


def exact(value, keys, code="shape"):
    require(type(value) is dict and set(value) == set(keys), code)
    return value


def canonical(value) -> bytes:
    """RFC 8785's exact-integer subdomain, the only numeric domain here."""
    def render(item, depth):
        require(depth <= 64, "json-depth")
        if item is None or type(item) is bool:
            return json.dumps(item)
        if type(item) is int:
            require(abs(item) <= UINT53, "json-integer")
            return str(item)
        if type(item) is str:
            require(not any(0xD800 <= ord(char) <= 0xDFFF for char in item), "json-surrogate")
            require(unicodedata.normalize("NFC", item) == item, "json-nfc")
            return json.dumps(item, ensure_ascii=False)
        if type(item) is list:
            return "[" + ",".join(render(child, depth + 1) for child in item) + "]"
        if type(item) is dict:
            require(all(type(key) is str for key in item), "json-key")
            for key in item:
                render(key, depth)
            keys = sorted(item, key=lambda key: key.encode("utf-16-be"))
            return "{" + ",".join(render(key, depth) + ":" + render(item[key], depth + 1)
                                   for key in keys) + "}"
        raise Refusal("json-type", type(item).__name__)

    result = render(value, 1).encode("utf-8")
    require(len(result) <= MAX_BYTES, "json-size")
    return result


def loads(raw: bytes):
    require(type(raw) is bytes and len(raw) <= MAX_BYTES, "json-size")
    require(not raw.startswith(b"\xef\xbb\xbf"), "json-bom")

    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, "json-duplicate-key")
            result[key] = value
        return result

    def noninteger(_):
        raise Refusal("json-number", "only exact uint53/integer tokens are supported")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_float=noninteger, parse_constant=noninteger)
        canonical(value)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise Refusal("json-invalid") from error
    return value


def H(space: str, value) -> str:
    require(space in {"rapp/1:particle", "rapp/1:wave", "rapp/1:egg-manifest",
                      "rapp/1:sealed-aad"}, "hash-domain")
    return hashlib.sha256(space.encode("ascii") + b"\n" + canonical(value)).hexdigest()


def Hb(space: str, raw: bytes) -> str:
    require(space in {"rapp/1:rappid", "rapp/1:egg", "rapp/1:seal"}, "hash-domain")
    require(type(raw) is bytes, "hash-bytes")
    return hashlib.sha256(space.encode("ascii") + b"\n" + raw).hexdigest()


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def unb64(text: str) -> bytes:
    require(type(text) is str and bool(re.fullmatch(r"[A-Za-z0-9_-]+", text)), "base64url")
    try:
        raw = base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)
    except ValueError as error:
        raise Refusal("base64url") from error
    require(b64(raw) == text, "base64url")
    return raw


def valid_rappid(value) -> bool:
    match = RAPPID.fullmatch(value) if type(value) is str else None
    return bool(match and len(match[1]) <= 39 and len(match[2]) <= 100)


def memory_owner(value):
    if type(value) is not str:
        return None
    owner, separator, instance = value.rpartition(":")
    return owner if (separator and valid_rappid(owner) and 1 <= len(instance) <= 64
                     and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", instance)) else None


def spki_bytes(key) -> bytes:
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def load_spki(der: bytes):
    try:
        key = serialization.load_der_public_key(der)
        require(spki_bytes(key) == der, "key-noncanonical")
        return key
    except (TypeError, ValueError, UnsupportedAlgorithm) as error:
        if isinstance(error, Refusal):
            raise
        raise Refusal("key-invalid") from error


def keyed_rappid(owner: str, slug: str, spki: bytes) -> str:
    identity = f"rappid:@{owner}/{slug}:{Hb('rapp/1:rappid', spki)}"
    require(valid_rappid(identity), "rappid")
    return identity


def stamp_ms(stamp: str) -> int:
    require(type(stamp) is str and bool(UTC.fullmatch(stamp)), "utc")
    try:
        parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise Refusal("utc") from error
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


def https_locator(value: str, *, require_chat=False) -> bool:
    if type(value) is not str or "\\" in value or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme == "https" and parsed.hostname
                    and not parsed.username and not parsed.password
                    and not parsed.query and not parsed.fragment
                    and (not require_chat or parsed.path.endswith("/chat"))
                    and (parsed.port is None or 0 < parsed.port <= 65535))
    except ValueError:
        return False


def chat_url(value: str) -> bool:
    return https_locator(value, require_chat=True)


def signature_header(signature: str):
    parts = signature.split(".") if type(signature) is str else []
    require(len(parts) == 3 and parts[1] == "", "signature-format")
    raw = unb64(parts[0])
    header = exact(loads(raw), {"alg", "b64", "crit", "kid"}, "signature-header")
    require(canonical(header) == raw, "signature-header-canonical")
    require(header["alg"] == "EdDSA" and header["b64"] is False
            and header["crit"] == ["b64"] and valid_rappid(header["kid"]), "signature-header")
    signature_bytes = unb64(parts[2])
    require(len(signature_bytes) == 64, "signature-length")
    return header["kid"], parts[0], signature_bytes


def sign(value: dict, identity: str, private_key) -> str:
    protected = b64(canonical({"alg": "EdDSA", "b64": False, "crit": ["b64"], "kid": identity}))
    return protected + ".." + b64(private_key.sign(protected.encode("ascii") + b"." + canonical(value)))


def verify_signature(value: dict, signature: str, keys: dict[str, bytes], expected=None) -> str:
    kid, protected, raw = signature_header(signature)
    require(expected is None or kid == expected, "signer")
    require(kid in keys, "unknown-key")
    der = keys[kid]
    require(Hb("rapp/1:rappid", der) == kid.rsplit(":", 1)[1], "key-binding")
    try:
        key = load_spki(der)
        require(isinstance(key, Ed25519PublicKey), "key-type")
        key.verify(raw, protected.encode("ascii") + b"." + canonical(value))
    except InvalidSignature as error:
        raise Refusal("signature-invalid") from error
    except (TypeError, ValueError) as error:
        if isinstance(error, Refusal):
            raise
        raise Refusal("key-invalid") from error
    return kid


def unsigned(value: dict) -> dict:
    return {key: child for key, child in value.items() if key != "sig"}


def build_frame(kind, stream, utc, payload, *, previous=None):
    frame = {
        "spec": "rapp/1", "kind": kind, "stream_id": stream,
        "seq": 0 if previous is None else previous["seq"] + 1,
        "utc": utc, "payload": payload, "payload_hash": H("rapp/1:particle", payload),
        "prev": None if previous is None else previous["payload_hash"],
        "prev_wave": None, "sig": None,
    }
    frame["frame_hash"] = H("rapp/1:wave", unsigned(frame))
    return frame


def verify_frame(frame: dict, keys: dict[str, bytes]) -> str:
    exact(frame, FRAME_KEYS, "frame-eleven-keys")
    canonical(frame)
    require(frame["spec"] == "rapp/1", "frame-spec")
    require(type(frame["seq"]) is int and 0 <= frame["seq"] <= UINT53, "frame-seq")
    require(memory_owner(frame["stream_id"]) is not None, "frame-memory-stream")
    require(type(frame["kind"]) is str and bool(re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*", frame["kind"])), "frame-kind")
    stamp_ms(frame["utc"])
    require(type(frame["payload"]) is dict, "frame-payload")
    require(frame["prev_wave"] is None, "frame-prev-wave")
    for field in ("payload_hash", "frame_hash"):
        require(type(frame[field]) is str and bool(HEX.fullmatch(frame[field])), "frame-hash-shape")
    require(frame["prev"] is None or type(frame["prev"]) is str
            and bool(HEX.fullmatch(frame["prev"])), "frame-prev")
    require(frame["payload_hash"] == H("rapp/1:particle", frame["payload"]), "payload-hash")
    preimage = {key: child for key, child in frame.items() if key not in {"frame_hash", "sig"}}
    require(frame["frame_hash"] == H("rapp/1:wave", preimage), "frame-hash")
    return verify_signature(unsigned(frame), frame["sig"], keys)


def verify_chain(frame: dict, head: dict | None, genesis_hash: str) -> None:
    if head is None:
        require(frame["seq"] == 0 and frame["prev"] is None
                and frame["frame_hash"] == genesis_hash, "frame-genesis")
    else:
        require(frame["stream_id"] == head["stream_id"] and frame["seq"] == head["seq"] + 1
                and frame["prev"] == head["payload_hash"] and frame["utc"] >= head["utc"],
                "frame-chain")


def plaintext_commitment(dek: bytes, plaintext: bytes) -> str:
    require(type(dek) is bytes and len(dek) == 32, "dek")
    prk = hmac.new(b"\0" * 32, dek, hashlib.sha256).digest()
    commitment_key = hmac.new(prk, b"rapp/1:sealed-commitment\x01", hashlib.sha256).digest()
    return hmac.new(commitment_key, plaintext, hashlib.sha256).hexdigest()


def sealed_aad(manifest):
    payload = manifest["payload"]
    return {
        "schema": payload["schema"], "artifact_rappid": manifest["rappid"],
        "created_utc": manifest["created_utc"], "key_id": payload["key_id"],
        "plaintext_commitment": payload["plaintext_commitment"],
        "plaintext_bytes": payload["plaintext_bytes"], "media_type": payload["media_type"],
    }


def pack_sealed(manifest: dict, ciphertext: bytes) -> bytes:
    class Utf8Info(zipfile.ZipInfo):
        def _encodeFilenameFlags(self):
            return self.filename.encode("utf-8"), self.flag_bits | 0x800

    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_STORED) as archive:
        for path, raw in (("manifest.json", canonical(manifest)), ("ciphertext.bin", ciphertext)):
            info = Utf8Info(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, raw)
    return result.getvalue()


def inspect_sealed(blob: bytes, address: str, keys: dict[str, bytes]):
    require(type(blob) is bytes and len(blob) <= MAX_BYTES, "egg-size")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            require([item.filename for item in infos] == ["manifest.json", "ciphertext.bin"],
                    "egg-members")
            require(all(item.compress_type == zipfile.ZIP_STORED
                        and item.file_size <= MAX_BYTES and not item.flag_bits & 1 for item in infos),
                    "egg-container")
            raw_manifest = archive.read("manifest.json")
            manifest = loads(raw_manifest)
            ciphertext = archive.read("ciphertext.bin")
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError, NotImplementedError) as error:
        raise Refusal("egg-container") from error
    exact(manifest, {"schema", "variant", "rappid", "created_utc", "contents", "payload", "sig"},
          "egg-manifest")
    require(canonical(manifest) == raw_manifest and pack_sealed(manifest, ciphertext) == blob,
            "egg-noncanonical")
    require(manifest["schema"] == "rapp/1-egg" and manifest["variant"] == "sealed", "egg-variant")
    require(valid_rappid(manifest["rappid"]), "egg-identity")
    stamp_ms(manifest["created_utc"])
    require(address == H("rapp/1:egg-manifest", unsigned(manifest)), "egg-address")
    verify_signature(unsigned(manifest), manifest["sig"], keys, manifest["rappid"])
    require(manifest["contents"] == [{"path": "ciphertext.bin", "hash": Hb("rapp/1:egg", ciphertext)}],
            "egg-content-hash")
    payload = exact(manifest["payload"], {
        "schema", "cipher", "nonce", "plaintext_commitment", "plaintext_bytes", "media_type",
        "key_id", "key_service_rappid", "key_service_url", "access", "aad_hash",
    }, "egg-seal")
    require(payload["schema"] == "rapp-sealed-artifact/1" and payload["cipher"] == "A256GCM"
            and payload["access"] == "scoped-key-release", "egg-seal")
    require(type(payload["plaintext_bytes"]) is int and 0 <= payload["plaintext_bytes"] <= MAX_PLAINTEXT,
            "egg-plaintext-size")
    require(len(ciphertext) == payload["plaintext_bytes"] + 16, "egg-ciphertext-size")
    for field in ("key_id", "plaintext_commitment", "aad_hash"):
        require(type(payload[field]) is str and bool(HEX.fullmatch(payload[field])), "egg-seal-hash")
    require(type(payload["media_type"]) is str and 0 < len(payload["media_type"]) <= 127
            and payload["media_type"] == payload["media_type"].strip(), "egg-media-type")
    require(len(unb64(payload["nonce"])) == 12, "egg-nonce")
    require(valid_rappid(payload["key_service_rappid"]) and chat_url(payload["key_service_url"]),
            "egg-key-service")
    require(payload["aad_hash"] == H("rapp/1:sealed-aad", sealed_aad(manifest)), "egg-aad")
    return manifest, ciphertext


def decrypt_sealed(manifest: dict, ciphertext: bytes, dek: bytes) -> bytes:
    require(type(dek) is bytes and len(dek) == 32, "dek")
    try:
        plaintext = AESGCM(dek).decrypt(unb64(manifest["payload"]["nonce"]), ciphertext,
                                        canonical(sealed_aad(manifest)))
    except InvalidTag as error:
        raise Refusal("egg-aead") from error
    require(len(plaintext) == manifest["payload"]["plaintext_bytes"], "egg-plaintext-size")
    require(hmac.compare_digest(plaintext_commitment(dek, plaintext),
                                manifest["payload"]["plaintext_commitment"]), "egg-commitment")
    return plaintext
