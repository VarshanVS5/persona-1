"""OWNER: Person 1 - Desktop Runtime & Safety. Do not edit without owner approval.

Windows action adapters and the fake/mock adapter used in tests and mock mode.
"""

from .base import (
    ActionAdapter,
    ActionResult,
    AdapterError,
    CancelledError,
    FailureCode,
)
from .fake import FakeActionAdapter, FakeBehaviour
from .windows import WindowsActionAdapter

__all__ = [
    "ActionAdapter",
    "ActionResult",
    "AdapterError",
    "CancelledError",
    "FailureCode",
    "FakeActionAdapter",
    "FakeBehaviour",
    "WindowsActionAdapter",
]
