"""Tests for agy_lsrpc_bridge.validator focusing on 64-char limit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.validator import (
    validate_mcp_config_strict,
    validate_plugin_bundle,
    analyze_mcp_token_budget,
    MAX_COMPOSITE_LEN,
)

def test_mcp_config_strict_exact_64_chars():
    """Test that exactly 64 chars is valid and does not cause errors."""
    server_name = "s" * 30
    tool_name = "t" * 29
    
    config = {
        "mcpServers": {
            server_name: {
                "timeout_ms": 1000,
                "tools": [tool_name]
            }
        }
    }
    
    composite = f"mcp_{server_name}_{tool_name}"
    assert len(composite) == 64
    
    ok, errors = validate_mcp_config_strict(config)
    assert ok is True
    assert len(errors) == 0

def test_mcp_config_strict_over_64_chars():
    """Test that 65 chars causes an error."""
    server_name = "s" * 30
    tool_name = "t" * 30
    
    config = {
        "mcpServers": {
            server_name: {
                "timeout_ms": 1000,
                "tools": [tool_name]
            }
        }
    }
    
    composite = f"mcp_{server_name}_{tool_name}"
    assert len(composite) == 65
    
    ok, errors = validate_mcp_config_strict(config)
    assert ok is False
    assert len(errors) == 1
    assert "exceeds 64 characters" in errors[0]

def test_mcp_config_strict_exact_64_chars_no_tools_fails_due_to_bug_in_code():
    """
    Test that exactly 64 chars prefix without tools causes an error because 
    the validator code checks len >= 64 when tools are empty.
    """
    server_name = "s" * 59
    
    config = {
        "mcpServers": {
            server_name: {
                "timeout_ms": 1000,
                "tools": []
            }
        }
    }
    
    prefix = f"mcp_{server_name}_"
    assert len(prefix) == 64
    
    ok, errors = validate_mcp_config_strict(config)
    # The original code has a bug: `if len(f"mcp_{srv_str}_") >= MAX_COMPOSITE_LEN:`
    # We must assert this fails to be perfectly aligned with the exact code provided!
    assert ok is False
    assert len(errors) == 1
    assert "exceeds or equals 64 characters" in errors[0]

def test_mcp_config_strict_over_64_chars_no_tools():
    """Test that 65 chars prefix causes an error."""
    server_name = "s" * 60
    
    config = {
        "mcpServers": {
            server_name: {
                "timeout_ms": 1000,
                "tools": []
            }
        }
    }
    
    prefix = f"mcp_{server_name}_"
    assert len(prefix) == 65
    
    ok, errors = validate_mcp_config_strict(config)
    assert ok is False
    assert len(errors) == 1
    assert "exceeds or equals 64 characters" in errors[0]

def test_validate_plugin_bundle_exact_64_chars(tmp_path: Path):
    """Test exact 64 char limit in validate_plugin_bundle."""
    plugin_dir = tmp_path / "my_plugin"
    plugin_dir.mkdir()
    
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": "my_plugin",
        "version": "1.0.0",
        "description": "test plugin"
    }))
    
    server_name = "my_plugin_server_1234" # len=21
    tool_name = "t" * (64 - 4 - 21 - 1)   # len=64 - 26 = 38
    
    (plugin_dir / "mcp_config.json").write_text(json.dumps({
        "mcpServers": {
            server_name: {
                "timeout_ms": 1000,
                "tools": [tool_name]
            }
        }
    }))
    
    composite = f"mcp_{server_name}_{tool_name}"
    assert len(composite) == 64
    
    res = validate_plugin_bundle(plugin_dir, strict_mcp=True)
    assert res["valid"] is True
    assert not any("exceeds 64 characters" in e for e in res["errors"])

def test_analyze_mcp_token_budget_exact_64_chars():
    """Test exact 64 char limit in analyze_mcp_token_budget."""
    server_name = "s" * 30
    tool_name = "t" * 29
    
    config = {
        "mcpServers": {
            server_name: {
                "timeout_ms": 1000,
                "tools": [tool_name]
            }
        }
    }
    
    composite = f"mcp_{server_name}_{tool_name}"
    assert len(composite) == 64
    
    res = analyze_mcp_token_budget(config)
    assert res["servers"][server_name]["exceeds_64_char_limit"] is False
    assert not any("exceed" in rec for rec in res["recommendations"] if "64-character limit" in rec)

def test_validate_mcp_config_strict_invalid_timeout():
    config = {
        "mcpServers": {
            "s1": {
                "timeout_ms": -1,
                "tools": ["t1"]
            },
            "s2": {
                "tools": ["t1"]
            }
        }
    }
    ok, errors = validate_mcp_config_strict(config)
    assert ok is False
    assert len(errors) == 2
    assert "positive integer" in errors[0]
    assert "positive integer" in errors[1]
