"""The install steps. Each step is a function over `Ctx` so they can be run, skipped and tested independently."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml

from .files import Ctx, copy_tree, read_json, write_bytes, write_json
from .specialists import SPECIALISTS, render
from .vendors import TOOLS, VENDORS, agent_filename, agent_source, codex_server_block, convert_agent, cursor_server, workflow_path

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
SKILL_REVISIONS = {
    "memory-bank": "e6c3043d0b445461541f0656a4ab28a9a730b5a1",
    "jevmem": "380d92227c114217a617ac95ab62d812fef4bc4d",
    "sdd": "5443fe57ff5f0fef25d8a76f75dae64953bb9e7b",
}

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
    model: str | None = None
    set_default_model: bool = True
    claude_compat: bool = False
    disable_auto_memory: bool = False
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


def _project_agent(ctx: Ctx, name: str, fallback: bytes) -> bytes:
    if not ctx.force:
        for tool in TOOLS:
            path = ctx.project / VENDORS[tool].agents_dir / agent_filename(tool, name)
            if path.is_file():
                ctx.log("source", path, f"project agent {name}")
                try:
                    return agent_source(tool, path.read_bytes())
                except (ValueError, KeyError, yaml.YAMLError) as exc:
                    raise SystemExit(f"error: cannot reuse project agent {path}: {exc}") from exc
    return fallback


def _write_agent(ctx: Ctx, opts: Options, name: str, claude_format: bytes):
    source = _project_agent(ctx, name, claude_format)
    for tool in opts.selected():
        dest = ctx.project / VENDORS[tool].agents_dir / agent_filename(tool, name)
        try:
            data = convert_agent(tool, source)
            if tool == "codex":
                fields = tomllib.loads(data.decode("utf-8"))
                if not all(isinstance(fields.get(k), str) and fields[k].strip()
                           for k in ("name", "description", "developer_instructions")):
                    raise ValueError("agent needs a name, description and developer_instructions")
        except (ValueError, yaml.YAMLError) as exc:
            raise SystemExit(f"error: cannot generate agent {dest}: {exc}") from exc
        if dest.is_file() and dest.read_bytes() != data and not ctx.force:
            ctx.warn(f"{dest.relative_to(ctx.project)} differs from the selected agent source; kept unchanged. Review cross-tool drift.")
        write_bytes(ctx, dest, data)


def install_agents(ctx: Ctx, opts: Options):
    for agent in sorted((opts.assets / "agents").glob("*.md")):
        if agent.name == "code-grader.md" and not opts.wants("sdd"):
            continue
        _write_agent(ctx, opts, agent.stem, agent.read_bytes())
    workflow = opts.assets / "development-workflow.md"
    if not ctx.force:
        for folder in (".agents", ".claude", ".cursor", ".codex"):
            existing = ctx.project / folder / "development-workflow.md"
            if existing.is_file():
                workflow = existing
                break
    ctx.log("source", workflow, "shared workflow")
    write_bytes(ctx, ctx.project / workflow_path(opts.tools), workflow.read_bytes())


def install_specialists(ctx: Ctx, opts: Options):
    for name in sorted(opts.with_coders):
        generic = _project_agent(ctx, "coder", (opts.assets / "agents/coder.md").read_bytes())
        _write_agent(ctx, opts, name, render(SPECIALISTS[name], opts.assets, source=generic))


def _fetch(url: str, into: Path, revision: str) -> Path:
    if shutil.which("git") is None:
        raise SystemExit("error: git is needed to fetch the skills (or pass --sources-dir with local clones)")
    subprocess.run(["git", "init", "--quiet", str(into)], check=True)
    subprocess.run(["git", "-C", str(into), "fetch", "--depth", "1", "--quiet", url, revision], check=True)
    subprocess.run(["git", "-C", str(into), "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True)
    actual = subprocess.check_output(["git", "-C", str(into), "rev-parse", "HEAD"], text=True).strip()
    if actual != revision:
        raise SystemExit(f"error: {url} resolved to {actual}, expected {revision}")
    return into


def install_skills(ctx: Ctx, opts: Options):
    wanted = [c for c in COMPONENTS if opts.wants(c)]
    if not wanted:
        return
    skills_dirs = [ctx.project / VENDORS[t].skills_dir for t in opts.selected()]
    # Resolve one project source for every destination before planning any writes.
    existing_skills = {}
    for component in wanted:
        skill_name = SKILL_SOURCES[component][2]
        for folder in (".claude/skills", ".cursor/skills", ".agents/skills", ".codex/skills"):
            candidate = ctx.project / folder / skill_name
            if (candidate / "SKILL.md").is_file():
                existing_skills[component] = candidate
                break
    for skills_dir in skills_dirs:
        if skills_dir.is_symlink():
            ctx.log("note", skills_dir, f"is a symlink to {os.readlink(skills_dir)}: skills are written there")
    provenance = {}
    with tempfile.TemporaryDirectory(prefix="agent-guild-") as tmp:
        for component in wanted:
            url, subpath, skill_name = SKILL_SOURCES[component]
            if opts.sources_dir is not None:
                repo = opts.sources_dir / REPO_DIRS[component]
                if not repo.is_dir():
                    raise SystemExit(f"error: {repo} not found (expected a clone of {url})")
            else:
                repo = _fetch(url, Path(tmp) / REPO_DIRS[component], SKILL_REVISIONS[component])
            src = repo / subpath
            if not (src / "SKILL.md").is_file():
                raise SystemExit(f"error: no SKILL.md in {src}")
            upstream_hash = hashlib.sha256()
            for item in sorted(src.rglob("*")):
                if item.is_file() and "__pycache__" not in item.parts:
                    upstream_hash.update(item.relative_to(src).as_posix().encode() + b"\0" + item.read_bytes())
            provenance[component] = {"url": url, "revision": SKILL_REVISIONS[component] if opts.sources_dir is None else "local",
                                     "sha256": upstream_hash.hexdigest()}
            local = existing_skills.get(component) if not ctx.force else None
            if local is not None:
                ctx.log("source", local, f"project skill {skill_name}; fill missing files from upstream")
            else:
                ctx.log("source", url, f"{skill_name} at {provenance[component]['revision']}")
            for skills_dir in skills_dirs:
                dest = skills_dir / skill_name
                if local is not None and not ctx.force:
                    if dest.is_dir() and dest != local:
                        shared = [p for p in local.rglob("*") if p.is_file() and (dest / p.relative_to(local)).is_file()]
                        if any(p.read_bytes() != (dest / p.relative_to(local)).read_bytes() for p in shared):
                            ctx.warn(f"{dest.relative_to(ctx.project)} differs from {local.relative_to(ctx.project)}; "
                                     "existing files kept. Review cross-tool drift.")
                    copy_tree(ctx, local, dest)
                copy_tree(ctx, src, dest)
    path = ctx.project / ".agents/skill-sources.json"
    existing, _ = read_json(path, ctx)
    provenance = {**existing, **provenance}
    write_json(ctx, path, provenance, "  ", ["resolved skill revisions"] if provenance != existing else [])


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


def install_rules(ctx: Ctx, opts: Options):
    """Append to the chosen instruction file. Developer-owned rules never move."""
    agents_md, claude_md = ctx.project / "AGENTS.md", ctx.project / "CLAUDE.md"
    target = claude_md if claude_md.exists() and not agents_md.exists() and opts.tools == {"claude"} else agents_md
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    crlf = target.exists() and b"\r\n" in target.read_bytes()
    other = claude_md if target == agents_md else agents_md
    other_text = other.read_text(encoding="utf-8") if other.exists() else ""
    added = []
    for heading, body in _rule_sections(opts):
        own_section = _take_rule_section(text, heading)[0]
        other_section = _take_rule_section(other_text, heading)[0]
        if own_section and other_section and own_section != other_section:
            ctx.warn(f"section '{heading}' is in both AGENTS.md and CLAUDE.md; review the copies for conflicting rules.")
        if own_section:
            ctx.log("skipped", target, f"section '{heading}' is already in {target.name}")
            continue
        if other_section:
            ctx.warn(f"section '{heading}' also exists in {other.name}; developer rules were not moved. Review the copies for conflicting rules.")
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + body + "\n"
        added.append(heading)
    if added:
        verb = "edit" if target.exists() else "create"
        ctx.write(target, (text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
        (ctx.edited_existing.append(target) if target.exists() else ctx.track_new(target))
        ctx.log(f"would {verb}" if ctx.dry_run else ("edited" if target.exists() else "created"), target, "+ " + ", ".join(added))
    if target == agents_md and "claude" in opts.tools:
        if opts.claude_compat:
            _import_agents_md(ctx, claude_md)
        elif claude_md.exists() and "@AGENTS.md" not in claude_md.read_text(encoding="utf-8"):
            ctx.warn("CLAUDE.md was preserved; Claude may prefer it over AGENTS.md. Import AGENTS.md yourself or use --claude-compat.")


def _import_agents_md(ctx: Ctx, claude_md: Path):
    existed = ctx.exists(claude_md)
    text = ctx.read(claude_md).decode("utf-8") if existed else ""
    if "@AGENTS.md" in text:
        return
    text = "@AGENTS.md\n" + (("\n" + text) if text.strip() else "")
    ctx.write(claude_md, text.encode("utf-8"))
    (ctx.edited_existing.append(claude_md) if existed else ctx.track_new(claude_md))
    verb = "edit" if existed else "create"
    ctx.log(f"would {verb}" if ctx.dry_run else ("edited" if existed else "created"), claude_md, "+ @AGENTS.md import")


def import_cursor_skills(ctx: Ctx, opts: Options):
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


def install_settings(ctx: Ctx, opts: Options):
    """Claude Code only: hooks, auto-memory switch and model are its settings."""
    if "claude" not in opts.tools:
        if opts.wants("jevmem"):
            ctx.warn("jevmem's session hooks are only set up for Claude Code; in Cursor and Codex the agents call "
                     "memory_recall themselves.")
        return
    shared_path = ctx.project / ".claude" / "settings.json"
    personal_path = ctx.project / ".claude" / "settings.local.json"
    scalar_path = personal_path if opts.personal_settings else shared_path

    shared, shared_indent = read_json(shared_path, ctx)
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
        scalars, scalar_indent = read_json(scalar_path, ctx)
    scalar_changes: list[str] = []
    effective = {**shared, **read_json(personal_path, ctx)[0]}
    if opts.wants("jevmem") and not opts.keep_auto_memory and (opts.disable_auto_memory or "autoMemoryEnabled" not in effective):
        scalars["autoMemoryEnabled"] = False
        scalar_changes.append("autoMemoryEnabled=false")
    model = opts.model or ("sonnet" if opts.set_default_model and "model" not in effective else None)
    if model and scalars.get("model") != model:
        scalars["model"] = model
        scalar_changes.append(f"model={model}")

    if scalar_path == shared_path:
        write_json(ctx, shared_path, shared, shared_indent, shared_changes + scalar_changes)
    else:
        write_json(ctx, shared_path, shared, shared_indent, shared_changes)
        write_json(ctx, scalar_path, scalars, scalar_indent, scalar_changes)


def install_mcp(ctx: Ctx, opts: Options):
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
            existing, _ = read_json(ctx.project / source, ctx)
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


def _write_mcp(ctx: Ctx, tool: str, servers_to_add: dict):
    path = ctx.project / VENDORS[tool].mcp_file
    if tool == "codex":
        _write_codex_mcp(ctx, path, servers_to_add)
        return
    data, indent = read_json(path, ctx)
    servers = data.setdefault("mcpServers", {})
    changes = []
    for key, server in servers_to_add.items():
        if key not in servers:
            servers[key] = cursor_server(server) if tool == "cursor" else server
            changes.append(f"{key} server")
    write_json(ctx, path, data, indent, changes)


def _write_codex_mcp(ctx: Ctx, path: Path, servers_to_add: dict):
    """Append [mcp_servers.<key>] tables to .codex/config.toml; existing entries and the rest of the file are kept."""
    text = ctx.read(path).decode("utf-8") if ctx.exists(path) else ""
    try:
        registered = tomllib.loads(text).get("mcp_servers", {})
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid TOML ({exc}); fix it or move it away and re-run")
    blocks = [codex_server_block(k, v) for k, v in servers_to_add.items() if k not in registered]
    if not blocks:
        ctx.log("unchanged", path)
        return
    existed = path.exists()
    updated = text.rstrip("\n") + ("\n\n" if text.strip() else "") + "\n".join(blocks)
    try:
        tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"error: cannot generate valid Codex MCP configuration: {exc}") from exc
    ctx.write(path, updated.encode("utf-8"))
    (ctx.edited_existing.append(path) if existed else ctx.track_new(path))
    changes = "+ " + ", ".join(f"{k} server" for k in servers_to_add if k not in registered)
    ctx.log(f"would {'edit' if existed else 'create'}" if ctx.dry_run else ("edited" if existed else "created"), path, changes)


def encoded_memory_dir(project: Path) -> Path:
    """Claude Code names a project's auto-memory folder after its absolute path, every non-alphanumeric char -> '-'."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project))


def import_auto_memory(ctx: Ctx, opts: Options):
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
        raise SystemExit("error: jevmem import-claude-memory failed; no installation files were written")


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=False)


def git_exclude(ctx: Ctx, opts: Options):
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
        original = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        block = ("" if not existing or existing[-1] == "" else "\n") + "# agent-guild\n" + "\n".join(entries) + "\n"
        ctx.write(exclude, (original + block).encode("utf-8"))
        ctx.log("would add" if ctx.dry_run else "added", exclude, f"{len(entries)} entries")
    else:
        ctx.log("unchanged", exclude)
    for path in ctx.edited_existing:
        rel = path.relative_to(ctx.project).as_posix()
        if _git(ctx.project, "ls-files", "--error-unmatch", rel).returncode == 0:
            ctx.warn(f"{rel} is tracked by git, so excluding can't hide the edit; `git diff {rel}` shows it.")


def _validate_configs(ctx: Ctx, opts: Options):
    if "codex" in opts.tools:
        for name in (".mcp.json", ".cursor/mcp.json"):
            path = ctx.project / name
            data, _ = read_json(path)
            if not isinstance(data.get("mcpServers", {}), dict):
                raise SystemExit(f"error: {path}: mcpServers must be an object")
    for tool in opts.selected():
        path = ctx.project / VENDORS[tool].mcp_file
        if tool == "codex":
            if path.exists():
                try:
                    config = tomllib.loads(path.read_text(encoding="utf-8"))
                except tomllib.TOMLDecodeError as exc:
                    raise SystemExit(f"error: {path} is not valid TOML: {exc}") from exc
                if not isinstance(config.get("mcp_servers", {}), dict):
                    raise SystemExit(f"error: {path}: mcp_servers must be a table")
            continue
        data, _ = read_json(path)
        if not isinstance(data.get("mcpServers", {}), dict):
            raise SystemExit(f"error: {path}: mcpServers must be an object")
    if "claude" in opts.tools and not opts.coders_only:
        for name in ("settings.json", "settings.local.json"):
            path = ctx.project / ".claude" / name
            data, _ = read_json(path)
            hooks = data.get("hooks", {})
            if not isinstance(hooks, dict):
                raise SystemExit(f"error: {path}: hooks must be an object")
            for groups in hooks.values():
                if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get("hooks", []), list)
                                                      or any(not isinstance(h, dict) for h in g.get("hooks", [])) for g in groups):
                    raise SystemExit(f"error: {path}: invalid hook groups")


def run_all(ctx: Ctx, opts: Options):
    _validate_configs(ctx, opts)
    if opts.coders_only:  # add language coders to an existing install: their agent, MCP server and routing rule only
        install_specialists(ctx, opts)
        install_rules(ctx, opts)
        install_mcp(ctx, opts)
        git_exclude(ctx, opts)
        ctx.apply()
        return
    # All functions build an in-memory plan; failures leave the project untouched.
    install_agents(ctx, opts)
    install_specialists(ctx, opts)
    install_skills(ctx, opts)
    import_cursor_skills(ctx, opts)
    install_rules(ctx, opts)
    install_mcp(ctx, opts)
    install_settings(ctx, opts)
    git_exclude(ctx, opts)
    import_auto_memory(ctx, opts)
    ctx.apply()
