## Friction log

Every memory-bank setup includes `memory/friction/` as a secondary maintenance backlog, separate from the project
memory used to resume work. It is not read at session start. The orchestrator records tool, documentation and
workflow problems when they happen, then keeps working. Use one small dated file (`YYYY-MM-DD-short-slug.md`)
per incident, following `memory/friction/README.md`: what was called, expected, got, and the workaround. Redact
secrets and personal paths; skip your own typos and one-off environment issues. Subagents report friction to the
orchestrator instead of writing memory themselves. Review open entries when planning maintenance; logging an issue
does not make fixing it part of the current task. Current blockers also belong in `memory/activeContext.md`.

The installer seeds only `memory/friction/`. If the core memory-bank files are missing, set them up from the
`memory-bank` skill's templates even though `memory/` already exists; copy only missing files and preserve all
existing notes.
