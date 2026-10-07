"""Project states and the events that move between them."""

from enum import Enum


class ProjectState(Enum):
    CREATED = "CREATED"
    COURSE_DISCOVERY = "COURSE_DISCOVERY"
    SOURCE_DISCOVERY = "SOURCE_DISCOVERY"
    CORPUS_BUILDING = "CORPUS_BUILDING"
    BLUEPRINT = "BLUEPRINT"
    AUTHORING = "AUTHORING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    RELEASE_CANDIDATE = "RELEASE_CANDIDATE"
    RELEASED = "RELEASED"


STATE_ORDER: tuple[ProjectState, ...] = tuple(ProjectState)


class ProjectEvent(Enum):
    PROJECT_CREATED = "project_created"
    BEGIN_DISCOVERY = "begin_discovery"
    COURSE_RECORDED = "course_recorded"
    CORPUS_STARTED = "corpus_started"
    CORPUS_SUFFICIENT = "corpus_sufficient"
    BLUEPRINT_ACCEPTED = "blueprint_accepted"
    AUTHORING_COMPLETE = "authoring_complete"
    VERIFICATION_PASSED = "verification_passed"
    REVIEWS_CURRENT = "reviews_current"
    RELEASE = "release"
    REFRESH_COURSE = "refresh_course"
    REGRESS = "regress"


class LocalSourceStatus(Enum):
    """Availability of user material. This is not a project state."""

    UNKNOWN = "UNKNOWN"
    NONE = "NONE"
    AVAILABLE = "AVAILABLE"
    IMPORTED = "IMPORTED"
    SKIPPED = "SKIPPED"


LOCAL_SOURCE_STATUSES: frozenset[str] = frozenset(item.value for item in LocalSourceStatus)


class SourceOrigin(Enum):
    """How a source arrived. Not an authority tier."""

    OFFICIAL_WEB = "official_web"
    ACADEMIC_EXTERNAL = "academic_external"
    USER_UPLOADED = "user_uploaded"
    LOCAL_PRIVATE = "local_private"
    COURSE_PLATFORM = "course_platform"
    INSTITUTIONAL_REPOSITORY = "institutional_repository"
    PUBLISHER = "publisher"
    GENERATED_DATA = "generated_data"


SOURCE_ORIGINS: frozenset[str] = frozenset(item.value for item in SourceOrigin)


class SourceRole(Enum):
    OFFICIAL_CURRICULUM = "OFFICIAL_CURRICULUM"
    COURSE_SCOPE = "COURSE_SCOPE"
    COURSE_TERMINOLOGY = "COURSE_TERMINOLOGY"
    LECTURE_EMPHASIS = "LECTURE_EMPHASIS"
    SCIENTIFIC_EVIDENCE = "SCIENTIFIC_EVIDENCE"
    BIBLIOGRAPHY = "BIBLIOGRAPHY"
    ASSESSMENT_PATTERN = "ASSESSMENT_PATTERN"
    PROBLEM_STYLE = "PROBLEM_STYLE"
    LAB_CONTEXT = "LAB_CONTEXT"
    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    HISTORICAL_EVIDENCE = "HISTORICAL_EVIDENCE"
    DATA_SOURCE = "DATA_SOURCE"
    SUPPLEMENTARY = "SUPPLEMENTARY"


SOURCE_ROLES: frozenset[str] = frozenset(item.value for item in SourceRole)

SOURCE_CLASSES: frozenset[str] = frozenset(
    {"A0", "A1", "A2", "A3", "B0", "B1", "B2", "C0", "C1", "D0", "D1", "D2", "E"}
)

COURSE_AUTHORITY: frozenset[str] = frozenset(
    {"unknown", "contextual", "course_specific", "official_course"}
)

SCIENTIFIC_AUTHORITY: frozenset[str] = frozenset(
    {"unknown", "contextual", "secondary", "maximal"}
)
