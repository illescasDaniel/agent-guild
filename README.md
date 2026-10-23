# agent-guild

[![PyPI](https://img.shields.io/pypi/v/agent-guild)](https://pypi.org/project/agent-guild/)

A ready-made **multi-agent setup for [Claude Code](https://claude.com/claude-code), [Cursor](https://cursor.com) and
[Codex](https://developers.openai.com/codex)**, installed into a project with one command. (The Sonnet/Opus/Haiku
tiering below is Claude Code's; Cursor and Codex agents inherit the session model.) A Sonnet **orchestrator** delegates to specialist subagents (Opus architect and grader, Sonnet coders, Haiku
utility), and three features come wired in:

- **Multiple agents**: `architect`, `coder` (parallel-safe), `code-grader` and `utility`, plus the orchestrator rules
  that decide who does what: routing, briefs and reports. See [development-workflow.md](development-workflow.md).
- **Memory**, in two layers, so context survives between sessions:
  - [memory-bank](https://github.com/illescasDaniel/memory-bank): *current state* (what's being worked on, decisions,
    progress), in a git-tracked `memory/` folder.
  - [jev-mem](https://github.com/illescasDaniel/jev-mem): *long-term facts*, recalled by relevance through an MCP
    server and session hooks.
- **Spec-Driven Development (SDD)**, via [sdd-feature](https://github.com/illescasDaniel/sdd-feature-skill): specs,
  design, interfaces, implementation and grading, with approval gates between phases. Included by default; omit it
  with `--without sdd`.

```bash
uvx agent-guild /path/to/project
```

Or let your coding agent do it. Paste this prompt into Claude Code, Cursor or Codex, opened in the project:

> Install agent-guild in this project. It is a PyPI package (`agent-guild`), normally run with `uvx` (or
> `pipx`/`pip` if `uv` isn't available). First read the project's existing instructions, agents, skills, MCP config and
> settings (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.cursor/`, `.codex/`, `.agents/`). Run
> `uvx agent-guild . --dry-run` and review the plan with me: which tools to target, which optional parts to include
> (`--with` language coders, `--without sdd`/`memory-bank`/`jevmem`, `--claude-compat`, `--model`), and anything that
> contradicts the project's current rules or setup. Never overwrite or move my existing rules; resolve conflicts with
> me, and ask before using `--force`. Then run the real install, review the resulting diff, warnings and next steps,
> adapt the generated sections (quality-gate command, layering, conventions) to this project, and tell me what is
> left for me to do.

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

> Not affiliated with or endorsed by Anthropic, Anysphere (Cursor) or OpenAI. "Claude", "Claude Code", "Cursor" and "Codex" are trademarks of their respective owners.

## Files

| File | Install to (Claude Code) | Role |
|---|---|---|
| [development-workflow.md](development-workflow.md) | `.agents/development-workflow.md` | Orchestrator rules: knowledge layers, routing, SDD phase → agent map, briefs, memory protocol |
| [agents/architect.md](agents/architect.md) | `~/.claude/agents/` | Opus, read-only. Plans, SDD Phase 1 design decisions, Phase 2 interfaces, root causes |
| [agents/coder.md](agents/coder.md) | `~/.claude/agents/` | Sonnet. Scoped implementation; parallel-safe |
| [agents/code-grader.md](agents/code-grader.md) | `~/.claude/agents/` | Opus, read-only. SDD Phase 5. Body identical to the sdd-feature skill's grader; only the frontmatter differs |
| [agents/utility.md](agents/utility.md) | `~/.claude/agents/` | Haiku. Checks, git, moves, bulk edits |

These are the Claude Code sources; the installer converts them for Cursor and Codex.

## Install

### Quick: the installer (per project)

`agent-guild` copies everything into a project (plain copies, not links, so the project can edit them) and is
safe to re-run: existing files that differ from the selected source are skipped unless you pass `--force`.
It resolves and validates all sources and configuration in an in-memory plan before writing project files.
`--dry-run` builds the same plan (including downloads into a temporary directory), without writing to the project.
Preflight failures leave the project unchanged; filesystem errors during the final writes can still leave a partial install.

```bash
uvx agent-guild /path/to/project --dry-run
```

```bash
uvx agent-guild /path/to/project
```

It does, in the project, for each coding tool it finds (see **Tools** below):

- copies the agents in that tool's format and folder (`.claude/agents/*.md`; `.cursor/agents/*.md` with `readonly`
  instead of `disallowedTools`; `.codex/agents/*.toml`), and one shared
  `.agents/development-workflow.md`, explicitly read by Claude Code, Cursor and Codex;
- copies the `memory-bank`, `jev-memory` and `sdd-feature` skills into that tool's skills folder (`.claude/skills/`,
  `.cursor/skills/`, `.agents/skills/` for Codex), cloned from GitHub, or from local clones with `--sources-dir DIR`;
- seeds `memory/friction/` from memory-bank's template and enables dated tool, doc and workflow incident notes by
  default. This secondary maintenance backlog is separate from the project memory used to resume work and is not
  read at session start. Existing log files are preserved, even with `--force`. `--without memory-bank` skips this setup too.
  The agent initializes missing core memory files from the skill templates when needed;
- adds four removable sections: *Agents and delegation*, *Memory bank*, *Friction log* and *Phase Gate Protocol*. If `AGENTS.md`
  exists, that is the target. If only `CLAUDE.md` exists and only Claude Code is selected, it is the target instead.
  Otherwise, creates `AGENTS.md`. Existing sections in the target are preserved; conflicts with sections in the
  other instruction file produce warnings. **No developer rules are moved, deleted or migrated between files.**
  Modern Claude Code (v2.1.277+, with built-in AGENTS support enabled) can read `AGENTS.md` directly when no
  project/local `CLAUDE.md` takes precedence. Use `--claude-compat` to add an `@AGENTS.md` import for older versions
  or sessions that prefer `CLAUDE.md`; meaningful existing Claude content is retained. With both files present,
  the installer warns if Claude may not load the new shared instructions. See [Claude's instruction loading docs](https://code.claude.com/docs/en/memory#agentsmd);
- adds the pinned jevmem server to the tool's MCP config (`.mcp.json`, `.cursor/mcp.json`, `.codex/config.toml`),
  merging into existing files. New Codex servers reuse matching project entries from `.mcp.json`, then
  `.cursor/mcp.json`, before falling back to defaults; existing Codex entries always win;
- for Claude Code only: adds the jevmem hooks to `.claude/settings.json`. It preserves existing project/local model
  and auto-memory preferences; only absent preferences default to `sonnet` and `autoMemoryEnabled: false`.
  `--model` and `--disable-auto-memory` explicitly override the corresponding destination settings.

**Tools.** The installer detects what the project uses: `.claude/` or `CLAUDE.md` → Claude Code, `.cursor/` → Cursor,
`.codex/` or `.agents/skills/` → Codex; with several, it installs for all of them, and with none, for Claude Code. Override
with `--tools claude,cursor,codex`. Cursor and Codex agents don't carry the Claude model tiering (Cursor gets
`model: inherit`, Codex inherits the session model) and Codex has no read-only switch for an agent, so the read-only
agents say it in their instructions. Cursor also reads `.claude/` and `.agents/` folders, so with several tools
installed it may list a skill twice.

| Flag | Effect |
|---|---|
| `--tools claude,cursor,codex` | Install for these tools instead of the detected ones |
| `--with coder-python` / `coder-swift` / `coder-typescript` | Add a language coder (repeatable): the generic coder, required to use that language's code-navigation MCP ([codenav-mcp](https://github.com/illescasDaniel/codenav-mcp), [codenav-swift-mcp](https://github.com/illescasDaniel/codenav-swift-mcp), [webnav-ts-mcp](https://github.com/illescasDaniel/webnav-ts-mcp)). Also adds the MCP server to `.mcp.json` (an existing entry is kept) and an `AGENTS.md` rule that routes that language's work to it. The MCP's own prerequisites (uv, a Swift toolchain, Node) are printed after the install |
| `--coders-only` | With `--with`: install only the language coders (agent, MCP server, `AGENTS.md` rule) and nothing else. After a normal install, the tool detects Python, Swift and TypeScript/JS projects and prints this command for the coders you don't have yet |
| `--without sdd` / `memory-bank` / `jevmem` | Leave a component out. `sdd` also drops `code-grader` and the gate section; `jevmem` drops its skill, server, hooks and the auto-memory switch |
| `--model ALIAS` | Explicitly set the Claude project model. When omitted, preserve project/local preferences and default to `sonnet` only if absent; `none` does not set a model |
| `--claude-compat` | Add a `CLAUDE.md` import of `AGENTS.md` for older Claude Code or sessions that prefer Claude instruction files. Off by default |
| `--disable-auto-memory` | Explicitly set `autoMemoryEnabled: false`; otherwise preserve an existing project/local preference |
| `--import-cursor-skills` | Also copy the project's `.cursor/skills/*` into `.claude/skills/` (needs `claude` among the tools); skills that already exist are kept |
| `--personal-settings` | Put `--model` and `autoMemoryEnabled` in the git-ignored `.claude/settings.local.json`. For a Claude-only install the rules also go to `CLAUDE.local.md` (Claude reads it next to `CLAUDE.md`; it starts with `@AGENTS.md` when the project only has `AGENTS.md`), so no shared file is edited; git-ignore it, or use `--git-exclude`. Cursor and Codex have no personal project instruction file, so with them selected the rules stay in `AGENTS.md` |
| `--import-auto-memory` | First import the project's existing auto-memory notes into jevmem |
| `--keep-auto-memory` | Don't switch auto-memory off |
| `--sources-dir DIR` | Use local clones named `memory-bank/`, `jev-mem/`, `sdd-feature-skill/` instead of the pinned upstream revisions; this is an explicit reproducibility override |
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

## Adding it to a project that already has its own setup

The installer never overwrites a file that differs from the shipped one (and skips rules sections that `AGENTS.md`
or `CLAUDE.md` already has), so it is safe to run on a project with its own agents, skills and rules. After it runs:

- **Skipped files are yours.** Anything the log marks `skipped ... differs` keeps your version. If it is an older or
  customised copy of a shipped one (the `sdd-feature` skill, `code-grader`, `jev-memory`), diff it against the shipped
  file and merge what you want by hand. `--force` replaces it instead.
- **All tools reuse project sources.** For agents, choose the first existing copy in Claude, Cursor, Codex order;
  convert it for missing tool copies. Language coders inherit the project's generic coder body. For skills, choose
  `.claude/skills`, `.cursor/skills`, `.agents/skills`, then legacy `.codex/skills`, and use that source for every
  tool. Full supporting trees are copied. Existing divergent copies stay protected and produce drift warnings.
  The selected source is printed, including in dry-runs. These are plain copies; later edits are not synchronized.
  `--force` deliberately uses shipped sources instead. Codex discovers project skills under `.agents/skills`.
- **Upstream skills are pinned.** Each release selects exact Git commits in `SKILL_REVISIONS`; fetching verifies
  the resolved commit. `.agents/skill-sources.json` records the upstream URLs, revisions and content hashes.
  `--sources-dir` records `local` plus content hashes instead, so local edits are visible in provenance.
- **New files can land next to yours.** A skill folder you already have keeps its `SKILL.md`, but the shipped files
  that are missing (templates, scripts) are added beside it. If `.claude/skills` is a symlink to `.cursor/skills`, the
  log says so, and the skills are written there.
- **Cursor reads `.claude/agents/` too.** The agents installed here work in Cursor without copies in `.cursor/agents/`
  (`.cursor/agents/` wins on a name clash). Cursor ignores `tools`, `disallowedTools` and `effort`, so the read-only
  agents are not read-only there. If your project has a test that requires every `.claude/agents/*.md` to have a
  `.cursor/agents/` twin, relax it to require the twin only for the Cursor agents.
- **Skip what you already have** with `--without memory-bank` / `jevmem` / `sdd`, for example when your own memory-bank
  skill has a different name.

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
  in `tools:` so they load up front. An `AGENTS.md` rule routes that language's work to them. Without `--with`, nothing
  changes.
- **The grader runs on Opus.** The code it grades was written by Sonnet coders, so a different, stronger model gives
  a more independent review.
- **SDD is included by default.** A standard installation adds its skill, grader and Phase Gate Protocol.
  Pass `--without sdd` to omit those additions. Existing developer-owned files and rules are not removed by this
  flag. The workflow activates SDD when the project adopts the protocol or explicitly invokes the skill.
- **Gates and gate status.** SDD gates stay between the orchestrator and the user. The gate status is recorded in
  `memory/activeContext.md`, so a new session resumes at the right gate.

## License

[MIT](LICENSE)
