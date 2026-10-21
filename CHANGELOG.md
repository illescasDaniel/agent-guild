# Changelog

## [1.0.0] - 2026-10-21

First release.

- Multi-agent setup for Claude Code: a Sonnet orchestrator that delegates to `architect`, `coder`, `code-grader` and
  `utility` subagents, with the routing, briefs and memory protocol in `development-workflow.md`.
- Memory in two layers: memory-bank (current state, in a git-tracked `memory/` folder) and jev-mem (long-term facts,
  recalled by relevance through an MCP server and hooks).
- Spec-Driven Development with approval gates via sdd-feature, opt-in per project.
- `agent-guild` installer: copies the agents, workflow rules and skills into a project, merges `CLAUDE.md`, `.mcp.json`
  and `.claude/settings.json`, and is safe to re-run. `--without`, `--model`, `--dry-run`, `--force` and more.
