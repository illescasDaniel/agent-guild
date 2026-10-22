"""The coding tools the setup can be installed for, where each one keeps its files, and the format it expects.

Agents are authored in Claude Code's format (`agents/*.md`); the other tools get a converted copy:

- Cursor: Markdown + YAML frontmatter, but with `readonly` instead of `disallowedTools`, no `color`/`effort`, and
  `model: inherit` (Cursor's model ids are not Claude's aliases). https://cursor.com/docs/context/subagents
- Codex: one TOML file per agent with `name`, `description` and `developer_instructions`; it has no read-only switch
  for an agent, so that is stated in the instructions. https://learn.chatgpt.com/docs/agent-configuration/subagents
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TOOLS = ("claude", "cursor", "codex")


@dataclass(frozen=True)
class Vendor:
    name: str
    agents_dir: str
    skills_dir: str
    agent_suffix: str
    mcp_file: str


VENDORS = {
    "claude": Vendor("claude", ".claude/agents", ".claude/skills", ".md", ".mcp.json"),
    "cursor": Vendor("cursor", ".cursor/agents", ".cursor/skills", ".md", ".cursor/mcp.json"),
    "codex": Vendor("codex", ".codex/agents", ".agents/skills", ".toml", ".codex/config.toml"),
}


def detect_tools(project: Path) -> list[str]:
    """Tools the project already uses, judged by their folders; Claude Code when nothing is found."""
    signs = {
        "claude": (".claude", "CLAUDE.md", ".mcp.json"),
        "cursor": (".cursor",),
        "codex": (".codex", ".agents/skills"),
    }
    found = [t for t in TOOLS if any((project / s).exists() for s in signs[t])]
    return found or ["claude"]


def parse_tools(value: str) -> list[str]:
    names = [n.strip().lower() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in TOOLS]
    if unknown or not names:
        raise SystemExit(f"error: --tools takes a comma-separated list of {', '.join(TOOLS)} (got {value!r})")
    return [t for t in TOOLS if t in names]


def agent_filename(tool: str, agent: str) -> str:
    return agent + VENDORS[tool].agent_suffix


def workflow_path(tools: list[str] | frozenset[str]) -> str:
    """All tools read this explicitly; its location does not select a coding tool."""
    return ".agents/development-workflow.md"


def _split(source: str) -> tuple[dict[str, Any], str]:
    match = re.fullmatch(r"---[ \t]*\n(.*?)^---[ \t]*\n(.*)", source.replace("\r\n", "\n"), re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError("agent needs YAML frontmatter delimited by --- lines")
    frontmatter, body = match.groups()
    fields = yaml.safe_load(frontmatter)
    if not isinstance(fields, dict) or any(not isinstance(fields.get(key), str) or not fields[key].strip()
                                          for key in ("name", "description")):
        raise ValueError("agent frontmatter needs a nonempty name and description")
    for key in ("tools", "disallowedTools"):
        if isinstance(fields.get(key), list):
            fields[key] = ", ".join(fields[key])
    return fields, body


def _is_read_only(fields: dict[str, str]) -> bool:
    return "Edit" in {t.strip() for t in fields.get("disallowedTools", "").split(",")}


def agent_source(tool: str, source: bytes) -> bytes:
    """Normalize a project agent to the source format for missing tool copies."""
    if tool == "claude":
        return source
    if tool == "cursor":
        fields, body = _split(source.decode("utf-8"))
        read_only = fields.get("readonly") in (True, "true")
        effort = None
    else:
        fields = tomllib.loads(source.decode("utf-8"))
        body = fields["developer_instructions"]
        prefix = "You are read-only: never edit, create or delete files.\n\n"
        read_only = body.startswith(prefix)
        if read_only:
            body = body.removeprefix(prefix)
        effort = fields.get("model_reasoning_effort")
    head = [f"name: {fields['name']}", f"description: {json.dumps(fields['description'], ensure_ascii=False)}"]
    if effort:
        head.append(f"effort: {effort}")
    if read_only:
        head.append("disallowedTools: Edit, Write, NotebookEdit")
    return ("---\n" + "\n".join(head) + "\n---\n" + body.lstrip("\n")).encode("utf-8")


def convert_agent(tool: str, source: bytes) -> bytes:
    """Turn a Claude Code agent file into `tool`'s format."""
    if tool == "claude":
        return source
    fields, body = _split(source.decode("utf-8"))
    read_only = _is_read_only(fields)
    if tool == "cursor":
        head = [f"name: {fields['name']}", f"description: {json.dumps(fields['description'], ensure_ascii=False)}",
                "model: inherit"]
        if read_only:
            head.append("readonly: true")
        return ("---\n" + "\n".join(head) + "\n---\n" + body).encode("utf-8")
    if tool == "codex":
        instructions = body.strip("\n")
        if read_only:
            instructions = "You are read-only: never edit, create or delete files.\n\n" + instructions
        escaped = instructions.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        lines = [f"name = {json.dumps(fields['name'])}",
                 f"description = {json.dumps(fields['description'], ensure_ascii=False)}"]
        if fields.get("effort") in ("low", "medium", "high", "xhigh", "max"):
            lines.append(f'model_reasoning_effort = "{"high" if fields["effort"] in ("xhigh", "max") else fields["effort"]}"')
        lines.append(f'developer_instructions = """\n{escaped}\n"""')
        return ("\n".join(lines) + "\n").encode("utf-8")
    raise ValueError(tool)


def cursor_server(server: dict) -> dict:
    return {k: v for k, v in server.items() if k != "type"}


def _toml_value(value) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {_toml_value(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def codex_server_block(key: str, server: dict) -> str:
    lines = [f"[mcp_servers.{key}]"]
    lines += [f"{k} = {_toml_value(v)}" for k, v in server.items() if k != "type"]
    return "\n".join(lines) + "\n"
