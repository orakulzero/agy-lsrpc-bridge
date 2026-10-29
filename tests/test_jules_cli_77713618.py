"""Agile V verification: `install` subcommand edge cases (agy-lsrpc-bridge)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge import cli


def test_install_parser_requires_marketplace_id():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["install"])


def test_install_parser_accepts_id_and_flags():
    parser = cli.build_parser()
    args = parser.parse_args(["install", "invalid_id_format!", "--json", "--address", "127.0.0.1:9"])
    assert args.subcommand == "install"
    assert args.marketplace_id == "invalid_id_format!"
    assert args.json is True
    assert args.address == "127.0.0.1:9"


def test_install_invalid_marketplace_id_error_handling(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, address=None, config_root=None):
            self.address = address
            self.config_root = config_root

        def install_marketplace_plugin(self, marketplace_id):
            calls.append(marketplace_id)
            # Simulate the client returning an error for an invalid marketplace ID
            return {"ok": False, "error": f"Invalid marketplace ID: {marketplace_id}", "code": 400}

    monkeypatch.setattr(cli, "LSRPCClient", FakeClient)

    # Use --json flag to test JSON output format handling
    rc = cli.main(["install", "invalid-@$#%-id", "--json"])
    
    # In cli.py it always returns 0 for install command
    assert rc == 0
    assert calls == ["invalid-@$#%-id"]
    
    # Read output and verify JSON formatting
    out = capsys.readouterr().out
    payload = json.loads(out)
    
    assert payload["ok"] is False
    assert "Invalid marketplace ID: invalid-@$#%-id" in payload["error"]
    assert payload["code"] == 400


def test_install_valid_marketplace_id(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, address=None, config_root=None):
            self.address = address
            self.config_root = config_root

        def install_marketplace_plugin(self, marketplace_id):
            calls.append(marketplace_id)
            return {"ok": True, "installed": marketplace_id}

    monkeypatch.setattr(cli, "LSRPCClient", FakeClient)

    rc = cli.main(["install", "valid-plugin-id"])
    
    assert rc == 0
    assert calls == ["valid-plugin-id"]
    
    out = capsys.readouterr().out
    payload = json.loads(out)
    
    assert payload["ok"] is True
    assert payload["installed"] == "valid-plugin-id"
