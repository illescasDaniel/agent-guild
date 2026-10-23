# Changelog

## [Unreleased]

## [1.3.3] - 2026-10-23

- Enable memory-bank friction logging by default: seed `memory/friction/` without replacing existing notes and
  install a separate Friction log rules section, including for projects with existing Memory bank rules.
- Clarify that friction is a secondary maintenance backlog, separate from session context. Pin the updated
  memory-bank skill, which includes friction in every setup and creates missing core files in partial memory banks.

## [1.3.2] - 2026-10-22

- Cursor and Codex agent copies now refer only to `AGENTS.md` instead of "`CLAUDE.md` / `AGENTS.md`"; Claude Code copies are unchanged.
- Keep CRLF line endings when appending the rules sections to an existing `AGENTS.md`/`CLAUDE.md`, instead of rewriting the file with LF.

## [1.3.1] - 2026-10-22

- Install Codex skills into the supported `.agents/skills/` discovery path. Reuse existing project skill copies,
  including supporting files, when adding Codex; legacy `.codex/skills/` installs are preserved as a migration source.
- Migrate shared rules from `CLAUDE.md` into `AGENTS.md` when adding Cursor or Codex, preserving project customizations,
  Claude-only sections and the Claude import shim. Warn on conflicting duplicate sections. Dry runs remain read-only.
- Reuse existing project MCP arguments and environment settings when adding a Codex server, while preserving existing
  Codex entries. Generated shared rules explicitly tell every tool to read the workflow file.
- Quote language-coder descriptions as valid YAML, and decode quoted values before converting to Cursor or Codex.

## [1.3.0] - 2026-10-22

- Cursor and Codex support. The installer detects the tools a project uses (`.claude/` or `CLAUDE.md`, `.cursor/`,
  `.codex/` or `.agents/`; Claude Code when none) and installs for each one, or for `--tools claude,cursor,codex`.
  Agents are written in each tool's format (Cursor `readonly`, Codex TOML), skills go to `.cursor/skills/` and
  `.codex/skills/`, and the jevmem and language-coder MCP servers to `.cursor/mcp.json` and `.codex/config.toml`.
  Hooks, auto-memory and the model setting stay Claude Code only.
- The rules sections now go to `AGENTS.md` (created if missing; `CLAUDE.md` only when it is the sole file). With Claude
  Code, `CLAUDE.md` gets an `@AGENTS.md` import.

## [1.2.1] - 2026-10-22

- The install log says `skipped ... section '<name>' is already in CLAUDE.md or AGENTS.md` instead of the confusing
  `unchanged`, notes when `.claude/skills` is a symlink and where skills are written, and ends with a hint to merge
  skipped files that differ by hand.
- README: a section on adding agent-guild to a project that already has its own agents, skills and rules.

## [1.2.0] - 2026-10-22

- Follow the updated sdd-feature skill: Phase 0 has a UI track (wireframe) and a system track (`DESIGN.md` with Mermaid
  diagrams), a fifth design decision (compatibility & rollout), a scenario per `F<n>` failure branch, and the grader
  checks design fidelity. Updated `sdd-rules.md`, `development-workflow.md`, `architect` and `code-grader`.
- `coder-typescript` knows that webnav diagnostics can report missing `@types` errors the project's own `tsc` does not.

## [1.1.0] - 2026-10-22

- `--with coder-python` / `coder-swift` / `coder-typescript`: optional language coders that must use the language's
  code-navigation MCP (codenav-mcp, codenav-swift-mcp, webnav-ts-mcp) for finding usages and refactoring. The installer
  also adds the MCP server to `.mcp.json` and a routing rule to `CLAUDE.md`.
- After an install, the tool detects Python, Swift and TypeScript/JavaScript in the project and suggests the matching
  `--with coder-…` command. `--coders-only` adds just those coders without touching anything else.
- The brief rules now say to state the goal, not how to search or edit.
- The generic `coder` prefers code-navigation tools when the project has them.
- The manual install instructions moved to `docs/manual_installation.md`.

## [1.0.0] - 2026-10-21

First release.

- Multi-agent setup for Claude Code: a Sonnet orchestrator that delegates to `architect`, `coder`, `code-grader` and
  `utility` subagents, with the routing, briefs and memory protocol in `development-workflow.md`.
- Memory in two layers: memory-bank (current state, in a git-tracked `memory/` folder) and jev-mem (long-term facts,
  recalled by relevance through an MCP server and hooks).
- Spec-Driven Development with approval gates via sdd-feature, opt-in per project.
- `agent-guild` installer: copies the agents, workflow rules and skills into a project, merges `CLAUDE.md`, `.mcp.json`
  and `.claude/settings.json`, and is safe to re-run. `--without`, `--model`, `--dry-run`, `--force` and more.
