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
