"""Tests for src/agy_lsrpc_bridge/scaffolder.py."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import sys

# Ensure src is in sys.path if not running via pytest with correct setup
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.scaffolder import (
    _strip_yaml_frontmatter,
    scaffold_plugin,
    consolidate_loose_customizations,
)


def test_strip_yaml_frontmatter_unclosed_delimiter():
    """
    Assert that _strip_yaml_frontmatter returns the input stripped with a single
    trailing newline when the text starts with `---` but never contains a closing
    `---` delimiter.
    """
    text = "---\ntitle: test\nonly one delimiter here"
    result = _strip_yaml_frontmatter(text)
    assert result == "---\ntitle: test\nonly one delimiter here\n"

def test_strip_yaml_frontmatter_normal():
    text = "---\ntitle: test\n---\n# Header\ncontent"
    result = _strip_yaml_frontmatter(text)
    assert result == "# Header\ncontent"

def test_strip_yaml_frontmatter_no_frontmatter():
    text = "# Header\ncontent  "
    result = _strip_yaml_frontmatter(text)
    assert result == "# Header\ncontent\n"

def test_strip_yaml_frontmatter_empty():
    assert _strip_yaml_frontmatter("") == "\n"
    assert _strip_yaml_frontmatter("   ") == "\n"

def test_scaffold_plugin_invalid_name(tmp_path):
    with pytest.raises(ValueError, match="Plugin name must contain lowercase alphanumeric characters"):
        scaffold_plugin(tmp_path, name="!!!", description="test")

def test_scaffold_plugin_basic(tmp_path):
    plugin_dir = scaffold_plugin(
        target_root=tmp_path,
        name="my-plugin",
        description="A test plugin",
        display_name="My Plugin",
        include_hooks=True,
        include_mcp=True,
    )
    
    assert plugin_dir.name == "my-plugin"
    assert plugin_dir.is_dir()
    assert (plugin_dir / "plugin.json").is_file()
    assert (plugin_dir / "README.md").is_file()
    assert (plugin_dir / "assets" / "logo.svg").is_file()
    assert (plugin_dir / "rules" / "AGENTS.md").is_file()
    assert (plugin_dir / "skills" / "my-plugin" / "SKILL.md").is_file()
    assert (plugin_dir / "agents" / "my-plugin-agent.md").is_file()
    assert (plugin_dir / "hooks.json").is_file()
    assert (plugin_dir / "mcp_config.json").is_file()

def test_consolidate_loose_customizations_no_plugin_json(tmp_path):
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()
    
    with pytest.raises(FileNotFoundError, match="Target plugin directory missing plugin.json"):
        consolidate_loose_customizations(plugin_dir)

def test_consolidate_loose_customizations_success(tmp_path):
    # Scaffold first
    plugin_dir = scaffold_plugin(tmp_path, "test-plugin", "test")
    
    # Create loose skill
    skill_dir = tmp_path / "loose-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Loose Skill\n", encoding="utf-8")
    
    # Create loose rule
    rule_file = tmp_path / "loose-rule.md"
    rule_file.write_text("---\ntags: [test]\n---\n# Loose Rule\n", encoding="utf-8")
    
    res = consolidate_loose_customizations(
        plugin_dir=plugin_dir,
        skill_dirs=[skill_dir],
        rule_files=[rule_file]
    )
    
    assert res["ok"] is True
    assert "loose-skill" in res["consolidated_skills"]
    assert "loose-rule.md" in res["consolidated_rules"]
    
    dest_skill = plugin_dir / "skills" / "loose-skill" / "SKILL.md"
    assert dest_skill.is_file()
    
    agents_md = plugin_dir / "rules" / "AGENTS.md"
    content = agents_md.read_text(encoding="utf-8")
    assert "# Loose Rule" in content
    assert "tags: [test]" not in content

def test_consolidate_loose_customizations_invalid_skill(tmp_path):
    plugin_dir = scaffold_plugin(tmp_path, "test-plugin2", "test")
    
    # Missing SKILL.md
    skill_dir = tmp_path / "bad-skill"
    skill_dir.mkdir()
    
    res = consolidate_loose_customizations(
        plugin_dir=plugin_dir,
        skill_dirs=[skill_dir],
    )
    
    assert res["consolidated_skills"] == []
