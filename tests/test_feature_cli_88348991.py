"""
tests/test_cli_subcommand_checker.py
Agile V verification: Helper function to check if a subcommand is valid.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.cli import is_valid_subcommand


def test_is_valid_subcommand_accepts_valid_subcommand():
    """Valid subcommand passes the check."""
    assert is_valid_subcommand("status") is True
    assert is_valid_subcommand("list") is True
    assert is_valid_subcommand("enable") is True
    assert is_valid_subcommand("disable") is True
    assert is_valid_subcommand("uninstall") is True
    assert is_valid_subcommand("install") is True
    assert is_valid_subcommand("validate") is True
    assert is_valid_subcommand("scaffold") is True
    assert is_valid_subcommand("consolidate") is True


def test_is_valid_subcommand_rejects_invalid_subcommand():
    """Invalid subcommand fails the check."""
    assert is_valid_subcommand("invalid") is False
    assert is_valid_subcommand("") is False


def test_is_valid_subcommand_handles_none():
    """None as input should return False."""
    assert is_valid_subcommand(None) is False
