# Evidence model

A user-provided file has an `origin` and, separately, a `source_class`.

Origin is the channel: `official_web`, `academic_external`, `user_uploaded`, `local_private`, `course_platform`, `institutional_repository`, `publisher`, or `generated_data`. An attachment is `user_uploaded`. An explicit private path is `local_private`. A Moodle PDF does not become `course_platform` just because the student attached it.

`source_class` is the only authority tier (`A0`–`E`). Intake leaves it empty. `authority_status` stays empty until an audit sets `source_class`, and then it repeats that same class. Classification moves from `PENDING` to `AUDITED`. Neither value means `ACCEPTED` or `verified`.

Roles are one array. They include `COURSE_TERMINOLOGY` and `LAB_CONTEXT`. A source may show what the course teaches and still not be scientific authority. `course_authority` does not corroborate a high-risk scientific claim. Wuolah may carry assessment or terminology roles and does not receive scientific authority automatically.

The same SHA-256 returns `already_registered` and the same `SRC-` id. A different hash for the same logical source is `sources.version_conflict` unless the caller sets `supersedes`. `new_version_of` is the inverse of that edge, computed when the source is read, not a second stored field. There is no `SRC-LOCAL-` prefix.

Impact of a new version is limited to entities linked to the previous source. Those entities are marked `DIRTY`. A review or verification whose binding hash no longer matches is `STALE`. An open `review_entity` or `verify_entity` task records `REVIEW_REQUIRED`. The project state does not restart. This is the source slice of impact, not the full evidence gate.
