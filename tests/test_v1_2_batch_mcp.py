"""Verification suite for agy-lsrpc-bridge v1.2.0: batch state manager and MCP token budget."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge import (
    LSRPCClient,
    __version__,
    analyze_mcp_token_budget,
    audit_git_repository,
)


def _create_sample_plugin_environment(tmp_path: Path) -> Path:
    """Create a mock plugins directory and config.json inside tmp_path."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Plugin 1: dir matches name
    p1 = plugins_dir / "alpha-plugin"
    p1.mkdir(parents=True, exist_ok=True)
    (p1 / "plugin.json").write_text(
        json.dumps({
            "name": "alpha-plugin",
            "displayName": "Alpha Plugin",
            "description": "Alpha test plugin",
            "version": "1.2.0",
            "disabled": False,
        }),
        encoding="utf-8",
    )

    # Plugin 2: dir is a hashed id, name is different
    p2 = plugins_dir / "dir-beta-hash-123"
    p2.mkdir(parents=True, exist_ok=True)
    (p2 / "plugin.json").write_text(
        json.dumps({
            "name": "beta-manifest-name",
            "displayName": "Beta Plugin",
            "description": "Beta test plugin",
            "version": "1.2.0",
            "disabled": True,
        }),
        encoding="utf-8",
    )

    # Plugin 3: another plugin
    p3 = plugins_dir / "gamma-plugin"
    p3.mkdir(parents=True, exist_ok=True)
    (p3 / "plugin.json").write_text(
        json.dumps({
            "name": "gamma-plugin",
            "displayName": "Gamma Plugin",
            "description": "Gamma test plugin",
            "version": "1.2.0",
            "disabled": False,
        }),
        encoding="utf-8",
    )

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({
            "userSettings": {"theme": "dark"},
            "plugins": {
                "alpha-plugin": {"enabled": True},
                "dir-beta-hash-123": {"enabled": False},
                "gamma-plugin": {"enabled": True},
            },
        }),
        encoding="utf-8",
    )

    return tmp_path


def test_v1_2_batch_set_plugin_states_all_success(tmp_path: Path) -> None:
    """Verify batch_set_plugin_states successfully mutates states with dict and sequence inputs."""
    cfg_root = _create_sample_plugin_environment(tmp_path)
    rpc_calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def mock_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        endpoint = url.rsplit("/", 1)[-1]
        rpc_calls.append((endpoint, json_body))
        return {}

    client = LSRPCClient(
        address="127.0.0.1:42100",
        config_root=cfg_root,
        transport=mock_transport,
    )

    # Apply dict batch: disable alpha, enable beta
    res = client.batch_set_plugin_states(
        {
            "alpha-plugin": False,
            "dir-beta-hash-123": True,
        },
        rollback_on_error=True,
    )

    assert res["success"] is True
    assert res["rolled_back"] is False
    assert res["error"] is None
    assert len(res["applied"]) == 2

    # Check applied entries
    assert res["applied"][0]["dir"] == "alpha-plugin"
    assert res["applied"][0]["enabled"] is False
    assert res["applied"][0]["previous_enabled"] is True

    assert res["applied"][1]["dir"] == "dir-beta-hash-123"
    assert res["applied"][1]["enabled"] is True
    assert res["applied"][1]["previous_enabled"] is False

    # Check disk state in config.json
    cfg = json.loads((cfg_root / "config.json").read_text(encoding="utf-8"))
    assert cfg["plugins"]["alpha-plugin"]["enabled"] is False
    assert cfg["plugins"]["dir-beta-hash-123"]["enabled"] is True
    assert cfg["userSettings"]["theme"] == "dark"

    # Check sequence input format
    res_seq = client.batch_set_plugin_states(
        [("gamma-plugin", False)],
        rollback_on_error=True,
    )
    assert res_seq["success"] is True
    cfg_seq = json.loads((cfg_root / "config.json").read_text(encoding="utf-8"))
    assert cfg_seq["plugins"]["gamma-plugin"]["enabled"] is False


def test_v1_2_batch_set_plugin_states_rollback_on_error(tmp_path: Path) -> None:
    """Verify batch_set_plugin_states restores prior mutations in reverse order when rollback_on_error=True."""
    cfg_root = _create_sample_plugin_environment(tmp_path)
    rpc_calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def mock_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        endpoint = url.rsplit("/", 1)[-1]
        rpc_calls.append((endpoint, json_body))
        # Simulate RPC failure when mutating gamma-plugin
        if endpoint == "JetboxWriteState" and json_body:
            plugins = json_body.get("userConfig", {}).get("plugins", {})
            if "gamma-plugin" in plugins:
                raise RuntimeError("Simulated JetboxWriteState RPC failure for gamma-plugin")
        return {}

    client = LSRPCClient(
        address="127.0.0.1:42100",
        config_root=cfg_root,
        transport=mock_transport,
    )

    # Initial states: alpha is True, beta is False, gamma is True
    # Batch tries: alpha -> False (succeeds), gamma -> False (fails with RuntimeError)
    res = client.batch_set_plugin_states(
        [
            ("alpha-plugin", False),
            ("gamma-plugin", False),
        ],
        rollback_on_error=True,
    )

    assert res["success"] is False
    assert res["rolled_back"] is True
    assert "Simulated JetboxWriteState RPC failure" in str(res["error"])

    # Verify rollback on disk: alpha-plugin should be restored to its initial True state
    cfg = json.loads((cfg_root / "config.json").read_text(encoding="utf-8"))
    assert cfg["plugins"]["alpha-plugin"]["enabled"] is True
    assert cfg["plugins"]["gamma-plugin"]["enabled"] is True


def test_v1_2_batch_set_plugin_states_partial_success_no_rollback(tmp_path: Path) -> None:
    """Verify batch_set_plugin_states applies partial mutations without rollback when rollback_on_error=False."""
    cfg_root = _create_sample_plugin_environment(tmp_path)

    client = LSRPCClient(
        address="127.0.0.1:42100",
        config_root=cfg_root,
    )

    # Batch has 3 items:
    # 1. alpha-plugin -> False (valid)
    # 2. non-existent-plugin -> True (invalid directory)
    # 3. gamma-plugin -> False (valid)
    res = client.batch_set_plugin_states(
        [
            ("alpha-plugin", False),
            ("non-existent-plugin", True),
            ("gamma-plugin", False),
        ],
        rollback_on_error=False,
    )

    assert res["success"] is False
    assert res["rolled_back"] is False
    assert res["error"] is not None
    assert "non-existent-plugin" in res["error"]

    # Both alpha-plugin and gamma-plugin should be mutated on disk
    assert len(res["applied"]) == 2
    cfg = json.loads((cfg_root / "config.json").read_text(encoding="utf-8"))
    assert cfg["plugins"]["alpha-plugin"]["enabled"] is False
    assert cfg["plugins"]["gamma-plugin"]["enabled"] is False


def test_v1_2_batch_set_plugin_states_enforces_directory_keyed_mutation(tmp_path: Path) -> None:
    """Verify batch_set_plugin_states rejects manifest names and requires true install directory."""
    cfg_root = _create_sample_plugin_environment(tmp_path)

    client = LSRPCClient(
        address="127.0.0.1:42100",
        config_root=cfg_root,
    )

    # Attempting to mutate by manifest name 'beta-manifest-name' instead of 'dir-beta-hash-123'
    res = client.batch_set_plugin_states(
        {"beta-manifest-name": True},
        rollback_on_error=True,
    )

    assert res["success"] is False
    assert res["rolled_back"] is True
    assert "manifest name" in str(res["error"]).lower()
    assert "dir-beta-hash-123" in str(res["error"])

    # Attempting with empty dict returns success
    empty_res = client.batch_set_plugin_states({})
    assert empty_res["success"] is True
    assert empty_res["applied"] == []

    # Invalid input type raises TypeError
    with pytest.raises(TypeError):
        client.batch_set_plugin_states("invalid_string_input")  # type: ignore


def test_v1_2_mcp_token_budget_normal_load(tmp_path: Path) -> None:
    """Verify analyze_mcp_token_budget calculates token footprint and stays within budget under normal load."""
    cfg = {
        "mcpServers": {
            "analysis_srv": {
                "command": "python",
                "timeout_ms": 15000,
                "tools": [
                    {
                        "name": "analyze_repo",
                        "description": "Analyze repository files and dependencies.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    },
                    {
                        "name": "run_linter",
                        "description": "Execute static linting checks.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"fix": {"type": "boolean"}},
                        },
                    },
                ],
            },
            "build_srv": {
                "command": "node",
                "timeout_ms": 10000,
                "tools": {
                    "compile": {"description": "Compile target bundle."},
                },
            },
        }
    }

    # Test from dictionary
    report = analyze_mcp_token_budget(cfg, max_token_budget=8000)
    assert report["within_budget"] is True
    assert report["total_estimated_tokens"] > 0
    assert report["budget_limit"] == 8000
    assert "analysis_srv" in report["servers"]
    assert "build_srv" in report["servers"]

    analysis_info = report["servers"]["analysis_srv"]
    assert analysis_info["tool_count"] == 2
    assert analysis_info["within_budget"] is True
    assert analysis_info["exceeds_64_char_limit"] is False
    assert "analyze_repo" in analysis_info["tools"]

    # Test from file Path
    cfg_file = tmp_path / "mcp_config.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    report_file = analyze_mcp_token_budget(cfg_file, max_token_budget=8000)
    assert report_file["total_estimated_tokens"] == report["total_estimated_tokens"]

    # Test from JSON string
    report_str = analyze_mcp_token_budget(json.dumps(cfg), max_token_budget=8000)
    assert report_str["total_estimated_tokens"] == report["total_estimated_tokens"]


def test_v1_2_mcp_token_budget_exceeded_triggers_recommendations() -> None:
    """Verify analyze_mcp_token_budget flags budget overflow and generates optimization recommendations."""
    cfg = {
        "mcpServers": {
            "heavy_server": {
                "command": "python",
                "timeout_ms": 10000,
                "tools": [
                    {
                        "name": "heavy_query",
                        "description": "A" * 600,  # Verbose description > 500 chars
                        "inputSchema": {
                            "type": "object",
                            "properties": {f"field_{i}": {"type": "string"} for i in range(25)},
                        },
                    }
                ],
            }
        }
    }

    # Strict low budget to force within_budget=False
    report = analyze_mcp_token_budget(cfg, max_token_budget=100)
    assert report["within_budget"] is False
    assert report["total_estimated_tokens"] > 100
    assert len(report["recommendations"]) >= 1

    # Check actionable advice
    rec_text = " ".join(report["recommendations"])
    assert "exceeds maximum budget" in rec_text
    assert "heavy_query" in rec_text or "heavy_server" in rec_text


def test_v1_2_mcp_token_budget_exceeds_64_char_limit() -> None:
    """Verify analyze_mcp_token_budget flags composite tool identifiers exceeding 64 characters."""
    long_tool_name = "t" * 55
    # Composite: mcp_srv_ + 55 chars = 63 chars (<= 64) -> add 5 more chars to exceed 64
    overlong_tool = "t" * 60
    cfg = {
        "mcpServers": {
            "srv": {
                "command": "python",
                "timeout_ms": 5000,
                "tools": [overlong_tool],
            }
        }
    }

    report = analyze_mcp_token_budget(cfg, max_token_budget=8000)
    srv_info = report["servers"]["srv"]
    assert srv_info["exceeds_64_char_limit"] is True
    assert any("64" in rec for rec in report["recommendations"])


def test_v1_2_mcp_token_budget_empty_and_malformed_handling(tmp_path: Path) -> None:
    """Verify analyze_mcp_token_budget handles empty, invalid, and malformed inputs safely."""
    # 1. None
    res_none = analyze_mcp_token_budget(None)  # type: ignore
    assert res_none["total_estimated_tokens"] == 0
    assert res_none["within_budget"] is True
    assert res_none["servers"] == {}

    # 2. Empty dict
    res_empty = analyze_mcp_token_budget({})
    assert res_empty["total_estimated_tokens"] == 0
    assert res_empty["within_budget"] is True

    # 3. Empty string
    res_empty_str = analyze_mcp_token_budget("   ")
    assert res_empty_str["total_estimated_tokens"] == 0
    assert res_empty_str["within_budget"] is True

    # 4. Malformed JSON string
    res_bad_json = analyze_mcp_token_budget("{unclosed json")
    assert res_bad_json["total_estimated_tokens"] == 0
    assert res_bad_json["within_budget"] is False
    assert any("Malformed JSON" in r for r in res_bad_json["recommendations"])

    # 5. Non-existent file Path
    res_missing_file = analyze_mcp_token_budget(tmp_path / "does_not_exist.json")
    assert res_missing_file["total_estimated_tokens"] == 0
    assert res_missing_file["within_budget"] is False
    assert any("not found" in r for r in res_missing_file["recommendations"])

    # 6. Invalid non-dict object
    res_bad_type = analyze_mcp_token_budget(42)  # type: ignore
    assert res_bad_type["within_budget"] is False
    assert any("Invalid configuration type" in r for r in res_bad_type["recommendations"])


def test_v1_2_oss_compliance_and_exports() -> None:
    """Verify package version, exported primitives, and 0 OSS audit violations."""
    assert __version__ in ("1.2.0", "2.0.0")
    assert callable(analyze_mcp_token_budget)
    assert hasattr(LSRPCClient, "batch_set_plugin_states")

    # 5-Gate Git OSS release audit check on repository root
    audit_report = audit_git_repository(REPO_ROOT)
    assert audit_report["passed"] is True, f"OSS audit violations found: {audit_report['violations']}"
    assert len(audit_report["violations"]) == 0
