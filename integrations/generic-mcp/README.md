# Generic MCP

Any MCP client can use the local process `studium mcp`. A future hosted transport would sit in front of the same tools, not a new core.

Tools: `studium_project_create`, `studium_project_list`, `studium_project_status`, `studium_source_capabilities`, `studium_source_status`, `studium_source_list`, `studium_source_get`, `studium_source_intake`, `studium_source_register`, `studium_source_audit`, `studium_source_remove`, `studium_source_impact`, `studium_source_reject`, `studium_course_document_list`, `studium_course_document_get`, `studium_course_document_record`, `studium_course_recorded`, `studium_public_source_list`, `studium_public_source_record`, `studium_public_source_check`, `studium_public_source_guide_citation`, `studium_blueprint_store`, `studium_blueprint_get`, `studium_claim_record`, `studium_claim_list`, `studium_verify`, `studium_render`, `studium_excerpt_record`, `studium_excerpt_list`, `studium_excerpt_get`, `studium_paragraph_record`, `studium_paragraph_list`, `studium_draft_completeness`, `studium_public_source_open_supplement`, `studium_problem_record`, `studium_problem_check`, `studium_computation_check`, `studium_problem_list`, `studium_book_next`, `studium_paragraph_replace`, `studium_media_record`, `studium_student_notes_record`, `studium_figure_record`, `studium_figure_check`, `studium_audit_record`, `studium_contradiction_scan`, `studium_book_review`.

There is no `arbitrary_shell`, no `arbitrary_file_read`, and no home-directory scan. Source ids use the existing `SRC-` prefix.

`studium_source_intake` accepts either `path` (an explicit file) or `attachment` (`handle`, `filename`, `content_base64`). The handle is not opened as a path.
