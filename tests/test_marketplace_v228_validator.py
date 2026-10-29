"""Locked Agile V verification suite for Antigravity Marketplace v2.28.1 Validator (REQ-LSRPC-MKT-01)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
import json
from pathlib import Path
import sys
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agy_lsrpc_bridge.marketplace_v228 import (
    ALLOWED_PLUGIN_JSON_KEYS,
    MarketplaceManifestAudit,
    MarketplaceV228Validator,
)


def _write_plugin_bundle(
    base_dir: Path, dir_name: str, manifest: dict[str, Any], logo_rel_path: str | None = "assets/logo.svg"
) -> Path:
    """Create a synthetic plugin directory with optional logo file for testing."""
    plugin_dir = base_dir / dir_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    if logo_rel_path:
        logo_file = plugin_dir / logo_rel_path
        logo_file.parent.mkdir(parents=True, exist_ok=True)
        logo_file.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return plugin_dir


def test_allowed_keys_and_frozen_audit_dataclass() -> None:
    """@requirement("REQ-LSRPC-MKT-01") Verify ALLOWED_PLUGIN_JSON_KEYS and frozen MarketplaceManifestAudit."""
    expected_keys = frozenset(
        {"name", "description", "logo", "suggestedPrompts", "displayName", "version", "author", "homepage", "repository", "disabled"}
    )
    assert isinstance(ALLOWED_PLUGIN_JSON_KEYS, frozenset)
    assert ALLOWED_PLUGIN_JSON_KEYS == expected_keys
    assert is_dataclass(MarketplaceManifestAudit)

    audit = MarketplaceManifestAudit(
        valid=True,
        plugin_name="sample-plugin",
        unknown_top_level_keys=[],
        errors=[],
        warnings=[],
        prompt_count=3,
        has_valid_logo=True,
    )
    with pytest.raises(FrozenInstanceError):
        audit.valid = False  # type: ignore[misc]


def test_validate_valid_marketplace_bundle(tmp_path: Path) -> None:
    """@requirement("REQ-LSRPC-MKT-01") Verify compliant v2.28.1 plugin bundle passes validation."""
    manifest = {
        "name": "agy-sample-plugin",
        "displayName": "AGY Sample Plugin",
        "description": "Valid Antigravity v2.28.1 marketplace plugin bundle.",
        "version": "2.3.0",
        "author": "orakulzero",
        "homepage": "https://example.com",
        "repository": "https://example.com/repo.git",
        "disabled": False,
        "logo": "assets/logo.svg",
        "suggestedPrompts": ["Run audit", "Check health", "Inspect status"],
    }
    pdir = _write_plugin_bundle(tmp_path, "agy-sample-plugin", manifest)
    validator = MarketplaceV228Validator()

    audit = validator.validate_plugin_bundle(pdir)
    assert isinstance(audit, MarketplaceManifestAudit)
    assert audit.valid is True
    assert audit.plugin_name == "agy-sample-plugin"
    assert audit.unknown_top_level_keys == []
    assert audit.errors == []
    assert audit.prompt_count == 3
    assert audit.has_valid_logo is True
    assert validator.validate_plugin_bundle(str(pdir)).valid is True


def test_validate_flags_unknown_top_level_keys(tmp_path: Path) -> None:
    """@requirement("REQ-LSRPC-MKT-01") Verify unknown top-level keys in plugin.json are flagged as errors."""
    manifest = {
        "name": "valid-name",
        "description": "Valid description.",
        "logo": "assets/logo.svg",
        "suggestedPrompts": ["Prompt one", "Prompt two", "Prompt three"],
        "mcpServers": {},
        "undocumentedKey": True,
    }
    pdir = _write_plugin_bundle(tmp_path, "valid-name", manifest)
    audit = MarketplaceV228Validator().validate_plugin_bundle(pdir)
    assert audit.valid is False
    assert set(audit.unknown_top_level_keys) == {"mcpServers", "undocumentedKey"}
    assert len(audit.errors) >= 1


def test_validate_kebab_case_name_and_non_empty_description(tmp_path: Path) -> None:
    """@requirement("REQ-LSRPC-MKT-01") Verify lowercase kebab-case name and non-empty description rules."""
    validator = MarketplaceV228Validator()
    for idx, bad_name in enumerate(["Bad_Name", "CamelCase", "-leading", "trailing-", "double--dash"]):
        pdir = _write_plugin_bundle(
            tmp_path, f"bad-{idx}", {"name": bad_name, "description": "", "logo": "assets/logo.svg", "suggestedPrompts": ["One"]}
        )
        audit = validator.validate_plugin_bundle(pdir)
        assert audit.valid is False
        assert len(audit.errors) >= 2


def test_validate_logo_relative_path_extension_and_existence(tmp_path: Path) -> None:
    """@requirement("REQ-LSRPC-MKT-01") Verify logo path rejects URLs, absolute paths, bad extensions, and missing files."""
    validator = MarketplaceV228Validator()
    bad_logos = [
        "https://example.com/logo.svg",
        "http://example.com/logo.png",
        "/absolute/path/logo.png",
        "C:\\Windows\\logo.png",
        "assets/logo.gif",
        "assets/missing.webp",
    ]
    for idx, bad_logo in enumerate(bad_logos):
        pdir = _write_plugin_bundle(
            tmp_path, f"logo-{idx}", {"name": f"logo-{idx}", "description": "Test.", "logo": bad_logo, "suggestedPrompts": ["One"]}
        )
        audit = validator.validate_plugin_bundle(pdir)
        assert audit.valid is False
        assert audit.has_valid_logo is False
        assert len(audit.errors) >= 1


def test_validate_suggested_prompts_constraints(tmp_path: Path) -> None:
    """@requirement("REQ-LSRPC-MKT-01") Verify suggestedPrompts enforces 1..3 non-empty strings."""
    validator = MarketplaceV228Validator()
    for idx, bad_prompts in enumerate([[], ["a", "b", "c", "d"], ["valid", "   "]]):
        pdir = _write_plugin_bundle(
            tmp_path, f"pr-{idx}", {"name": f"pr-{idx}", "description": "Test.", "logo": "assets/logo.svg", "suggestedPrompts": bad_prompts}
        )
        audit = validator.validate_plugin_bundle(pdir)
        assert audit.valid is False
        assert len(audit.errors) >= 1

    pdir_two = _write_plugin_bundle(
        tmp_path, "pr-two", {"name": "pr-two", "description": "Two prompts.", "logo": "assets/logo.svg", "suggestedPrompts": ["A", "B"]}
    )
    audit_two = validator.validate_plugin_bundle(pdir_two)
    assert audit_two.valid is True
    assert audit_two.prompt_count == 2


def test_detect_global_name_collisions(tmp_path: Path) -> None:
    """@requirement("REQ-LSRPC-MKT-01") Verify detect_global_name_collisions returns only colliding plugin names."""
    p1 = _write_plugin_bundle(tmp_path, "hash-dir-101", {"name": "colliding-plugin", "description": "First."})
    p2 = _write_plugin_bundle(tmp_path, "hash-dir-202", {"name": "colliding-plugin", "description": "Second."})
    p3 = _write_plugin_bundle(tmp_path, "unique-dir-303", {"name": "unique-plugin", "description": "Unique."})
    collisions = MarketplaceV228Validator().detect_global_name_collisions([p1, str(p2), p3])
    assert "unique-plugin" not in collisions
    assert "colliding-plugin" in collisions
    assert sorted(collisions["colliding-plugin"]) == ["hash-dir-101", "hash-dir-202"]
