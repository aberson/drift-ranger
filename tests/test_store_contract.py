"""Store-format contract for the records the intent-continuity contract reads.

Skill Mesh's intent-continuity contract reads, per outcome, one private intent record
(intended outcome, actual entry point, initial next gap) and the checkpoint records
(current capability, missing capability, next gap, progress, stage, evidence). This file
pins the on-disk shape of both records: ``<store>/<project>/intent.json`` and
``<store>/<project>/events/<unit>.json``. Everything else in a project folder (notes,
preparation folders) and the ``observatory`` snapshot folder is not a record.

The fixture store is a synthetic copy of a real store's layout; no real records are used.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable

import pytest
from conftest import FIXTURE_STORE

from drift_ranger import cli

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
INTENT_FIELDS = {
    "schema_version",
    "project_id",
    "intent",
    "entry_point",
    "initial_next_gap",
    "created_at",
}
EVENT_FIELDS = {
    "schema_version",
    "project_id",
    "unit",
    "recorded_at",
    "assertion_notice",
    "can",
    "cannot",
    "next_gap",
    "progress",
    "stage",
    "evidence",
}
# Present together, and only, when a checkpoint was qualified as unknown.
QUALIFICATION_FIELDS = {"qualification", "reported_progress", "reported_stage"}
# The producer's own vocabulary: one source of truth, shared with the CLI parser.
PROGRESS_VALUES = cli.PROGRESS_CHOICES
STAGE_VALUES = (*cli.STAGE_CHOICES, "unknown")


def _load(path: Path, problems: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        problems.append(f"{path.name}: unreadable JSON ({exc.__class__.__name__})")
        return None
    if not isinstance(value, dict):
        problems.append(f"{path.name}: not a JSON object")
        return None
    return value


def _common(record: dict[str, Any], label: str, project: str, problems: list[str]) -> None:
    version = record.get("schema_version")
    if type(version) is not int or version != 1:
        problems.append(f"{label}: schema_version must be the integer 1")
    if record.get("project_id") != project:
        problems.append(f"{label}: project_id must equal the project folder name")


def _text(record: dict[str, Any], key: str, label: str, problems: list[str]) -> None:
    if not isinstance(record.get(key), str):
        problems.append(f"{label}: {key} must be a string")


def _timestamp(record: dict[str, Any], key: str, label: str, problems: list[str]) -> None:
    value = record.get(key)
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        problems.append(f"{label}: {key} must be a UTC ISO-8601 timestamp ending in Z")


def intent_violations(path: Path, project: str) -> list[str]:
    problems: list[str] = []
    label = f"{project}/intent.json"
    record = _load(path, problems)
    if record is None:
        return problems
    if set(record) != INTENT_FIELDS:
        problems.append(f"{label}: fields {sorted(record)} differ from {sorted(INTENT_FIELDS)}")
    _common(record, label, project, problems)
    for key in ("intent", "entry_point", "initial_next_gap"):
        _text(record, key, label, problems)
    _timestamp(record, "created_at", label, problems)
    return problems


def event_violations(path: Path, project: str) -> list[str]:
    problems: list[str] = []
    label = f"{project}/events/{path.name}"
    record = _load(path, problems)
    if record is None:
        return problems
    keys = set(record)
    extra = keys - EVENT_FIELDS
    if not EVENT_FIELDS <= keys or extra not in (set(), QUALIFICATION_FIELDS):
        problems.append(f"{label}: fields {sorted(keys)} do not match the checkpoint record")
    _common(record, label, project, problems)
    unit = record.get("unit")
    if not isinstance(unit, str) or not cli.SAFE_ID.fullmatch(unit) or path.stem != unit:
        problems.append(f"{label}: unit must be a safe id equal to the file name")
    _timestamp(record, "recorded_at", label, problems)
    for key in ("assertion_notice", "can", "cannot", "next_gap"):
        _text(record, key, label, problems)
    progress = record.get("progress")
    stage = record.get("stage")
    evidence = record.get("evidence")
    if progress not in PROGRESS_VALUES:
        problems.append(f"{label}: progress must be one of {PROGRESS_VALUES}")
    if stage is not None and stage not in STAGE_VALUES:
        problems.append(f"{label}: stage must be null or one of {STAGE_VALUES}")
    if evidence is not None and not isinstance(evidence, str):
        problems.append(f"{label}: evidence must be null or a string")
    has_evidence = isinstance(evidence, str) and bool(evidence)
    if progress == "advanced" and not has_evidence:
        problems.append(f"{label}: advanced progress requires evidence")
    if stage == "available" and not has_evidence:
        problems.append(f"{label}: available stage requires evidence")
    if extra == QUALIFICATION_FIELDS and progress != "unknown":
        problems.append(f"{label}: a qualified checkpoint must record progress unknown")
    return problems


def contract_violations(store: Path) -> list[str]:
    """Return every contract violation in ``store``; an empty list means it conforms."""
    problems: list[str] = []
    for project in sorted(store.iterdir()):
        if project.name == "observatory" or not project.is_dir():
            continue
        intent = project / "intent.json"
        if not intent.is_file():
            continue
        if not cli.SAFE_ID.fullmatch(project.name):
            problems.append(f"{project.name}: project folder is not a safe id")
        problems.extend(intent_violations(intent, project.name))
        events = project / "events"
        if events.exists():
            if not events.is_dir():
                problems.append(f"{project.name}/events: not a directory")
                continue
            for event in sorted(events.glob("*.json")):
                problems.extend(event_violations(event, project.name))
    return problems


def assert_store_conforms(store: Path) -> None:
    problems = contract_violations(store)
    assert not problems, "store contract violations:\n" + "\n".join(problems)


def _projects(store: Path) -> list[str]:
    return sorted(
        path.name
        for path in store.iterdir()
        if path.is_dir() and path.name != "observatory" and (path / "intent.json").is_file()
    )


# --- The fixture is a faithful copy of the real layout ---------------------------------


def test_fixture_store_conforms_to_contract() -> None:
    assert_store_conforms(FIXTURE_STORE)


def test_fixture_store_covers_every_layout_shape() -> None:
    projects = _projects(FIXTURE_STORE)
    assert projects == ["alpha-tool", "beta.service", "gamma_app"]
    # A project with checkpoints, one without an events folder yet.
    assert len(list((FIXTURE_STORE / "alpha-tool" / "events").glob("*.json"))) == 3
    assert not (FIXTURE_STORE / "beta.service" / "events").exists()
    # Non-record files beside the records, as real project folders carry.
    assert (FIXTURE_STORE / "gamma_app" / "notes.json").is_file()
    assert (FIXTURE_STORE / "gamma_app" / "preparation-20260301").is_dir()
    # A qualified checkpoint and the derived explorer snapshot.
    qualified = json.loads(
        (FIXTURE_STORE / "gamma_app" / "events" / "second.pass.json").read_text("utf-8")
    )
    assert QUALIFICATION_FIELDS <= set(qualified)
    assert (FIXTURE_STORE / "observatory" / "intents.json").is_file()


def test_contract_vocabulary_is_the_producer_vocabulary() -> None:
    assert PROGRESS_VALUES is cli.PROGRESS_CHOICES
    assert set(STAGE_VALUES) - set(cli.STAGE_CHOICES) == {"unknown"}
    assert {"unchanged", "unknown"} == cli.NON_ADVANCING


# --- Producer round trip: what the CLI writes satisfies the contract ------------------


def _init(store: Path, project: str) -> None:
    cli.command_init(
        argparse.Namespace(
            project_id=project, intent="Ship a sample", entry_point="Run it", next_gap="Start"
        ),
        store,
    )


def _checkpoint(store: Path, project: str, unit: str, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "project_id": project,
        "unit": unit,
        "can": "Do one thing",
        "cannot": "Do the next thing",
        "next_gap": "The next thing",
        "progress": "unchanged",
        "evidence": None,
        "stage": None,
    }
    values.update(overrides)
    cli.command_checkpoint(argparse.Namespace(**values), store)


def test_records_written_by_the_cli_satisfy_the_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "fresh"
    _init(store, "sample")
    _checkpoint(store, "sample", "u1", progress="advanced", evidence="Ran it", stage="isolated")
    _checkpoint(store, "sample", "u2", progress="advanced")  # qualified: no evidence
    _checkpoint(store, "sample", "u3", progress="unchanged", stage="available")  # qualified
    _checkpoint(store, "sample", "u4", progress="unknown", evidence="   ", stage="accepted")
    capsys.readouterr()

    assert_store_conforms(store)
    intent = json.loads((store / "sample" / "intent.json").read_text("utf-8"))
    assert set(intent) == INTENT_FIELDS
    plain = json.loads((store / "sample" / "events" / "u1.json").read_text("utf-8"))
    assert set(plain) == EVENT_FIELDS
    qualified = json.loads((store / "sample" / "events" / "u2.json").read_text("utf-8"))
    assert set(qualified) == EVENT_FIELDS | QUALIFICATION_FIELDS


# --- Consumer: the CLI reads the fields the contract names -----------------------------


def test_show_reads_contract_fields_from_the_fixture_layout(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["show", "alpha-tool", "--store", str(store)]) == 0
    shown = capsys.readouterr().out.splitlines()
    assert "Intent: Make one routine reliable" in shown
    assert "Entry point: Run the documented command" in shown
    assert "Can: Complete the basic workflow" in shown
    assert "Cannot: Handle interrupted input" in shown
    assert "Next gap: Recover from interruption" in shown
    assert "Stage: isolated" in shown  # latest reported stage, skipping null stages
    assert "Advisory: REASSESS" in shown  # two consecutive unchanged checkpoints

    assert cli.main(["show", "beta.service", "--store", str(store)]) == 0
    assert "Next gap: Render the first page" in capsys.readouterr().out

    assert cli.main(["list", "--store", str(store)]) == 0
    assert capsys.readouterr().out.split() == _projects(store)


# --- Red on garbage: a malformed record makes the contract check fail ------------------


def _rewrite(path: Path, change: Callable[[dict[str, Any]], object]) -> None:
    record = json.loads(path.read_text("utf-8"))
    change(record)
    path.write_text(json.dumps(record), encoding="utf-8")


def _event(store: Path) -> Path:
    return store / "alpha-tool" / "events" / "unit-001.json"


def _intent(store: Path) -> Path:
    return store / "alpha-tool" / "intent.json"


MALFORMED: dict[str, Callable[[Path], object]] = {
    "event missing can": lambda s: _rewrite(_event(s), lambda r: r.pop("can")),
    "event progress outside vocabulary": lambda s: _rewrite(
        _event(s), lambda r: r.update(progress="maybe")
    ),
    "advanced without evidence": lambda s: _rewrite(_event(s), lambda r: r.update(evidence="")),
    "available without evidence": lambda s: _rewrite(
        _event(s), lambda r: r.update(stage="available", evidence=None, progress="unchanged")
    ),
    "event project id mismatch": lambda s: _rewrite(
        _event(s), lambda r: r.update(project_id="other")
    ),
    "unit differs from file name": lambda s: _rewrite(_event(s), lambda r: r.update(unit="x")),
    "schema version as text": lambda s: _rewrite(_event(s), lambda r: r.update(schema_version="1")),
    "timestamp without zone": lambda s: _rewrite(
        _event(s), lambda r: r.update(recorded_at="2026-01-06 10:00")
    ),
    "intent text not a string": lambda s: _rewrite(_intent(s), lambda r: r.update(intent=7)),
    "intent missing entry point": lambda s: _rewrite(_intent(s), lambda r: r.pop("entry_point")),
    "intent is a JSON array": lambda s: _intent(s).write_text("[]", encoding="utf-8"),
    "event is not JSON": lambda s: _event(s).write_text("broken", encoding="utf-8"),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_malformed_record_fails_the_contract(store: Path, case: str) -> None:
    assert_store_conforms(store)  # the unmodified copy is green
    MALFORMED[case](store)
    assert contract_violations(store)
    with pytest.raises(AssertionError, match="store contract violations"):
        assert_store_conforms(store)
