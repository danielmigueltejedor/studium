# Reconnecting a stale MCP server

An MCP client spawns `studium mcp` once and keeps that process. The process holds
the code it imported at startup. When the installed package changes, the running
server keeps answering with the old catalog: a tool that the new code declares
comes back as `mcp.unknown_tool`, and a fixed behaviour still misbehaves.

The running server can report this state and reload it. That is what
`studium_server_info` and `studium_server_reload` are for.

## Detect

Call `studium_server_info`. It returns:

- `loaded_code_fingerprint`: a content hash of the modules the process imported.
- `installed_code_fingerprint`: the same hash over the package on disk now.
- `new_tools` and `removed_tools`: the catalog difference, loaded versus on disk.
- `stale`: true when any of the three differs.
- `reconnect`: the exact next step, present only when `stale` is true.

From outside a session, `studium mcp --check` prints the installed version, the
installed fingerprint, and every tool name the catalog source declares. Compare
it with `installed_code_fingerprint` from `studium_server_info`.

## Reload

Call `studium_server_reload`. It reloads the tool catalog and the server module
in place, then announces `notifications/tools/list_changed`. A client that
honours the notification re-lists the tools and sees the new ones. The call
returns `new_tools` and the refreshed list.

Reload is best effort. It reuses the module globals the running serve loop
already reads, so a new tool that wraps existing functions works immediately. A
change that replaces a class a live session is an instance of, or a change to a
client that ignores `list_changed`, still needs a restart. `studium_server_info`
reports `stale` truthfully after a reload that did not converge.

## Restart

Stop the process that runs `studium mcp` and let the client spawn it again. Then
call `studium_server_info` and confirm `loaded_code_fingerprint` equals
`installed_code_fingerprint`. The server advertises
`capabilities.tools.listChanged` so a conforming client hides none of this.

## For server authors

Do not add a tool that reads files outside the workspace or the installed
package. The fingerprint reads only `<site-packages>/studium/**/*.py`. It is a
diagnostic, not a source of authority, and it never marks a book or a source
verified.
