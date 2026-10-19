#!/usr/bin/env python3
"""Keep private, local checkpoints about whether a project is advancing."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NON_ADVANCING = {"unchanged", "unknown"}
REASSESS_AFTER = 2


class DriftRangerError(Exception):
    """An expected error that can be shown without a traceback."""


def default_store() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "drift-ranger"
        return Path.home() / "AppData" / "Local" / "drift-ranger"

    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / "drift-ranger"
    return Path.home() / ".local" / "state" / "drift-ranger"


def resolve_store(raw_store: Optional[str]) -> Path:
    store = Path(raw_store).expanduser() if raw_store else default_store()
    store = store.resolve(strict=False)
    repository = Path(__file__).resolve().parent
    try:
        store.relative_to(repository)
    except ValueError:
        return store
    raise DriftRangerError(
        "refusing a state store inside the drift-ranger repository; choose an external path"
    )


def validate_id(value: str, label: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise DriftRangerError(
            f"invalid {label} {value!r}; use 1-64 ASCII letters, digits, dots, dashes, or underscores, starting with a letter or digit"
        )
    return value


def project_dir(store: Path, project_id: str) -> Path:
    return store / validate_id(project_id, "project id")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise DriftRangerError(f"not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise DriftRangerError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DriftRangerError(f"invalid JSON object in {path}")
    return value


def write_exclusive(path: Path, value: Dict[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise DriftRangerError(f"already exists: {path}") from exc
    except OSError as exc:
        raise DriftRangerError(f"cannot write {path}: {exc}") from exc


def load_intent(store: Path, project_id: str) -> Dict[str, Any]:
    return read_json(project_dir(store, project_id) / "intent.json")


def load_events(store: Path, project_id: str) -> List[Dict[str, Any]]:
    events_dir = project_dir(store, project_id) / "events"
    if not events_dir.exists():
        return []
    if not events_dir.is_dir():
        raise DriftRangerError(f"events path is not a directory: {events_dir}")

    events: List[Dict[str, Any]] = []
    for path in events_dir.glob("*.json"):
        event = read_json(path)
        event["_filename"] = path.name
        events.append(event)
    events.sort(key=lambda item: (str(item.get("recorded_at", "")), item["_filename"]))
    return events


def non_advancing_streak(events: Sequence[Dict[str, Any]]) -> int:
    streak = 0
    for event in reversed(events):
        if event.get("progress", "unknown") not in NON_ADVANCING:
            break
        streak += 1
    return streak


def command_init(args: argparse.Namespace, store: Path) -> None:
    project = project_dir(store, args.project_id)
    try:
        project.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DriftRangerError(f"cannot create {project}: {exc}") from exc

    intent = {
        "schema_version": 1,
        "project_id": args.project_id,
        "intent": args.intent,
        "entry_point": args.entry_point,
        "initial_next_gap": args.next_gap,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    write_exclusive(project / "intent.json", intent)
    print(f"initialized {args.project_id} in {project}")


def command_checkpoint(args: argparse.Namespace, store: Path) -> None:
    project = project_dir(store, args.project_id)
    load_intent(store, args.project_id)
    unit = validate_id(args.unit, "unit id")
    evidence = args.evidence.strip() if args.evidence else None

    progress = args.progress
    stage = args.stage
    qualifications: List[str] = []
    if progress == "advanced" and not evidence:
        progress = "unknown"
        qualifications.append("advanced requires evidence")
    if stage == "available" and not evidence:
        stage = "unknown"
        progress = "unknown"
        qualifications.append("available requires evidence")

    events_dir = project / "events"
    try:
        events_dir.mkdir(exist_ok=True)
    except OSError as exc:
        raise DriftRangerError(f"cannot create {events_dir}: {exc}") from exc

    event = {
        "schema_version": 1,
        "project_id": args.project_id,
        "unit": unit,
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assertion_notice": "Agent assertion; not independently verified proof.",
        "can": args.can,
        "cannot": args.cannot,
        "next_gap": args.next_gap,
        "progress": progress,
        "stage": stage,
        "evidence": evidence,
    }
    if qualifications:
        event["qualification"] = "; ".join(qualifications)
        event["reported_progress"] = args.progress
        event["reported_stage"] = args.stage

    write_exclusive(events_dir / f"{unit}.json", event)
    print(f"checkpointed {args.project_id}/{unit}: progress={progress}, stage={stage or 'not reported'}")
    if qualifications:
        print(f"qualified as unknown: {'; '.join(qualifications)}")


def command_show(args: argparse.Namespace, store: Path) -> None:
    intent = load_intent(store, args.project_id)
    events = load_events(store, args.project_id)

    print(f"Project: {args.project_id}")
    print(f"Intent: {intent.get('intent', '')}")
    print(f"Entry point: {intent.get('entry_point', '')}")
    print("Record type: agent assertions, not independently verified proof")

    if events:
        latest = events[-1]
        stage = "not reported"
        for event in reversed(events):
            if event.get("stage"):
                stage = str(event["stage"])
                break
        print(f"Can: {latest.get('can', '')}")
        print(f"Cannot: {latest.get('cannot', '')}")
        print(f"Next gap: {latest.get('next_gap', '')}")
        print(f"Stage: {stage}")
        print(f"Latest progress: {latest.get('progress', 'unknown')}")
    else:
        print("Can: no checkpoint recorded")
        print("Cannot: no checkpoint recorded")
        print(f"Next gap: {intent.get('initial_next_gap', '')}")
        print("Stage: not reported")
        print("Latest progress: unknown")

    streak = non_advancing_streak(events)
    print(f"Non-advancing streak: {streak}")
    if streak >= REASSESS_AFTER:
        print("Advisory: REASSESS")
    else:
        print("Advisory: continue tracking")


def command_list(store: Path) -> None:
    if not store.exists():
        print("No projects.")
        return
    if not store.is_dir():
        raise DriftRangerError(f"store is not a directory: {store}")

    project_ids = sorted(
        path.name for path in store.iterdir() if path.is_dir() and (path / "intent.json").is_file()
    )
    if not project_ids:
        print("No projects.")
        return
    for project_id in project_ids:
        print(project_id)


def add_store_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store",
        default=argparse.SUPPRESS,
        help="external private state directory (default: platform user state directory)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drift-ranger",
        description="Record local agent assertions about project progress.",
    )
    add_store_argument(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="create an immutable project intent")
    add_store_argument(init_parser)
    init_parser.add_argument("project_id")
    init_parser.add_argument("--intent", required=True)
    init_parser.add_argument("--entry-point", required=True)
    init_parser.add_argument("--next-gap", required=True)

    show_parser = commands.add_parser("show", help="show current assertions and advisory")
    add_store_argument(show_parser)
    show_parser.add_argument("project_id")

    checkpoint_parser = commands.add_parser("checkpoint", help="append one unique work-unit assertion")
    add_store_argument(checkpoint_parser)
    checkpoint_parser.add_argument("project_id")
    checkpoint_parser.add_argument("--unit", required=True)
    checkpoint_parser.add_argument("--can", required=True)
    checkpoint_parser.add_argument("--cannot", required=True)
    checkpoint_parser.add_argument("--next-gap", required=True)
    checkpoint_parser.add_argument(
        "--progress", required=True, choices=("advanced", "unchanged", "unknown")
    )
    checkpoint_parser.add_argument("--evidence")
    checkpoint_parser.add_argument(
        "--stage", choices=("implemented", "isolated", "available", "accepted")
    )

    list_parser = commands.add_parser("list", help="list initialized project ids")
    add_store_argument(list_parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        store = resolve_store(getattr(args, "store", None))
        if args.command == "init":
            command_init(args, store)
        elif args.command == "checkpoint":
            command_checkpoint(args, store)
        elif args.command == "show":
            command_show(args, store)
        elif args.command == "list":
            command_list(store)
        else:
            raise DriftRangerError(f"unsupported command: {args.command}")
    except DriftRangerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
