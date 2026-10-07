# Cursor

Cursor talks to Studium through `studium mcp` or the CLI. Both call the same source functions.

Intake only a path the user supplied, or an attachment the client has already read. Do not crawl the workspace or the home directory for course files.

Local sources are optional. `UNKNOWN` means ask once. `NONE` means continue research.
