"""The install steps. Each step is a function over `Ctx` so they can be run, skipped and tested independently."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .files import Ctx, copy_tree, read_json, write_bytes, write_json
from .specialists import SPECIALISTS, render
from .vendors import TOOLS, VENDORS, agent_filename, codex_server_block, convert_agent, cursor_server, workflow_path

JEVMEM_SPEC = "jevmem>=0.4.0,<0.5"
JEVMEM_SERVER = {"type": "stdio", "command": "uvx", "args": ["--from", JEVMEM_SPEC, "jevmem-mcp"]}
JEVMEM_HOOKS = {
    "SessionStart": ("jevmem hook session-start", 15),
    "UserPromptSubmit": ("jevmem hook user-prompt", 20),
}

# name -> (git url, skill folder inside the repo, name under .claude/skills/)
SKILL_SOURCES = {
    "memory-bank": ("https://github.com/illescasDaniel/memory-bank", "skills/memory-bank", "memory-bank"),
    "jevmem": ("https://github.com/illescasDaniel/jev-mem", ".claude/skills/jev-memory", "jev-memory"),
    "sdd": ("https://github.com/illescasDaniel/sdd-feature-skill", "skills/sdd-feature", "sdd-feature"),
}
REPO_DIRS = {"memory-bank": "memory-bank", "jevmem": "jev-mem", "sdd": "sdd-feature-skill"}
COMPONENTS = ("memory-bank", "jevmem", "sdd")

# (heading text that marks the section as already present, template file, component or None for always)
RULE_SECTIONS = (
    ("Agents and delegation", "agents-rules.md", None),
    ("Memory bank", "memory-bank-rules.md", "memory-bank"),
    ("Phase Gate Protocol", "sdd-rules.md", "sdd"),
)


@dataclass
class Options:
    assets: Path
    sources_dir: Path | None = None
    without: frozenset[str] = frozenset()
    with_coders: frozenset[str] = frozenset()
    coders_only: bool = False
    model: str | None = "sonnet"
    keep_auto_memory: bool = False
    personal_settings: bool = False
    import_auto_memory: bool = False
    import_cursor_skills: bool = False
    git_exclude: bool = False
    tools: frozenset[str] = frozenset({"claude"})

    def selected(self) -> list[str]:
        return [t for t in TOOLS if t in self.tools]

    def wants(self, component: str) -> bool:
        return component not in self.without


def _write_agent(ctx: Ctx, opts: Options, name: str, claude_format: bytes) -> None:
    for tool in opts.selected():
        dest = ctx.project / VENDORS[tool].agents_dir / agent_filename(tool, name)
        write_bytes(ctx, dest, convert_agent(tool, claude_format))


def install_agents(ctx: Ctx, opts: Options) -> None:
    for agent in sorted((opts.assets / "agents").glob("*.md")):
        if agent.name == "code-grader.md" and not opts.wants("sdd"):
            continue
        _write_agent(ctx, opts, agent.stem, agent.read_bytes())
    write_bytes(
        ctx,
        ctx.project / workflow_path(opts.tools),
        (opts.assets / "development-workflow.md").read_bytes(),
    )


def install_specialists(ctx: Ctx, opts: Options) -> None:
    for name in sorted(opts.with_coders):
        _write_agent(ctx, opts, name, render(SPECIALISTS[name], opts.assets))


def _fetch(url: str, into: Path) -> Path:
    if shutil.which("git") is None:
        raise SystemExit("error: git is needed to fetch the skills (or pass --sources-dir with local clones)")
    subprocess.run(["git", "clone", "--depth", "1", "--quiet", url, str(into)], check=True)
    return into


def install_skills(ctx: Ctx, opts: Options) -> None:
    wanted = [c for c in COMPONENTS if opts.wants(c)]
    if not wanted:
        return
    skills_dirs = [ctx.project / VENDORS[t].skills_dir for t in opts.selected()]
    # Snapshot project copies before installing: a new generic copy must not mask a customization.
    existing_skills = {}
    for component in wanted:
        skill_name = SKILL_SOURCES[component][2]
        for folder in (".claude/skills", ".cursor/skills", ".codex/skills"):
            candidate = ctx.project / folder / skill_name
            if (candidate / "SKILL.md").is_file():
                existing_skills[component] = candidate
                break
    for skills_dir in skills_dirs:
        if skills_dir.is_symlink():
            ctx.log("note", skills_dir, f"is a symlink to {os.readlink(skills_dir)}: skills are written there")
    with tempfile.TemporaryDirectory(prefix="agent-guild-") as tmp:
        for component in wanted:
            url, subpath, skill_name = SKILL_SOURCES[component]
            if opts.sources_dir is not None:
                repo = opts.sources_dir / REPO_DIRS[component]
                if not repo.is_dir():
                    raise SystemExit(f"error: {repo} not found (expected a clone of {url})")
            elif ctx.dry_run:
                ctx.log("would fetch", url, "-> " + ", ".join(f"{d.relative_to(ctx.project).as_posix()}/{skill_name}" for d in skills_dirs))
                continue
            else:
                repo = _fetch(url, Path(tmp) / REPO_DIRS[component])
            src = repo / subpath
            if not (src / "SKILL.md").is_file():
                raise SystemExit(f"error: no SKILL.md in {src}")
            for skills_dir in skills_dirs:
                dest = skills_dir / skill_name
                if skills_dir == ctx.project / VENDORS["codex"].skills_dir and not dest.exists() and component in existing_skills:
                    local = existing_skills[component]
                    ctx.log("note", dest, f"reusing project skill from {local.relative_to(ctx.project)}")
                    copy_tree(ctx, local, dest)
                # Fill missing shipped files on the first run as well as later runs.
                # Existing custom files remain protected by copy_tree's normal policy.
                copy_tree(ctx, src, dest)


def _rule_sections(opts: Options) -> list[tuple[str, str]]:
    """(heading that marks the section as present, body) for every rules section to add, in order."""
    if opts.coders_only:
        return [(SPECIALISTS[n].agent, SPECIALISTS[n].rule_body) for n in sorted(opts.with_coders)]
    sections = []
    for heading, template, component in RULE_SECTIONS:
        if component is None or opts.wants(component):
            body = (opts.assets / "templates" / template).read_text(encoding="utf-8").strip()
            names = [f"`{VENDORS[t].agents_dir}/`" for t in opts.selected()]
            dirs = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
            body = body.replace("{{AGENTS_DIRS}}", dirs).replace("{{WORKFLOW}}", workflow_path(opts.tools))
            sections.append((heading, body))
        if heading == "Agents and delegation":
            sections += [(SPECIALISTS[n].agent, SPECIALISTS[n].rule_body) for n in sorted(opts.with_coders)]
    return sections


def _take_rule_section(text: str, marker: str) -> tuple[str, str]:
    headings = list(re.finditer(r"^(#{1,6})[ \t]+(.+)$", text, re.MULTILINE))
    for index, heading in enumerate(headings):
        if marker not in heading.group(2):
            continue
        end = next((h.start() for h in headings[index + 1:] if len(h.group(1)) <= len(heading.group(1))), len(text))
        return text[heading.start():end].rstrip(), text[:heading.start()] + text[end:]
    return "", text


def _migrate_shared_rules(ctx: Ctx, opts: Options, agents_md: Path, claude_md: Path) -> tuple[str, str]:
    agents = agents_md.read_text(encoding="utf-8") if agents_md.exists() else ""
    claude = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    if not claude or not opts.tools - {"claude"}:
        return agents, claude
    if not agents_md.exists():
        # All existing project rules need to remain visible when adding a second tool.
        agents = re.sub(r"^@AGENTS\.md[ \t]*\n?", "", claude, flags=re.MULTILINE)
        claude = "@AGENTS.md\n"
    else:
        for marker, _ in _rule_sections(opts):
            section, remainder = _take_rule_section(claude, marker)
            if not section:
                continue
            if _take_rule_section(agents, marker)[0]:
                ctx.warn(f"section '{marker}' is in both AGENTS.md and CLAUDE.md; review the copies for conflicting rules.")
                continue
            agents = agents.rstrip() + "\n\n" + section + "\n"
            claude = remainder
    for path, text in ((agents_md, agents), (claude_md, claude)):
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        if text != original:
            (ctx.edited_existing.append(path) if path.exists() else ctx.track_new(path))
            if not ctx.dry_run:
                path.write_text(text, encoding="utf-8")
            ctx.log("would migrate" if ctx.dry_run else "migrated", path, "shared rules to AGENTS.md")
    return agents, claude


def install_rules(ctx: Ctx, opts: Options) -> None:
    """Add the rules sections to AGENTS.md (read by Codex, Cursor and others); CLAUDE.md only when it is the sole file.

    Claude Code does not read AGENTS.md, so when it is a selected tool CLAUDE.md gets an `@AGENTS.md` import.
    """
    agents_md, claude_md = ctx.project / "AGENTS.md", ctx.project / "CLAUDE.md"
    agents_text, claude_text = _migrate_shared_rules(ctx, opts, agents_md, claude_md)
    target = claude_md if claude_md.exists() and not agents_md.exists() and not opts.tools - {"claude"} else agents_md
    existed = target.exists()
    text = claude_text if target == claude_md else agents_text
    known = text + (agents_text if target == claude_md else claude_text)
    added = []
    for heading, body in _rule_sections(opts):
        if re.search(rf"^#+ .*{re.escape(heading)}", known, re.MULTILINE):
            ctx.log("skipped", target, f"section '{heading}' is already in AGENTS.md or CLAUDE.md")
            continue
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + body + "\n"
        added.append(heading)
    if added:
        if not ctx.dry_run:
            target.write_text(text, encoding="utf-8")
        verb = "edited" if existed else "created"
        (ctx.edited_existing.append(target) if existed else ctx.track_new(target))
        ctx.log(f"would {verb[:-1]}" if ctx.dry_run else verb, target, "+ " + ", ".join(added))
    if target == agents_md and ("claude" in opts.tools or claude_md.exists()):
        if not ctx.dry_run:
            _import_agents_md(ctx, claude_md)
        elif "@AGENTS.md" not in claude_text:
            ctx.log("would edit" if claude_md.exists() else "would create", claude_md, "+ @AGENTS.md import")


def _import_agents_md(ctx: Ctx, claude_md: Path) -> None:
    existed = claude_md.exists()
    text = claude_md.read_text(encoding="utf-8") if existed else ""
    if "@AGENTS.md" in text:
        return
    text = "@AGENTS.md\n" + (("\n" + text) if text.strip() else "")
    if not ctx.dry_run:
        claude_md.write_text(text, encoding="utf-8")
    (ctx.edited_existing.append(claude_md) if existed else ctx.track_new(claude_md))
    verb = "edit" if existed else "create"
    ctx.log(f"would {verb}" if ctx.dry_run else ("edited" if existed else "created"), claude_md, "+ @AGENTS.md import")


def import_cursor_skills(ctx: Ctx, opts: Options) -> None:
    """Copy the project's Cursor skills (.cursor/skills/*) into .claude/skills/. Existing skills are never replaced."""
    if not opts.import_cursor_skills:
        return
    if "claude" not in opts.tools:
        ctx.log("skipped", ".cursor/skills", "--import-cursor-skills copies into .claude/skills, and claude is not a selected tool")
        return
    src_root = ctx.project / ".cursor" / "skills"
    if not src_root.is_dir():
        ctx.log("skipped", ".cursor/skills", "not found")
        return
    for skill in sorted(p for p in src_root.iterdir() if (p / "SKILL.md").is_file()):
        dest = ctx.project / ".claude" / "skills" / skill.name
        if dest.exists() and not ctx.force:
            ctx.log("skipped", dest, "skill already exists (use --force to overwrite files)")
            continue
        copy_tree(ctx, skill, dest)


def _has_hook(groups: list, marker: str) -> bool:
    return any(marker in h.get("command", "") for g in groups for h in g.get("hooks", []))


def install_settings(ctx: Ctx, opts: Options) -> None:
    """Claude Code only: hooks, auto-memory switch and model are its settings."""
    if "claude" not in opts.tools:
        if opts.wants("jevmem"):
            ctx.warn("jevmem's session hooks are only set up for Claude Code; in Cursor and Codex the agents call "
                     "memory_recall themselves.")
        return
    shared_path = ctx.project / ".claude" / "settings.json"
    personal_path = ctx.project / ".claude" / "settings.local.json"
    scalar_path = personal_path if opts.personal_settings else shared_path

    shared, shared_indent = read_json(shared_path)
    shared_changes: list[str] = []
    if opts.wants("jevmem"):
        hooks = shared.setdefault("hooks", {})
        for event, (marker, timeout) in JEVMEM_HOOKS.items():
            groups = hooks.setdefault(event, [])
            if not _has_hook(groups, marker):
                command = f'uvx --from "{JEVMEM_SPEC}" {marker}'
                groups.append({"hooks": [{"type": "command", "command": command, "timeout": timeout}]})
                shared_changes.append(f"{event} hook")
        user_settings = Path.home() / ".claude" / "settings.json"
        if user_settings.exists() and "jevmem hook" in user_settings.read_text(encoding="utf-8"):
            ctx.warn("~/.claude/settings.json also has jevmem hooks: notes would be injected twice. Keep one set.")

    if scalar_path == shared_path:
        scalars, scalar_indent = shared, shared_indent
    else:
        scalars, scalar_indent = read_json(scalar_path)
    scalar_changes: list[str] = []
    if opts.wants("jevmem") and not opts.keep_auto_memory and scalars.get("autoMemoryEnabled") is not False:
        scalars["autoMemoryEnabled"] = False
        scalar_changes.append("autoMemoryEnabled=false")
    if opts.model and scalars.get("model") != opts.model:
        scalars["model"] = opts.model
        scalar_changes.append(f"model={opts.model}")

    if scalar_path == shared_path:
        write_json(ctx, shared_path, shared, shared_indent, shared_changes + scalar_changes)
    else:
        write_json(ctx, shared_path, shared, shared_indent, shared_changes)
        write_json(ctx, scalar_path, scalars, scalar_indent, scalar_changes)


def install_mcp(ctx: Ctx, opts: Options) -> None:
    servers_to_add = {}
    if opts.wants("jevmem") and not opts.coders_only:
        servers_to_add["jevmem"] = JEVMEM_SERVER
    for name in sorted(opts.with_coders):
        spec = SPECIALISTS[name]
        servers_to_add[spec.server_key] = spec.server
    if not servers_to_add:
        return
    codex_servers = dict(servers_to_add)
    if "codex" in opts.tools:
        for source in (".cursor/mcp.json", ".mcp.json"):
            existing, _ = read_json(ctx.project / source)
            for key, server in existing.get("mcpServers", {}).items():
                if key in codex_servers:
                    codex_servers[key] = server
    for tool in opts.selected():
        _write_mcp(ctx, tool, codex_servers if tool == "codex" else servers_to_add)
    user_config = Path.home() / ".claude.json"
    if user_config.exists() and "claude" in opts.tools:
        try:
            registered = json.loads(user_config.read_text(encoding="utf-8")).get("mcpServers", {})
            for key in servers_to_add:
                if key in registered:
                    ctx.warn(f"{key} is also registered at user scope; keep one registration so the server isn't listed twice.")
        except (json.JSONDecodeError, AttributeError):
            pass


def _write_mcp(ctx: Ctx, tool: str, servers_to_add: dict) -> None:
    path = ctx.project / VENDORS[tool].mcp_file
    if tool == "codex":
        _write_codex_mcp(ctx, path, servers_to_add)
        return
    data, indent = read_json(path)
    servers = data.setdefault("mcpServers", {})
    changes = []
    for key, server in servers_to_add.items():
        if key not in servers:
            servers[key] = cursor_server(server) if tool == "cursor" else server
            changes.append(f"{key} server")
    write_json(ctx, path, data, indent, changes)


def _write_codex_mcp(ctx: Ctx, path: Path, servers_to_add: dict) -> None:
    """Append [mcp_servers.<key>] tables to .codex/config.toml; existing entries and the rest of the file are kept."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        registered = tomllib.loads(text).get("mcp_servers", {})
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid TOML ({exc}); fix it or move it away and re-run")
    blocks = [codex_server_block(k, v) for k, v in servers_to_add.items() if k not in registered]
    if not blocks:
        ctx.log("unchanged", path)
        return
    existed = path.exists()
    if not ctx.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip("\n") + ("\n\n" if text.strip() else "") + "\n".join(blocks), encoding="utf-8")
    (ctx.edited_existing.append(path) if existed else ctx.track_new(path))
    changes = "+ " + ", ".join(f"{k} server" for k in servers_to_add if k not in registered)
    ctx.log(f"would {'edit' if existed else 'create'}" if ctx.dry_run else ("edited" if existed else "created"), path, changes)


def encoded_memory_dir(project: Path) -> Path:
    """Claude Code names a project's auto-memory folder after its absolute path, every non-alphanumeric char -> '-'."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project))


def import_auto_memory(ctx: Ctx, opts: Options) -> None:
    if not (opts.import_auto_memory and opts.wants("jevmem")):
        return
    root = encoded_memory_dir(ctx.project)
    if not (root / "memory").is_dir():
        ctx.log("skipped", "auto-memory import", f"no notes at {root}/memory")
        return
    cmd = ["uvx", "--from", JEVMEM_SPEC, "jevmem", "import-claude-memory", "--root", str(root)]
    if ctx.dry_run:
        ctx.log("would run", " ".join(cmd))
        return
    ctx.log("running", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ctx.project, check=False, env=os.environ)
    if result.returncode != 0:
        ctx.warn("jevmem import-claude-memory failed; auto-memory was NOT left unimported silently: fix it, or re-run with --keep-auto-memory.")


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=False)


def git_exclude(ctx: Ctx, opts: Options) -> None:
    """List the files this run created in .git/info/exclude (local to this clone, never committed)."""
    if not opts.git_exclude:
        return
    if shutil.which("git") is None or _git(ctx.project, "rev-parse", "--git-dir").returncode != 0:
        ctx.warn("--git-exclude: not a git repository, nothing excluded.")
        return
    exclude = Path(_git(ctx.project, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip())
    existing = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    entries = []
    for path, is_dir in ctx.new_paths:
        rel = path.relative_to(ctx.project).as_posix()
        entry = "/" + rel + ("/" if is_dir else "")
        if entry not in existing and entry not in entries:
            entries.append(entry)
    if entries:
        if not ctx.dry_run:
            exclude.parent.mkdir(parents=True, exist_ok=True)
            block = ("" if not existing or existing[-1] == "" else "\n") + "# agent-guild\n" + "\n".join(entries) + "\n"
            with exclude.open("a", encoding="utf-8") as fh:
                fh.write(block)
        ctx.log("would add" if ctx.dry_run else "added", exclude, f"{len(entries)} entries")
    else:
        ctx.log("unchanged", exclude)
    for path in ctx.edited_existing:
        rel = path.relative_to(ctx.project).as_posix()
        if _git(ctx.project, "ls-files", "--error-unmatch", rel).returncode == 0:
            ctx.warn(f"{rel} is tracked by git, so excluding can't hide the edit; `git diff {rel}` shows it.")


def run_all(ctx: Ctx, opts: Options) -> None:
    if opts.coders_only:  # add language coders to an existing install: their agent, MCP server and routing rule only
        install_specialists(ctx, opts)
        install_rules(ctx, opts)
        install_mcp(ctx, opts)
        git_exclude(ctx, opts)
        return
    # The import runs before the auto-memory switch is flipped, so no notes are lost.
    import_auto_memory(ctx, opts)
    install_agents(ctx, opts)
    install_specialists(ctx, opts)
    install_skills(ctx, opts)
    import_cursor_skills(ctx, opts)
    install_rules(ctx, opts)
    install_mcp(ctx, opts)
    install_settings(ctx, opts)
    git_exclude(ctx, opts)
