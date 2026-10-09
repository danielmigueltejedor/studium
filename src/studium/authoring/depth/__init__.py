"""Adaptive academic depth planning.

Determines how much depth a subject, topic, chapter, or section needs, and
plans the content until the academic objectives are covered. It never decides
that a chapter is complete merely because the minimum structure exists, and it
never asks for filler: the length estimate is derived from the planned
concepts, derivations, examples, and exercises, not the other way around.

The planner works without a specific AI provider. It produces structured
requirements that any compatible authoring client can follow.
"""

from studium.authoring.depth.length import (
    LENGTH_PREFERENCES,
    LengthScope,
    estimate_book_scope,
    validate_length_target,
)
from studium.authoring.depth.planner import (
    build_depth_plan,
    depth_plan_status,
    plan_requires_academic_blueprint,
)
from studium.authoring.depth.profiles import (
    PROFILES,
    AcademicProfile,
    resolve_depth_profile,
)

__all__ = [
    "LENGTH_PREFERENCES",
    "PROFILES",
    "AcademicProfile",
    "LengthScope",
    "build_depth_plan",
    "depth_plan_status",
    "estimate_book_scope",
    "plan_requires_academic_blueprint",
    "resolve_depth_profile",
    "validate_length_target",
]
