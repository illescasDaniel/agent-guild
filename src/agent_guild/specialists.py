"""Opt-in language coders (`--with coder-python` ...): the generic `coder`, plus a code-navigation MCP it must use.

Each specialist is generated from `agents/coder.md` so the generic prompt stays the single source: only the
frontmatter (name, description, tool allowlist) and a per-language navigation section differ.
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Specialist:
    agent: str  # also the --with value and the file name under .claude/agents/
    label: str
    extensions: str
    description: str
    server_key: str  # key in .mcp.json; tool names are mcp__<server_key>__<tool>
    server: dict
    tools: tuple[str, ...]
    prerequisite: str
    fragment: str  # file under templates/coders/

    @property
    def rule_heading(self) -> str:
        return f"{self.label} code goes to `{self.agent}`"

    @property
    def rule_body(self) -> str:
        paragraph = (
            f"Any task that adds, changes, renames, moves or deletes {self.extensions} code goes to `{self.agent}`, not "
            f"the generic `coder`: it uses the project's `{self.server_key}` MCP for type-checked navigation and "
            f"refactoring. Keep `coder` for everything else, and split a task that spans languages."
        )
        return f"## {self.rule_heading}\n\n" + textwrap.fill(paragraph, width=120, break_on_hyphens=False)


PYTHON_TOOLS = (
    "symbol_info", "outline", "callers", "implementations", "search_symbol", "workspace", "hover", "definition",
    "references", "diagnostics", "edit", "edit_symbol", "rename_symbol", "change_signature", "move", "quick_fix",
    "verify_changes", "apply_edit", "undo_edit",
)
SWIFT_TOOLS = (
    "symbol_info", "references", "callers", "implementations", "type_at", "outline", "search_symbol", "hover",
    "definition", "diagnostics", "workspace", "verify", "affected_tests", "rename_symbol", "change_signature",
    "edit_symbol", "insert_member", "delete_symbol", "move_symbol", "add_conformance", "fix_diagnostics", "refactor",
    "apply_edit", "check_edit", "undo_edit",
)
TYPESCRIPT_TOOLS = (
    "symbol_info", "outline", "callers", "implementations", "search_symbol", "workspace", "hover", "definition",
    "references", "diagnostics", "css_var", "selector", "edit", "edit_symbol", "rename_symbol", "move", "quick_fix",
    "verify_changes", "apply_edit", "undo_edit",
)

SPECIALISTS = {
    s.agent: s
    for s in (
        Specialist(
            agent="coder-python",
            label="Python",
            extensions="`.py`/`.pyi`",
            description=(
                "Implementation engineer for Python code, backed by the codenav MCP (type-checked navigation and "
                "refactoring). Use INSTEAD of `coder` for any task that adds, changes, renames, moves or deletes Python "
                "code (.py/.pyi): an architect plan step, SDD Phase 3 tests or Phase 4 implementation step, grader "
                "fixes, a bug with a known cause. Same contract as `coder`."
            ),
            server_key="codenav",
            server={"type": "stdio", "command": "uvx", "args": ["--from", "codenav-mcp>=0.2.1,<0.3", "codenav-mcp"]},
            tools=PYTHON_TOOLS,
            prerequisite="coder-python: needs uv and Python 3.11+ (codenav-mcp runs through uvx). For a src layout, "
            "set CODENAV_MCP_SOURCE_ROOT on the codenav MCP server.",
            fragment="python.md",
        ),
        Specialist(
            agent="coder-swift",
            label="Swift",
            extensions="Swift/Objective-C/C/C++ (`.swift`, `.m`, `.mm`, `.h`, `.c`, `.cpp`)",
            description=(
                "Implementation engineer for Swift code (also Objective-C, C and C++), backed by the codenav-swift MCP "
                "(compiler-aware navigation and refactoring). Use INSTEAD of `coder` for any task that adds, changes, "
                "renames, moves or deletes Swift or Objective-C code: an architect plan step, SDD Phase 3 tests or "
                "Phase 4 implementation step, grader fixes, a bug with a known cause. Same contract as `coder`."
            ),
            server_key="codenav-swift",
            server={"type": "stdio", "command": "codenav-swift-mcp", "env": {"CODENAV_SWIFT_WRITE": "1"}},
            tools=SWIFT_TOOLS,
            prerequisite="coder-swift: install the codenav-swift-mcp binary first (macOS 13+ and a Swift toolchain; see "
            "https://github.com/illescasDaniel/codenav-swift-mcp). Xcode projects also need a buildServer.json.",
            fragment="swift.md",
        ),
        Specialist(
            agent="coder-typescript",
            label="TypeScript",
            extensions="JavaScript/TypeScript/HTML/CSS (`.ts`, `.tsx`, `.js`, `.jsx`, `.html`, `.css`)",
            description=(
                "Implementation engineer for JavaScript, TypeScript, HTML and CSS code, backed by the webnav MCP "
                "(type-checked navigation and refactoring). Use INSTEAD of `coder` for any task that adds, changes, "
                "renames, moves or deletes such code: an architect plan step, SDD Phase 3 tests or Phase 4 "
                "implementation step, grader fixes, a bug with a known cause. Same contract as `coder`."
            ),
            server_key="webnav",
            server={"type": "stdio", "command": "npx", "args": ["webnav-ts-mcp@0.2"]},
            tools=TYPESCRIPT_TOOLS,
            prerequisite="coder-typescript: needs Node.js 20+ (webnav-ts-mcp runs through npx).",
            fragment="typescript.md",
        ),
    )
}

# Read-only jevmem tool the generic coder prompt refers to; the write tools stay out of the allowlist.
_JEVMEM_READ = ("mcp__jevmem__memory_recall",)
_BUILTIN_TOOLS = ("Read", "Edit", "Write", "Glob", "Grep", "Bash")


def render(spec: Specialist, assets: Path) -> bytes:
    """Build the specialist's agent file from the generic coder and the language fragment."""
    source = (assets / "agents" / "coder.md").read_text(encoding="utf-8")
    _, frontmatter, body = source.split("---\n", 2)
    tools = ", ".join((*_BUILTIN_TOOLS, *_JEVMEM_READ, *(f"mcp__{spec.server_key}__{t}" for t in spec.tools)))
    lines = []
    for line in frontmatter.splitlines():
        if line.startswith("name:"):
            line = f"name: {spec.agent}"
        elif line.startswith("description:"):
            line = f"description: {json.dumps(spec.description, ensure_ascii=False)}"
        elif line.startswith("disallowedTools:"):
            line = f"tools: {tools}"  # an allowlist replaces the denylist: the codenav tools load up front
        lines.append(line)
    section = (assets / "templates" / "coders" / spec.fragment).read_text(encoding="utf-8").strip()
    body, count = re.subn(r"\n## Rules", f"\n{section}\n\n## Rules", body, count=1)
    if count != 1:
        raise SystemExit("error: agents/coder.md has no '## Rules' heading to put the navigation section before")
    return ("---\n" + "\n".join(lines) + "\n---\n" + body).encode("utf-8")


_SKIP_DIRS = {"node_modules", "venv", "build", "dist", "Pods", "__pycache__", "site-packages"}
_MAX_DEPTH, _MAX_FILES = 3, 5000
_MARKERS = {  # agent -> (file names, file suffixes, directory suffixes)
    "coder-python": ({"pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "requirements.txt"}, {".py"}, set()),
    "coder-swift": ({"Package.swift"}, {".swift"}, {".xcodeproj", ".xcworkspace"}),
    "coder-typescript": ({"tsconfig.json", "package.json"}, {".ts", ".tsx", ".mts", ".cts", ".jsx"}, set()),
}


def detect_languages(project: Path) -> list[str]:
    """Language coders that fit the project: marker files or a few source files near the root (cheap, best effort)."""
    found: set[str] = set()
    seen = 0
    root_depth = len(project.parts)
    for dirpath, dirnames, filenames in os.walk(project):
        for agent, (names, suffixes, dir_suffixes) in _MARKERS.items():
            if any(f in names or Path(f).suffix in suffixes for f in filenames) or any(
                Path(d).suffix in dir_suffixes for d in dirnames
            ):
                found.add(agent)
        seen += len(filenames)
        if seen > _MAX_FILES or len(found) == len(_MARKERS):
            break
        too_deep = len(Path(dirpath).parts) - root_depth >= _MAX_DEPTH
        dirnames[:] = [] if too_deep else sorted(d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS)
    return sorted(found)
