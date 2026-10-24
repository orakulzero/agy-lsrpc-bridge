"""Verification suite for agy-lsrpc-bridge v1.1.0 upgrades: strict MCP & plugin drift."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.client import LSRPCClient, detect_plugin_drift
from agy_lsrpc_bridge.validator import validate_mcp_config_strict, validate_plugin_bundle


def test_v1_1_validate_mcp_config_strict_requirements() -> None:
    """Verify validate_mcp_config_strict enforces timeout_ms and <=64-char identifiers."""
    # 1. Missing timeout_ms
    invalid_cfg_1 = {
        "mcpServers": {
            "my_srv": {
                "command": "python",
                "args": ["-m", "srv"],
            }
        }
    }
    valid, errors = validate_mcp_config_strict(invalid_cfg_1)
    assert valid is False
    assert any("timeout_ms" in e for e in errors)

    # 2. Overlong composite tool identifier (> 64 chars)
    # Prefix: mcp_my_srv_ (11 chars) + tool name 54 chars = 65 chars
    long_tool = "x" * 54
    invalid_cfg_2 = {
        "mcpServers": {
            "my_srv": {
                "command": "python",
                "timeout_ms": 10000,
                "tools": [long_tool],
            }
        }
    }
    valid, errors = validate_mcp_config_strict(invalid_cfg_2)
    assert valid is False
    assert any("exceeds 64 characters" in e for e in errors)

    # 3. Valid configuration
    valid_cfg = {
        "mcpServers": {
            "my_srv": {
                "command": "python",
                "timeout_ms": 15000,
                "tools": ["query", "fetch_status"],
            }
        }
    }
    valid, errors = validate_mcp_config_strict(valid_cfg)
    assert valid is True
    assert errors == []


def test_v1_1_validate_plugin_bundle_strict_mcp_mode(tmp_path: Path) -> None:
    """Verify validate_plugin_bundle respects strict_mcp flag for timeout and identifier bounds."""
    pdir = tmp_path / "test-plugin"
    pdir.mkdir(parents=True)
    (pdir / "plugin.json").write_text(
        json.dumps({
            "name": "test-plugin",
            "displayName": "Test Plugin",
            "description": "Validation test bundle",
            "version": "1.1.0",
        }),
        encoding="utf-8",
    )
    # MCP without timeout_ms
    (pdir / "mcp_config.json").write_text(
        json.dumps({
            "mcpServers": {
                "test-plugin-server": {
                    "command": "python",
                    "tools": ["status"],
                }
            }
        }),
        encoding="utf-8",
    )

    # In default (non-strict) mode, missing timeout is only a warning
    res_normal = validate_plugin_bundle(pdir, strict_mcp=False)
    assert res_normal["valid"] is True
    assert any("timeout_ms" in w for w in res_normal["warnings"])

    # In strict_mcp mode, missing timeout is an error
    res_strict = validate_plugin_bundle(pdir, strict_mcp=True)
    assert res_strict["valid"] is False
    assert any("timeout_ms" in e for e in res_strict["errors"])


def test_v1_1_detect_plugin_drift(tmp_path: Path) -> None:
    """Verify detect_plugin_drift identifies manifest version differences and missing plugins."""
    source_root = tmp_path / "source_repos"
    plugins_dir = tmp_path / "installed_plugins"
    source_root.mkdir(parents=True)
    plugins_dir.mkdir(parents=True)

    # Setup source repo with version 1.1.0
    src_alpha = source_root / "alpha-plugin"
    src_alpha.mkdir(parents=True)
    (src_alpha / "plugin.json").write_text(
        json.dumps({
            "name": "alpha-plugin",
            "version": "1.1.0",
            "description": "Source alpha",
        }),
        encoding="utf-8",
    )

    # Setup installed plugin with older version 1.0.0
    inst_alpha = plugins_dir / "alpha-plugin"
    inst_alpha.mkdir(parents=True)
    (inst_alpha / "plugin.json").write_text(
        json.dumps({
            "name": "alpha-plugin",
            "version": "1.0.0",
            "description": "Installed alpha",
        }),
        encoding="utf-8",
    )

    # Setup source repo with beta-plugin not installed
    src_beta = source_root / "beta-plugin"
    src_beta.mkdir(parents=True)
    (src_beta / "plugin.json").write_text(
        json.dumps({
            "name": "beta-plugin",
            "version": "1.0.0",
            "description": "Beta plugin",
        }),
        encoding="utf-8",
    )

    # Standalone function
    report = detect_plugin_drift(
        source_roots=[src_alpha, src_beta],
        plugins_dir=plugins_dir,
    )
    assert report["drift_detected"] is True
    assert len(report["drifted_plugins"]) == 1
    assert report["drifted_plugins"][0]["name"] == "alpha-plugin"
    assert report["drifted_plugins"][0]["source_version"] == "1.1.0"
    assert report["drifted_plugins"][0]["installed_version"] == "1.0.0"
    assert "beta-plugin" in report["missing_in_plugins_dir"]

    # Client method invocation
    client = LSRPCClient(config_root=tmp_path)
    client_report = client.detect_plugin_drift(
        source_roots=[src_alpha, src_beta],
        plugins_dir=plugins_dir,
    )
    assert client_report["drift_detected"] is True
    assert len(client_report["drifted_plugins"]) == 1
