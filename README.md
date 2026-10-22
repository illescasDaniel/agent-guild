# agent-guild

[![PyPI](https://img.shields.io/pypi/v/agent-guild)](https://pypi.org/project/agent-guild/)

A ready-made **multi-agent setup for [Claude Code](https://claude.com/claude-code)**, installed into a project with one
command. A Sonnet **orchestrator** delegates to specialist subagents (Opus architect and grader, Sonnet coders, Haiku
utility), and three features come wired in:

- **Multiple agents**: `architect`, `coder` (parallel-safe), `code-grader` and `utility`, plus the orchestrator rules
  that decide who does what: routing, briefs and reports. See [development-workflow.md](development-workflow.md).
- **Memory**, in two layers, so context survives between sessions:
  - [memory-bank](https://github.com/illescasDaniel/memory-bank): *current state* (what's being worked on, decisions,
    progress), in a git-tracked `memory/` folder.
  - [jev-mem](https://github.com/illescasDaniel/jev-mem): *long-term facts*, recalled by relevance through an MCP
    server and session hooks.
- **Spec-Driven Development (SDD)**, via [sdd-feature](https://github.com/illescasDaniel/sdd-feature-skill): specs,
  design, interfaces, implementation and grading, with approval gates between phases. Opt-in per project.

```bash
uvx agent-guild /path/to/project
```

```
                         user
                          │  approvals (chat only)
                          ▼
              ┌──────────────────────┐   reads/writes   memory/ (state, gate status)
              │ orchestrator (Sonnet)│ ───────────────▶ jevmem (facts)      ← single writer
              └──────────────────────┘                  specs/, wireframes/
        plans │      chunks │       grade │      chores │
              ▼             ▼             ▼             ▼
        architect        coder ×N     code-grader     utility
        (Opus, RO)      (Sonnet)      (Opus, RO)      (Haiku)
              └── all read specs/, memory/, jevmem recall; report memory candidates + friction ──┘
```

> Not affiliated with or endorsed by Anthropic. "Claude" and "Claude Code" are trademarks of Anthropic.

## Files

| File | Install to | Role |
|---|---|---|
| [development-workflow.md](development-workflow.md) | imported from `~/.claude/CLAUDE.md` | Orchestrator rules: knowledge layers, routing, SDD phase → agent map, briefs, memory protocol |
| [agents/architect.md](agents/architect.md) | `~/.claude/agents/` | Opus, read-only. Plans, SDD Phase 1 design decisions, Phase 2 interfaces, root causes |
| [agents/coder.md](agents/coder.md) | `~/.claude/agents/` | Sonnet. Scoped implementation; parallel-safe |
| [agents/code-grader.md](agents/code-grader.md) | `~/.claude/agents/` | Opus, read-only. SDD Phase 5. Body identical to the sdd-feature skill's grader; only the frontmatter differs |
| [agents/utility.md](agents/utility.md) | `~/.claude/agents/` | Haiku. Checks, git, moves, bulk edits |

## Install

### Quick: the installer (per project)

`agent-guild` copies everything into a project (plain copies, not links, so the project can edit them) and is
safe to re-run: files that differ from the shipped version are skipped unless you pass `--force`.

```bash
uvx agent-guild /path/to/project --dry-run
```

```bash
uvx agent-guild /path/to/project
```

It does, in the project:

- copies `agents/*.md` and `development-workflow.md` into `.claude/`;
- copies the `memory-bank`, `jev-memory` and `sdd-feature` skills into `.claude/skills/` (cloned from GitHub, or from
  local clones with `--sources-dir DIR`);
- adds three removable sections to `CLAUDE.md`: *Agents and delegation*, *Memory bank* and *Phase Gate Protocol*. They
  live in `CLAUDE.md`, not `AGENTS.md`, because they are rules for Claude Code and its subagents; `AGENTS.md` stays
  tool-neutral. If the project has an `AGENTS.md`, `CLAUDE.md` starts with `@AGENTS.md`. A section that `CLAUDE.md` or
  `AGENTS.md` already has is not added again;
- adds the pinned jevmem server to `.mcp.json` and the jevmem hooks to `.claude/settings.json`, merging into existing
  files;
- sets `autoMemoryEnabled: false` and the project's model to `sonnet`.

| Flag | Effect |
|---|---|
| `--with coder-python` / `coder-swift` / `coder-typescript` | Add a language coder (repeatable): the generic coder, required to use that language's code-navigation MCP ([codenav-mcp](https://github.com/illescasDaniel/codenav-mcp), [codenav-swift-mcp](https://github.com/illescasDaniel/codenav-swift-mcp), [webnav-ts-mcp](https://github.com/illescasDaniel/webnav-ts-mcp)). Also adds the MCP server to `.mcp.json` (an existing entry is kept) and a `CLAUDE.md` rule that routes that language's work to it. The MCP's own prerequisites (uv, a Swift toolchain, Node) are printed after the install |
| `--coders-only` | With `--with`: install only the language coders (agent, MCP server, `CLAUDE.md` rule) and nothing else. After a normal install, the tool detects Python, Swift and TypeScript/JS projects and prints this command for the coders you don't have yet |
| `--without sdd` / `memory-bank` / `jevmem` | Leave a component out. `sdd` also drops `code-grader` and the gate section; `jevmem` drops its skill, server, hooks and the auto-memory switch |
| `--model ALIAS` | Project main-session model; default `sonnet` (the per-project alternative to the global setting below), `none` leaves it unset |
| `--import-cursor-skills` | Also copy the project's `.cursor/skills/*` into `.claude/skills/`; skills that already exist are kept |
| `--personal-settings` | Put `--model` and `autoMemoryEnabled` in the git-ignored `.claude/settings.local.json` |
| `--import-auto-memory` | First import the project's existing auto-memory notes into jevmem |
| `--keep-auto-memory` | Don't switch auto-memory off |
| `--sources-dir DIR` | Use local clones named `memory-bank/`, `jev-mem/`, `sdd-feature-skill/` instead of GitHub |
| `--git-exclude` | List the files this run *creates* in `.git/info/exclude` (local to your clone, never committed), so you can try the setup without it showing in `git status`. Off by default: files are added normally and your git settings apply. Edits to files git already tracks (e.g. an existing `.mcp.json`) can't be hidden; the tool warns about them |
| `--force`, `--dry-run` | Overwrite edited copies; show the plan without writing |

Still per machine, once: `uvx jevmem config init` and `uvx --from jevmem jevmem warmup`.

Prefer to do it by hand, or want the per-machine variant (agents and memory in `~/.claude` for every project)? See
[docs/manual_installation.md](https://github.com/illescasDaniel/agent-guild/blob/main/docs/manual_installation.md).

## Development

```bash
git clone https://github.com/illescasDaniel/agent-guild && cd agent-guild
uv run pytest
uv run agent-guild /path/to/project --dry-run
```

From a checkout, the CLI reads `agents/`, `templates/` and `development-workflow.md` at the repo root; the published
wheel bundles them.

## Design choices

- **The orchestrator is the only writer of memory.** Parallel coders writing `memory/` would conflict, and someone has
  to decide what is worth remembering. Subagents can read memory, including jevmem recall, and return **Memory
  candidates** and **Friction** sections in their reports.
- **Subagents don't get the jevmem hooks.** The `SessionStart` and `UserPromptSubmit` hooks fire in the main session
  only. So the agents that need history (architect, coder, grader) can call `memory_recall` themselves.
- **The files on disk are the hand-off.** Once a wireframe, `SPEC.md` or interfaces exist, briefs point to them
  instead of restating them. That solves the cold-start problem without long prompts.
- **`disallowedTools` instead of a `tools` allowlist** for architect, coder and grader. They inherit project MCP
  servers (e.g. code-navigation MCPs) without per-project edits, while jevmem writes and file edits stay
  blocked where needed. `utility` keeps a plain allowlist.
- **Language coders are separate, opt-in agents with an allowlist.** A generic `coder` only inherits the project's
  navigation MCPs; in practice it still reached for `grep` and `sed`, because the MCP tools arrive deferred (name
  only) and the brief or its own habits point elsewhere. `coder-python`, `coder-swift` and `coder-typescript`
  (`--with`) are generated from `coder.md` plus a navigation section that names the MCP's tools, and list those tools
  in `tools:` so they load up front. A `CLAUDE.md` rule routes that language's work to them. Without `--with`, nothing
  changes.
- **The grader runs on Opus.** The code it grades was written by Sonnet coders, so a different, stronger model gives
  a more independent review.
- **SDD is opt-in.** The global workflow uses SDD only when a project's `AGENTS.md` / `CLAUDE.md` adopts the Phase Gate
  Protocol, or when you ask for the `sdd-feature` skill directly. Projects that don't want gates just leave the rule
  out.
- **Gates and gate status.** SDD gates stay between the orchestrator and the user. The gate status is recorded in
  `memory/activeContext.md`, so a new session resumes at the right gate.

## License

[MIT](LICENSE)
