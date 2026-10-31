"""
tests/test_jules_cli.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.cli import is_valid_subcommand, validate_subcommand_args


def test_is_valid_subcommand_valid_inputs():
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


def test_is_valid_subcommand_invalid_inputs():
    invalid_subcommands = [
        "",
        "  ",
        "STATUS",
        "status ",
        "unknown",
        "help",
        "123",
        "enable ",
        " enable",
    ]
    for cmd in invalid_subcommands:
        assert is_valid_subcommand(cmd) is False


def test_is_valid_subcommand_none():
    assert is_valid_subcommand(None) is False


def test_validate_subcommand_args_missing_subcommand():
    args_dict = {}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is False
    assert result["errors"] == ["Missing 'subcommand' key in arguments"]


def test_validate_subcommand_args_unknown_subcommand():
    args_dict = {"subcommand": "unknown"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is False
    assert result["errors"] == ["Unknown subcommand: unknown"]


def test_validate_subcommand_args_status_valid():
    args_dict = {"subcommand": "status"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_subcommand_args_enable_valid():
    args_dict = {"subcommand": "enable", "target": "my-plugin"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_subcommand_args_enable_missing_required():
    args_dict = {"subcommand": "enable"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is False
    assert result["errors"] == ["Missing required argument 'target' for subcommand 'enable'"]


def test_validate_subcommand_args_install_valid():
    args_dict = {"subcommand": "install", "marketplace_id": "com.example.plugin"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_subcommand_args_install_missing_required():
    args_dict = {"subcommand": "install"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is False
    assert result["errors"] == ["Missing required argument 'marketplace_id' for subcommand 'install'"]


def test_validate_subcommand_args_scaffold_valid():
    args_dict = {
        "subcommand": "scaffold",
        "target_root": "/tmp",
        "name": "my-plugin",
        "description": "My test plugin",
    }
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_subcommand_args_scaffold_missing_multiple_required():
    args_dict = {"subcommand": "scaffold", "target_root": "/tmp"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is False
    assert len(result["errors"]) == 2
    assert "Missing required argument 'name' for subcommand 'scaffold'" in result["errors"]
    assert "Missing required argument 'description' for subcommand 'scaffold'" in result["errors"]


def test_validate_subcommand_args_consolidate_valid():
    args_dict = {"subcommand": "consolidate", "plugin_dir": "/tmp/plugin"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_subcommand_args_extra_args_ignored():
    args_dict = {
        "subcommand": "list",
        "extra_arg1": "value1",
        "extra_arg2": 123,
    }
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is True
    assert result["errors"] == []
