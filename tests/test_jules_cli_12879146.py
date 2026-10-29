"""Agile V verification: `disable` subcommand edge cases (agy-lsrpc-bridge)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge import cli


def test_disable_parser_requires_target():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["disable"])


def test_disable_parser_accepts_target_and_flags():
    parser = cli.build_parser()
    args = parser.parse_args(["disable", "my-plugin", "--json", "--address", "127.0.0.1:9"])
    assert args.subcommand == "disable"
    assert args.target == "my-plugin"
    assert args.json is True
    assert args.address == "127.0.0.1:9"


def test_disable_invokes_set_plugin_enabled_false(monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, address=None, config_root=None):
            self.address = address
            self.config_root = config_root

        def set_plugin_enabled(self, target, enabled):
            calls.append((target, enabled))
            return {"ok": True, "target": target, "enabled": enabled}

    monkeypatch.setattr(cli, "LSRPCClient", FakeClient)

    rc = cli.main(["disable", "edge-case-plugin", "--json"])
    assert rc == 0
    assert calls == [("edge-case-plugin", False)]
    payload = json.loads(capsys.readouterr().out)
    assert payload["enabled"] is False
    assert payload["target"] == "edge-case-plugin"


def test_disable_edge_case_dir_target_json(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, address=None, config_root=None):
            pass

        def set_plugin_enabled(self, target, enabled):
            return {"ok": False, "target": target, "enabled": enabled, "error": f"Plugin directory '{target}' does not exist"}

    monkeypatch.setattr(cli, "LSRPCClient", FakeClient)

    rc = cli.main(["disable", "/does/not/exist", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error"] == "Plugin directory '/does/not/exist' does not exist"

def test_disable_edge_case_dir_target_non_json(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, address=None, config_root=None):
            pass

        def set_plugin_enabled(self, target, enabled):
            return {"ok": False, "target": target, "enabled": enabled, "error": f"Plugin directory '{target}' does not exist"}

    monkeypatch.setattr(cli, "LSRPCClient", FakeClient)

    rc = cli.main(["disable", "/does/not/exist"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error"] == "Plugin directory '/does/not/exist' does not exist"
