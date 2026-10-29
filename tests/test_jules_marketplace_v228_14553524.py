"""Tests for Antigravity Marketplace v2.28.1 Manifest & Bundle Validator."""

import sys
from pathlib import Path
import json

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.marketplace_v228 import MarketplaceV228Validator


@pytest.fixture
def validator():
    return MarketplaceV228Validator()


def create_plugin(tmp_path: Path, manifest: dict, filename: str = "plugin.json", in_cursor: bool = False, logo_name: str | None = None) -> Path:
    pdir = tmp_path / "my-plugin"
    pdir.mkdir(parents=True, exist_ok=True)
    
    if in_cursor:
        cursor_dir = pdir / ".Cursor-plugin"
        cursor_dir.mkdir()
        manifest_path = cursor_dir / filename
    else:
        manifest_path = pdir / filename
        
    if filename.endswith(".json"):
        manifest_path.write_text(json.dumps(manifest))
    else:
        manifest_path.write_text(str(manifest)) # for invalid json cases

    if logo_name:
        logo_path = pdir / logo_name
        logo_path.write_text("dummy logo data")

    return pdir


def test_empty_name_field_results_in_error(validator, tmp_path):
    """Test that a plugin directory with a plugin.json file containing an empty `name` field
    results in an error indicating the field is required and must be kebab-case."""
    manifest = {
        "name": "",
        "description": "A valid description"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("Field 'name' is required and must be a non-empty lowercase kebab-case string" in err for err in result.errors)


def test_whitespace_name_field_results_in_error(validator, tmp_path):
    """Test that a name field with only spaces is treated as empty."""
    manifest = {
        "name": "   ",
        "description": "A valid description"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("Field 'name' is required and must be a non-empty lowercase kebab-case string" in err for err in result.errors)


def test_missing_name_field_results_in_error(validator, tmp_path):
    """Test that missing name field results in an error."""
    manifest = {
        "description": "A valid description"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("Field 'name' is required and must be a non-empty lowercase kebab-case string" in err for err in result.errors)


def test_invalid_kebab_case_name(validator, tmp_path):
    """Test that a non-kebab-case name results in an error."""
    manifest = {
        "name": "Not-Kebab_Case",
        "description": "A valid description"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("must be lowercase kebab-case matching" in err for err in result.errors)


def test_valid_manifest(validator, tmp_path):
    """Test a fully valid manifest."""
    manifest = {
        "name": "valid-plugin-name",
        "description": "A valid description",
        "logo": "logo.png",
        "suggestedPrompts": ["Prompt 1", "Prompt 2"]
    }
    plugin_dir = create_plugin(tmp_path, manifest, logo_name="logo.png")
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert result.valid
    assert result.plugin_name == "valid-plugin-name"
    assert result.errors == []
    assert result.warnings == []
    assert result.prompt_count == 2
    assert result.has_valid_logo


def test_cursor_plugin_dir(validator, tmp_path):
    """Test manifest in .Cursor-plugin/plugin.json."""
    manifest = {
        "name": "cursor-plugin",
        "description": "desc"
    }
    plugin_dir = create_plugin(tmp_path, manifest, in_cursor=True)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert result.valid
    assert result.plugin_name == "cursor-plugin"


def test_missing_plugin_json(validator, tmp_path):
    """Test behavior when plugin.json is completely missing."""
    pdir = tmp_path / "empty-plugin"
    pdir.mkdir()
    result = validator.validate_plugin_bundle(pdir)
    
    assert not result.valid
    assert any("Missing required plugin.json" in err for err in result.errors)


def test_invalid_json(validator, tmp_path):
    """Test behavior with malformed json."""
    pdir = tmp_path / "bad-json"
    pdir.mkdir()
    (pdir / "plugin.json").write_text("{ bad json")
    
    result = validator.validate_plugin_bundle(pdir)
    assert not result.valid
    assert any("Invalid JSON in plugin.json" in err for err in result.errors)


def test_root_not_object(validator, tmp_path):
    """Test behavior when root is a list, not an object."""
    pdir = tmp_path / "list-json"
    pdir.mkdir()
    (pdir / "plugin.json").write_text('["name", "description"]')
    
    result = validator.validate_plugin_bundle(pdir)
    assert not result.valid
    assert any("plugin.json root must be a JSON object" in err for err in result.errors)


def test_unknown_top_level_keys(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "unknownKey": "value"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert result.unknown_top_level_keys == ["unknownKey"]
    assert any("Unknown top-level key 'unknownKey'" in err for err in result.errors)


def test_invalid_description(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "   "
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("Field 'description' is required and must be a non-empty string" in err for err in result.errors)


def test_missing_logo_warning(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert result.valid
    assert any("Field 'logo' is missing" in warn for warn in result.warnings)
    assert not result.has_valid_logo


def test_invalid_logo_url(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "logo": "https://example.com/logo.png"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("must be a relative path inside the plugin directory" in err for err in result.errors)


def test_invalid_logo_absolute_path(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "logo": "/tmp/logo.png"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("must be a relative path inside the plugin directory" in err for err in result.errors)


def test_invalid_logo_extension(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "logo": "logo.gif"
    }
    plugin_dir = create_plugin(tmp_path, manifest, logo_name="logo.gif")
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("has unsupported extension '.gif'" in err for err in result.errors)


def test_logo_file_does_not_exist(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "logo": "missing.png"
    }
    plugin_dir = create_plugin(tmp_path, manifest)  # don't create the file
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("Logo file does not exist inside plugin bundle" in err for err in result.errors)


def test_suggested_prompts_not_list(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "suggestedPrompts": "just a string"
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("must be a list of 1..3 non-empty strings" in err for err in result.errors)


def test_suggested_prompts_length(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "suggestedPrompts": ["1", "2", "3", "4"]
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("must contain 1..3 items (got 4)" in err for err in result.errors)


def test_suggested_prompts_empty_string(validator, tmp_path):
    manifest = {
        "name": "plugin",
        "description": "desc",
        "suggestedPrompts": ["valid", "   "]
    }
    plugin_dir = create_plugin(tmp_path, manifest)
    result = validator.validate_plugin_bundle(plugin_dir)
    
    assert not result.valid
    assert any("Field 'suggestedPrompts[1]' must be a non-empty string" in err for err in result.errors)
    assert result.prompt_count == 1


def test_detect_global_name_collisions(validator, tmp_path):
    # Plugin 1: p1
    p1 = create_plugin(tmp_path / "p1", {"name": "shared-name", "description": "desc"})
    # Plugin 2: p2
    p2 = create_plugin(tmp_path / "p2", {"name": "shared-name", "description": "desc"})
    # Plugin 3: p3
    p3 = create_plugin(tmp_path / "p3", {"name": "unique-name", "description": "desc"})
    
    collisions = validator.detect_global_name_collisions([p1, p2, p3])
    
    assert "shared-name" in collisions
    assert set(collisions["shared-name"]) == {"my-plugin", "my-plugin"} # because create_plugin hardcodes 'my-plugin'

def test_detect_global_name_collisions_distinct(validator, tmp_path):
    p1 = tmp_path / "plugin1"
    p1.mkdir()
    (p1 / "plugin.json").write_text(json.dumps({"name": "shared-name"}))
    
    p2 = tmp_path / "plugin2"
    p2.mkdir()
    (p2 / "plugin.json").write_text(json.dumps({"name": "shared-name"}))
    
    p3 = tmp_path / "plugin3"
    p3.mkdir()
    (p3 / "plugin.json").write_text(json.dumps({"name": "unique-name"}))
    
    collisions = validator.detect_global_name_collisions([p1, p2, p3])
    
    assert "shared-name" in collisions
    assert set(collisions["shared-name"]) == {"plugin1", "plugin2"}
    assert "unique-name" not in collisions
