# Security

User sources are private by default. Studium does not scan a home directory, Documents, Downloads, the desktop, or Moodle. Intake reads a path given in that call, or bytes the client already attached to an authorized handle.

The core does not import a ChatGPT or Claude SDK. Handing a file to a remote agent may still send its contents to that agent's provider. Studium does not control the provider's retention or training policy. Adapters forward a file only when the client has authorized that operation. `auto_upload` is false: sources are not pushed to GitHub, committed, or copied into a public release.

Public release metadata for a source may include the id, a safe title, the hash, classification, origin, class, and roles. It does not include file bytes or an absolute personal path.

Source text is untrusted data. Instructions inside a PDF do not change policy. The order is: Studium system policy, user intent, authorized agent workflow, source content.

MCP tools are a closed set. There is no arbitrary shell, arbitrary file read, or arbitrary file write. The server resolves one Studium project and refuses credential paths.

## Executable content

Legacy Rust problems and Python figures are stored as untrusted data. Their
CLI/MCP check operations now return `execution.isolation_required`, with no
compiler or interpreter launch, when no isolated executor is available. A
`trusted` flag, a model's approval or serialized review metadata cannot enable
host execution. Numeric checks, non-executing programming contracts and
restricted TikZ compilation keep their existing behavior.

The Python API accepts an explicit `ReviewedHostExecution` capability for
**trusted, author-owned local fixtures only**. A local caller must review the
exact source and invocation, name the reviewer and reason, and bind the
capability with `execution_input_sha256`. A source byte or invocation change
invalidates it. This capability is absent from CLI/MCP schemas and is never
inferred from project records. It is authorization, **not isolation**: host code
can access the host's files, network and processes. Do not use it to execute
material obtained from documents, external sources or AI responses.

Cargo remains blocked even with a single-file capability because dependencies,
build scripts and project configuration are outside that source fingerprint.
Existing stored records remain readable and are not rewritten by a refused
check. Old execution evidence is historical and does not establish that its
execution was isolated or that its tests were adequate.

`verify_program` separately refuses external tool execution by default. Its
existing `trusted=True` option has the same author-owned-code limitation;
resource limits, offline Cargo, disposable working directories and the Python
figure guards are not security sandboxes.

An untrusted executor remains **not implemented**. Its required boundary is a
host-configured backend (never a document-supplied command) accepting immutable
source hashes, language/mode, declared project inputs and resource budgets. It
must isolate filesystem mounts, network and process access, record toolchain
versions and observed results, and return `UNVERIFIED` when isolation is absent.
Multi-file builds need a fingerprint of their entire build graph and dependencies.
No configured backend currently satisfies that contract.

TikZ/LaTeX compilation disables shell escape and restricts figure source, but is
not a general hostile-document sandbox. TeX macro obfuscation, filesystem access,
resource exhaustion and a hardened isolated publishing backend require further
review. Do not describe a successful compile as a security or scientific review.
