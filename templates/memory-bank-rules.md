## Memory bank

Project state lives in `memory/` (git-tracked, so it follows the branch). At session start, read
`memory/activeContext.md` then `memory/progress.md`. Update on these triggers only: a task is completed or discovered
(`progress.md`); focus changes, a blocker is hit or work concludes (`activeContext.md`); a significant technical
decision is made (`decisions.md`, append-only, newest first). Full protocol: the `memory-bank` skill.
