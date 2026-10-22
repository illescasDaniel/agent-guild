import json
from pathlib import Path

import pytest

from agent_guild.cli import main

REPOS = {"memory-bank": "skills/memory-bank", "jev-mem": ".claude/skills/jev-memory",
         "sdd-feature-skill": "skills/sdd-feature"}


@pytest.fixture
def sources(tmp_path):
    root = tmp_path / "sources"
    for repo, sub in REPOS.items():
        (root / repo / sub).mkdir(parents=True)
        (root / repo / sub / "SKILL.md").write_text(f"# {repo}\n")
    return root


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()


def run(project, sources, *extra):
    return main([str(project), "--sources-dir", str(sources), *extra])


def test_given_empty_project_when_installed_then_everything_is_copied(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources)
    # then
    for name in ("architect", "coder", "code-grader", "utility"):
        assert (project / ".claude/agents" / f"{name}.md").is_file()
    assert (project / ".claude/development-workflow.md").is_file()
    for skill in ("memory-bank", "jev-memory", "sdd-feature"):
        assert (project / ".claude/skills" / skill / "SKILL.md").is_file()
    claude_md = (project / "CLAUDE.md").read_text()
    assert "@.claude/development-workflow.md" in claude_md
    assert "## Memory bank" in claude_md and "Phase Gate Protocol" in claude_md
    settings = json.loads((project / ".claude/settings.json").read_text())
    assert settings["model"] == "sonnet" and settings["autoMemoryEnabled"] is False
    assert set(settings["hooks"]) == {"SessionStart", "UserPromptSubmit"}
    assert "jevmem" in json.loads((project / ".mcp.json").read_text())["mcpServers"]


def test_given_agents_md_only_when_installed_then_claude_md_imports_it_and_holds_the_sections(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n")
    # when
    run(project, sources)
    # then
    assert (project / "CLAUDE.md").read_text().startswith("@AGENTS.md\n")
    assert "## Agents and delegation" in (project / "CLAUDE.md").read_text()
    assert (project / "AGENTS.md").read_text() == "# Rules\n"


def test_given_installed_project_when_run_again_then_nothing_changes(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    run(project, sources)
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    # when
    run(project, sources)
    # then
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


def test_given_edited_agent_when_run_again_then_edit_is_kept_unless_forced(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    run(project, sources)
    coder = project / ".claude/agents/coder.md"
    coder.write_text("mine")
    # when / then
    run(project, sources)
    assert coder.read_text() == "mine"
    run(project, sources, "--force")
    assert coder.read_text() != "mine"


def test_given_without_sdd_and_jevmem_then_those_parts_are_left_out(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources, "--without", "sdd", "--without", "jevmem")
    # then
    assert not (project / ".claude/agents/code-grader.md").exists()
    assert not (project / ".claude/skills/sdd-feature").exists()
    assert not (project / ".claude/skills/jev-memory").exists()
    assert not (project / ".mcp.json").exists()
    assert json.loads((project / ".claude/settings.json").read_text()) == {"model": "sonnet"}
    assert "Phase Gate" not in (project / "CLAUDE.md").read_text()


def test_given_existing_settings_when_installed_then_they_are_merged_with_indent_kept(tmp_path, sources):
    # given
    project = tmp_path / "p"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude/settings.json").write_text('{\n\t"permissions": {"allow": ["Bash(ls)"]}\n}\n')
    (project / ".mcp.json").write_text('{"mcpServers": {"codenav": {"command": "x"}}}')
    # when
    run(project, sources)
    # then
    text = (project / ".claude/settings.json").read_text()
    assert text.startswith('{\n\t"permissions"')
    assert json.loads(text)["permissions"] == {"allow": ["Bash(ls)"]}
    assert set(json.loads((project / ".mcp.json").read_text())["mcpServers"]) == {"codenav", "jevmem"}


def test_given_personal_settings_then_model_and_auto_memory_go_to_local_file(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources, "--model", "sonnet", "--personal-settings")
    # then
    local = json.loads((project / ".claude/settings.local.json").read_text())
    assert local == {"autoMemoryEnabled": False, "model": "sonnet"}
    assert "model" not in json.loads((project / ".claude/settings.json").read_text())


def test_given_dry_run_then_nothing_is_written(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources, "--dry-run")
    # then
    assert list(project.iterdir()) == []


def test_given_model_none_then_model_is_not_set(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources, "--model", "none")
    # then
    assert "model" not in json.loads((project / ".claude/settings.json").read_text())


def test_given_sections_already_in_agents_md_then_claude_md_does_not_repeat_them(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("## Memory bank\n\n## Phase Gate Protocol\n")
    # when
    run(project, sources)
    # then
    text = (project / "CLAUDE.md").read_text()
    assert "## Agents and delegation" in text
    assert "## Memory bank" not in text and "Phase Gate" not in text


def test_given_cursor_skills_when_importing_then_copied_without_replacing_existing(tmp_path, sources):
    # given
    project = tmp_path / "p"
    (project / ".cursor/skills/mine").mkdir(parents=True)
    (project / ".cursor/skills/mine/SKILL.md").write_text("mine")
    (project / ".cursor/skills/sdd-feature").mkdir()
    (project / ".cursor/skills/sdd-feature/SKILL.md").write_text("cursor version")
    # when
    run(project, sources, "--import-cursor-skills")
    # then
    assert (project / ".claude/skills/mine/SKILL.md").read_text() == "mine"
    assert (project / ".claude/skills/sdd-feature/SKILL.md").read_text() != "cursor version"


def _git(project, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=True).stdout


def test_given_git_exclude_then_new_files_are_hidden_but_tracked_edits_are_warned(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    project.mkdir()
    _git(project, "init", "-q")
    (project / ".mcp.json").write_text('{"mcpServers": {}}')
    _git(project, "add", ".mcp.json")
    # when
    run(project, sources, "--git-exclude")
    # then
    status = _git(project, "status", "--short")
    assert ".claude" not in status and "CLAUDE.md" not in status
    assert ".mcp.json" in status
    assert ".mcp.json is tracked by git" in capsys.readouterr().out
    exclude = (project / ".git/info/exclude").read_text()
    assert "/.claude/" in exclude and "/CLAUDE.md" in exclude and exclude.count("# agent-guild") == 1


def test_given_no_git_exclude_flag_then_git_exclude_is_untouched(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    _git(project, "init", "-q")
    before = (project / ".git/info/exclude").read_text()
    # when
    run(project, sources)
    # then
    assert (project / ".git/info/exclude").read_text() == before
    assert ".claude" in _git(project, "status", "--short")


def test_given_no_with_flag_then_no_language_coder_or_navigation_server_is_installed(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources)
    # then
    assert sorted(p.name for p in (project / ".claude/agents").glob("coder-*.md")) == []
    assert set(json.loads((project / ".mcp.json").read_text())["mcpServers"]) == {"jevmem"}
    assert "coder-python" not in (project / "CLAUDE.md").read_text()


@pytest.mark.parametrize("agent, server_key, tool", [
    ("coder-python", "codenav", "rename_symbol"),
    ("coder-swift", "codenav-swift", "rename_symbol"),
    ("coder-typescript", "webnav", "rename_symbol"),
])
def test_given_with_coder_then_agent_server_and_routing_rule_are_installed(tmp_path, sources, agent, server_key, tool):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources, "--with", agent)
    # then
    text = (project / ".claude/agents" / f"{agent}.md").read_text()
    frontmatter, body = text.split("---\n")[1:3]
    assert f"name: {agent}\n" in frontmatter
    assert "disallowedTools" not in frontmatter
    assert f"mcp__{server_key}__{tool}" in frontmatter
    assert "mcp__jevmem__memory_write" not in frontmatter
    assert "model: sonnet" in frontmatter
    assert "## Rules" in body and "navigation (" in body
    assert server_key in json.loads((project / ".mcp.json").read_text())["mcpServers"]
    claude_md = (project / "CLAUDE.md").read_text()
    assert f"`{agent}`" in claude_md
    assert claude_md.index(f"`{agent}`") < claude_md.index("## Memory bank")


def test_given_with_coder_when_run_again_then_nothing_changes_and_rule_is_not_repeated(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    run(project, sources, "--with", "coder-python", "--with", "coder-swift")
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    # when
    run(project, sources, "--with", "coder-python", "--with", "coder-swift")
    # then
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before
    assert (project / "CLAUDE.md").read_text().count("## Python code goes to") == 1


def test_given_existing_server_entry_when_with_coder_then_it_is_kept(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    custom = {"command": "codenav-mcp", "env": {"CODENAV_MCP_SOURCE_ROOT": "src"}}
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"codenav": custom}}))
    # when
    run(project, sources, "--with", "coder-python")
    # then
    assert json.loads((project / ".mcp.json").read_text())["mcpServers"]["codenav"] == custom


def test_given_with_coder_and_without_jevmem_then_server_is_still_added(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when
    run(project, sources, "--without", "jevmem", "--with", "coder-typescript")
    # then
    assert set(json.loads((project / ".mcp.json").read_text())["mcpServers"]) == {"webnav"}


def touch(root, *names):
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("")


def test_given_python_project_without_coder_when_installed_then_the_command_to_add_it_is_suggested(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    touch(project, "pyproject.toml", "src/app/main.py")
    # when
    run(project, sources)
    # then
    out = capsys.readouterr().out
    assert f"uvx agent-guild {project} --with coder-python --coders-only" in out
    assert "coder-swift" not in out and "coder-typescript" not in out


def test_given_mixed_project_then_every_matching_language_is_suggested(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    touch(project, "Package.swift", "web/package.json", "node_modules/x/pyproject.toml", ".venv/lib/a.py")
    # when
    run(project, sources)
    # then
    out = capsys.readouterr().out
    assert "--with coder-swift" in out and "--with coder-typescript" in out
    assert "--with coder-python" not in out  # only inside skipped folders


def test_given_coder_chosen_or_already_installed_then_it_is_not_suggested(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    touch(project, "pyproject.toml", "package.json")
    run(project, sources, "--with", "coder-python")
    capsys.readouterr()
    # when
    run(project, sources)  # coder-python is now on disk; coder-typescript still isn't
    # then
    out = capsys.readouterr().out
    assert "--with coder-python" not in out and "--with coder-typescript" in out


def test_given_dry_run_or_no_known_language_then_nothing_is_suggested(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    touch(project, "pyproject.toml")
    empty = tmp_path / "empty"
    empty.mkdir()
    # when
    run(project, sources, "--dry-run")
    run(empty, sources)
    # then
    assert "--coders-only" not in capsys.readouterr().out


def test_given_coders_only_then_only_the_coder_server_and_rule_are_added(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "CLAUDE.md").write_text("# Mine\n")
    # when
    run(project, sources, "--with", "coder-python", "--coders-only")
    # then
    files = {p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file()}
    assert files == {".claude/agents/coder-python.md", ".mcp.json", "CLAUDE.md"}
    assert set(json.loads((project / ".mcp.json").read_text())["mcpServers"]) == {"codenav"}
    claude_md = (project / "CLAUDE.md").read_text()
    assert claude_md.startswith("# Mine") and "`coder-python`" in claude_md and "Memory bank" not in claude_md


def test_given_coders_only_without_with_then_it_is_refused(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when / then
    with pytest.raises(SystemExit):
        run(project, sources, "--coders-only")
