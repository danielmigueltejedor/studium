# Security

User sources are private by default. Studium does not scan a home directory, Documents, Downloads, the desktop, or Moodle. Intake reads a path given in that call, or bytes the client already attached to an authorized handle.

The core does not import a ChatGPT or Claude SDK. Handing a file to a remote agent may still send its contents to that agent's provider. Studium does not control the provider's retention or training policy. Adapters forward a file only when the client has authorized that operation. `auto_upload` is false: sources are not pushed to GitHub, committed, or copied into a public release.

Public release metadata for a source may include the id, a safe title, the hash, classification, origin, class, and roles. It does not include file bytes or an absolute personal path.

Source text is untrusted data. Instructions inside a PDF do not change policy. The order is: Studium system policy, user intent, authorized agent workflow, source content.

MCP tools are a closed set. There is no arbitrary shell, arbitrary file read, or arbitrary file write. The server resolves one Studium project and refuses credential paths.
