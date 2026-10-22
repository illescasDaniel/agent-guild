# Manual install

The recommended way is the `agent-guild` installer (see the [README](../README.md#install)). These steps do the
same thing by hand, and also cover the per-machine variant. The language coders (`--with coder-python` and friends)
have no manual steps: use the installer for those.

Two parts:

1. **Agents and orchestrator rules**: always per machine. They're how you work, not part of any one project.
2. **Memory and skills** (jevmem MCP server and hooks, auto-memory switch, skills): **per project (recommended)** or
   per machine. Pick one per project, not both. Doing both injects jevmem notes twice and registers the server twice.

## 1. Agents and orchestrator rules (per machine)

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

## 2a. Memory and skills per project (recommended)

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

## 2b. Memory and skills per machine

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

## Importing auto-memory

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
