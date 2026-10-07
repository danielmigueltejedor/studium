"""A checkout install must import when the working directory is not the repo."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _version() -> str:
    with (REPO / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    return project["version"]


def _env(venv: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["VIRTUAL_ENV"] = str(venv)
    env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
    return env


def _install(venv: Path, *args: str) -> None:
    completed = subprocess.run(
        [str(venv / "bin" / "pip"), "install", *args],
        cwd="/tmp",
        env=_env(venv),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def _assert_importable_from_tmp(venv: Path) -> None:
    env = _env(venv)
    python = venv / "bin" / "python"
    script = venv / "bin" / "studium"
    expected = f"studium {_version()}\n"
    for _ in range(2):
        imported = subprocess.run(
            [str(python), "-c", "import studium"],
            cwd="/tmp",
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert imported.returncode == 0, imported.stderr
        version = subprocess.run(
            [str(script), "--version"],
            cwd="/tmp",
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert version.returncode == 0, version.stderr
        assert version.stdout == expected


def test_editable_install_imports_outside_the_repo(tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    _install(venv, "-e", str(REPO))
    pth = next((venv / "lib").glob("python*/site-packages/__editable__.studium-*.pth"))
    assert pth.read_text(encoding="utf-8").strip() == str(REPO / "src")
    _assert_importable_from_tmp(venv)


def test_regular_install_imports_outside_the_repo(tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    _install(venv, str(REPO))
    _assert_importable_from_tmp(venv)
