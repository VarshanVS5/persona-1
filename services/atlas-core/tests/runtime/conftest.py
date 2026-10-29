"""Person 1 runtime test configuration.

The project owner's shared ``tests/conftest.py`` and ``pyproject.toml`` are
still placeholders, so this local conftest makes the runtime importable when
these tests are run directly (``pytest services/atlas-core/tests/runtime``)
without an installed package. It only touches sys.path; it does not change any
owner-owned behaviour. When the owner publishes packaging/conftest, this can be
removed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# services/atlas-core/src on sys.path -> `import atlas...` works.
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture
def allowed_apps() -> list[str]:
    return ["notepad", "calc"]
