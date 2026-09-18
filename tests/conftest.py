from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def sandbox() -> Iterator[Path]:
    root = Path(__file__).resolve().parents[1] / ".test-work" / ("case-" + uuid.uuid4().hex)
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
