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
    assert (project / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    agents_md = (project / "AGENTS.md").read_text()
    assert "@.claude/development-workflow.md" in agents_md
    assert "## Memory bank" in agents_md and "Phase Gate Protocol" in agents_md
    settings = json.loads((project / ".claude/settings.json").read_text())
    assert settings["model"] == "sonnet" and settings["autoMemoryEnabled"] is False
    assert set(settings["hooks"]) == {"SessionStart", "UserPromptSubmit"}
    assert "jevmem" in json.loads((project / ".mcp.json").read_text())["mcpServers"]


def test_given_agents_md_only_when_installed_then_it_holds_the_sections_and_claude_md_imports_it(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n")
    # when
    run(project, sources)
    # then
    assert (project / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert (project / "AGENTS.md").read_text().startswith("# Rules\n")
    assert "## Agents and delegation" in (project / "AGENTS.md").read_text()


def test_given_claude_md_only_when_installed_then_the_sections_go_there(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "CLAUDE.md").write_text("# Mine\n")
    # when
    run(project, sources)
    # then
    assert not (project / "AGENTS.md").exists()
    assert "## Agents and delegation" in (project / "CLAUDE.md").read_text()


def test_given_both_files_when_installed_then_agents_md_gets_the_sections_and_claude_md_keeps_its_text(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n")
    (project / "CLAUDE.md").write_text("# Claude only\n")
    # when
    run(project, sources)
    # then
    assert "## Agents and delegation" in (project / "AGENTS.md").read_text()
    assert (project / "CLAUDE.md").read_text() == "@AGENTS.md\n\n# Claude only\n"


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
    assert "Phase Gate" not in (project / "AGENTS.md").read_text()


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


def test_given_sections_already_in_agents_md_then_they_are_not_repeated(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("## Memory bank\n\n## Phase Gate Protocol\n")
    # when
    run(project, sources)
    # then
    text = (project / "AGENTS.md").read_text()
    assert "## Agents and delegation" in text
    assert text.count("## Memory bank") == 1 and text.count("Phase Gate") == 1


def test_given_cursor_skills_when_importing_then_copied_without_replacing_existing(tmp_path, sources):
    # given
    project = tmp_path / "p"
    (project / ".cursor/skills/mine").mkdir(parents=True)
    (project / ".cursor/skills/mine/SKILL.md").write_text("mine")
    (project / ".cursor/skills/sdd-feature").mkdir()
    (project / ".cursor/skills/sdd-feature/SKILL.md").write_text("cursor version")
    # when
    run(project, sources, "--tools", "claude,cursor", "--import-cursor-skills")
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
    assert "coder-python" not in (project / "AGENTS.md").read_text()


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
    agents_md = (project / "AGENTS.md").read_text()
    assert f"`{agent}`" in agents_md
    assert agents_md.index(f"`{agent}`") < agents_md.index("## Memory bank")


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
    assert (project / "AGENTS.md").read_text().count("## Python code goes to") == 1


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


def test_given_edited_agent_when_run_again_then_the_merge_hint_is_printed(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    project.mkdir()
    run(project, sources)
    (project / ".claude/agents/coder.md").write_text("mine")
    capsys.readouterr()
    # when
    run(project, sources)
    # then
    assert "merge the changes by hand" in capsys.readouterr().out


def test_given_sections_already_in_agents_md_then_the_log_says_skipped_not_unchanged(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("## Memory bank\n\n## Phase Gate Protocol\n")
    # when
    run(project, sources)
    # then
    out = capsys.readouterr().out
    assert "skipped    AGENTS.md  section 'Phase Gate Protocol' is already in AGENTS.md or CLAUDE.md" in out


def test_given_symlinked_skills_dir_then_the_log_notes_where_skills_are_written(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    (project / ".cursor/skills").mkdir(parents=True)
    (project / ".claude").mkdir()
    try:
        (project / ".claude/skills").symlink_to(project / ".cursor/skills", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    # when
    run(project, sources)
    # then
    assert "is a symlink to" in capsys.readouterr().out
    assert (project / ".cursor/skills/sdd-feature/SKILL.md").is_file()


def _tree(project):
    return sorted(p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file())


def test_given_cursor_folder_when_installed_then_cursor_gets_its_own_format_and_no_claude_files(tmp_path, sources):
    # given
    project = tmp_path / "p"
    (project / ".cursor").mkdir(parents=True)
    # when
    run(project, sources)
    # then
    files = _tree(project)
    assert not any(f.startswith(".claude/") or f in ("CLAUDE.md", ".mcp.json") for f in files)
    architect = (project / ".cursor/agents/architect.md").read_text()
    assert 'readonly: true' in architect and "model: inherit" in architect
    assert "disallowedTools" not in architect and "color:" not in architect and "effort:" not in architect
    assert "readonly" not in (project / ".cursor/agents/coder.md").read_text()
    for skill in ("memory-bank", "jev-memory", "sdd-feature"):
        assert (project / ".cursor/skills" / skill / "SKILL.md").is_file()
    assert (project / ".cursor/development-workflow.md").is_file()
    assert "@.cursor/development-workflow.md" in (project / "AGENTS.md").read_text()
    assert "jevmem" in json.loads((project / ".cursor/mcp.json").read_text())["mcpServers"]
    assert "type" not in json.loads((project / ".cursor/mcp.json").read_text())["mcpServers"]["jevmem"]


def test_given_codex_folder_when_installed_then_agents_are_toml_and_skills_go_to_codex_skills(tmp_path, sources, capsys):
    # given
    import tomllib
    project = tmp_path / "p"
    (project / ".codex").mkdir(parents=True)
    # when
    run(project, sources, "--with", "coder-python")
    # then
    for name in ("architect", "coder", "code-grader", "utility", "coder-python"):
        agent = tomllib.loads((project / ".codex/agents" / f"{name}.toml").read_text())
        assert agent["name"] == name and agent["description"] and agent["developer_instructions"].strip()
    architect = tomllib.loads((project / ".codex/agents/architect.toml").read_text())
    assert architect["model_reasoning_effort"] == "high"
    assert architect["developer_instructions"].startswith("You are read-only")
    assert not tomllib.loads((project / ".codex/agents/coder.toml").read_text())["developer_instructions"].startswith("You are read-only")
    assert (project / ".codex/skills/sdd-feature/SKILL.md").is_file()
    assert not (project / ".agents").exists()
    config = tomllib.loads((project / ".codex/config.toml").read_text())
    assert config["mcp_servers"]["jevmem"]["command"] == "uvx"
    assert config["mcp_servers"]["codenav"]["args"][0] == "--from"
    assert not (project / ".claude").exists()
    assert "jevmem's session hooks are only set up for Claude Code" in capsys.readouterr().out


def test_given_several_tools_detected_then_all_of_them_are_installed_and_share_one_workflow_doc(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    for folder in (".claude", ".cursor", ".codex"):
        (project / folder).mkdir(parents=True)
    # when
    run(project, sources)
    # then
    files = _tree(project)
    assert ".claude/agents/coder.md" in files and ".cursor/agents/coder.md" in files and ".codex/agents/coder.toml" in files
    assert [f for f in files if f.endswith("development-workflow.md")] == [".claude/development-workflow.md"]
    assert "tools: claude, cursor, codex (detected)" in capsys.readouterr().out
    rules = (project / "AGENTS.md").read_text()
    assert "`.claude/agents/`, `.cursor/agents/` and `.codex/agents/`" in rules


def test_given_tools_flag_then_it_overrides_detection(tmp_path, sources):
    # given
    project = tmp_path / "p"
    (project / ".cursor").mkdir(parents=True)
    # when
    run(project, sources, "--tools", "codex")
    # then
    assert (project / ".codex/agents/coder.toml").is_file()
    assert not (project / ".cursor/agents").exists() and not (project / ".claude").exists()


def test_given_unknown_tool_then_it_is_refused(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    # when / then
    with pytest.raises(SystemExit):
        run(project, sources, "--tools", "emacs")


def test_given_codex_config_with_other_settings_then_servers_are_appended_and_run_again_changes_nothing(tmp_path, sources):
    # given
    project = tmp_path / "p"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex/config.toml").write_text('model = "x"\n\n[mcp_servers.jevmem]\ncommand = "mine"\n')
    # when
    run(project, sources, "--with", "coder-swift")
    run(project, sources, "--with", "coder-swift")
    # then
    import tomllib
    config = tomllib.loads((project / ".codex/config.toml").read_text())
    assert config["model"] == "x" and config["mcp_servers"]["jevmem"]["command"] == "mine"
    assert config["mcp_servers"]["codenav-swift"]["env"] == {"CODENAV_SWIFT_WRITE": "1"}
    assert (project / ".codex/config.toml").read_text().count("[mcp_servers.codenav-swift]") == 1


def test_given_claude_md_only_and_codex_then_a_warning_says_codex_will_not_read_it(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    (project / ".codex").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("# Mine\n")
    # when
    run(project, sources)
    # then
    assert "only has a CLAUDE.md" in capsys.readouterr().out
