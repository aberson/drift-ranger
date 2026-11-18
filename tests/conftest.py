"""Shared test helpers. Tests never read or write the real private store."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import drift_ranger

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
# A synthetic copy of the real store layout. It sits inside the repository, so the CLI
# refuses it directly; tests copy it to a temporary external directory first.
FIXTURE_STORE = FIXTURES / "store"

# The package under test must be the one in src/, not the same-named checkout shim.
assert Path(drift_ranger.__file__).resolve().parent == REPO / "src" / "drift_ranger"


def copy_fixture_store(destination: Path) -> Path:
    """Replace ``destination`` with a fresh copy of the fixture store and return it."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(FIXTURE_STORE, destination)
    return destination


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """A disposable external copy of the fixture store."""
    return copy_fixture_store(tmp_path / "store")
