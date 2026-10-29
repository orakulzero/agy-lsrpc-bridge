"""
tests/test_cli_validator_helper.py
Agile V verification: validate_subcommand_args helper function
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.cli import validate_subcommand_args


def test_validate_subcommand_args_accepts_valid_status_args():
    """Valid status subcommand passes validation."""
    args_dict = {
        "subcommand": "status",
        "address": "localhost:8080",
        "config_root": "/tmp/config",
        "workspace_uri": ["file:///workspace"],
        "json": True,
    }
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_subcommand_args_rejects_missing_subcommand():
    """Missing subcommand field fails validation."""
    args_dict = {"address": "localhost:8080"}
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is False
    assert len(result["errors"]) == 1
    assert "subcommand" in result["errors"][0].lower()


def test_validate_subcommand_args_rejects_scaffold_missing_required():
    """Scaffold subcommand without required fields fails validation."""
    args_dict = {
        "subcommand": "scaffold",
        "target_root": "/tmp/plugins",
        "json": True,
    }
    result = validate_subcommand_args(args_dict)
    assert result["valid"] is False
    assert any("name" in err.lower() for err in result["errors"])
    assert any("description" in err.lower() for err in result["errors"])
