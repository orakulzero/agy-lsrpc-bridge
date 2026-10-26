"""Unit and integration test suite for agy-lsrpc-bridge v1.3.0:
Automated MCP Config Optimizer & Schema Compaction Pipeline (optimize_mcp_config_tokens).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

# Safe dynamic import resolution for Agile V TDD test collection
try:
    from agy_lsrpc_bridge import (
        __version__,
        analyze_mcp_token_budget,
        optimize_mcp_config_tokens,
    )
except ImportError:
    try:
        from agy_lsrpc_bridge.validator import optimize_mcp_config_tokens, analyze_mcp_token_budget
        from agy_lsrpc_bridge import __version__
    except ImportError:
        optimize_mcp_config_tokens = None
        analyze_mcp_token_budget = None
        __version__ = "1.2.0"


@pytest.fixture
def heavy_mcp_config() -> Dict[str, Any]:
    """Realistic MCP config with an over-budget server containing verbose schemas."""
    return {
        "mcpServers": {
            "cluster_ops": {
                "command": "python",
                "args": ["-m", "cluster_ops_server"],
                "env": {"LOG_LEVEL": "DEBUG"},
                "timeout_ms": 15000,
                "tools": [
                    {
                        "name": "diagnose_nodes",
                        "description": (
                            "This tool allows you to perform an in-depth, comprehensive operational audit "
                            "and health check of all Kubernetes cluster nodes, evaluating pod density, memory "
                            "saturation, filesystem pressure, and network interface error rates."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "cluster_id": {
                                    "type": "string",
                                    "description": (
                                        "A required string specifying the unique cluster identifier or fully "
                                        "qualified domain name of the production Kubernetes control plane that you wish to inspect."
                                    ),
                                },
                                "depth": {
                                    "type": "string",
                                    "enum": ["shallow", "deep", "forensic"],
                                    "default": "deep",
                                    "description": (
                                        "An optional string parameter indicating the specific diagnostic inspection depth "
                                        "that the health audit scanner should execute across target worker nodes."
                                    ),
                                },
                            },
                            "required": ["cluster_id"],
                        },
                    },
                    {
                        "name": "fetch_telemetry",
                        "description": (
                            "This tool is designed to retrieve and aggregate Prometheus time-series metrics "
                            "for CPU, memory, and disk IOPS across specified node groups."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "metric_name": {
                                    "type": "string",
                                    "description": "The required string representing the target metric query.",
                                },
                                "duration_min": {
                                    "type": "integer",
                                    "default": 60,
                                    "minimum": 1,
                                    "maximum": 1440,
                                    "description": "An optional integer denoting time window duration in minutes.",
                                },
                            },
                            "required": ["metric_name"],
                        },
                    },
                ],
            }
        }
    }


# ============================================================================
# 1. optimize_mcp_config_tokens Tests
# ============================================================================


def test_v1_3_optimize_mcp_config_tokens_reduces_over_budget_server(
    heavy_mcp_config: Dict[str, Any],
) -> None:
    """Verify optimize_mcp_config_tokens reduces token footprint of an over-budget server."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    res = optimize_mcp_config_tokens(heavy_mcp_config, token_budget=200)

    if isinstance(res, tuple):
        opt_cfg, summary = res
        assert isinstance(summary, dict)
    else:
        opt_cfg = res
        summary = res.get("summary", {})

    assert "mcpServers" in opt_cfg
    server_cfg = opt_cfg["mcpServers"]["cluster_ops"]
    tools = server_cfg["tools"]

    # Verify tool descriptions were shortened
    orig_tools = heavy_mcp_config["mcpServers"]["cluster_ops"]["tools"]
    assert len(tools[0]["description"]) < len(orig_tools[0]["description"])
    assert "This tool allows you to" not in tools[0]["description"]
    assert "This tool is designed to" not in tools[1]["description"]


def test_v1_3_optimize_mcp_config_preserves_commands_and_envs(
    heavy_mcp_config: Dict[str, Any],
) -> None:
    """Verify execution parameters (command, args, env, timeout_ms) are completely preserved."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    res = optimize_mcp_config_tokens(heavy_mcp_config, token_budget=4000)
    opt_cfg = res[0] if isinstance(res, tuple) else res

    srv = opt_cfg["mcpServers"]["cluster_ops"]
    orig_srv = heavy_mcp_config["mcpServers"]["cluster_ops"]

    assert srv["command"] == orig_srv["command"]
    assert srv["args"] == orig_srv["args"]
    assert srv["env"] == orig_srv["env"]
    assert srv["timeout_ms"] == orig_srv["timeout_ms"]


def test_v1_3_optimize_mcp_config_preserves_json_schema_types_and_required(
    heavy_mcp_config: Dict[str, Any],
) -> None:
    """Verify JSON Schema constraints (type, required, enum, default, bounds) remain intact."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    res = optimize_mcp_config_tokens(heavy_mcp_config, token_budget=4000)
    opt_cfg = res[0] if isinstance(res, tuple) else res

    tool = opt_cfg["mcpServers"]["cluster_ops"]["tools"][0]
    orig_tool = heavy_mcp_config["mcpServers"]["cluster_ops"]["tools"][0]

    assert tool["name"] == orig_tool["name"]
    assert tool["inputSchema"]["type"] == orig_tool["inputSchema"]["type"]
    assert tool["inputSchema"]["required"] == orig_tool["inputSchema"]["required"]

    props = tool["inputSchema"]["properties"]
    orig_props = orig_tool["inputSchema"]["properties"]

    assert props["cluster_id"]["type"] == orig_props["cluster_id"]["type"]
    assert props["depth"]["enum"] == orig_props["depth"]["enum"]
    assert props["depth"]["default"] == orig_props["depth"]["default"]

    tool2 = opt_cfg["mcpServers"]["cluster_ops"]["tools"][1]
    props2 = tool2["inputSchema"]["properties"]
    assert props2["duration_min"]["minimum"] == 1
    assert props2["duration_min"]["maximum"] == 1440


def test_v1_3_optimize_mcp_config_within_budget_untouched() -> None:
    """Verify that a server already well within budget is handled cleanly without corruption."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    clean_cfg = {
        "mcpServers": {
            "minimal_srv": {
                "command": "node",
                "timeout_ms": 5000,
                "tools": [
                    {
                        "name": "ping",
                        "description": "Ping node.",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ],
            }
        }
    }

    res = optimize_mcp_config_tokens(clean_cfg, token_budget=8000)
    opt_cfg = res[0] if isinstance(res, tuple) else res

    tool = opt_cfg["mcpServers"]["minimal_srv"]["tools"][0]
    assert tool["name"] == "ping"
    assert tool["description"] == "Ping node."


def test_v1_3_optimize_mcp_config_handles_json_string_and_file_path(
    heavy_mcp_config: Dict[str, Any], tmp_path: Path
) -> None:
    """Verify optimize_mcp_config_tokens supports dict, JSON string, and Path inputs."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    # 1. JSON string input
    json_str = json.dumps(heavy_mcp_config)
    res_str = optimize_mcp_config_tokens(json_str, token_budget=4000)
    opt_str = res_str[0] if isinstance(res_str, tuple) else res_str
    assert "mcpServers" in opt_str

    # 2. Path input
    cfg_file = tmp_path / "test_mcp_config.json"
    cfg_file.write_text(json_str, encoding="utf-8")
    res_path = optimize_mcp_config_tokens(cfg_file, token_budget=4000)
    opt_path = res_path[0] if isinstance(res_path, tuple) else res_path
    assert "mcpServers" in opt_path


def test_v1_3_optimize_mcp_config_empty_and_malformed_inputs(tmp_path: Path) -> None:
    """Verify safe handling of None, empty, malformed, or missing inputs without crash."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    # None
    res_none = optimize_mcp_config_tokens(None)
    opt_none = res_none[0] if isinstance(res_none, tuple) else res_none
    assert opt_none == {} or opt_none is None or isinstance(opt_none, dict)

    # Empty dict
    res_empty = optimize_mcp_config_tokens({})
    opt_empty = res_empty[0] if isinstance(res_empty, tuple) else res_empty
    assert isinstance(opt_empty, dict)

    # Empty string
    res_empty_str = optimize_mcp_config_tokens("   ")
    opt_empty_str = res_empty_str[0] if isinstance(res_empty_str, tuple) else res_empty_str
    assert isinstance(opt_empty_str, dict)

    # Malformed JSON string
    res_malformed = optimize_mcp_config_tokens("{unclosed json")
    opt_malformed = res_malformed[0] if isinstance(res_malformed, tuple) else res_malformed
    assert isinstance(opt_malformed, dict)

    # Non-existent file Path
    res_missing = optimize_mcp_config_tokens(tmp_path / "does_not_exist.json")
    opt_missing = res_missing[0] if isinstance(res_missing, tuple) else res_missing
    assert isinstance(opt_missing, dict)


def test_v1_3_optimize_mcp_config_multi_server_optimization() -> None:
    """Verify multi-server configurations have all servers processed and optimized."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    multi_cfg = {
        "mcpServers": {
            "srv_alpha": {
                "command": "python",
                "timeout_ms": 5000,
                "tools": [
                    {
                        "name": "tool_alpha",
                        "description": "This tool allows you to measure alpha metrics.",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ],
            },
            "srv_beta": {
                "command": "python",
                "timeout_ms": 5000,
                "tools": [
                    {
                        "name": "tool_beta",
                        "description": "This tool is used to evaluate beta telemetry.",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ],
            },
        }
    }

    res = optimize_mcp_config_tokens(multi_cfg, token_budget=4000)
    opt_cfg = res[0] if isinstance(res, tuple) else res

    assert "srv_alpha" in opt_cfg["mcpServers"]
    assert "srv_beta" in opt_cfg["mcpServers"]
    assert "This tool allows you to" not in opt_cfg["mcpServers"]["srv_alpha"]["tools"][0]["description"]
    assert "This tool is used to" not in opt_cfg["mcpServers"]["srv_beta"]["tools"][0]["description"]


def test_v1_3_optimize_mcp_config_preserves_under_64_char_names(
    heavy_mcp_config: Dict[str, Any],
) -> None:
    """Verify tool names remain <= 64 characters and conform to identifier constraints."""
    assert (
        optimize_mcp_config_tokens is not None
    ), "optimize_mcp_config_tokens must be implemented and exported"

    res = optimize_mcp_config_tokens(heavy_mcp_config, token_budget=4000)
    opt_cfg = res[0] if isinstance(res, tuple) else res

    for srv_name, srv_data in opt_cfg["mcpServers"].items():
        assert len(srv_name) <= 64
        for tool in srv_data.get("tools", []):
            tname = tool["name"] if isinstance(tool, dict) else str(tool)
            assert len(tname) <= 64


def test_v1_3_lsrpc_bridge_exports_and_version() -> None:
    """Verify v1.3.0 version bump and optimize_mcp_config_tokens export."""
    assert __version__ == "1.3.0", "Package __version__ must be bumped to 1.3.0"
    import agy_lsrpc_bridge

    assert hasattr(
        agy_lsrpc_bridge, "optimize_mcp_config_tokens"
    ), "optimize_mcp_config_tokens must be exported in agy_lsrpc_bridge"
    assert (
        "optimize_mcp_config_tokens" in agy_lsrpc_bridge.__all__
    ), "optimize_mcp_config_tokens must be included in __all__"
