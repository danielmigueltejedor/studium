# Evidence model

A user-provided file has an `origin` and, separately, a `source_class`.

Origin is the channel: `official_web`, `academic_external`, `user_uploaded`, `local_private`, `course_platform`, `institutional_repository`, `publisher`, or `generated_data`. An attachment is `user_uploaded`. An explicit private path is `local_private`. A Moodle PDF does not become `course_platform` just because the student attached it.

`source_class` is the only authority tier (`A0`–`E`). Intake leaves it empty. `authority_status` stays empty until an audit sets `source_class`, and then it repeats that same class. Classification moves from `PENDING` to `AUDITED`. Neither value means `ACCEPTED` or `verified`.

Roles are one array. They include `COURSE_TERMINOLOGY` and `LAB_CONTEXT`. A source may show what the course teaches and still not be scientific authority. `course_authority` does not corroborate a high-risk scientific claim. Wuolah may carry assessment or terminology roles and does not receive scientific authority automatically.

The same SHA-256 returns `already_registered` and the same `SRC-` id. A different hash for the same logical source is `sources.version_conflict` unless the caller sets `supersedes`. `new_version_of` is the inverse of that edge, computed when the source is read, not a second stored field. There is no `SRC-LOCAL-` prefix.

Impact of a new version is limited to entities linked to the previous source. Those entities are marked `DIRTY`. A review or verification whose binding hash no longer matches is `STALE`. An open `review_entity` or `verify_entity` task records `REVIEW_REQUIRED`. The project state does not restart. This is the source slice of impact, not the full evidence gate.

## Quoting a user-provided file

`studium_excerpt_record` accepts the `SRC-` id of a registered user file together with the same `path` the user gave, a `locator` (for example `Tema 3, p. 12`) and optionally a `page` (PDF page or PPTX slide). The server reads the file again, requires its SHA-256 to equal the registered version, extracts its text (UTF-8 text formats, DOCX, PPTX, EPUB; PDF through `pdftotext`), and stores the excerpt only when the quoted text is in the file, on `page` when given. Matching ignores line breaks, line-break hyphens, ligatures and typographic quotes and dashes, nothing else. The path and the rest of the file are never stored; the excerpt keeps the quote, the locator, the source hash and how the quote was checked (`quote_check`). A scanned PDF without a text layer, a spreadsheet, or a missing `pdftotext` is rejected with the reason; a file registered only as an attachment cannot be quoted yet.

A quote found in the file is provenance, not verification: the excerpt stays `PENDING` with no authority. A paragraph may cite it while that exact file version is live and not rejected. For corroboration all user files count as one witness, so `two_witnesses` needs at least one public source next to them. The bibliography lists a quoted file by its file name as private, unverified user material.

### Pages that are images

Slides and scans keep equations and diagrams as images, so the text layer has nothing to quote. `studium_source_page_image` renders one page of a registered PDF to a PNG (poppler `pdftoppm`, 50–200 dpi) in the system temporary folder, after checking that the file hashes to the registered version; nothing is written to the project. The client looks at the image and records what it read with `studium_excerpt_record` and `transcribed_from_image` with `page`. When the text layer already holds the words the excerpt is a normal checked quote; otherwise it is stored as `quote_check.status = client_transcription` with `verified = false`, the page and the SHA-256 of the rendered page. The server never saw those words, so such an excerpt can be cited by a paragraph but never makes an equation `source_supported`; the equation stays for human review.
