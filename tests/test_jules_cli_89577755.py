from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.cli import (
    is_valid_subcommand,
    validate_subcommand_args,
    _emit,
    build_parser,
    main,
)

# --- is_valid_subcommand ---
def test_is_valid_subcommand_boundaries():
    assert is_valid_subcommand(None) is False
    assert is_valid_subcommand("") is False
    assert is_valid_subcommand("  ") is False
    assert is_valid_subcommand("invalid_cmd") is False

@pytest.mark.parametrize("cmd", [
    "status", "list", "enable", "disable", "uninstall", 
    "install", "validate", "scaffold", "consolidate"
])
def test_is_valid_subcommand_valid_cmds(cmd):
    assert is_valid_subcommand(cmd) is True

# --- validate_subcommand_args ---
def test_validate_subcommand_args_missing_subcommand():
    res = validate_subcommand_args({})
    assert res["valid"] is False
    assert "Missing 'subcommand' key" in res["errors"][0]

def test_validate_subcommand_args_unknown_subcommand():
    res = validate_subcommand_args({"subcommand": "fake_cmd"})
    assert res["valid"] is False
    assert "Unknown subcommand" in res["errors"][0]

def test_validate_subcommand_args_missing_multiple_required():
    res = validate_subcommand_args({"subcommand": "scaffold"})
    assert res["valid"] is False
    assert len(res["errors"]) == 3
    assert any("target_root" in err for err in res["errors"])
    assert any("name" in err for err in res["errors"])
    assert any("description" in err for err in res["errors"])

@pytest.mark.parametrize("cmd,reqs", [
    ("status", {}),
    ("list", {}),
    ("enable", {"target": "plugin1"}),
    ("disable", {"target": "plugin1"}),
    ("uninstall", {"target": "plugin1"}),
    ("install", {"marketplace_id": "com.ex.plugin"}),
    ("validate", {"plugin_dir": "/tmp/plugin"}),
    ("scaffold", {"target_root": "/tmp", "name": "my-plug", "description": "desc"}),
    ("consolidate", {"plugin_dir": "/tmp/plugin"}),
])
def test_validate_subcommand_args_valid(cmd, reqs):
    args = {"subcommand": cmd, **reqs, "extra_arg": "should_be_ignored"}
    res = validate_subcommand_args(args)
    assert res["valid"] is True
    assert len(res["errors"]) == 0

# --- _emit ---
def test_emit_output(capsys):
    payload = {"status": "ok", "msg": "hello"}
    _emit(payload, as_json=True)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data == payload

    # Since code ignores as_json flag and always prints JSON:
    _emit(payload, as_json=False)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data == payload

# --- build_parser ---
def test_build_parser_options():
    parser = build_parser()
    subparsers_actions = [
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    ]
    choices = subparsers_actions[0].choices.keys()
    assert "status" in choices
    assert "consolidate" in choices

# --- main (argparse exit boundaries) ---
def test_main_no_args():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2

def test_main_unknown_subcommand():
    with pytest.raises(SystemExit) as exc:
        main(["unknown-cmd"])
    assert exc.value.code == 2

def test_main_missing_required_arg_for_scaffold():
    with pytest.raises(SystemExit) as exc:
        main(["scaffold"])  # missing --target-root, etc.
    assert exc.value.code == 2

# --- main (Client Subcommands) ---
@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_status(mock_client_cls, capsys):
    mock_client = MagicMock()
    mock_client.healthz.return_value = {"ok": True}
    mock_client.list_plugins.return_value = ["plugin_A"]
    mock_client_cls.return_value = mock_client

    ret = main(["status", "--workspace-uri", "file:///a", "--workspace-uri", "file:///b"])
    assert ret == 0
    mock_client_cls.assert_called_once_with(address=None, config_root=None)
    mock_client.list_plugins.assert_called_once_with(workspace_uris=["file:///a", "file:///b"])
    
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["ok"] is True
    assert data["plugin_count"] == 1
    assert "plugin_A" in data["plugins"]

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_list(mock_client_cls, capsys):
    mock_client = MagicMock()
    mock_client.list_plugins.return_value = ["p1", "p2"]
    mock_client_cls.return_value = mock_client

    ret = main(["list", "--config-root", "/home/usr/.gemini"])
    assert ret == 0
    mock_client_cls.assert_called_once_with(address=None, config_root=Path("/home/usr/.gemini"))
    
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["count"] == 2

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_enable(mock_client_cls):
    mock_client = MagicMock()
    mock_client.set_plugin_enabled.return_value = {"ok": True}
    mock_client_cls.return_value = mock_client

    assert main(["enable", "p1"]) == 0
    mock_client.set_plugin_enabled.assert_called_once_with("p1", True)

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_disable(mock_client_cls):
    mock_client = MagicMock()
    mock_client.set_plugin_enabled.return_value = {"ok": True}
    mock_client_cls.return_value = mock_client

    assert main(["disable", "p1"]) == 0
    mock_client.set_plugin_enabled.assert_called_once_with("p1", False)

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_uninstall(mock_client_cls):
    mock_client = MagicMock()
    mock_client.uninstall_plugin.return_value = {"ok": True}
    mock_client_cls.return_value = mock_client

    assert main(["uninstall", "p1"]) == 0
    mock_client.uninstall_plugin.assert_called_once_with("p1")

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_install(mock_client_cls):
    mock_client = MagicMock()
    mock_client.install_marketplace_plugin.return_value = {"ok": True}
    mock_client_cls.return_value = mock_client

    assert main(["install", "market_123", "--address", "localhost:9999"]) == 0
    mock_client_cls.assert_called_once_with(address="localhost:9999", config_root=None)
    mock_client.install_marketplace_plugin.assert_called_once_with("market_123")

# --- main (Other Subcommands) ---
@patch("agy_lsrpc_bridge.cli.validate_plugin_bundle")
def test_main_validate(mock_validate):
    mock_validate.return_value = {"valid": True}
    assert main(["validate", "/plugin"]) == 0
    mock_validate.assert_called_once_with(Path("/plugin"))

    mock_validate.return_value = {"valid": False, "errors": ["err1"]}
    assert main(["validate", "/plugin"]) == 1

@patch("agy_lsrpc_bridge.cli.validate_plugin_bundle")
@patch("agy_lsrpc_bridge.cli.scaffold_plugin")
def test_main_scaffold(mock_scaffold, mock_validate):
    mock_scaffold.return_value = Path("/out/plugin")
    mock_validate.return_value = {"valid": True}
    
    args = [
        "scaffold",
        "--target-root", "/out",
        "--name", "plug",
        "--description", "desc",
        "--display-name", "Plug",
        "--include-hooks",
        "--include-mcp"
    ]
    assert main(args) == 0
    mock_scaffold.assert_called_once_with(
        target_root=Path("/out"),
        name="plug",
        description="desc",
        display_name="Plug",
        include_hooks=True,
        include_mcp=True
    )
    mock_validate.assert_called_once_with(Path("/out/plugin"))

    # When validation fails
    mock_validate.return_value = {"valid": False}
    assert main(args) == 1

@patch("agy_lsrpc_bridge.cli.consolidate_loose_customizations")
def test_main_consolidate(mock_consol):
    mock_consol.return_value = {"ok": True}
    args = [
        "consolidate",
        "--plugin-dir", "/out",
        "--skill-dir", "/s1",
        "--skill-dir", "/s2",
        "--rule-file", "/r1.md"
    ]
    assert main(args) == 0
    mock_consol.assert_called_once_with(
        plugin_dir=Path("/out"),
        skill_dirs=[Path("/s1"), Path("/s2")],
        rule_files=[Path("/r1.md")]
    )

def test_main_unhandled_subcommand(monkeypatch):
    # simulate parsed args that aren't handled (shouldn't happen in practice due to argparse choices, but hits coverage for `return 1` at the end)
    parser_mock = MagicMock()
    args_mock = MagicMock()
    args_mock.subcommand = "made_up_cmd"
    parser_mock.parse_args.return_value = args_mock
    monkeypatch.setattr("agy_lsrpc_bridge.cli.build_parser", lambda: parser_mock)
    
    assert main([]) == 1
