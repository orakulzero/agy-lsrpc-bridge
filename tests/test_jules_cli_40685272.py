"""
tests/test_jules_cli.py
"""

from __future__ import annotations

import sys
from pathlib import Path
import json
import argparse
from unittest.mock import patch, MagicMock

import pytest

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


def test_is_valid_subcommand():
    # Boundary: None
    assert is_valid_subcommand(None) is False
    
    # Boundary: Empty string
    assert is_valid_subcommand("") is False
    
    # Boundary: Invalid subcommand
    assert is_valid_subcommand("invalid") is False
    assert is_valid_subcommand(" status ") is False
    
    # Boundary: Valid subcommands
    valid_subcommands = [
        "status",
        "list",
        "enable",
        "disable",
        "uninstall",
        "install",
        "validate",
        "scaffold",
        "consolidate",
    ]
    for cmd in valid_subcommands:
        assert is_valid_subcommand(cmd) is True


def test_validate_subcommand_args_missing_subcommand():
    # Boundary: Empty dict
    res = validate_subcommand_args({})
    assert res["valid"] is False
    assert res["errors"] == ["Missing 'subcommand' key in arguments"]
    
    # Boundary: Invalid subcommand
    res = validate_subcommand_args({"subcommand": "nonexistent"})
    assert res["valid"] is False
    assert res["errors"] == ["Unknown subcommand: nonexistent"]


def test_validate_subcommand_args_missing_args():
    # Boundary: Missing required argument
    res = validate_subcommand_args({"subcommand": "enable"})
    assert res["valid"] is False
    assert res["errors"] == ["Missing required argument 'target' for subcommand 'enable'"]
    
    res = validate_subcommand_args({"subcommand": "scaffold", "target_root": "root", "name": "name"})
    assert res["valid"] is False
    assert res["errors"] == ["Missing required argument 'description' for subcommand 'scaffold'"]


def test_validate_subcommand_args_valid_args():
    # Boundary: All required arguments present
    res = validate_subcommand_args({"subcommand": "enable", "target": "my-plugin"})
    assert res["valid"] is True
    assert res["errors"] == []
    
    res = validate_subcommand_args({
        "subcommand": "scaffold",
        "target_root": "root",
        "name": "name",
        "description": "desc"
    })
    assert res["valid"] is True
    assert res["errors"] == []


def test_emit(capsys):
    # Boundary: as_json=True
    payload = {"key": "value"}
    _emit(payload, as_json=True)
    captured = capsys.readouterr()
    assert captured.out == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    
    # Boundary: as_json=False (currently has the same behavior in the code)
    _emit(payload, as_json=False)
    captured = capsys.readouterr()
    assert captured.out == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def test_build_parser():
    parser = build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.prog == "agy-lsrpc-bridge"
    
    # Boundary: Check if subparsers are created
    subparsers_actions = [
        action for action in parser._actions 
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) == 1
    subparsers = subparsers_actions[0].choices
    
    expected_subparsers = {
        "status", "list", "enable", "disable", "uninstall",
        "install", "validate", "scaffold", "consolidate"
    }
    assert set(subparsers.keys()) == expected_subparsers


@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_status(mock_client_class, capsys):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.healthz.return_value = "ok"
    mock_client.list_plugins.return_value = ["plugin1"]
    
    ret = main(["status", "--address", "localhost:8080"])
    
    assert ret == 0
    mock_client_class.assert_called_once_with(address="localhost:8080", config_root=None)
    mock_client.healthz.assert_called_once()
    mock_client.list_plugins.assert_called_once_with(workspace_uris=None)
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True
    assert out["health"] == "ok"
    assert out["plugin_count"] == 1
    assert out["plugins"] == ["plugin1"]


@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_list(mock_client_class, capsys):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.list_plugins.return_value = ["plugin1", "plugin2"]
    
    ret = main(["list", "--workspace-uri", "file:///ws"])
    
    assert ret == 0
    mock_client.list_plugins.assert_called_once_with(workspace_uris=["file:///ws"])
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True
    assert out["count"] == 2
    assert out["plugins"] == ["plugin1", "plugin2"]


@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_enable(mock_client_class, capsys):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.set_plugin_enabled.return_value = {"ok": True}
    
    ret = main(["enable", "my-plugin"])
    
    assert ret == 0
    mock_client.set_plugin_enabled.assert_called_once_with("my-plugin", True)
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True


@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_disable(mock_client_class, capsys):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.set_plugin_enabled.return_value = {"ok": True}
    
    ret = main(["disable", "my-plugin"])
    
    assert ret == 0
    mock_client.set_plugin_enabled.assert_called_once_with("my-plugin", False)
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True


@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_uninstall(mock_client_class, capsys):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.uninstall_plugin.return_value = {"ok": True}
    
    ret = main(["uninstall", "my-plugin"])
    
    assert ret == 0
    mock_client.uninstall_plugin.assert_called_once_with("my-plugin")
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True


@patch("agy_lsrpc_bridge.cli.LSRPCClient")
def test_main_install(mock_client_class, capsys):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.install_marketplace_plugin.return_value = {"ok": True}
    
    ret = main(["install", "market-id"])
    
    assert ret == 0
    mock_client.install_marketplace_plugin.assert_called_once_with("market-id")
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True


@patch("agy_lsrpc_bridge.cli.validate_plugin_bundle")
def test_main_validate(mock_validate, capsys):
    # Boundary: Valid plugin
    mock_validate.return_value = {"valid": True}
    
    ret = main(["validate", "/path/to/plugin"])
    
    assert ret == 0
    mock_validate.assert_called_once_with(Path("/path/to/plugin"))
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["valid"] is True

    # Boundary: Invalid plugin
    mock_validate.return_value = {"valid": False}
    
    ret = main(["validate", "/path/to/plugin2"])
    
    assert ret == 1
    assert mock_validate.call_count == 2
    mock_validate.assert_called_with(Path("/path/to/plugin2"))


@patch("agy_lsrpc_bridge.cli.validate_plugin_bundle")
@patch("agy_lsrpc_bridge.cli.scaffold_plugin")
def test_main_scaffold(mock_scaffold, mock_validate, capsys):
    # Boundary: Valid scaffold
    mock_scaffold.return_value = Path("/target/plugin")
    mock_validate.return_value = {"valid": True}
    
    ret = main([
        "scaffold",
        "--target-root", "/target",
        "--name", "plugin-name",
        "--description", "desc",
        "--display-name", "Plugin Name",
        "--include-hooks",
        "--include-mcp"
    ])
    
    assert ret == 0
    mock_scaffold.assert_called_once_with(
        target_root=Path("/target"),
        name="plugin-name",
        description="desc",
        display_name="Plugin Name",
        include_hooks=True,
        include_mcp=True,
    )
    mock_validate.assert_called_once_with(Path("/target/plugin"))
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True
    assert out["plugin_dir"] == "/target/plugin"
    assert out["validation"]["valid"] is True

    # Boundary: Invalid scaffold validation
    mock_scaffold.reset_mock()
    mock_validate.reset_mock()
    
    mock_scaffold.return_value = Path("/target/plugin2")
    mock_validate.return_value = {"valid": False}
    
    ret = main([
        "scaffold",
        "--target-root", "/target",
        "--name", "plugin2",
        "--description", "desc"
    ])
    
    assert ret == 1
    mock_scaffold.assert_called_once_with(
        target_root=Path("/target"),
        name="plugin2",
        description="desc",
        display_name=None,
        include_hooks=False,
        include_mcp=False,
    )
    mock_validate.assert_called_once_with(Path("/target/plugin2"))


@patch("agy_lsrpc_bridge.cli.consolidate_loose_customizations")
def test_main_consolidate(mock_consolidate, capsys):
    mock_consolidate.return_value = {"ok": True}
    
    ret = main([
        "consolidate",
        "--plugin-dir", "/plugin",
        "--skill-dir", "/skill1",
        "--skill-dir", "/skill2",
        "--rule-file", "/rule1.md"
    ])
    
    assert ret == 0
    mock_consolidate.assert_called_once_with(
        plugin_dir=Path("/plugin"),
        skill_dirs=[Path("/skill1"), Path("/skill2")],
        rule_files=[Path("/rule1.md")],
    )
    
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["ok"] is True


def test_main_no_args(capsys):
    with pytest.raises(SystemExit):
        main([])


def test_main_unhandled_subcommand():
    # main doesn't have an unhandled subcommand because parse_args fails if not one of the choices
    # But we can test what happens if we bypass build_parser somehow or if we hit the fallback `return 1`
    # We can do this by mocking parse_args
    with patch("agy_lsrpc_bridge.cli.build_parser") as mock_build_parser:
        mock_parser = MagicMock()
        mock_build_parser.return_value = mock_parser
        
        mock_args = MagicMock()
        mock_args.subcommand = "unknown_command"
        mock_parser.parse_args.return_value = mock_args
        
        ret = main(["unknown_command"])
        assert ret == 1
