# Generic MCP

Any MCP client can use the local process `studium mcp`. A future hosted transport would sit in front of the same tools, not a new core.

Tools: `studium_project_create`, `studium_project_list`, `studium_project_status`, `studium_source_capabilities`, `studium_source_status`, `studium_source_list`, `studium_source_get`, `studium_source_intake`, `studium_source_register`, `studium_source_audit`, `studium_source_remove`, `studium_source_impact`, `studium_source_reject`.

There is no `arbitrary_shell`, no `arbitrary_file_read`, and no home-directory scan. Source ids use the existing `SRC-` prefix.

`studium_source_intake` accepts either `path` (an explicit file) or `attachment` (`handle`, `filename`, `content_base64`). The handle is not opened as a path.
