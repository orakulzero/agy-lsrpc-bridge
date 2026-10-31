from __future__ import annotations

import sys
from pathlib import Path
import json

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.cli import is_valid_subcommand, validate_subcommand_args, _emit

def test_is_valid_subcommand():
    assert is_valid_subcommand("status") is True
    assert is_valid_subcommand("consolidate") is True
    assert is_valid_subcommand("scaffold") is True
    assert is_valid_subcommand("invalid_cmd") is False
    assert is_valid_subcommand(None) is False
    assert is_valid_subcommand("") is False

def test_validate_subcommand_args_missing_subcommand():
    result = validate_subcommand_args({"some": "arg"})
    assert result["valid"] is False
    assert "Missing 'subcommand' key" in result["errors"][0]

def test_validate_subcommand_args_unknown_subcommand():
    result = validate_subcommand_args({"subcommand": "unknown"})
    assert result["valid"] is False
    assert "Unknown subcommand: unknown" in result["errors"][0]

def test_validate_subcommand_args_missing_required():
    result = validate_subcommand_args({"subcommand": "enable"})
    assert result["valid"] is False
    assert "Missing required argument 'target'" in result["errors"][0]

def test_validate_subcommand_args_scaffold_missing_multiple():
    result = validate_subcommand_args({"subcommand": "scaffold", "target_root": "dir"})
    assert result["valid"] is False
    assert any("name" in e for e in result["errors"])
    assert any("description" in e for e in result["errors"])

def test_validate_subcommand_args_valid():
    result = validate_subcommand_args({"subcommand": "status"})
    assert result["valid"] is True
    assert not result["errors"]

    result = validate_subcommand_args({
        "subcommand": "scaffold",
        "target_root": "dir",
        "name": "my-plugin",
        "description": "desc"
    })
    assert result["valid"] is True
    assert not result["errors"]

def test_emit_json(capsys):
    payload = {"key": "value"}
    _emit(payload, as_json=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == payload

def test_emit_non_json(capsys):
    payload = {"key": "value"}
    # The current implementation of _emit outputs JSON regardless of `as_json`
    _emit(payload, as_json=False)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == payload

from unittest.mock import patch, MagicMock

from agy_lsrpc_bridge.cli import build_parser, main

def test_build_parser():
    parser = build_parser()
    
    # Missing required argument 'subcommand'
    with pytest.raises(SystemExit):
        parser.parse_args([])

    # status
    args = parser.parse_args(["status"])
    assert args.subcommand == "status"
    assert args.address is None
    assert args.config_root is None
    assert args.workspace_uri == []
    assert args.json is False

    args = parser.parse_args(["status", "--address", "localhost:1234", "--config-root", "/conf", "--workspace-uri", "file://1", "--workspace-uri", "file://2", "--json"])
    assert args.address == "localhost:1234"
    assert args.config_root == "/conf"
    assert args.workspace_uri == ["file://1", "file://2"]
    assert args.json is True

    # enable missing target
    with pytest.raises(SystemExit):
        parser.parse_args(["enable"])

    # scaffold missing args
    with pytest.raises(SystemExit):
        parser.parse_args(["scaffold", "--target-root", "dir"])


@patch("agy_lsrpc_bridge.cli.LSRPCClient")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_status(mock_emit, mock_client_cls):
    mock_client = MagicMock()
    mock_client.healthz.return_value = "OK"
    mock_client.list_plugins.return_value = ["plugin1", "plugin2"]
    mock_client_cls.return_value = mock_client

    ret = main(["status", "--address", "localhost:1234"])
    assert ret == 0

    mock_client_cls.assert_called_once_with(address="localhost:1234", config_root=None)
    mock_client.healthz.assert_called_once()
    mock_client.list_plugins.assert_called_once_with(workspace_uris=None)

    mock_emit.assert_called_once_with({
        "ok": True,
        "health": "OK",
        "plugin_count": 2,
        "plugins": ["plugin1", "plugin2"]
    }, as_json=True)

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_list(mock_emit, mock_client_cls):
    mock_client = MagicMock()
    mock_client.list_plugins.return_value = ["plugin1"]
    mock_client_cls.return_value = mock_client

    ret = main(["list", "--workspace-uri", "file://workspace"])
    assert ret == 0

    mock_client.list_plugins.assert_called_once_with(workspace_uris=["file://workspace"])
    mock_emit.assert_called_once_with({
        "ok": True,
        "count": 1,
        "plugins": ["plugin1"]
    }, as_json=True)

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_enable_disable(mock_emit, mock_client_cls):
    mock_client = MagicMock()
    mock_client.set_plugin_enabled.return_value = {"enabled": True}
    mock_client_cls.return_value = mock_client

    ret = main(["enable", "my-plugin"])
    assert ret == 0

    mock_client.set_plugin_enabled.assert_called_once_with("my-plugin", True)
    mock_emit.assert_called_once_with({"enabled": True}, as_json=True)

    mock_emit.reset_mock()
    mock_client.set_plugin_enabled.reset_mock()
    mock_client.set_plugin_enabled.return_value = {"enabled": False}

    ret = main(["disable", "my-plugin"])
    assert ret == 0

    mock_client.set_plugin_enabled.assert_called_once_with("my-plugin", False)
    mock_emit.assert_called_once_with({"enabled": False}, as_json=True)

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_uninstall(mock_emit, mock_client_cls):
    mock_client = MagicMock()
    mock_client.uninstall_plugin.return_value = {"uninstalled": True}
    mock_client_cls.return_value = mock_client

    ret = main(["uninstall", "my-plugin"])
    assert ret == 0

    mock_client.uninstall_plugin.assert_called_once_with("my-plugin")
    mock_emit.assert_called_once_with({"uninstalled": True}, as_json=True)

@patch("agy_lsrpc_bridge.cli.LSRPCClient")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_install(mock_emit, mock_client_cls):
    mock_client = MagicMock()
    mock_client.install_marketplace_plugin.return_value = {"installed": True}
    mock_client_cls.return_value = mock_client

    ret = main(["install", "12345"])
    assert ret == 0

    mock_client.install_marketplace_plugin.assert_called_once_with("12345")
    mock_emit.assert_called_once_with({"installed": True}, as_json=True)

@patch("agy_lsrpc_bridge.cli.validate_plugin_bundle")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_validate(mock_emit, mock_validate):
    mock_validate.return_value = {"valid": True}
    
    ret = main(["validate", "my/plugin/dir"])
    assert ret == 0
    mock_validate.assert_called_once_with(Path("my/plugin/dir"))
    mock_emit.assert_called_once_with({"valid": True}, as_json=True)
    
    mock_validate.reset_mock()
    mock_emit.reset_mock()
    
    mock_validate.return_value = {"valid": False}
    ret = main(["validate", "my/plugin/dir"])
    assert ret == 1
    mock_validate.assert_called_once_with(Path("my/plugin/dir"))
    mock_emit.assert_called_once_with({"valid": False}, as_json=True)

@patch("agy_lsrpc_bridge.cli.scaffold_plugin")
@patch("agy_lsrpc_bridge.cli.validate_plugin_bundle")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_scaffold(mock_emit, mock_validate, mock_scaffold):
    mock_scaffold.return_value = Path("new/plugin")
    mock_validate.return_value = {"valid": True}
    
    ret = main([
        "scaffold",
        "--target-root", "out",
        "--name", "test-plugin",
        "--description", "test desc",
        "--display-name", "Test Plugin",
        "--include-hooks",
        "--include-mcp"
    ])
    assert ret == 0
    mock_scaffold.assert_called_once_with(
        target_root=Path("out"),
        name="test-plugin",
        description="test desc",
        display_name="Test Plugin",
        include_hooks=True,
        include_mcp=True
    )
    mock_validate.assert_called_once_with(Path("new/plugin"))
    mock_emit.assert_called_once_with({
        "ok": True,
        "plugin_dir": "new/plugin",
        "validation": {"valid": True}
    }, as_json=True)

    mock_scaffold.reset_mock()
    mock_validate.reset_mock()
    mock_emit.reset_mock()
    
    mock_validate.return_value = {"valid": False}
    ret = main([
        "scaffold",
        "--target-root", "out",
        "--name", "test-plugin",
        "--description", "test desc"
    ])
    assert ret == 1
    mock_scaffold.assert_called_once_with(
        target_root=Path("out"),
        name="test-plugin",
        description="test desc",
        display_name=None,
        include_hooks=False,
        include_mcp=False
    )
    mock_emit.assert_called_once_with({
        "ok": False,
        "plugin_dir": "new/plugin",
        "validation": {"valid": False}
    }, as_json=True)

@patch("agy_lsrpc_bridge.cli.consolidate_loose_customizations")
@patch("agy_lsrpc_bridge.cli._emit")
def test_main_consolidate(mock_emit, mock_consolidate):
    mock_consolidate.return_value = {"consolidated": True}
    
    ret = main([
        "consolidate",
        "--plugin-dir", "target/plugin",
        "--skill-dir", "skill1",
        "--skill-dir", "skill2",
        "--rule-file", "rule1.md"
    ])
    
    assert ret == 0
    mock_consolidate.assert_called_once_with(
        plugin_dir=Path("target/plugin"),
        skill_dirs=[Path("skill1"), Path("skill2")],
        rule_files=[Path("rule1.md")]
    )
    mock_emit.assert_called_once_with({"consolidated": True}, as_json=True)

@patch("agy_lsrpc_bridge.cli.build_parser")
def test_main_unknown_subcommand(mock_build_parser):
    # This shouldn't normally happen since argparse catches unknown subcommands,
    # but we can test the fallback return 1 in main()
    parser = MagicMock()
    args = MagicMock()
    args.subcommand = "unknown_cmd"
    parser.parse_args.return_value = args
    mock_build_parser.return_value = parser
    
    ret = main(["unknown_cmd"])
    assert ret == 1
