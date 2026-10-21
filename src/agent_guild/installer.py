"""The install steps. Each step is a function over `Ctx` so they can be run, skipped and tested independently."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .files import Ctx, copy_tree, read_json, write_bytes, write_json

JEVMEM_SPEC = "jevmem>=0.4.0,<0.5"
JEVMEM_SERVER = {"type": "stdio", "command": "uvx", "args": ["--from", JEVMEM_SPEC, "jevmem-mcp"]}
JEVMEM_HOOKS = {
    "SessionStart": ("jevmem hook session-start", 15),
    "UserPromptSubmit": ("jevmem hook user-prompt", 20),
}
WORKFLOW_IMPORT = "@.claude/development-workflow.md"

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
    model: str | None = "sonnet"
    keep_auto_memory: bool = False
    personal_settings: bool = False
    import_auto_memory: bool = False
    import_cursor_skills: bool = False
    git_exclude: bool = False

    def wants(self, component: str) -> bool:
        return component not in self.without


def install_agents(ctx: Ctx, opts: Options) -> None:
    for agent in sorted((opts.assets / "agents").glob("*.md")):
        if agent.name == "code-grader.md" and not opts.wants("sdd"):
            continue
        write_bytes(ctx, ctx.project / ".claude" / "agents" / agent.name, agent.read_bytes())
    write_bytes(
        ctx,
        ctx.project / ".claude" / "development-workflow.md",
        (opts.assets / "development-workflow.md").read_bytes(),
    )


def _fetch(url: str, into: Path) -> Path:
    if shutil.which("git") is None:
        raise SystemExit("error: git is needed to fetch the skills (or pass --sources-dir with local clones)")
    subprocess.run(["git", "clone", "--depth", "1", "--quiet", url, str(into)], check=True)
    return into


def install_skills(ctx: Ctx, opts: Options) -> None:
    wanted = [c for c in COMPONENTS if opts.wants(c)]
    if not wanted:
        return
    with tempfile.TemporaryDirectory(prefix="agent-guild-") as tmp:
        for component in wanted:
            url, subpath, skill_name = SKILL_SOURCES[component]
            if opts.sources_dir is not None:
                repo = opts.sources_dir / REPO_DIRS[component]
                if not repo.is_dir():
                    raise SystemExit(f"error: {repo} not found (expected a clone of {url})")
            elif ctx.dry_run:
                ctx.log("would fetch", url, f"-> .claude/skills/{skill_name}")
                continue
            else:
                repo = _fetch(url, Path(tmp) / REPO_DIRS[component])
            src = repo / subpath
            if not (src / "SKILL.md").is_file():
                raise SystemExit(f"error: no SKILL.md in {src}")
            copy_tree(ctx, src, ctx.project / ".claude" / "skills" / skill_name)


def install_rules(ctx: Ctx, opts: Options) -> None:
    """The new sections live in CLAUDE.md (Claude-only rules); AGENTS.md stays tool-neutral and is just imported."""
    agents_md, claude_md = ctx.project / "AGENTS.md", ctx.project / "CLAUDE.md"
    existed = claude_md.exists()
    text = claude_md.read_text(encoding="utf-8") if existed else ""
    known = text + (agents_md.read_text(encoding="utf-8") if agents_md.exists() else "")
    added = []
    if agents_md.exists() and "@AGENTS.md" not in text:
        text = "@AGENTS.md\n" + (("\n" + text) if text.strip() else "")
        added.append("@AGENTS.md import")
    for heading, template, component in RULE_SECTIONS:
        if component is not None and not opts.wants(component):
            continue
        if re.search(rf"^#+ .*{re.escape(heading)}", known, re.MULTILINE):
            ctx.log("unchanged", claude_md, f"already has '{heading}' (CLAUDE.md or AGENTS.md)")
            continue
        body = (opts.assets / "templates" / template).read_text(encoding="utf-8").strip()
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + body + "\n"
        added.append(heading)
    if added:
        if not ctx.dry_run:
            claude_md.write_text(text, encoding="utf-8")
        verb = "edited" if existed else "created"
        (ctx.edited_existing.append(claude_md) if existed else ctx.track_new(claude_md))
        ctx.log(f"would {verb[:-1]}" if ctx.dry_run else verb, claude_md, "+ " + ", ".join(added))


def import_cursor_skills(ctx: Ctx, opts: Options) -> None:
    """Copy the project's Cursor skills (.cursor/skills/*) into .claude/skills/. Existing skills are never replaced."""
    if not opts.import_cursor_skills:
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
    if not opts.wants("jevmem"):
        return
    path = ctx.project / ".mcp.json"
    data, indent = read_json(path)
    servers = data.setdefault("mcpServers", {})
    changes = []
    if "jevmem" not in servers:
        servers["jevmem"] = JEVMEM_SERVER
        changes.append("jevmem server")
    user_config = Path.home() / ".claude.json"
    if user_config.exists():
        try:
            if "jevmem" in json.loads(user_config.read_text(encoding="utf-8")).get("mcpServers", {}):
                ctx.warn("jevmem is also registered at user scope; keep one registration so the server isn't listed twice.")
        except (json.JSONDecodeError, AttributeError):
            pass
    write_json(ctx, path, data, indent, changes)


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
    # The import runs before the auto-memory switch is flipped, so no notes are lost.
    import_auto_memory(ctx, opts)
    install_agents(ctx, opts)
    install_skills(ctx, opts)
    import_cursor_skills(ctx, opts)
    install_rules(ctx, opts)
    install_mcp(ctx, opts)
    install_settings(ctx, opts)
    git_exclude(ctx, opts)
