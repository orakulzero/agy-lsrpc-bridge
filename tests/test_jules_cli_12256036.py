"""
tests/test_jules_cli.py
Tests for agy_lsrpc_bridge.cli
"""

from __future__ import annotations

import sys
from pathlib import Path
import json

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.cli import is_valid_subcommand, validate_subcommand_args, _emit


def test_is_valid_subcommand_valid():
    """Test is_valid_subcommand with valid inputs."""
    valid_cmds = [
        "status", "list", "enable", "disable", 
        "uninstall", "install", "validate", 
        "scaffold", "consolidate"
    ]
    for cmd in valid_cmds:
        assert is_valid_subcommand(cmd) is True


def test_is_valid_subcommand_invalid():
    """Test is_valid_subcommand with invalid inputs."""
    assert is_valid_subcommand(None) is False
    assert is_valid_subcommand("") is False
    assert is_valid_subcommand("invalid_cmd") is False
    assert is_valid_subcommand("STATUS") is False


def test_validate_subcommand_args_missing_subcommand():
    """Test validate_subcommand_args when subcommand is missing."""
    res = validate_subcommand_args({})
    assert res["valid"] is False
    assert "errors" in res
    assert "Missing 'subcommand' key" in res["errors"][0]


def test_validate_subcommand_args_unknown_subcommand():
    """Test validate_subcommand_args with unknown subcommand."""
    res = validate_subcommand_args({"subcommand": "unknown"})
    assert res["valid"] is False
    assert "errors" in res
    assert "Unknown subcommand: unknown" in res["errors"][0]


def test_validate_subcommand_args_status_list():
    """Test validate_subcommand_args with status and list."""
    res = validate_subcommand_args({"subcommand": "status"})
    assert res["valid"] is True
    assert len(res["errors"]) == 0

    res = validate_subcommand_args({"subcommand": "list"})
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_validate_subcommand_args_missing_required_args():
    """Test validate_subcommand_args when required arguments are missing."""
    res = validate_subcommand_args({"subcommand": "enable"})
    assert res["valid"] is False
    assert "Missing required argument 'target'" in res["errors"][0]

    res = validate_subcommand_args({"subcommand": "scaffold", "target_root": "/tmp"})
    assert res["valid"] is False
    assert len(res["errors"]) == 2
    assert any("name" in err for err in res["errors"])
    assert any("description" in err for err in res["errors"])


def test_validate_subcommand_args_all_required_args_present():
    """Test validate_subcommand_args with all required arguments present."""
    res = validate_subcommand_args({
        "subcommand": "scaffold",
        "target_root": "/tmp",
        "name": "my-plugin",
        "description": "A plugin"
    })
    assert res["valid"] is True
    assert len(res["errors"]) == 0


def test_emit_json(capsys):
    """Test _emit function with JSON formatting."""
    payload = {"key": "value", "list": [1, 2, 3]}
    _emit(payload, as_json=True)
    captured = capsys.readouterr()
    expected_output = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert captured.out == expected_output


def test_emit_not_json(capsys):
    """Test _emit function when as_json is False (falls back to json in current implementation)."""
    payload = {"key": "value"}
    _emit(payload, as_json=False)
    captured = capsys.readouterr()
    expected_output = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert captured.out == expected_output
