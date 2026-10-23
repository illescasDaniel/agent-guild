from __future__ import annotations

import argparse
from pathlib import Path

from .files import Ctx
from .installer import COMPONENTS, Options, run_all
from .specialists import SPECIALISTS, detect_languages
from .vendors import TOOLS, VENDORS, agent_filename, detect_tools, parse_tools

_BUNDLED = Path(__file__).resolve().parent / "_assets"  # present in installed wheels
DEFAULT_ASSETS = _BUNDLED if _BUNDLED.is_dir() else Path(__file__).resolve().parents[2]  # else: a source checkout

KEPT_HINT = """Files marked "skipped ... differs" keep your version. If a skill or agent of yours is an older or customised
copy of a shipped one, diff it against the shipped file and merge the changes by hand (--force replaces it)."""

NEXT_STEPS = """Next steps:
  - Review the diff (git status / git diff); edit or delete any copied file or AGENTS.md section you don't want.
  - Per machine, once: `uvx jevmem config init` and `uvx --from jevmem jevmem warmup`.
  - With memory-bank: ask Claude to "set up the memory bank".
  - Restart your coding tool (Claude Code, Cursor, Codex) in the project so the agents, skills, hooks and MCP server load."""


CODERS_NEXT_STEPS = """Next steps:
  - Review the diff (git status / git diff).
  - Restart your coding tool in the project so the agents and MCP server load."""


def suggest_coders(project: Path, chosen: list[str]) -> None:
    """After an install, point at the language coders that fit the project and are not installed yet."""
    missing = [
        name for name in detect_languages(project)
        if name not in chosen and not any((project / v.agents_dir / agent_filename(t, name)).exists() for t, v in VENDORS.items())
    ]
    if not missing:
        return
    print("\nThis project looks like it uses code that a language coder can navigate and refactor with a "
          "code-navigation MCP (optional; adds only the agent, the MCP server and an AGENTS.md routing rule):")
    for name in missing:
        spec = SPECIALISTS[name]
        print(f"  - {spec.label}:  uvx agent-guild {project} --with {name} --coders-only")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-guild",
        description="Copy the agent-guild setup (agents, workflow rules, skills, jevmem wiring) into a project. "
        "Everything is copied, not linked, so the project can edit it. Existing files that differ are never overwritten "
        "unless --force.",
    )
    p.add_argument("project", type=Path, help="path to the project's root")
    p.add_argument("--tools", metavar="LIST",
                   help=f"comma-separated tools to install for: {', '.join(TOOLS)}. Default: the ones the project already "
                        "uses (.claude/ or CLAUDE.md, .cursor/, .codex/ or .agents/skills/), or claude when none is found. Each gets "
                        "agents and skills in its own format and folder, and an MCP config")
    p.add_argument("--without", action="append", default=[], choices=COMPONENTS, metavar="COMPONENT",
                   help=f"leave a component out (repeatable): {', '.join(COMPONENTS)}. "
                        "'sdd' also drops the code-grader agent; 'jevmem' drops skill, MCP server, hooks and the auto-memory switch")
    p.add_argument("--with", dest="with_coders", action="append", default=[], choices=sorted(SPECIALISTS),
                   metavar="CODER",
                   help=f"add a language coder (repeatable): {', '.join(sorted(SPECIALISTS))}. Each is the generic coder plus "
                        "a code-navigation MCP it must use for that language; the MCP server and an AGENTS.md routing rule "
                        "are added too. Off by default")
    p.add_argument("--coders-only", action="store_true",
                   help="with --with: install only the language coders (agent, MCP server, routing rule) and leave "
                        "everything else in the project untouched")
    p.add_argument("--model", metavar="ALIAS",
                   help="explicitly set the Claude model; otherwise preserve existing settings, defaulting to sonnet "
                        "only when absent; 'none' leaves it unset")
    p.add_argument("--claude-compat", action="store_true",
                   help="add a CLAUDE.md @AGENTS.md import for older Claude Code or sessions preferring CLAUDE.md")
    p.add_argument("--personal-settings", action="store_true",
                   help="write --model and autoMemoryEnabled to .claude/settings.local.json instead of the committed settings.json; "
                        "for a Claude-only install, also put the rules in CLAUDE.local.md instead of AGENTS.md/CLAUDE.md")
    memory = p.add_mutually_exclusive_group()
    memory.add_argument("--keep-auto-memory", action="store_true", help="don't set autoMemoryEnabled=false")
    memory.add_argument("--disable-auto-memory", action="store_true",
                        help="explicitly set autoMemoryEnabled=false; otherwise preserve an existing preference")
    p.add_argument("--import-auto-memory", action="store_true",
                   help="first import the project's existing Claude auto-memory notes into jevmem (needs jevmem configured)")
    p.add_argument("--import-cursor-skills", action="store_true",
                   help="also copy the project's .cursor/skills/* into .claude/skills/ (existing skills are kept)")
    p.add_argument("--git-exclude", action="store_true",
                   help="list the files this run creates in .git/info/exclude, so they stay out of git status (local only; "
                        "off by default, in which case files are added normally under your own git settings)")
    p.add_argument("--sources-dir", type=Path, metavar="DIR",
                   help="use local clones (memory-bank/, jev-mem/, sdd-feature-skill/ inside DIR) instead of fetching from GitHub")
    p.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, metavar="DIR", help=argparse.SUPPRESS)
    p.add_argument("--force", action="store_true", help="overwrite copied files that differ from the shipped version")
    p.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.coders_only and not args.with_coders:
        parser.error("--coders-only needs at least one --with")
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"error: {project} is not a directory")
    if not (args.assets / "agents").is_dir():
        raise SystemExit(f"error: no agents/ in {args.assets}; run from a checkout of agent-guild or pass --assets")
    tools = parse_tools(args.tools) if args.tools else detect_tools(project)
    ctx = Ctx(project=project, dry_run=args.dry_run, force=args.force)
    opts = Options(
        assets=args.assets,
        sources_dir=args.sources_dir.expanduser().resolve() if args.sources_dir else None,
        without=frozenset(args.without),
        with_coders=frozenset(args.with_coders),
        coders_only=args.coders_only,
        model=None if args.model is None or args.model.lower() == "none" else args.model,
        set_default_model=args.model is None,
        claude_compat=args.claude_compat,
        disable_auto_memory=args.disable_auto_memory,
        keep_auto_memory=args.keep_auto_memory,
        personal_settings=args.personal_settings,
        import_auto_memory=args.import_auto_memory,
        import_cursor_skills=args.import_cursor_skills,
        git_exclude=args.git_exclude,
        tools=frozenset(tools),
    )
    run_all(ctx, opts)
    print(f"{'Dry run for' if args.dry_run else 'Installed into'} {project}")
    print(f"  tools: {', '.join(tools)} ({'--tools' if args.tools else 'detected'})")
    print("\n".join(ctx.lines))
    for w in ctx.warnings:
        print(f"warning: {w}")
    if any(line.lstrip().startswith("skipped") and "differs" in line for line in ctx.lines):
        print(f"\n{KEPT_HINT}")
    if not args.dry_run:
        print(CODERS_NEXT_STEPS if args.coders_only else NEXT_STEPS)
        for name in sorted(args.with_coders):
            print(f"  - {SPECIALISTS[name].prerequisite}")
        suggest_coders(project, args.with_coders)
    return 0
