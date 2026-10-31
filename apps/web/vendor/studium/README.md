# Studium in the browser

Pinned upstream: https://github.com/danielmigueltejedor/studium/tree/f7bc7310507b83bb23738511843fc7c7f1b6c96e
Apache-2.0. The two planning source files below have only trailing whitespace
normalized; their semantics are unchanged. public/studium-python.js embeds them.

public/studium-core.js additionally packages all 118 original Python modules,
byte-for-byte, with per-file SHA-256 hashes and the original license. The browser
adapter is public/studium-core-bridge.txt; it does not replace framework gates.
Pyodide executes project creation, source intake/versioning, academic hierarchy,
depth, excerpts, paragraphs, review, verification reports and draft TeX export.
SymPy/Pint are available, but checks requiring Python threads, subprocesses or TeX
cannot complete in this runtime. No project is marked released. Expert and
semantic review remain pending. See the application README for execution limits.
