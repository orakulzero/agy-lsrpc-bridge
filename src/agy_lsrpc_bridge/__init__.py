"""Antigravity Language Server ConnectRPC Bridge, Live Plugin Manager & Plugin Scaffolder."""

from __future__ import annotations

from agy_lsrpc_bridge.client import LSRPCClient, detect_plugin_drift
from agy_lsrpc_bridge.oss_audit import audit_git_repository
from agy_lsrpc_bridge.scaffolder import (
    consolidate_loose_customizations,
    scaffold_plugin,
)
from agy_lsrpc_bridge.validator import (
    ALLOWED_PLUGIN_MANIFEST_KEYS,
    analyze_mcp_token_budget,
    audit_cross_plugin_mcp_collisions,
    optimize_mcp_config_tokens,
    parse_jsonc,
    validate_mcp_config_strict,
    validate_plugin_bundle,
)

__version__ = "2.0.0"

__all__ = [
    "ALLOWED_PLUGIN_MANIFEST_KEYS",
    "LSRPCClient",
    "__version__",
    "analyze_mcp_token_budget",
    "audit_cross_plugin_mcp_collisions",
    "audit_git_repository",
    "consolidate_loose_customizations",
    "detect_plugin_drift",
    "optimize_mcp_config_tokens",
    "parse_jsonc",
    "scaffold_plugin",
    "validate_mcp_config_strict",
    "validate_plugin_bundle",
]
