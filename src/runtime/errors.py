"""Runtime error types shared across planning, authoring, and execution modules."""

from __future__ import annotations


class PlanGenerationError(RuntimeError):
    """Raised when the autonomous planner cannot produce a valid plan."""
