# Contributor instructions

- Keep `drift_ranger.py` a single-file Python standard-library CLI. Do not add a daemon, service, package dependency, network access, uploads, or telemetry.
- Treat all stored intent, capability, gap, and evidence text as private user data. Public examples and documentation must remain generic.
- Keep the default state store outside the repository and preserve the runtime refusal for any explicitly selected store that resolves inside the repository.
- Preserve immutable initialization and exclusive, append-only checkpoint files. Never silently overwrite an intent or checkpoint unit.
- Describe checkpoint content as agent assertions, not verified proof. Evidence is a note supplied by the agent and does not establish truth by itself.
- Preserve the reassessment rule: two consecutive `unchanged` or `unknown` events trigger `REASSESS`; `unknown` never counts as advancement.
- Preserve evidence qualification: `advanced` and `available` require non-empty evidence or must be represented as unknown.
