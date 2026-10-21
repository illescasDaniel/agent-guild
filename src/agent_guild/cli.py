from __future__ import annotations

import argparse
from pathlib import Path

from .files import Ctx
from .installer import COMPONENTS, Options, run_all

_BUNDLED = Path(__file__).resolve().parent / "_assets"  # present in installed wheels
DEFAULT_ASSETS = _BUNDLED if _BUNDLED.is_dir() else Path(__file__).resolve().parents[2]  # else: a source checkout

NEXT_STEPS = """Next steps:
  - Review the diff (git status / git diff); edit or delete any copied file or CLAUDE.md section you don't want.
  - Per machine, once: `uvx jevmem config init` and `uvx --from jevmem jevmem warmup`.
  - With memory-bank: ask Claude to "set up the memory bank".
  - Restart Claude Code in the project so the agents, skills, hooks and MCP server load."""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-guild",
        description="Copy the agent-guild setup (agents, workflow rules, skills, jevmem wiring) into a project. "
        "Everything is copied, not linked, so the project can edit it. Existing files that differ are never overwritten "
        "unless --force.",
    )
    p.add_argument("project", type=Path, help="path to the project's root")
    p.add_argument("--without", action="append", default=[], choices=COMPONENTS, metavar="COMPONENT",
                   help=f"leave a component out (repeatable): {', '.join(COMPONENTS)}. "
                        "'sdd' also drops the code-grader agent; 'jevmem' drops skill, MCP server, hooks and the auto-memory switch")
    p.add_argument("--model", default="sonnet", metavar="ALIAS",
                   help="the project's main-session model (default: sonnet; 'none' leaves it unset)")
    p.add_argument("--personal-settings", action="store_true",
                   help="write --model and autoMemoryEnabled to .claude/settings.local.json instead of the committed settings.json")
    p.add_argument("--keep-auto-memory", action="store_true", help="don't set autoMemoryEnabled=false")
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
    args = build_parser().parse_args(argv)
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"error: {project} is not a directory")
    if not (args.assets / "agents").is_dir():
        raise SystemExit(f"error: no agents/ in {args.assets}; run from a checkout of agent-guild or pass --assets")
    ctx = Ctx(project=project, dry_run=args.dry_run, force=args.force)
    opts = Options(
        assets=args.assets,
        sources_dir=args.sources_dir.expanduser().resolve() if args.sources_dir else None,
        without=frozenset(args.without),
        model=None if args.model.lower() == "none" else args.model,
        keep_auto_memory=args.keep_auto_memory,
        personal_settings=args.personal_settings,
        import_auto_memory=args.import_auto_memory,
        import_cursor_skills=args.import_cursor_skills,
        git_exclude=args.git_exclude,
    )
    run_all(ctx, opts)
    print(f"{'Dry run for' if args.dry_run else 'Installed into'} {project}")
    print("\n".join(ctx.lines))
    for w in ctx.warnings:
        print(f"warning: {w}")
    if not args.dry_run:
        print(NEXT_STEPS)
    return 0
