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
- **The grader runs on Opus.** The code it grades was written by Sonnet coders, so a different, stronger model gives
  a more independent review.
- **SDD is opt-in.** The global workflow uses SDD only when a project's `AGENTS.md` / `CLAUDE.md` adopts the Phase Gate
  Protocol, or when you ask for the `sdd-feature` skill directly. Projects that don't want gates just leave the rule
  out.
- **Gates and gate status.** SDD gates stay between the orchestrator and the user. The gate status is recorded in
  `memory/activeContext.md`, so a new session resumes at the right gate.

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

The manual steps below do the same thing by hand, and also cover the per-machine variant.

### Manual install

Two parts:

1. **Agents and orchestrator rules**: always per machine. They're how you work, not part of any one project.
2. **Memory and skills** (jevmem MCP server and hooks, auto-memory switch, skills): **per project (recommended)** or
   per machine. Pick one per project, not both. Doing both injects jevmem notes twice and registers the server twice.

### 1. Agents and orchestrator rules (per machine)

```bash
mkdir -p ~/.claude/agents && ln -s /path/to/agent-guild/agents/*.md ~/.claude/agents/
```

```bash
printf '\n@/path/to/agent-guild/development-workflow.md\n' >> ~/.claude/CLAUDE.md
```

Orchestrator model: either globally, in `~/.claude/settings.json`, replace `"model": "opusplan"` with
`"model": "sonnet"`; or only for a project, with `"model": "sonnet"` in its `.claude/settings.json` (or
`.claude/settings.local.json` to keep it personal). The installer does the latter by default.

jevmem's own settings (API key or local model, `~/.jevmem/config.jsonc`) and its embedding model are per machine
either way:

```bash
uvx jevmem config init
```

```bash
uvx --from jevmem jevmem warmup
```

### 2a. Memory and skills per project (recommended)

Everything lives in the repo and is committed. Worktrees, branches and other contributors get the same setup, and
nothing leaks into projects that don't use it.

Run these from the project's root.

**Skills**, into `.claude/skills/`:

```bash
npx skills add illescasDaniel/memory-bank -a claude-code -y
```

```bash
npx skills add illescasDaniel/sdd-feature-skill -a claude-code -y
```

The `jev-memory` skill isn't packaged for `npx skills`. Copy it from a clone of jev-mem:

```bash
cp -r jev-mem/.claude/skills/jev-memory .claude/skills/
```

**jevmem MCP server**, in the project's `.mcp.json`, pinned:

```bash
claude mcp add --scope project jevmem -- uvx --from "jevmem>=0.4.0,<0.5" jevmem-mcp
```

If you already registered jevmem at user scope (`claude mcp add --scope user jevmem …`), that works too. The server
only provides tools and injects nothing, and notes are stored per project (`project:<repo name>`) either way. Keep
just one registration, so the server isn't listed twice.

**Hooks and auto-memory switch**, in the project's `.claude/settings.json`:

```json
{
  "autoMemoryEnabled": false,
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "uvx --from \"jevmem>=0.4.0,<0.5\" jevmem hook session-start", "timeout": 15}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "uvx --from \"jevmem>=0.4.0,<0.5\" jevmem hook user-prompt", "timeout": 20}]}]
  }
}
```

Before setting `autoMemoryEnabled: false`, import the project's existing auto-memory notes (see
[Importing auto-memory](#importing-auto-memory)). To turn auto-memory off only for yourself, without committing the
change, put that key in `.claude/settings.local.json` instead.

**Rules**, in the project's `AGENTS.md` / `CLAUDE.md`:

- **Memory bank**: the snippet from the [memory-bank README](https://github.com/illescasDaniel/memory-bank#use-it),
  then ask the agent to "set up the memory bank".
- **SDD, if wanted**: the Phase Gate Protocol snippet from the
  [sdd-feature README](https://github.com/illescasDaniel/sdd-feature-skill#add-this-to-your-agentsmd--claudemd),
  adjusted to the project's paths. Leave it out to keep SDD manual: the skill still works when you ask for it.
- **Quality gate command, test conventions, code-navigation MCPs**: the agents look for these there.

### 2b. Memory and skills per machine

For when you want the same setup in every project without touching repos. Don't combine it with 2a in the same
project.

```bash
npx skills add illescasDaniel/memory-bank -a claude-code -g -y
```

```bash
npx skills add illescasDaniel/sdd-feature-skill -a claude-code -g -y
```

```bash
cp -r jev-mem/.claude/skills/jev-memory ~/.claude/skills/
```

```bash
claude mcp add --scope user jevmem -- uvx --from "jevmem>=0.4.0,<0.5" jevmem-mcp
```

In `~/.claude/settings.json`, add `"autoMemoryEnabled": false` at the top level. Then merge these hooks into the
existing `hooks` block, next to the `PreToolUse` one:

```json
"SessionStart": [{"hooks": [{"type": "command", "command": "uvx --from \"jevmem>=0.4.0,<0.5\" jevmem hook session-start", "timeout": 15}]}],
"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "uvx --from \"jevmem>=0.4.0,<0.5\" jevmem hook user-prompt", "timeout": 20}]}]
```

Then remove the same hooks, server and skills from any project that already defines them.

The per-project rules in `AGENTS.md` / `CLAUDE.md` (memory bank snippet, optional SDD snippet, quality gate) are still
added per project.

### Importing auto-memory

Claude Code's built-in auto-memory (`~/.claude/projects/<encoded-path>/memory/*.md`) is a second fact store that
overlaps with jevmem. Before switching it off for a project, import its notes. Run this from the project's root, so
the notes land in the same `project:<name>` scope that the hooks and MCP server use. Point `--root` at that project's
folder only, because the default imports every project's memory at once:

```bash
uvx jevmem import-claude-memory --root ~/.claude/projects/<encoded-project-path>
```

- **Folder name:** the project's absolute path with `/` replaced by `-`.
- **Jev must be configured.** Writes are screened by Jev, so the key or local model must be set up, or the notes are
  queued unscreened and hidden from recall.
- **Check the result** with `uvx jevmem list`, and `memory_forget` anything stale.

After the switch, the old files stay on disk, but Claude no longer reads or writes them. To turn auto-memory off for a
single shell instead, set the environment variable `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.

## Development

```bash
git clone https://github.com/illescasDaniel/agent-guild && cd agent-guild
uv run pytest
uv run agent-guild /path/to/project --dry-run
```

From a checkout, the CLI reads `agents/`, `templates/` and `development-workflow.md` at the repo root; the published
wheel bundles them.

## License

[MIT](LICENSE)
