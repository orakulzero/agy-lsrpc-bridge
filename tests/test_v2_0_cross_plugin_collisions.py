"""Tests for Antigravity v2.0.0 Cross-Plugin MCP Tool Collision and Fleet Schema Budget Auditor (REQ-LB-201).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List
import pytest

import agy_lsrpc_bridge

try:
    from agy_lsrpc_bridge import audit_cross_plugin_mcp_collisions
except ImportError:
    try:
        from agy_lsrpc_bridge.validator import audit_cross_plugin_mcp_collisions
    except ImportError:
        def audit_cross_plugin_mcp_collisions(*args: Any, **kwargs: Any) -> Any:
            from agy_lsrpc_bridge.validator import audit_cross_plugin_mcp_collisions as fn
            return fn(*args, **kwargs)


# ============================================================================
# Helpers: Sample Plugin MCP Config Fixtures
# ============================================================================


def _build_healthy_fleet_configs() -> Dict[str, Any]:
    """Construct a clean, collision-free multi-plugin configuration dictionary."""
    return {
        "agy-brain-memory": {
            "mcpServers": {
                "brain_memory": {
                    "tools": [
                        {"name": "search_brain", "description": "Search indexed steps.", "inputSchema": {"type": "object"}},
                        {"name": "analyze_health", "description": "Analyze database health.", "inputSchema": {"type": "object"}},
                    ]
                }
            }
        },
        "agy-doctor-mux": {
            "mcpServers": {
                "doctor_mux": {
                    "tools": [
                        {"name": "diagnose_desktop", "description": "Diagnose desktop health.", "inputSchema": {"type": "object"}},
                        {"name": "heal_worktree", "description": "Heal stale git worktree locks.", "inputSchema": {"type": "object"}},
                    ]
                }
            }
        },
        "agy-secret-shield": {
            "mcpServers": {
                "secret_shield": {
                    "tools": [
                        {"name": "scan_secrets", "description": "Scan AST for secrets.", "inputSchema": {"type": "object"}},
                    ]
                }
            }
        },
    }


# ============================================================================
# 1. Version and Re-export Tests (REQ-LB-201)
# ============================================================================


def test_v2_0_lsrpc_bridge_version_and_exports() -> None:
    """Verify package version is 2.0.0 and audit_cross_plugin_mcp_collisions is exported."""
    assert agy_lsrpc_bridge.__version__ == "2.0.0", "Package version must be bumped to 2.0.0"
    assert hasattr(agy_lsrpc_bridge, "audit_cross_plugin_mcp_collisions")
    all_symbols = getattr(agy_lsrpc_bridge, "__all__", [])
    assert "audit_cross_plugin_mcp_collisions" in all_symbols


# ============================================================================
# 2. Cross-Plugin MCP Collision & Fleet Budget Tests (REQ-LB-201)
# ============================================================================


def test_req201_audit_cross_plugin_mcp_collisions_healthy_fleet() -> None:
    """REQ-LB-201: Collision-free plugin fleet within budget returns valid=True and has_collisions=False."""
    configs = _build_healthy_fleet_configs()
    report = audit_cross_plugin_mcp_collisions(plugin_configs=configs)
    assert isinstance(report, dict)
    assert report.get("valid") is True
    assert report.get("has_collisions") is False
    assert report.get("within_fleet_budget") is True
    assert report.get("collisions") == []
    assert len(report.get("plugins_audited", [])) == 3
    assert report.get("total_tools") == 5


def test_req201_audit_cross_plugin_mcp_collisions_detects_tool_name_clash() -> None:
    """REQ-LB-201: Detects colliding tool names defined across distinct plugins."""
    clashing_configs = _build_healthy_fleet_configs()
    # Add colliding tool 'scan_secrets' to doctor_mux
    clashing_configs["agy-doctor-mux"]["mcpServers"]["doctor_mux"]["tools"].append(
        {"name": "scan_secrets", "description": "Duplicate scanner.", "inputSchema": {"type": "object"}}
    )
    report = audit_cross_plugin_mcp_collisions(plugin_configs=clashing_configs)
    assert report.get("valid") is False
    assert report.get("has_collisions") is True
    collisions = report.get("collisions", [])
    assert len(collisions) >= 1
    clash_tool_names = [c["tool_name"] if isinstance(c, dict) else c for c in collisions]
    assert "scan_secrets" in clash_tool_names


def test_req201_audit_cross_plugin_mcp_collisions_composite_name_clash() -> None:
    """REQ-LB-201: Detects composite Antigravity collisions ('mcp_<server>_<tool>')."""
    composite_clash = {
        "plugin-alpha": {
            "mcpServers": {
                "shared_srv": {
                    "tools": [{"name": "inspect", "description": "Alpha inspect", "inputSchema": {"type": "object"}}]
                }
            }
        },
        "plugin-beta": {
            "mcpServers": {
                "shared_srv": {
                    "tools": [{"name": "inspect", "description": "Beta inspect", "inputSchema": {"type": "object"}}]
                }
            }
        },
    }
    report = audit_cross_plugin_mcp_collisions(plugin_configs=composite_clash)
    assert report.get("has_collisions") is True
    assert report.get("valid") is False


def test_req201_audit_cross_plugin_mcp_collisions_overlong_name_exceeds_64_chars() -> None:
    """REQ-LB-201: Flags tool names or composite names exceeding 64 characters."""
    configs = {
        "plugin-audit": {
            "mcpServers": {
                "audit_server": {
                    "tools": [
                        {
                            "name": "a_tool_with_an_unnecessarily_verbose_name_that_exceeds_sixty_four_characters_long",
                            "description": "Too long",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                }
            }
        }
    }
    report = audit_cross_plugin_mcp_collisions(plugin_configs=configs)
    assert report.get("valid") is False
    overlong = report.get("overlong_tools", [])
    assert len(overlong) >= 1


def test_req201_audit_cross_plugin_mcp_collisions_fleet_budget_exceeded() -> None:
    """REQ-LB-201: Flags fleet when aggregate schema tokens exceed fleet_token_budget."""
    configs = _build_healthy_fleet_configs()
    # Artificially low budget: 200 tokens
    report = audit_cross_plugin_mcp_collisions(plugin_configs=configs, fleet_token_budget=200)
    assert report.get("within_fleet_budget") is False
    assert report.get("valid") is False
    assert report.get("fleet_estimated_tokens", 0) > 200
    assert len(report.get("recommendations", [])) >= 1


def test_req201_audit_cross_plugin_mcp_collisions_per_plugin_budget_flagging() -> None:
    """REQ-LB-201: Flags individual plugins exceeding per_plugin_token_budget."""
    verbose_plugin = {
        "verbose-plugin": {
            "mcpServers": {
                "verbose_server": {
                    "tools": [
                        {
                            "name": f"verbose_tool_{i}",
                            "description": "A very long detailed verbose description " * 10,
                            "inputSchema": {
                                "type": "object",
                                "properties": {f"param_{j}": {"type": "string", "description": "param doc"} for j in range(10)},
                            },
                        }
                        for i in range(5)
                    ]
                }
            }
        }
    }
    report = audit_cross_plugin_mcp_collisions(plugin_configs=verbose_plugin, per_plugin_token_budget=500)
    over_budget = report.get("over_budget_plugins", [])
    assert len(over_budget) >= 1
    flagged = [p["plugin"] if isinstance(p, dict) else p for p in over_budget]
    assert "verbose-plugin" in flagged


def test_req201_audit_cross_plugin_mcp_collisions_directory_discovery(tmp_path: Path) -> None:
    """REQ-LB-201: Discovers plugins with mcp_config.json in subdirectories."""
    # Plugin A
    p_a = tmp_path / "plugin-a"
    p_a.mkdir()
    (p_a / "mcp_config.json").write_text(json.dumps({
        "mcpServers": {"srv_a": {"tools": [{"name": "tool_a", "inputSchema": {"type": "object"}}]}}
    }), encoding="utf-8")

    # Plugin B
    p_b = tmp_path / "plugin-b"
    p_b.mkdir()
    (p_b / "mcp_config.json").write_text(json.dumps({
        "mcpServers": {"srv_b": {"tools": [{"name": "tool_b", "inputSchema": {"type": "object"}}]}}
    }), encoding="utf-8")

    report = audit_cross_plugin_mcp_collisions(plugins_dir=tmp_path)
    assert report.get("valid") is True
    assert len(report.get("plugins_audited", [])) == 2


def test_req201_audit_cross_plugin_mcp_collisions_empty_and_corrupt_configs(tmp_path: Path) -> None:
    """REQ-LB-201: Handles empty plugins directory and malformed JSON files gracefully."""
    # Empty dir
    empty_report = audit_cross_plugin_mcp_collisions(plugins_dir=tmp_path)
    assert isinstance(empty_report, dict)
    assert empty_report.get("total_tools") == 0

    # Corrupt config
    p_bad = tmp_path / "bad-plugin"
    p_bad.mkdir()
    (p_bad / "mcp_config.json").write_text("NOT_JSON_DATA", encoding="utf-8")
    corrupt_report = audit_cross_plugin_mcp_collisions(plugins_dir=tmp_path)
    assert isinstance(corrupt_report, dict)


def test_req201_audit_cross_plugin_mcp_collisions_generates_compaction_recommendation() -> None:
    """REQ-LB-201: Over-budget fleet generates recommendations for schema compaction."""
    configs = _build_healthy_fleet_configs()
    report = audit_cross_plugin_mcp_collisions(plugin_configs=configs, fleet_token_budget=50)
    recs = report.get("recommendations", [])
    assert len(recs) >= 1
    assert any("compact" in r.lower() or "budget" in r.lower() or "token" in r.lower() for r in recs)


def test_req201_audit_cross_plugin_mcp_collisions_strictly_ignores_google_flow_video() -> None:
    """REQ-LB-201: Out-of-scope google-flow-video is strictly skipped during audit."""
    configs = _build_healthy_fleet_configs()
    configs["google-flow-video"] = {
        "mcpServers": {
            "flow_server": {
                "tools": [
                    # Identical tool name to brain-memory 'search_brain', but must be ignored
                    {"name": "search_brain", "description": "Flow tool", "inputSchema": {"type": "object"}},
                ]
            }
        }
    }
    report = audit_cross_plugin_mcp_collisions(plugin_configs=configs)
    # Since google-flow-video is ignored, no collision should be flagged on 'search_brain'
    assert report.get("has_collisions") is False
    assert "google-flow-video" not in report.get("plugins_audited", [])


def test_req201_audit_cross_plugin_mcp_collisions_custom_budgets() -> None:
    """REQ-LB-201: Custom fleet_token_budget and per_plugin_token_budget are respected."""
    configs = _build_healthy_fleet_configs()
    report = audit_cross_plugin_mcp_collisions(
        plugin_configs=configs,
        fleet_token_budget=30000,
        per_plugin_token_budget=10000,
    )
    assert report.get("fleet_token_budget") == 30000


def test_req201_audit_cross_plugin_mcp_collisions_report_schema() -> None:
    """REQ-LB-201: Validates that all required schema keys exist in the output dictionary."""
    report = audit_cross_plugin_mcp_collisions(plugin_configs=_build_healthy_fleet_configs())
    required_keys = [
        "valid",
        "plugins_audited",
        "total_tools",
        "fleet_estimated_tokens",
        "fleet_token_budget",
        "within_fleet_budget",
        "collisions",
        "has_collisions",
        "over_budget_plugins",
        "overlong_tools",
        "recommendations",
    ]
    for key in required_keys:
        assert key in report, f"Missing required key '{key}' in audit report"
