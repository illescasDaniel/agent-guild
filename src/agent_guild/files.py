"""File operations shared by the installer steps. Every write goes through `Ctx` so --dry-run is honoured."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Ctx:
    project: Path
    dry_run: bool = False
    force: bool = False
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    new_paths: list[tuple[Path, bool]] = field(default_factory=list)  # (topmost new path, is a directory)
    edited_existing: list[Path] = field(default_factory=list)
    pending: dict[Path, bytes] = field(default_factory=dict)

    def exists(self, path: Path) -> bool:
        return path in self.pending or path.exists()

    def read(self, path: Path) -> bytes:
        return self.pending[path] if path in self.pending else path.read_bytes()

    def write(self, path: Path, data: bytes):
        if path.exists() and not path.is_file():
            raise SystemExit(f"error: {path} must be a file")
        for parent in path.parents:
            if parent.exists() and not parent.is_dir():
                raise SystemExit(f"error: {parent} must be a directory")
        self.pending[path] = data

    def apply(self):
        """Apply only after every source and generated configuration has been checked."""
        if self.dry_run:
            return
        for path, data in self.pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def log(self, status: str, path: Path | str, note: str = "") -> None:
        shown = path
        if isinstance(path, Path):
            try:
                shown = path.relative_to(self.project)
            except ValueError:
                shown = path
        self.lines.append(f"  {status:<10} {shown}{('  ' + note) if note else ''}")

    def track_new(self, dest: Path) -> None:
        """Remember `dest`, or the topmost directory that doesn't exist yet and will contain it."""
        top = dest
        for parent in dest.parents:
            if parent == self.project or parent.exists():
                break
            top = parent
        if (top, top != dest) not in self.new_paths:
            self.new_paths.append((top, top != dest))

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def write_bytes(ctx: Ctx, dest: Path, data: bytes) -> str:
    """Create `dest`, or replace it only with --force. Never overwrites a file that differs by default."""
    if ctx.exists(dest):
        if ctx.read(dest) == data:
            ctx.log("unchanged", dest)
            return "unchanged"
        if not ctx.force:
            ctx.log("skipped", dest, "differs from the shipped version (use --force to overwrite)")
            return "skipped"
        status = "replaced"
        ctx.edited_existing.append(dest)
    else:
        status = "created"
        ctx.track_new(dest)
    ctx.write(dest, data)
    ctx.log(status if not ctx.dry_run else f"would {status.removesuffix('d')}", dest)
    return status


def copy_tree(ctx: Ctx, src: Path, dest: Path) -> None:
    for item in sorted(src.rglob("*")):
        parts = item.relative_to(src).parts
        if item.is_file() and ".git" not in parts and "__pycache__" not in parts:
            write_bytes(ctx, dest / item.relative_to(src), item.read_bytes())


def read_json(path: Path, ctx: Ctx | None = None) -> tuple[dict[str, Any], str]:
    """Return (data, indent). Missing file -> ({}, two spaces). Matches the file's existing indent style."""
    if not (ctx.exists(path) if ctx else path.exists()):
        return {}, "  "
    text = ctx.read(path).decode("utf-8") if ctx else path.read_text(encoding="utf-8")
    if not text.strip():
        return {}, "  "
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid JSON ({exc}); fix it or move it away and re-run")
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} must contain a JSON object")
    indent = "\t" if "\n\t" in text else "  "
    return data, indent


def write_json(ctx: Ctx, path: Path, data: dict[str, Any], indent: str, changes: list[str]) -> None:
    if not changes:
        ctx.log("unchanged", path)
        return
    verb = "edit" if ctx.exists(path) else "create"
    if verb == "edit":
        ctx.edited_existing.append(path)
    else:
        ctx.track_new(path)
    ctx.write(path, (json.dumps(data, indent=indent, ensure_ascii=False) + "\n").encode("utf-8"))
    ctx.log(f"would {verb}" if ctx.dry_run else ("edited" if verb == "edit" else "created"), path, "+ " + ", ".join(changes))
