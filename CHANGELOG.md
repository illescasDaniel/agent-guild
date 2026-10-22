# Changelog

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
