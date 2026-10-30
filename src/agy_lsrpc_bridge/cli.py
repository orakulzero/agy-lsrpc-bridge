"""
src/agy_lsrpc_bridge/cli.py
CLI Entrypoint for `agy-lsrpc-bridge`.
Subcommands:
- `status`      : Check Language Server `/healthz` and return compact plugin inventory.
- `list`        : List installed plugins (context-flood-safe).
- `enable`      : Live-enable a plugin via `JetboxWriteState` keyed by true install `dir`.
- `disable`     : Live-disable a plugin via `JetboxWriteState` keyed by true install `dir`.
- `uninstall`   : Safely uninstall a plugin (`DeletePlugin`) with Built-in & Stale-Disabled guards.
- `install`     : Install a Marketplace plugin via `InstallCustomization`.
- `validate`    : Validate an Antigravity 2.0 plugin bundle against all loader rules.
- `scaffold`    : Scaffold a new Antigravity 2.0 native plugin bundle.
- `consolidate` : Consolidate loose skills and rules into a target plugin bundle.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, List, Optional

from agy_lsrpc_bridge.client import LSRPCClient
from agy_lsrpc_bridge.scaffolder import (
    consolidate_loose_customizations,
    scaffold_plugin,
)
from agy_lsrpc_bridge.validator import validate_plugin_bundle


def is_valid_subcommand(subcommand: str | None) -> bool:
    """Helper function to check if a subcommand is valid."""
    if subcommand is None:
        return False
    valid_subcommands = {
        "status",
        "list",
        "enable",
        "disable",
        "uninstall",
        "install",
        "validate",
        "scaffold",
        "consolidate",
    }
    return subcommand in valid_subcommands


def validate_subcommand_args(args_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Pre-flight validator for CLI argument combinations.
    """
    errors = []
    
    if "subcommand" not in args_dict:
        return {"valid": False, "errors": ["Missing 'subcommand' key in arguments"]}
        
    cmd = args_dict["subcommand"]
    
    required_args = {
        "status": [],
        "list": [],
        "enable": ["target"],
        "disable": ["target"],
        "uninstall": ["target"],
        "install": ["marketplace_id"],
        "validate": ["plugin_dir"],
        "scaffold": ["target_root", "name", "description"],
        "consolidate": ["plugin_dir"],
    }
    
    if cmd not in required_args:
        return {"valid": False, "errors": [f"Unknown subcommand: {cmd}"]}
        
    for req in required_args[cmd]:
        if req not in args_dict:
            errors.append(f"Missing required argument '{req}' for subcommand '{cmd}'")
            
    return {"valid": len(errors) == 0, "errors": errors}


def _emit(payload: Any, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agy-lsrpc-bridge",
        description="Antigravity Language Server ConnectRPC Bridge, Live Plugin Manager & Scaffolder",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # status
    p_status = sub.add_parser("status", help="Check Language Server health and list plugins")
    p_status.add_argument("--address", default=None, help="Language Server host:port")
    p_status.add_argument("--config-root", default=None, help="Path to ~/.gemini/config")
    p_status.add_argument("--workspace-uri", action="append", default=[], help="Workspace file:// URI")
    p_status.add_argument("--json", action="store_true", help="Emit JSON output")

    # list
    p_list = sub.add_parser("list", help="List installed plugins (context-safe)")
    p_list.add_argument("--address", default=None)
    p_list.add_argument("--config-root", default=None)
    p_list.add_argument("--workspace-uri", action="append", default=[])
    p_list.add_argument("--json", action="store_true")

    # enable
    p_enable = sub.add_parser("enable", help="Live-enable a plugin by dir or name")
    p_enable.add_argument("target", help="Plugin dir or name")
    p_enable.add_argument("--address", default=None)
    p_enable.add_argument("--config-root", default=None)
    p_enable.add_argument("--json", action="store_true")

    # disable
    p_disable = sub.add_parser("disable", help="Live-disable a plugin by dir or name")
    p_disable.add_argument("target", help="Plugin dir or name")
    p_disable.add_argument("--address", default=None)
    p_disable.add_argument("--config-root", default=None)
    p_disable.add_argument("--json", action="store_true")

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="Safely uninstall a plugin")
    p_uninstall.add_argument("target", help="Plugin dir or name")
    p_uninstall.add_argument("--address", default=None)
    p_uninstall.add_argument("--config-root", default=None)
    p_uninstall.add_argument("--json", action="store_true")

    # install
    p_install = sub.add_parser("install", help="Install a Marketplace plugin by ID")
    p_install.add_argument("marketplace_id", help="Marketplace customization ID")
    p_install.add_argument("--address", default=None)
    p_install.add_argument("--config-root", default=None)
    p_install.add_argument("--json", action="store_true")

    # validate
    p_validate = sub.add_parser("validate", help="Validate an Antigravity 2.0 plugin bundle")
    p_validate.add_argument("plugin_dir", help="Path to plugin directory")
    p_validate.add_argument("--json", action="store_true")

    # scaffold
    p_scaffold = sub.add_parser("scaffold", help="Scaffold a compliant Antigravity 2.0 plugin")
    p_scaffold.add_argument("--target-root", required=True, help="Parent directory for plugin")
    p_scaffold.add_argument("--name", required=True, help="Lowercase kebab-case plugin name")
    p_scaffold.add_argument("--description", required=True, help="Plugin description")
    p_scaffold.add_argument("--display-name", default=None, help="Optional human display name")
    p_scaffold.add_argument("--include-hooks", action="store_true", help="Include root hooks.json")
    p_scaffold.add_argument("--include-mcp", action="store_true", help="Include prefixed mcp_config.json")
    p_scaffold.add_argument("--json", action="store_true")

    # consolidate
    p_consolidate = sub.add_parser("consolidate", help="Consolidate loose skills and rules into a plugin")
    p_consolidate.add_argument("--plugin-dir", required=True, help="Target plugin directory")
    p_consolidate.add_argument("--skill-dir", action="append", default=[], help="Loose skill directory")
    p_consolidate.add_argument("--rule-file", action="append", default=[], help="Loose markdown rule file")
    p_consolidate.add_argument("--json", action="store_true")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.subcommand

    if cmd in ("status", "list", "enable", "disable", "uninstall", "install"):
        cfg_root = Path(args.config_root) if getattr(args, "config_root", None) else None
        client = LSRPCClient(address=getattr(args, "address", None), config_root=cfg_root)

        if cmd == "status":
            health = client.healthz()
            plugins = client.list_plugins(workspace_uris=args.workspace_uri or None)
            _emit(
                {
                    "ok": True,
                    "health": health,
                    "plugin_count": len(plugins),
                    "plugins": plugins,
                },
                as_json=True,
            )
            return 0

        if cmd == "list":
            plugins = client.list_plugins(workspace_uris=args.workspace_uri or None)
            _emit({"ok": True, "count": len(plugins), "plugins": plugins}, as_json=True)
            return 0

        if cmd == "enable":
            res = client.set_plugin_enabled(args.target, True)
            _emit(res, as_json=True)
            return 0

        if cmd == "disable":
            res = client.set_plugin_enabled(args.target, False)
            _emit(res, as_json=True)
            return 0

        if cmd == "uninstall":
            res = client.uninstall_plugin(args.target)
            _emit(res, as_json=True)
            return 0

        if cmd == "install":
            res = client.install_marketplace_plugin(args.marketplace_id)
            _emit(res, as_json=True)
            return 0

    if cmd == "validate":
        res = validate_plugin_bundle(Path(args.plugin_dir))
        _emit(res, as_json=True)
        return 0 if res["valid"] else 1

    if cmd == "scaffold":
        pdir = scaffold_plugin(
            target_root=Path(args.target_root),
            name=args.name,
            description=args.description,
            display_name=args.display_name,
            include_hooks=args.include_hooks,
            include_mcp=args.include_mcp,
        )
        validation = validate_plugin_bundle(pdir)
        _emit(
            {
                "ok": validation["valid"],
                "plugin_dir": str(pdir),
                "validation": validation,
            },
            as_json=True,
        )
        return 0 if validation["valid"] else 1

    if cmd == "consolidate":
        res = consolidate_loose_customizations(
            plugin_dir=Path(args.plugin_dir),
            skill_dirs=[Path(p) for p in args.skill_dir],
            rule_files=[Path(p) for p in args.rule_file],
        )
        _emit(res, as_json=True)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
