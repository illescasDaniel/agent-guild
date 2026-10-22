## Phase Gate Protocol (Spec-Driven Development)

Every feature or user-facing change goes through these phases. Full workflow: the `sdd-feature` skill.

| Phase | Deliverable | Gate |
|-------|-------------|------|
| **0 — Design** | UI track: `wireframes/<screen>.html` (self-contained HTML/CSS). System track (APIs, data, jobs, events, services): `design/<feature>/DESIGN.md` with Mermaid diagrams, checked with `design_preview.py --check`. Fullstack: both | **Stop.** Ask for design approval (one gate for both tracks). |
| **1 — Spec** | `specs/<feature>/SPEC.md`: agreed Design decisions (success criteria, failure handling, performance/resource budget, trust boundary, compatibility & rollout), a scenario for every `F<n>` failure branch of the design, BDD scenarios, Out of scope | **Stop.** Ask for spec approval. |
| **2 — Architecture** | Domain types and interfaces only | **Stop.** Ask for approval before tests/adapters. |
| **3 — Tests** | Unit tests from the BDD scenarios | Run them. |
| **4 — Implementation** | Use cases, adapters, UI | Until tests pass; must match the approved wireframe and `DESIGN.md`. |
| **5 — Grade** | Read-only `code-grader` subagent scores the branch against the spec | Automatic: fix FAILs, max 2 rounds, show the scorecard. |

- **Never skip a gate.** "Implement the plan", "complete all todos", an attached plan file or plan-mode approval is
  **not** design or spec approval; approval must be explicit, in chat. One gate per approval: after the wireframe, end
  the turn and wait.
- If implementation reveals a spec flaw, rewrite the spec, get re-approval, then continue. Don't patch around a bad spec.
- No production code before spec approval. Allowed before it: `wireframes/`, `design/`, `specs/` and docs.
