# drift-ranger

## Description

`drift-ranger` is a small, local CLI for recording what an agent says a project can do, what it still cannot do, and what gap comes next. It stores assertions, not independently verified proof.

The tool uses only the Python standard library. It has no daemon, network calls, uploads, or telemetry.

## Why

Long-running agent work drifts: supporting tasks (tests, reviews, documents) can quietly replace the outcome the user asked for. `drift-ranger` keeps one private record per outcome and flags when two consecutive work units did not advance it, so the coordinator reassesses instead of adding more supporting work. See [the intent contract](docs/intent-contract.md).

## Install

Requires Python 3.8 or newer and [uv](https://docs.astral.sh/uv/). From the root of a clone of this repository, run:

```text
uv tool install --from . drift-ranger
```

This puts the `drift-ranger` command on your PATH. `drift-ranger --version` prints the installed version.

Without installing, the same CLI runs from the repository root as `python ./drift_ranger.py <command> ...` (a thin shim over `src/drift_ranger/cli.py`) or, with `src` on `PYTHONPATH`, as `python -m drift_ranger <command> ...`.

## Quick start

List the projects recorded in your default private store (prints `No projects.` on first use):

```text
drift-ranger list
```

Record an outcome, one checkpoint, and read it back:

```powershell
drift-ranger init sample-tool --intent "Make one routine reliable" --entry-point "Run the documented command" --next-gap "Exercise the first real workflow"

drift-ranger checkpoint sample-tool --unit work-001 --can "Complete the basic workflow" --cannot "Handle interrupted input" --next-gap "Recover from interruption" --progress advanced --evidence "Manual run completed" --stage implemented

drift-ranger show sample-tool
```

Project and unit IDs are path-safe identifiers: 1-64 ASCII letters, digits, dots, dashes, or underscores, beginning with a letter or digit. An `init` never overwrites an existing intent. Each checkpoint unit is written once to its own event file, and reusing that unit ID is refused.

Two consecutive checkpoints reported as `unchanged` or `unknown` produce a `REASSESS` advisory. Unknown status never counts as advancement. Reporting `advanced` or stage `available` without a non-empty evidence string is stored as `unknown`.

## Verify

From the root of a clone of this repository, run:

```text
uv run --extra dev pytest -q
```

Verification passes when the command exits with status zero and pytest reports every test passed. The tests use synthetic records in temporary stores only. They check that every subcommand of the checkout shim, `python -m drift_ranger` and the console command produces the same output as the original single-file script, and that stored records match the store-format contract.

## Supported platforms

Verified on Windows 11 with Python 3.14 (evidence: `tests/test_cli.py`). Linux and macOS with Python 3.8 or newer are supported by design (the store follows `XDG_STATE_HOME`) but have not been verified.

## Input and output

Input is command-line arguments: one subcommand (`init`, `checkpoint`, `show`, `list`, `export-observatory`) and an optional `--store <directory>`. Output is plain text on standard output; errors go to standard error. The records themselves are local JSON files in the private store described below, owned by the user who runs the tool.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The command succeeded. |
| `1` | An expected error: a missing, invalid or existing record, an unusable store, or a store inside the repository. The message is printed as `error: ...` on standard error. |
| `2` | A usage error: a missing or unknown subcommand, argument or choice. |

## Private state

State is kept outside this repository by default:

- Windows: `%LOCALAPPDATA%\drift-ranger`
- Other systems: `$XDG_STATE_HOME/drift-ranger`, or `~/.local/state/drift-ranger` when `XDG_STATE_HOME` is unset

Choose another external directory by placing `--store` before or after the command:

```powershell
drift-ranger show --store D:\private-state\drift-ranger sample-tool
```

The CLI resolves the store path and refuses any location inside the repository (or, for an installed copy, inside its package directory), reducing the chance that private project notes are published with the code. Store contents remain ordinary local JSON files; protect and back them up according to their sensitivity.

## Data layout

Each project has an immutable initial `intent.json` and an `events` directory. Checkpoints are append-only in normal use and named by their unique unit ID. `show` orders events by their UTC record time and reports the latest capability assertion, next gap, latest reported stage, and non-advancing streak. Other files in a project folder are ignored.

The store-format contract for both records is pinned by `tests/test_store_contract.py`, which runs against a synthetic copy of the store layout in `tests/fixtures/store`.

The tool does not independently inspect builds, deployments, logs, or external services. Evidence text is an agent-provided note and must be evaluated by the reader.

## Local intent explorer

From this repository, run `python ./drift_ranger.py export-observatory` (or `drift-ranger export-observatory` when installed) to refresh
`observatory/intents.json` inside the default private store. Dev Observatory's
**Show intents** uses its shared project, list and detail Explorer. **Refresh intents**
under all verbs invokes this command; reload the page afterward. It displays a
snapshot, not live monitoring, and rejects snapshots older than seven days.

The artifact contains private intent and capability text. It stays outside Git and
is available only in the local served Observatory, never static or portfolio exports.
The command changes only this derived snapshot; immutable intent and append-only
checkpoint records remain unchanged. Failed exports preserve the previous snapshot.
A custom `--store` is supported by the CLI, but Observatory reads the default store only.

The versioned payload uses `explorer.v1` with `generated_at` and `items` containing
stable hashed `id`, project `label`, intent `summary` and readable `detail` fields.
Inputs are bounded to 256 KiB per record, 1,000 projects and 10,000 checkpoints;
output is bounded to 1 MB. Missing/invalid/oversized input fails visibly.

The exporter tests are in `tests/test_observatory_export.py`; they use synthetic records in temporary external stores.

## Development

```text
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run mypy drift_ranger.py
```

`mypy` checks the shim separately because it shares the package's module name. `tests/fixtures/baseline/drift_ranger_v0.py.txt` is a frozen copy of the original single-file script, kept as the behaviour baseline; do not edit it.

## License

MIT. See [LICENSE](LICENSE).
