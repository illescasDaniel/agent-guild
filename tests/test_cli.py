import json
from pathlib import Path

import pytest

from agent_guild.cli import main
from agent_guild.vendors import convert_agent

REPOS = {"memory-bank": "skills/memory-bank", "jev-mem": ".claude/skills/jev-memory",
         "sdd-feature-skill": "skills/sdd-feature"}


@pytest.fixture
def sources(tmp_path):
    root = tmp_path / "sources"
    for repo, sub in REPOS.items():
        (root / repo / sub).mkdir(parents=True)
        (root / repo / sub / "SKILL.md").write_text(f"# {repo}\n")
    friction = root / "memory-bank/skills/memory-bank/templates/friction"
    friction.mkdir(parents=True)
    (friction / "README.md").write_text("# Friction log\n\nOne dated file per incident.\n")
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
    assert (project / ".agents/development-workflow.md").is_file()
    for skill in ("memory-bank", "jev-memory", "sdd-feature"):
        assert (project / ".claude/skills" / skill / "SKILL.md").is_file()
    assert not (project / "CLAUDE.md").exists()
    agents_md = (project / "AGENTS.md").read_text()
    assert "Read `.agents/development-workflow.md`." in agents_md
    assert "## Memory bank" in agents_md and "Phase Gate Protocol" in agents_md
    settings = json.loads((project / ".claude/settings.json").read_text())
    assert settings["model"] == "sonnet" and settings["autoMemoryEnabled"] is False
    assert set(settings["hooks"]) == {"SessionStart", "UserPromptSubmit"}
    assert "jevmem" in json.loads((project / ".mcp.json").read_text())["mcpServers"]


@pytest.mark.parametrize("tool", ["claude", "cursor", "codex", "claude,cursor,codex"])
def test_friction_is_enabled_for_every_tool_without_replacing_existing_memory_rules(tmp_path, sources, tool):
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("## Memory bank\n\nCustom memory rules.\n")

    run(project, sources, "--tools", tool)

    assert (project / "memory/friction/README.md").read_bytes() == (
        sources / "memory-bank/skills/memory-bank/templates/friction/README.md").read_bytes()
    rules = (project / "AGENTS.md").read_text()
    assert "Custom memory rules." in rules
    assert "## Friction log" in rules and "secondary maintenance backlog" in rules
    assert "even though `memory/` already exists" in rules


@pytest.mark.parametrize("force", [False, True])
def test_friction_setup_preserves_existing_logs_and_memory(tmp_path, sources, force):
    project = tmp_path / "p"
    friction = project / "memory/friction"
    friction.mkdir(parents=True)
    (friction / "README.md").write_text("Custom friction policy.\n")
    (friction / "2026-10-23-tool-error.md").write_text("An existing incident.\n")
    (project / "memory/activeContext.md").write_text("Current project focus.\n")
    before = {p: p.read_bytes() for p in (project / "memory").rglob("*") if p.is_file()}

    run(project, sources, *(["--force"] if force else []))

    assert {p: p.read_bytes() for p in (project / "memory").rglob("*") if p.is_file()} == before


def test_without_memory_bank_skips_friction_setup(tmp_path, sources):
    project = tmp_path / "p"
    project.mkdir()

    run(project, sources, "--without", "memory-bank")

    assert not (project / "memory").exists()
    assert "## Friction log" not in (project / "AGENTS.md").read_text()


def test_given_agents_md_only_when_installed_then_it_holds_the_sections_and_claude_md_imports_it(tmp_path, sources):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n")
    # when
    run(project, sources)
    # then
    assert not (project / "CLAUDE.md").exists()
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
    assert (project / "CLAUDE.md").read_text() == "# Claude only\n"


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
    assert (project / ".claude/skills/sdd-feature/SKILL.md").read_text() == "cursor version"


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
    assert "/.claude/" in exclude and "/AGENTS.md" in exclude and "/.agents/" in exclude and exclude.count("# agent-guild") == 1


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
    assert "project agent coder" in capsys.readouterr().out


def test_given_sections_already_in_agents_md_then_the_log_says_skipped_not_unchanged(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("## Memory bank\n\n## Phase Gate Protocol\n")
    # when
    run(project, sources)
    # then
    out = capsys.readouterr().out
    assert "skipped    AGENTS.md  section 'Phase Gate Protocol' is already in AGENTS.md" in out


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
    assert (project / ".agents/development-workflow.md").is_file()
    assert "Read `.agents/development-workflow.md`." in (project / "AGENTS.md").read_text()
    assert "jevmem" in json.loads((project / ".cursor/mcp.json").read_text())["mcpServers"]
    assert "type" not in json.loads((project / ".cursor/mcp.json").read_text())["mcpServers"]["jevmem"]


def test_given_codex_folder_when_installed_then_agents_are_toml_and_skills_go_to_agents_skills(tmp_path, sources, capsys):
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
    assert (project / ".agents/skills/sdd-feature/SKILL.md").is_file()
    assert not (project / ".codex/skills").exists()
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
    assert [f for f in files if f.endswith("development-workflow.md")] == [".agents/development-workflow.md"]
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


def test_given_claude_md_only_and_codex_then_developer_rules_are_not_migrated(tmp_path, sources, capsys):
    # given
    project = tmp_path / "p"
    (project / ".codex").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("# Mine\n")
    # when
    run(project, sources)
    # then
    assert "# Mine" not in (project / "AGENTS.md").read_text()
    assert (project / "CLAUDE.md").read_text() == "# Mine\n"


def test_given_claude_md_reference_when_converting_for_cursor_or_codex_then_only_agents_md_is_named():
    source = b'---\nname: x\ndescription: d\n---\nFollow `CLAUDE.md` / `AGENTS.md` rules; read `AGENTS.md` / `CLAUDE.md`.\n'
    for tool in ("cursor", "codex"):
        converted = convert_agent(tool, source).decode()
        assert "CLAUDE.md" not in converted
        assert "Follow `AGENTS.md` rules; read `AGENTS.md`." in converted
    assert b"`CLAUDE.md` / `AGENTS.md`" in convert_agent("claude", source)


def test_given_crlf_agent_source_when_converting_then_same_result_as_lf():
    # Windows checkouts may turn the shipped agent files into CRLF
    lf = b'---\nname: x\ndescription: d\ndisallowedTools: Edit, Write\n---\nBody\n'
    for tool in ("cursor", "codex"):
        assert convert_agent(tool, lf.replace(b"\n", b"\r\n")) == convert_agent(tool, lf)


def test_given_rules_only_in_claude_when_adding_codex_then_custom_sections_stay_in_claude(tmp_path, sources):
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Shared\n\n## Memory bank\n\nProject memory rules.\n")
    (project / "CLAUDE.md").write_text(
        "@AGENTS.md\n\n## Agents and delegation\n\nCustom routing.\n\n### Briefs\n\nKeep these.\n\n"
        "## Python code goes to `coder-python`\n\nCustom Python rule.\n\n## Claude only\n\nKeep locally.\n"
    )
    run(project, sources, "--tools", "claude,codex", "--with", "coder-python")
    shared = (project / "AGENTS.md").read_text()
    local = (project / "CLAUDE.md").read_text()
    assert "Custom routing." not in shared and "### Briefs" not in shared
    assert "Custom Python rule." not in shared and "Project memory rules." in shared
    assert "Custom routing." in local and "Custom Python rule." in local
    assert "### Briefs\n\nKeep these." in local
    assert "## Claude only\n\nKeep locally." in local and local.startswith("@AGENTS.md\n")
    assert "## Claude only" not in shared
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    run(project, sources, "--tools", "claude,codex", "--with", "coder-python")
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("with_agents", [False, True])
def test_given_legacy_rules_when_dry_run_then_migration_writes_nothing(tmp_path, sources, with_agents):
    project = tmp_path / "p"
    project.mkdir()
    (project / "CLAUDE.md").write_text("# Rules\n\n## Agents and delegation\n\nMy routing.\n")
    if with_agents:
        (project / "AGENTS.md").write_text("# Shared\n")
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    run(project, sources, "--tools", "claude,codex", "--dry-run")
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


def test_given_conflicting_shared_rules_then_both_copies_are_kept_and_warning_is_printed(tmp_path, sources, capsys):
    project = tmp_path / "p"
    project.mkdir()
    (project / "AGENTS.md").write_text("## Agents and delegation\n\nShared version.\n")
    (project / "CLAUDE.md").write_text("## Agents and delegation\n\nLocal version.\n")
    run(project, sources, "--tools", "claude,codex")
    assert "Shared version." in (project / "AGENTS.md").read_text()
    assert "Local version." in (project / "CLAUDE.md").read_text()
    assert "review the copies for conflicting rules" in capsys.readouterr().out


@pytest.mark.parametrize("folder", [".claude/skills", ".cursor/skills", ".codex/skills"])
@pytest.mark.parametrize("tools", ["codex", "claude,cursor,codex"])
def test_given_customized_skill_when_adding_codex_then_project_copy_and_support_files_are_reused(tmp_path, sources, folder, tools):
    # given: upstream has both a conflicting helper and a file missing from the project copy
    shipped = sources / "sdd-feature-skill/skills/sdd-feature"
    (shipped / "scripts").mkdir()
    (shipped / "scripts/check.py").write_text("# Shipped helper\n")
    (shipped / "templates").mkdir()
    (shipped / "templates/SPEC.md").write_text("# Shipped spec template\n")
    project = tmp_path / "p"
    skill = project / folder / "sdd-feature"
    (skill / "scripts").mkdir(parents=True)
    (skill / "support/nested").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Custom project SDD\n")
    (skill / "scripts/check.py").write_text("# Custom helper\n")
    (skill / "support/nested/notes.txt").write_text("Custom supporting notes\n")
    original = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}

    # when: a dry-run precedes the first installation
    run(project, sources, "--tools", tools, "--dry-run")
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == original
    run(project, sources, "--tools", tools)

    # then: custom files win, and missing shipped files arrive on the first run
    installed = project / ".agents/skills/sdd-feature"
    assert (installed / "SKILL.md").read_text() == "# Custom project SDD\n"
    assert (installed / "scripts/check.py").read_text() == "# Custom helper\n"
    assert (installed / "support/nested/notes.txt").read_text() == "Custom supporting notes\n"
    assert (installed / "templates/SPEC.md").read_text() == "# Shipped spec template\n"
    assert all(p.read_bytes() == data for p, data in original.items())
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    run(project, sources, "--tools", tools)
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


def test_given_existing_codex_skill_then_other_tools_do_not_replace_it(tmp_path, sources):
    project = tmp_path / "p"
    for folder, text in ((".cursor/skills", "Cursor custom"), (".agents/skills", "Codex custom")):
        skill = project / folder / "sdd-feature"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(text)
    run(project, sources, "--tools", "codex")
    assert (project / ".agents/skills/sdd-feature/SKILL.md").read_text() == "Codex custom"


@pytest.mark.parametrize("source", [".mcp.json", ".cursor/mcp.json"])
def test_given_project_navigation_config_when_adding_codex_then_command_args_and_environment_are_reused(tmp_path, sources, source):
    import tomllib
    project = tmp_path / "p"
    path = project / source
    path.parent.mkdir(parents=True, exist_ok=True)
    server = {"command": "custom-nav", "args": ["--custom"], "env": {"SOURCE_ROOT": "custom/src"}}
    path.write_text(json.dumps({"mcpServers": {"codenav": server}}))
    run(project, sources, "--tools", "codex", "--with", "coder-python")
    config = tomllib.loads((project / ".codex/config.toml").read_text())
    assert config["mcp_servers"]["codenav"] == server


def test_given_existing_codex_server_then_cross_tool_settings_do_not_override_it(tmp_path, sources):
    import tomllib
    project = tmp_path / "p"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex/config.toml").write_text('[mcp_servers.codenav]\ncommand = "codex-custom"\n')
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"codenav": {"command": "claude-custom"}}}))
    run(project, sources, "--tools", "codex", "--with", "coder-python")
    config = tomllib.loads((project / ".codex/config.toml").read_text())
    assert config["mcp_servers"]["codenav"] == {"command": "codex-custom"}


@pytest.mark.parametrize("name", ["coder-python", "coder-swift", "coder-typescript"])
def test_given_language_coder_then_yaml_description_is_quoted_and_converted_descriptions_match(tmp_path, sources, name):
    import tomllib
    from agent_guild.specialists import SPECIALISTS
    project = tmp_path / "p"
    project.mkdir()
    run(project, sources, "--tools", "claude,cursor,codex", "--with", name)
    for folder in (".claude/agents", ".cursor/agents"):
        text = (project / folder / f"{name}.md").read_text()
        description = next(line.removeprefix("description: ") for line in text.splitlines() if line.startswith("description: "))
        assert json.loads(description) == SPECIALISTS[name].description
    codex = tomllib.loads((project / ".codex/agents" / f"{name}.toml").read_text())
    assert codex["description"] == SPECIALISTS[name].description


@pytest.mark.parametrize('tools,files,target', [
    ('claude', [], 'AGENTS.md'),
    ('claude', ['CLAUDE.md'], 'CLAUDE.md'),
    ('claude', ['AGENTS.md'], 'AGENTS.md'),
    ('claude', ['AGENTS.md', 'CLAUDE.md'], 'AGENTS.md'),
    ('claude,cursor,codex', ['CLAUDE.md'], 'AGENTS.md'),
    ('cursor,codex', ['AGENTS.md', 'CLAUDE.md'], 'AGENTS.md'),
])
def test_instruction_policy_never_moves_developer_rules(tmp_path, sources, tools, files, target):
    project = tmp_path / 'project'
    project.mkdir()
    for name in files:
        (project / name).write_text(f'# Developer {name}\n')
    original = {name: (project / name).read_bytes() for name in files}
    run(project, sources, '--tools', tools)
    assert '## Agents and delegation' in (project / target).read_text()
    for name, data in original.items():
        if name == target:
            assert (project / name).read_bytes().startswith(data)
        else:
            assert (project / name).read_bytes() == data
    if 'CLAUDE.md' not in files:
        assert not (project / 'CLAUDE.md').exists()
    before = {p: p.read_bytes() for p in project.rglob('*') if p.is_file()}
    run(project, sources, '--tools', tools)
    assert {p: p.read_bytes() for p in project.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('existing', [False, True])
def test_explicit_claude_compat_import_is_idempotent(tmp_path, sources, existing):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'AGENTS.md').write_text('# Shared\n')
    if existing:
        (project / 'CLAUDE.md').write_text('# Claude-specific\n')
    run(project, sources, '--tools', 'claude,codex', '--claude-compat')
    text = (project / 'CLAUDE.md').read_text()
    assert text == '@AGENTS.md\n' + ('\n# Claude-specific\n' if existing else '')
    run(project, sources, '--tools', 'claude,codex', '--claude-compat')
    assert (project / 'CLAUDE.md').read_text() == text


@pytest.mark.parametrize('personal', [False, True])
def test_existing_settings_are_preserved_unless_explicitly_overridden(tmp_path, sources, personal):
    project = tmp_path / 'project'
    (project / '.claude').mkdir(parents=True)
    path = project / '.claude' / ('settings.local.json' if personal else 'settings.json')
    path.write_text(json.dumps({'model': 'opus', 'autoMemoryEnabled': True}))
    args = ['--personal-settings'] if personal else []
    run(project, sources, '--tools', 'claude', *args)
    assert json.loads(path.read_text())['model'] == 'opus'
    assert json.loads(path.read_text())['autoMemoryEnabled'] is True
    run(project, sources, '--tools', 'claude', '--model', 'haiku', '--disable-auto-memory', *args)
    config = json.loads(path.read_text())
    assert config['model'] == 'haiku' and config['autoMemoryEnabled'] is False


def test_personal_settings_inherit_shared_preferences(tmp_path, sources):
    project = tmp_path / 'project'
    (project / '.claude').mkdir(parents=True)
    (project / '.claude/settings.json').write_text('{"model":"opus","autoMemoryEnabled":true}')
    run(project, sources, '--personal-settings')
    assert not (project / '.claude/settings.local.json').exists()
    assert json.loads((project / '.claude/settings.json').read_text())['autoMemoryEnabled'] is True


@pytest.mark.parametrize('tool,folder,suffix', [
    ('claude', '.claude/agents', '.md'), ('cursor', '.cursor/agents', '.md'), ('codex', '.codex/agents', '.toml'),
])
def test_project_agent_is_reused_for_every_missing_tool(tmp_path, sources, tool, folder, suffix):
    import tomllib
    project = tmp_path / 'project'
    (project / folder).mkdir(parents=True)
    source = b'---\nname: architect\ndescription: "My project architect: custom rules"\ndisallowedTools: Edit, Write\n---\nProject-specific plan.\n'
    path = project / folder / ('architect' + suffix)
    path.write_bytes(convert_agent(tool, source))
    original = path.read_bytes()
    run(project, sources, '--tools', 'claude,cursor,codex')
    assert path.read_bytes() == original
    for dest in ['.claude/agents/architect.md', '.cursor/agents/architect.md']:
        text = (project / dest).read_text()
        assert 'My project architect: custom rules' in text and 'Project-specific plan.' in text
    codex = tomllib.loads((project / '.codex/agents/architect.toml').read_text())
    assert codex['description'] == 'My project architect: custom rules'
    assert 'Project-specific plan.' in codex['developer_instructions']
    assert codex['developer_instructions'].startswith('You are read-only')


def test_multiline_yaml_and_tool_lists_survive_conversion():
    import tomllib
    source = b'---\nname: architect\ndescription: >-\n  Custom architect\n  for this project\ndisallowedTools:\n  - Edit\n  - Write\n---\nInstructions.\n'
    data = tomllib.loads(convert_agent('codex', source).decode())
    assert data['description'] == 'Custom architect for this project'
    assert data['developer_instructions'].startswith('You are read-only')


def test_different_existing_agents_are_preserved_and_warned(tmp_path, sources, capsys):
    project = tmp_path / 'project'
    for folder, description in [('.claude/agents', 'Claude custom'), ('.cursor/agents', 'Cursor custom')]:
        (project / folder).mkdir(parents=True)
        (project / folder / 'coder.md').write_text(f'---\nname: coder\ndescription: {description}\n---\nProject rules.\n')
    run(project, sources, '--tools', 'claude,cursor,codex')
    assert 'Cursor custom' in (project / '.cursor/agents/coder.md').read_text()
    assert 'Claude custom' in (project / '.codex/agents/coder.toml').read_text()
    assert 'cross-tool drift' in capsys.readouterr().out


@pytest.mark.parametrize('source_folder', ['.claude/skills', '.cursor/skills', '.agents/skills', '.codex/skills'])
def test_all_tool_skills_reuse_one_project_source(tmp_path, sources, source_folder):
    project = tmp_path / 'project'
    source = project / source_folder / 'sdd-feature'
    (source / 'nested').mkdir(parents=True)
    (source / 'SKILL.md').write_text('# Project SDD\n')
    (source / 'nested/helper.txt').write_text('Project helper\n')
    run(project, sources, '--tools', 'claude,cursor,codex')
    for folder in ['.claude/skills', '.cursor/skills', '.agents/skills']:
        assert (project / folder / 'sdd-feature/SKILL.md').read_text() == '# Project SDD\n'
        assert (project / folder / 'sdd-feature/nested/helper.txt').read_text() == 'Project helper\n'


@pytest.mark.parametrize('path,content', [
    ('.mcp.json', '{broken'), ('.codex/config.toml', 'broken = ['),
    ('.claude/settings.json', '{broken'), ('.cursor/mcp.json', '{"mcpServers": []}'),
    ('.claude/settings.json', '{"hooks": []}'), ('.claude/settings.local.json', '{broken'),
])
def test_preflight_configuration_failure_changes_nothing(tmp_path, sources, path, content):
    project = tmp_path / 'project'
    config = project / path
    config.parent.mkdir(parents=True)
    config.write_text(content)
    before = {p: p.read_bytes() for p in project.rglob('*') if p.is_file()}
    with pytest.raises(SystemExit):
        run(project, sources, '--tools', 'claude,cursor,codex')
    assert {p: p.read_bytes() for p in project.rglob('*') if p.is_file()} == before


def test_missing_last_skill_leaves_no_partial_install(tmp_path, sources):
    project = tmp_path / 'project'
    project.mkdir()
    (sources / 'sdd-feature-skill/skills/sdd-feature/SKILL.md').unlink()
    with pytest.raises(SystemExit, match='no SKILL.md'):
        run(project, sources, '--tools', 'claude,cursor,codex')
    assert list(project.iterdir()) == []


def test_download_failure_leaves_no_partial_install(tmp_path, monkeypatch):
    import subprocess
    from agent_guild import installer
    project = tmp_path / 'project'
    project.mkdir()
    def fail(*args):
        raise subprocess.CalledProcessError(1, 'git fetch')
    monkeypatch.setattr(installer, '_fetch', fail)
    with pytest.raises(subprocess.CalledProcessError):
        main([str(project)])
    assert list(project.iterdir()) == []


def test_default_downloads_are_pinned_and_recorded(tmp_path, sources, monkeypatch, capsys):
    from agent_guild import installer
    project = tmp_path / 'project'
    project.mkdir()
    requested = []
    def fetch(url, into, revision):
        requested.append((url, revision))
        return sources / into.name
    monkeypatch.setattr(installer, '_fetch', fetch)
    main([str(project), '--dry-run'])
    assert list(project.iterdir()) == []
    assert {revision for _, revision in requested} == set(installer.SKILL_REVISIONS.values())
    assert all(len(revision) == 40 for _, revision in requested)
    assert installer.SKILL_REVISIONS['sdd'] in capsys.readouterr().out
    main([str(project)])
    manifest = json.loads((project / '.agents/skill-sources.json').read_text())
    assert manifest['sdd']['revision'] == installer.SKILL_REVISIONS['sdd']
    assert len(manifest['sdd']['sha256']) == 64


def test_failed_memory_import_does_not_disable_memory_or_write_install(tmp_path, sources, monkeypatch):
    from agent_guild import installer
    project = tmp_path / 'project'
    project.mkdir()
    (installer.encoded_memory_dir(project) / 'memory').mkdir(parents=True)
    class Failed:
        returncode = 1
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **kw: Failed())
    with pytest.raises(SystemExit, match='no installation files were written'):
        run(project, sources, '--import-auto-memory')
    assert list(project.iterdir()) == []


def test_shared_workflow_does_not_enable_codex_on_next_install(tmp_path, sources, capsys):
    project = tmp_path / 'project'
    project.mkdir()
    run(project, sources)
    capsys.readouterr()
    run(project, sources)
    assert 'tools: claude (detected)' in capsys.readouterr().out
    assert not (project / '.codex').exists()


def test_invalid_generated_codex_config_leaves_no_install_files(tmp_path, sources):
    project = tmp_path / 'project'
    project.mkdir()
    path = project / '.mcp.json'
    path.write_text('{"mcpServers":{"jevmem":{"command":"custom","env":null}}}')
    original = path.read_bytes()
    with pytest.raises(SystemExit, match='cannot generate valid Codex MCP'):
        run(project, sources, '--tools', 'claude,cursor,codex')
    assert _tree(project) == ['.mcp.json']
    assert path.read_bytes() == original


def test_existing_workflow_is_reused_without_moving_the_original(tmp_path, sources):
    project = tmp_path / 'project'
    (project / '.claude').mkdir(parents=True)
    (project / '.claude/development-workflow.md').write_text('# Custom workflow\n')
    run(project, sources, '--tools', 'claude,cursor,codex')
    assert (project / '.agents/development-workflow.md').read_text() == '# Custom workflow\n'
    assert (project / '.claude/development-workflow.md').read_text() == '# Custom workflow\n'
    assert 'Read `.agents/development-workflow.md`.' in (project / 'AGENTS.md').read_text()


def test_language_coder_keeps_project_generic_instructions(tmp_path, sources):
    from agent_guild.cli import DEFAULT_ASSETS
    project = tmp_path / 'project'
    (project / '.claude/agents').mkdir(parents=True)
    generic = (DEFAULT_ASSETS / 'agents/coder.md').read_text().replace('## Rules', '## Rules\n- Preserve project-specific convention XYZ.')
    (project / '.claude/agents/coder.md').write_text(generic)
    run(project, sources, '--tools', 'claude,cursor,codex', '--with', 'coder-python')
    for folder, suffix in [('.claude/agents', '.md'), ('.cursor/agents', '.md'), ('.codex/agents', '.toml')]:
        assert 'Preserve project-specific convention XYZ.' in (project / folder / ('coder-python' + suffix)).read_text()


def test_language_coder_from_cursor_source_has_explicit_navigation_tools(tmp_path, sources):
    from agent_guild.cli import DEFAULT_ASSETS
    import yaml
    project = tmp_path / 'project'
    (project / '.cursor/agents').mkdir(parents=True)
    generic = convert_agent('cursor', (DEFAULT_ASSETS / 'agents/coder.md').read_bytes())
    (project / '.cursor/agents/coder.md').write_bytes(generic)
    run(project, sources, '--tools', 'claude,cursor,codex', '--with', 'coder-python')
    fields = yaml.safe_load((project / '.claude/agents/coder-python.md').read_text().split('---\n', 2)[1])
    assert 'mcp__codenav__symbol_info' in fields['tools']
    assert 'disallowedTools' not in fields


def test_indented_separator_in_yaml_description_is_not_a_frontmatter_boundary():
    import tomllib
    source = b'---\nname: coder\ndescription: |\n  Project\n  ---\n  instructions\n---\nBody.\n'
    data = tomllib.loads(convert_agent('codex', source).decode())
    assert data['description'] == 'Project\n---\ninstructions\n'
    assert data['developer_instructions'] == 'Body.\n'
