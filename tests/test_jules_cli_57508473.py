"""Test _emit function handles non-serializable objects in the payload."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.cli import _emit


def test_emit_serializable_dict(capsys):
    payload = {"status": "ok", "count": 42}
    _emit(payload, as_json=True)
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == {"status": "ok", "count": 42}


def test_emit_serializable_list(capsys):
    payload = [1, 2, 3, "test"]
    _emit(payload, as_json=True)
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == [1, 2, 3, "test"]


def test_emit_non_serializable_object_raises_typeerror(capsys):
    class NonSerializable:
        def __init__(self):
            self.data = "internal"
    
    payload = {"result": NonSerializable()}
    with pytest.raises(TypeError, match="Object of type NonSerializable is not JSON serializable"):
        _emit(payload, as_json=True)


def test_emit_non_serializable_set_raises_typeerror(capsys):
    payload = {"items": {1, 2, 3}}
    with pytest.raises(TypeError, match="Object of type set is not JSON serializable"):
        _emit(payload, as_json=True)


def test_emit_nested_non_serializable_raises_typeerror(capsys):
    payload = {"outer": {"inner": Path("/tmp/test")}}
    with pytest.raises(TypeError, match="Object of type .*Path.* is not JSON serializable"):
        _emit(payload, as_json=True)


def test_emit_unicode_characters(capsys):
    payload = {"message": "Hello 世界 🌍"}
    _emit(payload, as_json=True)
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["message"] == "Hello 世界 🌍"
