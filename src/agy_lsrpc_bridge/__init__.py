"""Antigravity Language Server ConnectRPC Bridge, Live Plugin Manager & Plugin Scaffolder."""

from __future__ import annotations

from agy_lsrpc_bridge.client import LSRPCClient, detect_plugin_drift
from agy_lsrpc_bridge.scaffolder import (
    consolidate_loose_customizations,
    scaffold_plugin,
)
from agy_lsrpc_bridge.validator import (
    ALLOWED_PLUGIN_MANIFEST_KEYS,
    parse_jsonc,
    validate_mcp_config_strict,
    validate_plugin_bundle,
)

__version__ = "1.1.0"

__all__ = [
    "ALLOWED_PLUGIN_MANIFEST_KEYS",
    "LSRPCClient",
    "__version__",
    "consolidate_loose_customizations",
    "detect_plugin_drift",
    "parse_jsonc",
    "scaffold_plugin",
    "validate_mcp_config_strict",
    "validate_plugin_bundle",
]
