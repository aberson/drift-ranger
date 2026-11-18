"""CLI entry points: unchanged behaviour, the version flag, and packaging wiring.

The behaviour baseline is the pre-package single-file script, kept verbatim in
``tests/fixtures/baseline/drift_ranger_v0.py.txt`` (git blob pinned below). Every
subcommand runs through the baseline, the checkout shim, ``python -m drift_ranger`` and
the console-script target ``drift_ranger.cli:main`` against identical fixture stores at
the same path, and must produce identical stdout and stderr bytes, exit codes and store
contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from conftest import FIXTURES, REPO, copy_fixture_store

import drift_ranger
from drift_ranger import cli

BASELINE = FIXTURES / "baseline" / "drift_ranger_v0.py.txt"
# `git rev-parse dab3ddc:drift_ranger.py`: the script as it was before packaging.
BASELINE_BLOB = "d8667cbb032e61baa5bfbb99da50bc64ed6cbd24"
SHIM = REPO / "drift_ranger.py"
SRC = REPO / "src"
CONSOLE_SCRIPT = "import sys; from drift_ranger.cli import main; sys.exit(main())"

RUNNERS = {
    "baseline": [sys.executable, str(BASELINE)],
    "shim": [sys.executable, str(SHIM)],
    "module": [sys.executable, "-m", "drift_ranger"],
    "console-script": [sys.executable, "-c", CONSOLE_SCRIPT],
}
STORE = "<STORE>"  # replaced by the per-test explicit store path
MISSING = "<MISSING>"  # replaced by a path that does not exist
TIMESTAMP_KEYS = {"created_at", "recorded_at", "generated_at"}
# The one intended difference from the baseline: the new top-level ``--version`` option
# appears in the top-level usage line that argparse prints with a top-level usage error.
VERSION_IN_USAGE = b"[--version] "
TOP_LEVEL_USAGE_ERRORS = {"no-command", "unknown-command"}
NEWLINE = os.linesep.encode()


class Result(NamedTuple):
    code: int
    stdout: bytes
    stderr: bytes
    files: dict[str, Any]


def _break_intent(store: Path) -> None:
    (store / "alpha-tool" / "intent.json").write_text("broken", encoding="utf-8")


INIT = ["--intent", "Sample intent", "--entry-point", "Run it", "--next-gap", "First gap"]
CHECK = ["--can", "One thing", "--cannot", "Next thing", "--next-gap", "Next gap"]


def _checkpoint(project: str, unit: str, progress: str, *extra: str) -> list[str]:
    return [
        "checkpoint",
        project,
        "--unit",
        unit,
        *CHECK,
        "--progress",
        progress,
        *extra,
        "--store",
        STORE,
    ]


# (case id, argv, optional store mutation before the run)
CASES: list[tuple[str, list[str], Any]] = [
    ("list", ["list", "--store", STORE], None),
    ("list-store-first", ["--store", STORE, "list"], None),
    ("list-default-store", ["list"], None),
    ("list-missing-store", ["list", "--store", MISSING], None),
    ("show-reassess", ["show", "alpha-tool", "--store", STORE], None),
    ("show-no-events", ["show", "beta.service", "--store", STORE], None),
    ("show-qualified-non-ascii", ["show", "gamma_app", "--store", STORE], None),
    ("show-default-store", ["show", "gamma_app"], None),
    ("show-missing-project", ["show", "absent", "--store", STORE], None),
    ("show-invalid-id", ["show", "../escape", "--store", STORE], None),
    ("init-new", ["init", "delta-new", *INIT, "--store", STORE], None),
    ("init-existing", ["init", "alpha-tool", *INIT, "--store", STORE], None),
    ("init-invalid-id", ["init", "bad/id", *INIT, "--store", STORE], None),
    (
        "checkpoint-advanced",
        _checkpoint(
            "alpha-tool", "u-10", "advanced", "--evidence", "Synthetic run", "--stage", "available"
        ),
        None,
    ),
    ("checkpoint-advanced-no-evidence", _checkpoint("beta.service", "u-11", "advanced"), None),
    (
        "checkpoint-available-no-evidence",
        _checkpoint("alpha-tool", "u-12", "unchanged", "--stage", "available", "--evidence", " "),
        None,
    ),
    ("checkpoint-duplicate-unit", _checkpoint("alpha-tool", "unit-001", "unknown"), None),
    ("checkpoint-missing-project", _checkpoint("absent", "u-13", "unknown"), None),
    ("checkpoint-bad-progress", _checkpoint("alpha-tool", "u-14", "maybe"), None),
    ("export-observatory", ["export-observatory", "--store", STORE], None),
    ("export-observatory-default-store", ["export-observatory"], None),
    ("export-observatory-missing-store", ["export-observatory", "--store", MISSING], None),
    ("export-observatory-malformed", ["export-observatory", "--store", STORE], _break_intent),
    ("no-command", [], None),
    ("unknown-command", ["frobnicate"], None),
    ("show-missing-argument", ["show", "--store", STORE], None),
    *[
        (f"help-{name}", [name, "--help"], None)
        for name in ("init", "show", "checkpoint", "list", "export-observatory")
    ],
]


def _environment(sandbox: Path, src_on_path: bool) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME"):
        env.pop(key, None)
    # Point the default store at the sandbox; the real private store is never touched.
    env["LOCALAPPDATA"] = str(sandbox / "localappdata")
    env["XDG_STATE_HOME"] = str(sandbox / "localappdata")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["COLUMNS"] = "100"
    if src_on_path:
        env["PYTHONPATH"] = str(SRC)
    return env


def _snapshot(store: Path) -> dict[str, Any]:
    """Store contents with run-time timestamps masked, keyed by relative path."""
    if not store.exists():
        return {}
    files: dict[str, Any] = {}
    for path in sorted(store.rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        try:
            value: Any = json.loads(raw)
        except ValueError:
            value = raw
        if isinstance(value, dict):
            value = {k: "<ts>" if k in TIMESTAMP_KEYS else v for k, v in value.items()}
        files[path.relative_to(store).as_posix()] = value
    return files


def _run(runner: str, argv: list[str], mutate: Any, sandbox: Path) -> Result:
    """Run one entry point in its own sandbox, with the sandbox path masked in its output."""
    (sandbox / "cwd").mkdir(parents=True)
    store = sandbox / "store"
    default_store = sandbox / "localappdata" / "drift-ranger"
    copy_fixture_store(store)
    copy_fixture_store(default_store)
    if mutate is not None:
        mutate(store)
    args = [
        str(store) if arg == STORE else str(sandbox / "missing") if arg == MISSING else arg
        for arg in argv
    ]
    completed = subprocess.run(
        [*RUNNERS[runner], *args],
        cwd=sandbox / "cwd",  # neutral: never the checkout, whose shim shares the name
        env=_environment(sandbox, src_on_path=runner in {"module", "console-script"}),
        capture_output=True,
        timeout=60,
        check=False,
    )
    # Runners execute concurrently in sibling sandboxes, so the one place a store path is
    # echoed (init's confirmation, not-found errors) is masked before byte comparison.
    location = str(sandbox).encode()
    return Result(
        completed.returncode,
        completed.stdout.replace(location, b"<SANDBOX>"),
        completed.stderr.replace(location, b"<SANDBOX>"),
        {"store": _snapshot(store), "default": _snapshot(default_store)},
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    (tmp_path / "cwd").mkdir()
    return tmp_path


@pytest.mark.parametrize(("case", "argv", "mutate"), CASES, ids=[c[0] for c in CASES])
def test_every_entry_point_matches_the_pre_package_script(
    tmp_path: Path, case: str, argv: list[str], mutate: Any
) -> None:
    with ThreadPoolExecutor(max_workers=len(RUNNERS)) as pool:
        futures = {
            runner: pool.submit(_run, runner, argv, mutate, tmp_path / runner) for runner in RUNNERS
        }
        results = {runner: future.result() for runner, future in futures.items()}
    baseline = results.pop("baseline")
    shim = results["shim"]
    assert baseline.stdout or baseline.stderr, "the baseline produced no output"
    # The shim reproduces the pre-package script byte for byte.
    assert shim.code == baseline.code
    assert shim.stdout == baseline.stdout
    assert shim.files == baseline.files
    if case in TOP_LEVEL_USAGE_ERRORS:
        # Same message; argparse may re-wrap the longer usage line, so compare words.
        assert shim.stderr.count(VERSION_IN_USAGE) == 1
        assert shim.stderr.replace(VERSION_IN_USAGE, b"").split() == baseline.stderr.split()
    else:
        assert shim.stderr == baseline.stderr
    # Every installed-entry-point form reproduces the shim byte for byte.
    for runner, result in results.items():
        assert result == shim, runner


def test_matrix_covers_every_subcommand() -> None:
    subcommands = {"init", "show", "checkpoint", "list", "export-observatory"}
    parser = cli.build_parser()
    choices = [a.choices for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert set(choices[0]) == subcommands
    exercised = {argv[0] for _, argv, _ in CASES if argv and argv[0] in subcommands}
    assert exercised == subcommands


def test_baseline_fixture_is_the_pre_package_script() -> None:
    data = BASELINE.read_bytes().replace(b"\r\n", b"\n")
    blob = hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()  # a git object id
    assert blob == BASELINE_BLOB


# --- The version flag (the manifest health check) -------------------------------------


@pytest.mark.parametrize("runner", ["shim", "module", "console-script"])
def test_version_flag_prints_the_package_version(sandbox: Path, runner: str) -> None:
    completed = subprocess.run(
        [*RUNNERS[runner], "--version"],
        cwd=sandbox / "cwd",
        env=_environment(sandbox, src_on_path=runner != "shim"),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout == f"drift-ranger {drift_ranger.__version__}".encode() + NEWLINE
    assert not (sandbox / "localappdata").exists()  # no store is touched


def test_version_has_one_source() -> None:
    assert vars(cli)["__version__"] is drift_ranger.__version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", drift_ranger.__version__)
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'(?m)^dynamic = \["version"\]$', pyproject)
    assert not re.search(r"(?m)^version\s*=", pyproject)
    assert re.search(r'(?m)^path = "src/drift_ranger/__init__.py"$', pyproject)


# --- Packaging wiring: the console command reaches the CLI -----------------------------


def test_console_script_targets_cli_main() -> None:
    tomllib = pytest.importorskip("tomllib")
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == []  # standard library only
    module_name, _, attribute = project["scripts"]["drift-ranger"].partition(":")
    module = __import__(module_name, fromlist=[attribute])
    assert getattr(module, attribute) is cli.main


def test_console_main_runs_a_subcommand(store: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["export-observatory", "--store", str(store)]) == 0
    assert capsys.readouterr().out == "Refreshed private intent snapshot: 3 projects.\n"
    snapshot = json.loads((store / "observatory" / "intents.json").read_text("utf-8"))
    assert [item["label"] for item in snapshot["items"]] == [
        "alpha-tool",
        "beta.service",
        "gamma_app",
    ]


# --- The store-inside-the-repository refusal is preserved ------------------------------


@pytest.mark.parametrize("runner", ["shim", "module"])
def test_store_inside_the_checkout_is_refused(sandbox: Path, runner: str) -> None:
    inside = REPO / "state" / "refusal-probe"
    completed = subprocess.run(
        [*RUNNERS[runner], "init", "probe", *INIT, "--store", str(inside)],
        cwd=sandbox / "cwd",
        env=_environment(sandbox, src_on_path=runner == "module"),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stderr == (
        b"error: refusing a state store inside the drift-ranger repository; "
        b"choose an external path" + NEWLINE
    )
    assert not inside.exists()


def test_repository_root_is_the_checkout() -> None:
    assert cli.repository_root() == REPO


def test_installed_package_refuses_its_own_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "site-packages" / "drift_ranger"
    package.mkdir(parents=True)
    shutil.copy(Path(cli.__file__), package / "cli.py")
    monkeypatch.setattr(cli, "__file__", str(package / "cli.py"))
    assert cli.repository_root() == package.resolve()
    with pytest.raises(cli.DriftRangerError, match="refusing a state store"):
        cli.resolve_store(str(package / "store"))
    assert cli.resolve_store(str(tmp_path / "external")) == (tmp_path / "external").resolve()
