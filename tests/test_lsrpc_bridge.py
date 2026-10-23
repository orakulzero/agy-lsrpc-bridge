"""Isolated Agile V verification suite for agy-lsrpc-bridge (BL-20261023-LSRPC-L2)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def _make_sample_rpc_plugins() -> Dict[str, Any]:
    """Return a realistic raw GetAllPlugins payload with oversized skill/agent bodies."""
    return {
        "plugins": [
            {
                "name": "data-tools",
                "path": "/home/dev/.gemini/config/plugins/-1870732469773246571",
                "disabled": False,
                "isGlobal": True,
                "skills": [
                    {
                        "name": "sql-query",
                        "description": "Execute SQL queries",
                        "content": "# SQL Query\n" + ("X" * 60000),
                    }
                ],
                "agents": [
                    {
                        "name": "db-agent",
                        "description": "Database specialist",
                        "content": "# DB Agent\n" + ("Y" * 50000),
                    }
                ],
                "rules": [
                    {
                        "path": "/home/dev/.gemini/config/plugins/-1870732469773246571/rules/AGENTS.md",
                        "content": "# Rules\n" + ("Z" * 20000),
                    }
                ],
                "hooksJson": '{"hooks": {"SessionStart": []}}',
                "mcpServers": {
                    "data-tools-postgres": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-postgres"],
                    }
                },
            },
            {
                "name": "agy-core-builtin",
                "path": "/app/resources/app/extensions/antigravity/builtin/plugins/agy-core-builtin",
                "disabled": False,
                "isGlobal": True,
                "skills": [],
                "agents": [],
                "rules": [],
                "hooksJson": "",
                "mcpServers": {},
            },
        ]
    }


def test_req001_healthz_and_call_rpc(tmp_path: Path) -> None:
    """REQ-001: Verify LSRPCClient healthz() and call_rpc() request formatting and headers."""
    from agy_lsrpc_bridge.client import LSRPCClient

    calls: List[Tuple[str, str, Dict[str, str], Optional[Dict[str, Any]]]] = []

    def mock_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        calls.append((method, url, headers, json_body))
        if url.endswith("/healthz"):
            return {"status": "ok"}
        return {"plugins": []}

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-secret-token",
        config_root=tmp_path,
        transport=mock_transport,
    )

    health = client.healthz()
    assert health["ok"] is True
    assert health["address"] == "127.0.0.1:42100"
    assert health["live_rpc"] is True
    assert calls[0][0] == "GET"
    assert calls[0][1] == "http://127.0.0.1:42100/healthz"

    rpc_res = client.call_rpc("GetAllPlugins", {"workspaceUris": ["file:///workspace"]})
    assert rpc_res == {"plugins": []}
    assert calls[1][0] == "POST"
    assert (
        calls[1][1]
        == "http://127.0.0.1:42100/exa.language_server_pb.LanguageServerService/GetAllPlugins"
    )
    assert calls[1][2].get("x-codeium-csrf-token") == "csrf-secret-token"
    assert calls[1][3] == {"workspaceUris": ["file:///workspace"]}


def test_req001_list_plugins_context_compaction(tmp_path: Path) -> None:
    """REQ-001: Verify list_plugins() strips 50KB+ skill/agent/rule bodies into compact metadata."""
    from agy_lsrpc_bridge.client import LSRPCClient

    def mock_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        return _make_sample_rpc_plugins()

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-secret-token",
        config_root=tmp_path,
        transport=mock_transport,
    )

    items = client.list_plugins(workspace_uris=["file:///workspace"])
    assert len(items) == 2

    first = items[0]
    assert first["name"] == "data-tools"
    assert first["dir"] == "-1870732469773246571"
    assert first["disabled"] is False
    assert first["isGlobal"] is True
    assert first["isBuiltin"] is False
    assert first["skills"] == ["sql-query"]
    assert first["agents"] == ["db-agent"]
    assert first["rules"] == [
        "/home/dev/.gemini/config/plugins/-1870732469773246571/rules/AGENTS.md"
    ]
    assert first["hooks"] is True
    assert first["mcp"] == ["data-tools-postgres"]
    assert first["customizationLink"] == "[data-tools](customization://-1870732469773246571)"

    second = items[1]
    assert second["name"] == "agy-core-builtin"
    assert second["dir"] == "agy-core-builtin"
    assert second["isBuiltin"] is True
    assert second["hooks"] is False

    serialized = json.dumps(items)
    assert len(serialized) < 2000
    assert "XXXXX" not in serialized
    assert "YYYYY" not in serialized


def test_req001_list_plugins_offline_fallback(tmp_path: Path) -> None:
    """REQ-001: Verify offline filesystem fallback when Language Server RPC is unreachable."""
    from agy_lsrpc_bridge.client import LSRPCClient

    plugin_dir = tmp_path / "plugins" / "-999888777"
    (plugin_dir / "skills" / "offline-skill").mkdir(parents=True)
    (plugin_dir / "agents").mkdir(parents=True)
    (plugin_dir / "rules").mkdir(parents=True)

    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "offline-tool", "description": "Offline fallback plugin"}),
        encoding="utf-8",
    )
    (plugin_dir / "skills" / "offline-skill" / "SKILL.md").write_text(
        "---\nname: offline-skill\ndescription: test\n---\n# Offline Skill\n",
        encoding="utf-8",
    )
    (plugin_dir / "agents" / "offline-agent.md").write_text(
        "---\ndescription: test agent\n---\n# Agent\n",
        encoding="utf-8",
    )
    (plugin_dir / "rules" / "AGENTS.md").write_text("# Offline rule\n", encoding="utf-8")
    (plugin_dir / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")
    (plugin_dir / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"offline-tool-srv": {"command": "node"}}}),
        encoding="utf-8",
    )
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "plugins": {"-999888777": {"enabled": False}},
                "userSettings": {"theme": "dark"},
            }
        ),
        encoding="utf-8",
    )

    def failing_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        raise ConnectionError("Language Server unreachable")

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-token",
        config_root=tmp_path,
        transport=failing_transport,
    )

    items = client.list_plugins()
    assert len(items) == 1
    item = items[0]
    assert item["name"] == "offline-tool"
    assert item["dir"] == "-999888777"
    assert item["disabled"] is True
    assert item["isGlobal"] is True
    assert item["isBuiltin"] is False
    assert item["skills"] == ["offline-skill"]
    assert item["agents"] == ["offline-agent"]
    assert len(item["rules"]) == 1
    assert item["hooks"] is True
    assert item["mcp"] == ["offline-tool-srv"]
    assert item["customizationLink"] == "[offline-tool](customization://-999888777)"


def test_req002_resolve_plugin_dir_by_name_and_dir(tmp_path: Path) -> None:
    """REQ-002: Verify resolve_plugin_dir resolves by exact dir or display name and raises on missing."""
    from agy_lsrpc_bridge.client import LSRPCClient

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-token",
        config_root=tmp_path,
        transport=lambda m, u, h, b: _make_sample_rpc_plugins(),
    )

    by_name = client.resolve_plugin_dir("data-tools")
    assert by_name["dir"] == "-1870732469773246571"
    assert by_name["name"] == "data-tools"

    by_dir = client.resolve_plugin_dir("-1870732469773246571")
    assert by_dir["dir"] == "-1870732469773246571"
    assert by_dir["name"] == "data-tools"

    with pytest.raises(ValueError):
        client.resolve_plugin_dir("non-existent-plugin")


def test_req002_set_plugin_enabled_uses_true_dir_and_preserves_config(tmp_path: Path) -> None:
    """REQ-002: Verify set_plugin_enabled keys JetboxWriteState by true dir and preserves config.json."""
    from agy_lsrpc_bridge.client import LSRPCClient

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"userSettings": {"editorFontSize": 14}, "plugins": {}}),
        encoding="utf-8",
    )

    rpc_calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def mock_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        endpoint = url.rsplit("/", 1)[-1]
        rpc_calls.append((endpoint, json_body))
        if endpoint == "GetAllPlugins":
            return _make_sample_rpc_plugins()
        return {}

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-token",
        config_root=tmp_path,
        transport=mock_transport,
    )

    res = client.set_plugin_enabled("data-tools", False)
    assert res["ok"] is True
    assert res["dir"] == "-1870732469773246571"
    assert res["name"] == "data-tools"
    assert res["enabled"] is False
    assert res["restart_required"] is False
    assert res["customizationLink"] == "[data-tools](customization://-1870732469773246571)"

    jetbox_calls = [c for c in rpc_calls if c[0] == "JetboxWriteState"]
    assert len(jetbox_calls) == 1
    assert jetbox_calls[0][1] == {
        "userConfig": {"plugins": {"-1870732469773246571": {"enabled": False}}}
    }

    updated_cfg = json.loads(config_file.read_text(encoding="utf-8"))
    assert updated_cfg["userSettings"] == {"editorFontSize": 14}
    assert updated_cfg["plugins"]["-1870732469773246571"] == {"enabled": False}


def test_req002_uninstall_builtin_plugin_raises_permission_error(tmp_path: Path) -> None:
    """REQ-002: Verify Guard 1 blocks uninstalling built-in plugins with PermissionError."""
    from agy_lsrpc_bridge.client import LSRPCClient

    rpc_calls: List[str] = []

    def mock_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        endpoint = url.rsplit("/", 1)[-1]
        rpc_calls.append(endpoint)
        return _make_sample_rpc_plugins()

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-token",
        config_root=tmp_path,
        transport=mock_transport,
    )

    with pytest.raises(PermissionError):
        client.uninstall_plugin("agy-core-builtin")

    assert "DeletePlugin" not in rpc_calls


def test_req002_uninstall_disabled_plugin_reenables_before_delete(tmp_path: Path) -> None:
    """REQ-002: Verify Guard 2 re-enables a disabled plugin via JetboxWriteState before DeletePlugin."""
    from agy_lsrpc_bridge.client import LSRPCClient

    payload = _make_sample_rpc_plugins()
    payload["plugins"][0]["disabled"] = True

    rpc_calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def mock_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        endpoint = url.rsplit("/", 1)[-1]
        rpc_calls.append((endpoint, json_body))
        if endpoint == "GetAllPlugins":
            return payload
        return {}

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-token",
        config_root=tmp_path,
        transport=mock_transport,
    )

    res = client.uninstall_plugin("data-tools")
    assert res["ok"] is True
    assert res["dir"] == "-1870732469773246571"
    assert res["reenabled_before_delete"] is True
    assert res["deleted"] is True

    mutation_calls = [c for c in rpc_calls if c[0] in ("JetboxWriteState", "DeletePlugin")]
    assert len(mutation_calls) == 2
    assert mutation_calls[0] == (
        "JetboxWriteState",
        {"userConfig": {"plugins": {"-1870732469773246571": {"enabled": True}}}},
    )
    assert mutation_calls[1] == (
        "DeletePlugin",
        {"pluginId": "-1870732469773246571"},
    )


def test_req002_install_marketplace_plugin_and_error_handling(tmp_path: Path) -> None:
    """REQ-002: Verify install_marketplace_plugin validates id and handles missing source errors."""
    from agy_lsrpc_bridge.client import LSRPCClient

    def ok_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        assert url.endswith("/InstallCustomization")
        assert json_body == {"id": "mp-98765"}
        return {}

    client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-token",
        config_root=tmp_path,
        transport=ok_transport,
    )

    with pytest.raises(ValueError):
        client.install_marketplace_plugin("")

    res = client.install_marketplace_plugin("mp-98765")
    assert res["ok"] is True
    assert res["id"] == "mp-98765"
    assert res["restart_required"] is True

    def missing_source_transport(
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        raise RuntimeError("rpc error: code = Unknown desc = source for customization not found")

    bad_client = LSRPCClient(
        address="127.0.0.1:42100",
        csrf_token="csrf-token",
        config_root=tmp_path,
        transport=missing_source_transport,
    )

    try:
        err_res = bad_client.install_marketplace_plugin("invalid-mp-id")
        assert err_res["ok"] is False
        assert "marketplace" in err_res.get("error", "").lower()
    except (RuntimeError, ValueError) as exc:
        assert "marketplace" in str(exc).lower() or "source for customization not found" in str(exc).lower()


def test_req003_validate_valid_plugin_with_jsonc(tmp_path: Path) -> None:
    """REQ-003: Verify validate_plugin_bundle accepts valid JSONC plugin.json and components."""
    from agy_lsrpc_bridge.validator import validate_plugin_bundle

    pdir = tmp_path / "sample-plugin"
    (pdir / "assets").mkdir(parents=True)
    (pdir / "rules").mkdir(parents=True)
    (pdir / "skills" / "sample-plugin").mkdir(parents=True)
    (pdir / "agents").mkdir(parents=True)

    (pdir / "assets" / "logo.svg").write_text("<svg></svg>", encoding="utf-8")
    (pdir / "plugin.json").write_text(
        """{
  // JSONC comment allowed in plugin manifest
  "name": "sample-plugin",
  "displayName": "Sample Plugin",
  "description": "Valid bundle with JSONC",
  "version": "0.1.0",
  "logo": "assets/logo.svg",
  "suggestedPrompts": [
    "Run sample check",
    "Inspect sample status",
  ],
}""",
        encoding="utf-8",
    )
    (pdir / "rules" / "AGENTS.md").write_text(
        "# Sample Operational Rules\n\n1. Keep everything deterministic.\n",
        encoding="utf-8",
    )
    (pdir / "skills" / "sample-plugin" / "SKILL.md").write_text(
        "---\nname: sample-plugin\ndescription: Sample skill\n---\n# Skill\n",
        encoding="utf-8",
    )
    (pdir / "agents" / "sample-plugin-agent.md").write_text(
        "---\ndescription: Sample agent\n---\n# Agent\n",
        encoding="utf-8",
    )
    (pdir / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")
    (pdir / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"sample-plugin-server": {"command": "node"}}}),
        encoding="utf-8",
    )

    res = validate_plugin_bundle(pdir)
    assert res["valid"] is True
    assert res["errors"] == []
    assert res["plugin_name"] == "sample-plugin"
    assert res["dir_name"] == "sample-plugin"


def test_req003_validate_rejects_unknown_keys_and_bad_prompts(tmp_path: Path) -> None:
    """REQ-003: Verify validator rejects unknown top-level keys, remote logos, and >3 suggestedPrompts."""
    from agy_lsrpc_bridge.validator import validate_plugin_bundle

    pdir = tmp_path / "bad-manifest-plugin"
    pdir.mkdir(parents=True)
    (pdir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "bad-manifest-plugin",
                "description": "Invalid manifest fields",
                "author": "Forbidden Author Key",
                "homepage": "https://example.com",
                "logo": "https://example.com/logo.svg",
                "suggestedPrompts": ["one", "two", "three", "four"],
            }
        ),
        encoding="utf-8",
    )

    res = validate_plugin_bundle(pdir)
    assert res["valid"] is False
    joined_errors = " | ".join(res["errors"])
    assert "author" in joined_errors
    assert "homepage" in joined_errors
    assert "logo" in joined_errors
    assert "suggestedPrompts" in joined_errors


def test_req003_validate_catches_nested_hooks_frontmatter_rules_and_unprefixed_mcp(
    tmp_path: Path,
) -> None:
    """REQ-003: Verify validator catches hooks/hooks.json trap, YAML frontmatter in rules, and unprefixed MCP keys."""
    from agy_lsrpc_bridge.validator import validate_plugin_bundle

    pdir = tmp_path / "trap-plugin"
    (pdir / "hooks").mkdir(parents=True)
    (pdir / "rules").mkdir(parents=True)

    (pdir / "plugin.json").write_text(
        json.dumps({"name": "trap-plugin", "description": "Plugin with structural traps"}),
        encoding="utf-8",
    )
    (pdir / "hooks" / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")
    (pdir / "rules" / "AGENTS.md").write_text(
        "---\ntrigger: always_on\n---\n# Bad Frontmatter Rule\n",
        encoding="utf-8",
    )
    (pdir / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"unprefixed-server": {"command": "node"}}}),
        encoding="utf-8",
    )

    res = validate_plugin_bundle(pdir)
    assert res["valid"] is False
    assert len(res["errors"]) >= 3
    joined_errors = " | ".join(res["errors"])
    assert "hooks.json" in joined_errors
    assert "frontmatter" in joined_errors.lower() or "---" in joined_errors
    assert "unprefixed-server" in joined_errors


def test_req004_scaffold_plugin_passes_validator(tmp_path: Path) -> None:
    """REQ-004: Verify scaffold_plugin generates a compliant Antigravity 2.0 plugin bundle."""
    from agy_lsrpc_bridge.scaffolder import scaffold_plugin
    from agy_lsrpc_bridge.validator import validate_plugin_bundle

    pdir = scaffold_plugin(
        target_root=tmp_path,
        name="test-kit",
        description="Automated test kit plugin",
        display_name="Test Kit",
        include_hooks=True,
        include_mcp=True,
    )

    assert pdir == tmp_path / "test-kit"
    assert (pdir / "plugin.json").is_file()
    assert (pdir / "README.md").is_file()
    assert (pdir / "assets" / "logo.svg").is_file()
    assert (pdir / "rules" / "AGENTS.md").is_file()
    assert (pdir / "skills" / "test-kit" / "SKILL.md").is_file()
    assert (pdir / "agents" / "test-kit-agent.md").is_file()
    assert (pdir / "hooks.json").is_file()
    assert (pdir / "mcp_config.json").is_file()

    validation = validate_plugin_bundle(pdir)
    assert validation["valid"] is True
    assert validation["errors"] == []


def test_req004_consolidate_loose_customizations_strips_rule_frontmatter(tmp_path: Path) -> None:
    """REQ-004: Verify consolidate_loose_customizations imports loose skills and strips rule frontmatter."""
    from agy_lsrpc_bridge.scaffolder import consolidate_loose_customizations, scaffold_plugin
    from agy_lsrpc_bridge.validator import validate_plugin_bundle

    pdir = scaffold_plugin(
        target_root=tmp_path / "out",
        name="merged-pack",
        description="Consolidated plugin bundle",
    )

    loose_skill = tmp_path / "loose" / "extra-skill"
    loose_skill.mkdir(parents=True)
    (loose_skill / "SKILL.md").write_text(
        "---\nname: extra-skill\ndescription: Extra loose skill\n---\n# Extra Skill\n",
        encoding="utf-8",
    )

    loose_rule = tmp_path / "loose" / "extra-rule.md"
    loose_rule.write_text(
        "---\ntrigger: always_on\ndescription: Loose rule\n---\n# Consolidated Extra Rule\nKeep outputs concise.\n",
        encoding="utf-8",
    )

    result = consolidate_loose_customizations(
        plugin_dir=pdir,
        skill_dirs=[loose_skill],
        rule_files=[loose_rule],
    )
    assert result["ok"] is True
    assert "extra-skill" in result["consolidated_skills"]
    assert (pdir / "skills" / "extra-skill" / "SKILL.md").is_file()

    agents_md = (pdir / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert not agents_md.lstrip().startswith("---")
    assert "# Consolidated Extra Rule" in agents_md
    assert "Keep outputs concise." in agents_md

    validation = validate_plugin_bundle(pdir)
    assert validation["valid"] is True


def test_req005_cli_scaffold_validate_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """REQ-005: Verify CLI subcommands scaffold, validate, and status --json."""
    from agy_lsrpc_bridge.cli import main as cli_main

    rc_scaffold = cli_main(
        [
            "scaffold",
            "--target-root",
            str(tmp_path),
            "--name",
            "cli-bundle",
            "--description",
            "Bundle created by CLI",
            "--include-hooks",
            "--include-mcp",
            "--json",
        ]
    )
    assert rc_scaffold == 0
    out_scaffold = json.loads(capsys.readouterr().out)
    assert out_scaffold["ok"] is True

    rc_validate = cli_main(["validate", str(tmp_path / "cli-bundle"), "--json"])
    assert rc_validate == 0
    out_validate = json.loads(capsys.readouterr().out)
    assert out_validate["valid"] is True

    rc_status = cli_main(["status", "--config-root", str(tmp_path), "--json"])
    assert rc_status == 0
    out_status = json.loads(capsys.readouterr().out)
    assert "plugins" in out_status


def test_req005_repo_self_hosted_skill_and_plugin_bundle() -> None:
    """REQ-005: Verify repository ships valid self-hosted skill, plugin bundle, and MIT LICENSE."""
    from agy_lsrpc_bridge.validator import validate_plugin_bundle

    skill_md = REPO_ROOT / ".agents" / "skills" / "agy-lsrpc-bridge" / "SKILL.md"
    assert skill_md.is_file()

    plugin_dir = REPO_ROOT / "plugins" / "agy-lsrpc-bridge"
    assert (plugin_dir / "plugin.json").is_file()
    res = validate_plugin_bundle(plugin_dir)
    assert res["valid"] is True, f"Self-hosted plugin bundle invalid: {res['errors']}"

    license_file = REPO_ROOT / "LICENSE"
    assert license_file.is_file()
    assert "MIT License" in license_file.read_text(encoding="utf-8")


def test_req005_oss_five_gate_hygiene_zero_cyrillic_and_zero_pii() -> None:
    """REQ-005: Verify zero Cyrillic characters and zero personal identifiers across tracked files."""
    cyrillic_re = re.compile(r"[\u0400-\u04FF]")
    forbidden_tokens = [
        "Ora" + "kul" + " " + "Gr" + "ey",
        "Ora" + "kul",
        "ANTI" + "GRAVITY",
        "kuro" + "ora" + "kul" + "grey",
    ]
    ignored_dirs = {".git", ".pytest_cache", "__pycache__", ".supergraph", ".venv"}

    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignored_dirs for part in path.parts):
            continue
        if path.suffix.lower() in {".pyc", ".png", ".jpg", ".jpeg", ".webp", ".ico"}:
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(REPO_ROOT)
        assert cyrillic_re.search(text) is None, f"Cyrillic characters found in {rel}"
        for token in forbidden_tokens:
            assert token not in text, f"Forbidden token found in {rel}"
