# drift-ranger

`drift-ranger` is a small, local CLI for recording what an agent says a project can do, what it still cannot do, and what gap comes next. It stores assertions, not independently verified proof.

The tool uses only the Python standard library. It has no daemon, network calls, uploads, or telemetry.

## Run it

Use Python 3.8 or newer:

```powershell
python .\drift_ranger.py init sample-tool --intent "Make one routine reliable" --entry-point "Run the documented command" --next-gap "Exercise the first real workflow"

python .\drift_ranger.py checkpoint sample-tool --unit work-001 --can "Complete the basic workflow" --cannot "Handle interrupted input" --next-gap "Recover from interruption" --progress advanced --evidence "Manual run completed" --stage implemented

python .\drift_ranger.py show sample-tool
python .\drift_ranger.py list
```

Project and unit IDs are path-safe identifiers: 1-64 ASCII letters, digits, dots, dashes, or underscores, beginning with a letter or digit. An `init` never overwrites an existing intent. Each checkpoint unit is written once to its own event file, and reusing that unit ID is refused.

Two consecutive checkpoints reported as `unchanged` or `unknown` produce a `REASSESS` advisory. Unknown status never counts as advancement. Reporting `advanced` or stage `available` without a non-empty evidence string is stored as `unknown`.

## Private state

State is kept outside this repository by default:

- Windows: `%LOCALAPPDATA%\drift-ranger`
- Other systems: `$XDG_STATE_HOME/drift-ranger`, or `~/.local/state/drift-ranger` when `XDG_STATE_HOME` is unset

Choose another external directory by placing `--store` before or after the command:

```powershell
python .\drift_ranger.py show --store D:\private-state\drift-ranger sample-tool
```

The CLI resolves the store path and refuses any location inside the repository, reducing the chance that private project notes are published with the code. Store contents remain ordinary local JSON files; protect and back them up according to their sensitivity.

## Data layout

Each project has an immutable initial `intent.json` and an `events` directory. Checkpoints are append-only in normal use and named by their unique unit ID. `show` orders events by their UTC record time and reports the latest capability assertion, next gap, latest reported stage, and non-advancing streak.

The tool does not independently inspect builds, deployments, logs, or external services. Evidence text is an agent-provided note and must be evaluated by the reader.
