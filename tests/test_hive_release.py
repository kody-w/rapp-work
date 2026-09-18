from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rapp_work import (
    HiveHighWater,
    HiveStreamPosition,
    HiveVector,
    ReleaseObservation,
    ReleaseObservationStore,
    SignedRelease,
    Workspace,
    verify_hive_high_water,
)
from rapp_work.errors import Refusal
from rapp_work.rapp1 import canonical, hash_json, mint_rappid


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def position(stream: str, names: list[str]) -> HiveStreamPosition:
    history = tuple(digest(name) for name in names)
    return HiveStreamPosition(stream, len(history) - 1, history[-1], history)


def vectors() -> tuple[HiveVector, HiveVector]:
    mother = mint_rappid("example", "hive")
    dimension = mint_rappid("example", "dimension")
    first = HiveVector(
        mother,
        1,
        digest("registry-1"),
        tuple(sorted((position(mother, ["m0"]), position(dimension, ["d0"])), key=lambda x: x.stream_id)),
    )
    second = HiveVector(
        mother,
        2,
        digest("registry-2"),
        tuple(
            sorted(
                (
                    position(mother, ["m0", "m1"]),
                    position(dimension, ["d0", "d1"]),
                ),
                key=lambda x: x.stream_id,
            )
        ),
        ((1, digest("registry-1")), (2, digest("registry-2"))),
    )
    return first, second


def test_hive_vector_high_water_requires_retained_lineage() -> None:
    first, second = vectors()
    assert verify_hive_high_water(second, first)["status"] == "verified-high-water"
    assert HiveHighWater(first).accept(second).vector == second


def test_hive_vector_rollback_fork_and_missing_stream_refuse() -> None:
    first, second = vectors()
    with pytest.raises(Refusal, match="REFUSE_HIVE_ROLLBACK"):
        verify_hive_high_water(first, second)
    mother = second.hive_rappid
    forked = HiveVector(
        mother,
        2,
        second.registry_hash,
        tuple(
            sorted(
                (
                    position(mother, ["m0", "fork"]),
                    second.streams[0] if second.streams[0].stream_id != mother else second.streams[1],
                ),
                key=lambda x: x.stream_id,
            )
        ),
        second.registry_history,
    )
    with pytest.raises(Refusal, match="REFUSE_HIVE_FORK"):
        verify_hive_high_water(forked, second)
    missing = HiveVector(
        mother,
        2,
        second.registry_hash,
        (position(mother, ["m0", "m1"]),),
        second.registry_history,
    )
    with pytest.raises(Refusal, match="REFUSE_HIVE_ROLLBACK"):
        verify_hive_high_water(missing, first)
    registry_without_lineage = HiveVector(
        second.hive_rappid,
        2,
        second.registry_hash,
        second.streams,
    )
    with pytest.raises(Refusal, match="REFUSE_HIVE_FORK"):
        verify_hive_high_water(registry_without_lineage, first)


def test_release_observation_store_is_immutable_and_bounded(sandbox) -> None:
    store = ReleaseObservationStore(sandbox / "observations", maximum=2)
    first = ReleaseObservation(
        release_sha256=digest("release-1"),
        plan_sha256=digest("plan-1"),
        source="fixture",
        transport="filesystem",
        observed_utc="2026-09-18T12:00:00.000Z",
    )
    second = ReleaseObservation(
        release_sha256=digest("release-2"),
        plan_sha256=digest("plan-2"),
        source="fixture",
        transport="private-git",
        observed_utc="2026-09-18T12:00:01.000Z",
    )
    assert store.observe(first, expected_sha256=first.sha256)["status"] == "recorded"
    assert store.observe(first, expected_sha256=first.sha256)["status"] == "unchanged"
    assert store.observe(second, expected_sha256=second.sha256)["count"] == 2
    third = ReleaseObservation(
        release_sha256=digest("release-3"),
        plan_sha256=digest("plan-3"),
        source="fixture",
        transport="memory",
        observed_utc="2026-09-18T12:00:02.000Z",
    )
    with pytest.raises(Refusal, match="REFUSE_RELEASE_OBSERVATION_LIMIT"):
        store.observe(third, expected_sha256=third.sha256)
    assert store.status()["count"] == 2


def store_snapshot(root) -> dict[str, tuple[int, bytes | None]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat(follow_symlinks=False).st_mode & 0o777,
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


def test_release_observation_store_refuses_unmanaged_layout_without_effects(
    sandbox,
) -> None:
    root = sandbox / "observations"
    root.mkdir(mode=0o700)
    (root / "observations").mkdir(mode=0o700)
    before = store_snapshot(root)
    store = ReleaseObservationStore(root)
    observation = ReleaseObservation(
        release_sha256=digest("release"),
        plan_sha256=digest("plan"),
        source="fixture",
        transport="filesystem",
        observed_utc="2026-09-18T12:00:00.000Z",
    )
    with pytest.raises(Refusal, match="REFUSE_RELEASE_STORE"):
        store.observe(observation, expected_sha256=observation.sha256)
    assert store_snapshot(root) == before
    assert not (root / ".store.lock").exists()
    assert not (root / "index.json").exists()


def test_release_observation_store_validates_existing_index_before_writes(
    sandbox,
) -> None:
    root = sandbox / "observations"
    store = ReleaseObservationStore(root)
    first = ReleaseObservation(
        release_sha256=digest("release-1"),
        plan_sha256=digest("plan-1"),
        source="fixture",
        transport="filesystem",
        observed_utc="2026-09-18T12:00:00.000Z",
    )
    store.observe(first, expected_sha256=first.sha256)
    (root / "index.json").write_bytes(
        canonical(
            {
                "maximum": 128,
                "observations": [],
                "schema": "rapp-work-release-observation-index/1",
            }
        ).encode()
    )
    before = store_snapshot(root)
    second = ReleaseObservation(
        release_sha256=digest("release-2"),
        plan_sha256=digest("plan-2"),
        source="fixture",
        transport="filesystem",
        observed_utc="2026-09-18T12:00:01.000Z",
    )
    with pytest.raises(Refusal, match="REFUSE_RELEASE_STORE"):
        store.observe(second, expected_sha256=second.sha256)
    assert store_snapshot(root) == before
    assert not (root / "observations" / f"{second.sha256}.json").exists()


def detached_signature(private: Ed25519PrivateKey, kid: str, value: dict) -> str:
    header = canonical({"alg": "EdDSA", "b64": False, "crit": ["b64"], "kid": kid}).encode()
    protected = base64.urlsafe_b64encode(header).rstrip(b"=")
    signature = private.sign(protected + b"." + canonical(value).encode())
    return protected.decode() + ".." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def verified_bundle_fixture(
    private: Ed25519PrivateKey,
    owner: str,
    spki: bytes,
    mother: str,
    registries: list[dict],
) -> SimpleNamespace:
    files = {}
    history = []
    for unsigned in registries:
        document = {
            **unsigned,
            "sig": detached_signature(private, owner, unsigned),
        }
        sequence = unsigned["registry_seq"]
        address = hash_json("rapp/1:particle", document)
        files[f"registry-history/{sequence}-{address}.json"] = canonical(document).encode()
        history.append((sequence, hash_json("rapp/1:particle", unsigned)))
    frame = {
        "frame_hash": digest("mother-genesis"),
        "seq": 0,
        "stream_id": mother,
    }
    return SimpleNamespace(
        anchor={
            "owner_rappid": owner,
            "spki_der_b64": base64.b64encode(spki).decode(),
        },
        files=files,
        gate=SimpleNamespace(_retained={frame["frame_hash"]: frame}),
        pointer={
            "hive_rappid": mother,
            "projections": [],
            "registry": {
                "hash": history[-1][1],
                "seq": history[-1][0],
            },
        },
        resolver=SimpleNamespace(chain=lambda _frame_hash: ()),
    )


def test_verified_bundle_preserves_authenticated_registry_advances() -> None:
    private = Ed25519PrivateKey.from_private_bytes(
        hashlib.sha256(b"registry lineage fixture").digest()
    )
    spki = private.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    owner = mint_rappid("example", "registry-owner", spki)
    mother = mint_rappid("example", "registry-hive")

    def registry(sequence: int, marker: str) -> dict:
        return {
            "canonical_source": "urn:rapp:test:registry-history",
            "entries": [{"marker": marker}],
            "registry_seq": sequence,
            "schema": "rapp/1-registry",
        }

    first_registry = registry(1, "stable")
    second_registry = registry(2, "stable")
    first = HiveVector.from_verified_bundle(
        verified_bundle_fixture(private, owner, spki, mother, [first_registry])
    )
    second = HiveVector.from_verified_bundle(
        verified_bundle_fixture(
            private,
            owner,
            spki,
            mother,
            [first_registry, second_registry],
        )
    )
    assert second.registry_history == (
        (1, first.registry_hash),
        (2, second.registry_hash),
    )
    assert verify_hive_high_water(second, first)["status"] == "verified-high-water"
    with pytest.raises(Refusal, match="REFUSE_HIVE_ROLLBACK"):
        verify_hive_high_water(first, second)

    fork = HiveVector.from_verified_bundle(
        verified_bundle_fixture(
            private,
            owner,
            spki,
            mother,
            [first_registry, registry(2, "fork")],
        )
    )
    with pytest.raises(Refusal, match="REFUSE_HIVE_FORK"):
        verify_hive_high_water(fork, second)


def test_signed_release_binds_complete_plan(sandbox) -> None:
    plan = Workspace.plan_scaffold(
        sandbox / "workspace",
        owner_label="example",
        slug="signed",
        world_id="example-world",
    )
    private = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"signed release fixture").digest())
    spki = private.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signer = mint_rappid("example", "release-signer", spki)
    unsigned = {
        "plan": plan.to_dict(),
        "plan_sha256": plan.sha256,
        "schema": "rapp-work-signed-release/1",
        "signer_rappid": signer,
    }
    signed = SignedRelease(plan, signer, detached_signature(private, signer, unsigned))
    assert signed.verify(spki)["status"] == "verified"
    altered = json.loads(json.dumps(signed.to_dict()))
    altered["plan"]["target"] += "-changed"
    with pytest.raises(Refusal):
        SignedRelease.from_dict(altered)
