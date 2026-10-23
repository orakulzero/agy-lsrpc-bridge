"""
src/agy_lsrpc_bridge/validator.py
Spec-compliant Antigravity 2.0 Plugin Bundle Validator.
Enforces:
1. Valid JSON / JSONC manifest (`plugin.json`) with strictly allowed top-level fields.
2. Root-level `hooks.json` placement (catching the `hooks/hooks.json` native plugin trap).
3. Relative logo asset path ending in `.svg`, `.png`, `.jpg`, `.jpeg`, or `.webp` and existing on disk.
4. `suggestedPrompts` array with at most 3 non-empty strings.
5. `rules/AGENTS.md` without YAML frontmatter (`---`).
6. `mcp_config.json` server keys prefixed with `<plugin_name>` and `<64`-char constraint.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

ALLOWED_PLUGIN_MANIFEST_KEYS: Set[str] = {
    "name",
    "displayName",
    "description",
    "version",
    "logo",
    "suggestedPrompts",
    "disabled",
}

ALLOWED_LOGO_EXTENSIONS: Set[str] = {".svg", ".png", ".jpg", ".jpeg", ".webp"}


def parse_jsonc(raw_text: str) -> Any:
    """Parse JSON with single-line (//), block (/* */) comments and trailing commas."""
    # Remove single-line comments not inside strings
    out_chars: List[str] = []
    in_str = False
    escape = False
    i = 0
    n = len(raw_text)
    while i < n:
        ch = raw_text[i]
        if in_str:
            out_chars.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
        else:
            if ch == '"':
                in_str = True
                out_chars.append(ch)
                i += 1
            elif ch == "/" and i + 1 < n and raw_text[i + 1] == "/":
                i += 2
                while i < n and raw_text[i] not in ("\n", "\r"):
                    i += 1
            elif ch == "/" and i + 1 < n and raw_text[i + 1] == "*":
                i += 2
                while i + 1 < n and not (raw_text[i] == "*" and raw_text[i + 1] == "/"):
                    i += 1
                i += 2
            else:
                out_chars.append(ch)
                i += 1

    no_comments = "".join(out_chars)
    no_trailing_commas = re.sub(r",\s*([\]}])", r"\1", no_comments)
    return json.loads(no_trailing_commas)


def validate_plugin_bundle(
    plugin_dir: Path,
    installed_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Audit an Antigravity 2.0 plugin directory against all loader and runtime rules."""
    pdir = Path(plugin_dir).resolve()
    errors: List[str] = []
    warnings: List[str] = []
    dir_name = pdir.name
    plugin_name = dir_name

    manifest_path = pdir / "plugin.json"
    if not manifest_path.is_file():
        errors.append(f"Missing required plugin.json at {manifest_path}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "plugin_name": plugin_name,
            "dir_name": dir_name,
        }

    try:
        manifest = parse_jsonc(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            errors.append("plugin.json root must be a JSON object")
            manifest = {}
    except Exception as exc:
        errors.append(f"Invalid JSON/JSONC in plugin.json: {exc}")
        manifest = {}

    # 1. Check top-level fields
    for key in manifest:
        if key not in ALLOWED_PLUGIN_MANIFEST_KEYS:
            errors.append(
                f"Disallowed top-level key '{key}' in plugin.json "
                f"(allowed: {sorted(ALLOWED_PLUGIN_MANIFEST_KEYS)})"
            )

    raw_name = manifest.get("name")
    if raw_name is not None:
        if not isinstance(raw_name, str) or not raw_name.strip():
            errors.append("Field 'name' in plugin.json must be a non-empty string")
        else:
            plugin_name = raw_name.strip()

    if installed_names and plugin_name in installed_names:
        warnings.append(
            f"Plugin name '{plugin_name}' collides with an already installed plugin name"
        )

    # 2. Check logo path and extension
    logo_val = manifest.get("logo")
    if logo_val is not None:
        if not isinstance(logo_val, str) or not logo_val.strip():
            errors.append("Field 'logo' in plugin.json must be a non-empty relative path")
        else:
            logo_str = logo_val.strip()
            if (
                logo_str.startswith("http://")
                or logo_str.startswith("https://")
                or Path(logo_str).is_absolute()
                or logo_str.startswith("/")
                or logo_str.startswith("\\")
            ):
                errors.append(
                    f"Field 'logo' ('{logo_str}') must be a relative path inside the plugin directory, not a URL or absolute path"
                )
            else:
                ext = Path(logo_str).suffix.lower()
                if ext not in ALLOWED_LOGO_EXTENSIONS:
                    errors.append(
                        f"Field 'logo' ('{logo_str}') must end with one of {sorted(ALLOWED_LOGO_EXTENSIONS)}"
                    )
                logo_file = pdir / logo_str
                if not logo_file.is_file():
                    errors.append(f"Logo file referenced in plugin.json does not exist: {logo_str}")

    # 3. Check suggestedPrompts (<= 3 non-empty strings)
    prompts = manifest.get("suggestedPrompts")
    if prompts is not None:
        if not isinstance(prompts, list):
            errors.append("Field 'suggestedPrompts' must be a list of strings")
        else:
            if len(prompts) > 3:
                errors.append(
                    f"Field 'suggestedPrompts' has {len(prompts)} entries; maximum allowed is 3"
                )
            for idx, item in enumerate(prompts):
                if not isinstance(item, str) or not item.strip():
                    errors.append(
                        f"Field 'suggestedPrompts[{idx}]' must be a non-empty string"
                    )

    # 4. Check hooks.json placement (must be at plugin root, not stranded in hooks/hooks.json)
    nested_hooks = pdir / "hooks" / "hooks.json"
    root_hooks = pdir / "hooks.json"
    if nested_hooks.is_file() and not root_hooks.is_file():
        errors.append(
            "Native plugins must place hooks.json at the plugin root (<plugin_dir>/hooks.json), not inside hooks/hooks.json"
        )
    if root_hooks.is_file():
        try:
            parse_jsonc(root_hooks.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Invalid JSON in root hooks.json: {exc}")

    # 5. Check rules/AGENTS.md has no YAML frontmatter
    rules_dir = pdir / "rules"
    if rules_dir.is_dir():
        for rule_file in rules_dir.glob("*.md"):
            content = rule_file.read_text(encoding="utf-8", errors="ignore").lstrip()
            if content.startswith("---"):
                errors.append(
                    f"Rule file 'rules/{rule_file.name}' must be plain markdown without YAML frontmatter ('---')"
                )

    # 6. Check mcp_config.json server names are prefixed with plugin_name
    mcp_path = pdir / "mcp_config.json"
    if mcp_path.is_file():
        try:
            mcp_data = parse_jsonc(mcp_path.read_text(encoding="utf-8"))
            servers = (mcp_data or {}).get("mcpServers") or {}
            if not isinstance(servers, dict):
                errors.append("mcp_config.json 'mcpServers' must be an object")
            else:
                for srv_name in servers:
                    if not str(srv_name).startswith(plugin_name):
                        errors.append(
                            f"MCP server '{srv_name}' in mcp_config.json must be prefixed with plugin name '{plugin_name}' to avoid global namespace collisions"
                        )
                    if len(str(srv_name)) > 48:
                        warnings.append(
                            f"MCP server '{srv_name}' is {len(str(srv_name))} chars; keep short so mcp_<server>_<tool> stays under 64 chars"
                        )
        except Exception as exc:
            errors.append(f"Invalid JSON in mcp_config.json: {exc}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "plugin_name": plugin_name,
        "dir_name": dir_name,
    }
