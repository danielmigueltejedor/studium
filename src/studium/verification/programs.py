"""Language adapters with explicit evidence scopes and bounded, opt-in execution.

This is NOT a security sandbox. Untrusted programs are refused. Callers must
review the exact source hash before opting in, or provide external isolation.
No invocation is accepted from a document; commands come only from adapters.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Mode = Literal["syntax", "compile", "run", "test"]
_ALIASES = {"py": "python", "rs": "rust", "c++": "cpp", "js": "javascript", "ts": "typescript", "sh": "bash"}


@dataclass(frozen=True)
class CodeArtifact:
    language: str
    source: str
    mode: Mode = "syntax"
    expected_stdout: str | None = None
    filename: str | None = None
    version: str | None = None
    partial: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"syntax", "compile", "run", "test"}:
            raise ValueError("unsupported verification mode")
        if len(self.source.encode("utf-8")) > 200_000:
            raise ValueError("source exceeds 200 KB")
        if self.filename is not None and (Path(self.filename).name != self.filename or self.filename in {"", ".", ".."}):
            raise ValueError("filename must be a simple file name")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LanguageAdapter:
    language: str
    executable: str
    extension: str

    def commands(self, artifact: CodeArtifact, executable: str) -> list[list[str]]:
        source = "example." + self.extension
        mode = artifact.mode
        if self.language == "python":
            return [[executable, "-I", "-m", "unittest", "discover", "-v", "-p", "example.py"]] if mode == "test" else [[executable, "-I", source]]
        if self.language == "typescript":
            flags = ["--noEmit"] if mode == "syntax" else []
            return [[executable, "--strict", "--target", "es2022", *flags, source]]
        if self.language == "javascript":
            flags = ["--check"] if mode == "syntax" else ["--test"] if mode == "test" else []
            return [[executable, *flags, source]]
        if self.language == "bash":
            return [[executable, "-n", source]]
        if self.language == "rust":
            flags = ["--test"] if mode == "test" else ["--crate-type", "lib", "--emit=metadata"] if mode in {"syntax", "compile"} else []
            compile_cmd = [executable, "--edition=2024", *flags, source, "-o", "program"]
        else:
            standard = "-std=c17" if self.language == "c" else "-std=c++20"
            flags = ["-fsyntax-only"] if mode == "syntax" else ["-c"] if mode == "compile" else []
            compile_cmd = [executable, standard, "-Wall", "-Wextra", *flags, source, "-o", "program"]
        return [compile_cmd, [str(Path.cwd() / "program")]] if mode in {"run", "test"} else [compile_cmd]


ADAPTERS = {a.language: a for a in (
    LanguageAdapter("python", sys.executable, "py"), LanguageAdapter("rust", "rustc", "rs"),
    LanguageAdapter("c", "cc", "c"), LanguageAdapter("cpp", "c++", "cpp"),
    LanguageAdapter("javascript", "node", "mjs"), LanguageAdapter("typescript", "tsc", "ts"),
    LanguageAdapter("bash", "bash", "sh"),
)}


def _limits() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8_000_000, 8_000_000))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _run(command: list[str], directory: Path, timeout: float) -> dict[str, object]:
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "SDKROOT", "HOME", "USERPROFILE", "RUSTUP_HOME", "CARGO_HOME") if key in os.environ}
    env.update({"TMPDIR": str(directory), "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"})
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   env=env, start_new_session=True, preexec_fn=_limits if os.name == "posix" else None)
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # Clean up descendants too, including children left by a parent that exited.
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            elif process.poll() is None:
                process.kill()
            process.wait()
        stdout.seek(0)
        stderr.seek(0)
        out, err = stdout.read(64_001), stderr.read(64_001)
        return {"command": command, "returncode": process.returncode, "stdout": out[:64_000].decode("utf-8", "replace"),
                "stderr": err[:64_000].decode("utf-8", "replace"), "timed_out": timed_out,
                "truncated": len(out) > 64_000 or len(err) > 64_000}


def verify_program(artifact: CodeArtifact, *, trusted: bool = False, timeout: float = 20) -> dict[str, object]:
    """Verify only the requested property; a successful exit alone is EXECUTED.

    ``trusted=True`` is a caller decision, never inferred from source metadata.
    Do not expose it as an automatically approved MCP/CLI command for documents.
    """
    if not 0 < timeout <= 120:
        raise ValueError("timeout must be between 0 and 120 seconds")
    language = _ALIASES.get(artifact.language.lower(), artifact.language.lower())
    result: dict[str, object] = {"schema_version": "1.0", "source_sha256": artifact.sha256, "language": language,
                                 "requested_mode": artifact.mode, "filename": artifact.filename, "declared_version": artifact.version,
                                 "classification": "UNVERIFIED", "passed": None, "commands": [], "tool_version": None,
                                 "expected_stdout": artifact.expected_stdout, "observed_stdout": None,
                                 "limitations": ["Finite tests do not prove correctness.", "Resource limits are not a security sandbox."]}

    def finish(classification: str, passed: bool | None, detail: str) -> dict[str, object]:
        return {**result, "classification": classification, "passed": passed, "detail": detail}

    if artifact.partial:
        return finish("INTENTIONAL_PARTIAL", None, "Explicitly partial; no execution claimed.")
    if language in {"json", "toml"} or (language == "python" and artifact.mode == "syntax"):
        try:
            if language == "json":
                json.loads(artifact.source, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            elif language == "toml":
                tomllib.loads(artifact.source)
            else:
                ast.parse(artifact.source)
        except (ValueError, SyntaxError) as exc:
            return finish("FAILED", False, str(exc))
        result["tool_version"] = sys.version.split()[0]
        if artifact.mode != "syntax":
            return finish("UNVERIFIED", None, "A format parser cannot execute or test a program.")
        return finish("SYNTAX_VALIDATED", True, "Parsed without executing; behavior was not checked.")
    adapter = ADAPTERS.get(language)
    if adapter is None or (language == "bash" and artifact.mode != "syntax"):
        return finish("UNVERIFIED", None, "No adapter for the requested language/mode.")
    if language == "typescript" and artifact.mode in {"run", "test"}:
        return finish("UNVERIFIED", None, "Use a reviewed project adapter for TypeScript runtime tests; this adapter typechecks and compiles.")
    if language == "python" and artifact.mode == "compile":
        return finish("UNVERIFIED", None, "Use syntax to parse Python, or run/test to check behavior.")
    if not trusted:
        return finish("ISOLATION_REQUIRED", None, "Review this exact source hash or execute in an external sandbox.")
    executable = shutil.which(adapter.executable)
    if executable is None:
        return finish("PENDING_TOOLCHAIN", None, "Tool not found on PATH: " + adapter.executable)
    with tempfile.TemporaryDirectory(prefix="studium-code-") as temp:
        directory = Path(temp)
        (directory / ("example." + adapter.extension)).write_text(artifact.source, encoding="utf-8")
        try:
            version = _run([executable, "--version"], directory, min(timeout, 5))
        except OSError as exc:
            return finish("PENDING_TOOLCHAIN", None, str(exc))
        if version["returncode"] != 0 or version["timed_out"]:
            return finish("PENDING_TOOLCHAIN", None, "Installed executable failed its version probe.")
        result["tool_version"] = str(version["stdout"] or version["stderr"]).splitlines()[:1]
        commands = adapter.commands(artifact, executable)
        # The executable output path is always in the disposable workspace.
        if len(commands) == 2:
            commands[-1] = [str(directory / "program")]
        results = []
        for command in commands:
            try:
                run = _run(command, directory, timeout)
            except OSError as exc:
                return finish("PENDING_TOOLCHAIN", None, str(exc))
            results.append(run)
            result["commands"] = results
            if run["timed_out"]:
                return finish("TIMEOUT", False, "Time budget exceeded.")
            if artifact.mode == "test" and language == "python" and "Ran 0 tests" in str(run["stderr"]):
                return finish("UNVERIFIED", None, "No tests were collected.")
            if run["returncode"] != 0 or run["truncated"]:
                return finish("FAILED", False, "Tool failed or output exceeded the reporting limit.")
        observed = str(results[-1]["stdout"])
        result["observed_stdout"] = observed
        if artifact.mode == "syntax":
            return finish("SYNTAX_VALIDATED", True, "Tool accepted syntax; behavior was not checked.")
        if artifact.mode == "compile":
            return finish("COMPILED", True, "Compiled without execution; behavior was not checked.")
        if artifact.mode == "test":
            transcript = observed + str(results[-1]["stderr"])
            patterns = {"rust": r"test result: ok\. ([1-9]\d*) passed", "python": r"Ran ([1-9]\d*) tests?", "javascript": r"(?:# tests |\u2139 tests )([1-9]\d*)", "typescript": r"(?:# tests |\u2139 tests )([1-9]\d*)"}
            pattern = patterns.get(language)
            if pattern is None or re.search(pattern, transcript) is None:
                return finish("UNVERIFIED", None, "No positive test count from a supported test runner.")
            return finish("TESTS_PASSED", True, "Runner reported nonzero passing tests; inspect test adequacy separately.")
        if artifact.expected_stdout is None:
            return finish("EXECUTED", None, "Exited successfully; no expected output supplied.")
        if observed != artifact.expected_stdout:
            return finish("FAILED", False, "Observed stdout differs from the exact expected stdout.")
        result["artifact"] = asdict(artifact)
        return finish("OUTPUT_MATCHED", True, "Observed stdout exactly matches the supplied expectation.")
