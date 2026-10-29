"""OWNER: Person 1 - Desktop Runtime & Safety. Do not edit without owner approval.

Executes validated, approved plan steps with timeouts and cancellation
(FR-07, FR-09). ``build_runtime`` is the stable assembly entry point.
"""

from .events import make_event
from .factory import build_runtime, resolve_allowed_apps
from .runtime import ExecutionRuntime, StepOutcome, TaskOutcome

__all__ = [
    "ExecutionRuntime",
    "StepOutcome",
    "TaskOutcome",
    "build_runtime",
    "make_event",
    "resolve_allowed_apps",
]
