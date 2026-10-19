# drift-ranger

## Intended outcome

A coordinator can preserve the user's intended journey across work and handoffs,
report actual capability changes, and notice when supporting work displaces delivery.

## Initial scope

Implemented as a Python standard-library CLI and a portable instruction contract.
Intent records and checkpoint events remain in an external local private store;
the public repository contains tooling and generic documentation only.

The CLI initializes an outcome, appends uniquely identified work checkpoints, lists
records, and shows capability, next gap and reassessment status. Two consecutive
unchanged or unknown checkpoints signal REASSESS. The coordinator makes the scope
decision; the tool never authorizes execution or certifies evidence.

Skill integrations establish intent during planning, map work to gaps during build
coordination, preserve it through task-handoff, and report delivery truth at closeout.
See [the contract](../intent-contract.md).

## Delivery status

Initial implementation delivered without tests or independent verification at the
requester's direction. No daemon, dashboard, hosted data store, telemetry, mandatory
review campaign, or automatic publication of project information is in scope.
