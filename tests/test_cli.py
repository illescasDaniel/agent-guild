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
