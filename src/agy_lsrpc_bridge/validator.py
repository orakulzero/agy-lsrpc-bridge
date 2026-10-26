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

import copy
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

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
VALID_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_.\-:]+$")
MAX_COMPOSITE_LEN = 64


def validate_mcp_config_strict(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Strictly validate MCP configuration enforcing <=64-char names and timeout_ms > 0."""
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    if not isinstance(servers, dict):
        return False, ["mcp_config.json 'mcpServers' must be an object"]

    errors: List[str] = []
    for orig_srv, srv_cfg in servers.items():
        srv_str = str(orig_srv)
        if not isinstance(srv_cfg, dict):
            errors.append(f"Server '{srv_str}' configuration must be an object")
            continue

        timeout_val = srv_cfg.get("timeout_ms")
        if not isinstance(timeout_val, int) or isinstance(timeout_val, bool) or timeout_val <= 0:
            errors.append(f"Server '{srv_str}' is missing a positive integer 'timeout_ms'.")

        tools = srv_cfg.get("tools")
        tool_names: List[str] = []
        if isinstance(tools, list):
            tool_names = [str(t) for t in tools]
        elif isinstance(tools, dict):
            tool_names = [str(t) for t in tools.keys()]

        if tool_names:
            for tool_name in tool_names:
                composite = f"mcp_{srv_str}_{tool_name}"
                if not VALID_IDENTIFIER_RE.match(composite):
                    errors.append(f"Identifier '{composite}' contains invalid characters.")
                if len(composite) > MAX_COMPOSITE_LEN:
                    errors.append(
                        f"Identifier '{composite}' exceeds 64 characters (length: {len(composite)})."
                    )
        else:
            if not VALID_IDENTIFIER_RE.match(f"mcp_{srv_str}"):
                errors.append(f"Server '{srv_str}' contains invalid characters.")
            if len(f"mcp_{srv_str}_") >= MAX_COMPOSITE_LEN:
                errors.append(
                    f"Server prefix 'mcp_{srv_str}_' exceeds or equals 64 characters."
                )

    return len(errors) == 0, errors


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
    strict_mcp: bool = False,
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

    # 6. Check mcp_config.json server names are prefixed with plugin_name, timeout_ms, and <=64-char limit
    mcp_path = pdir / "mcp_config.json"
    if mcp_path.is_file():
        try:
            mcp_data = parse_jsonc(mcp_path.read_text(encoding="utf-8"))
            servers = (mcp_data or {}).get("mcpServers") or {}
            if not isinstance(servers, dict):
                errors.append("mcp_config.json 'mcpServers' must be an object")
            else:
                for srv_name, srv_cfg in servers.items():
                    srv_str = str(srv_name)
                    if not srv_str.startswith(plugin_name):
                        errors.append(
                            f"MCP server '{srv_name}' in mcp_config.json must be prefixed with plugin name '{plugin_name}' to avoid global namespace collisions"
                        )
                    if len(srv_str) > 48:
                        warnings.append(
                            f"MCP server '{srv_name}' is {len(srv_str)} chars; keep short so mcp_<server>_<tool> stays under 64 chars"
                        )
                    if isinstance(srv_cfg, dict):
                        timeout_val = srv_cfg.get("timeout_ms")
                        if timeout_val is None:
                            if strict_mcp:
                                errors.append(
                                    f"Server '{srv_name}' is missing a positive integer 'timeout_ms'."
                                )
                            else:
                                warnings.append(
                                    f"Server '{srv_name}' is missing recommended 'timeout_ms'."
                                )
                        elif not isinstance(timeout_val, int) or isinstance(timeout_val, bool) or timeout_val <= 0:
                            errors.append(
                                f"Server '{srv_name}' 'timeout_ms' must be a positive integer, got {timeout_val!r}."
                            )

                        tools = srv_cfg.get("tools")
                        tool_names: List[str] = []
                        if isinstance(tools, list):
                            tool_names = [str(t) for t in tools]
                        elif isinstance(tools, dict):
                            tool_names = [str(t) for t in tools.keys()]

                        for tname in tool_names:
                            comp = f"mcp_{srv_str}_{tname}"
                            if not VALID_IDENTIFIER_RE.match(comp):
                                errors.append(f"Identifier '{comp}' contains invalid characters.")
                            if len(comp) > MAX_COMPOSITE_LEN:
                                errors.append(
                                    f"Identifier '{comp}' exceeds 64 characters (length: {len(comp)})."
                                )
                if strict_mcp:
                    ok_strict, strict_errs = validate_mcp_config_strict(mcp_data)
                    for serr in strict_errs:
                        if serr not in errors:
                            errors.append(serr)
        except Exception as exc:
            errors.append(f"Invalid JSON in mcp_config.json: {exc}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "plugin_name": plugin_name,
        "dir_name": dir_name,
    }


def analyze_mcp_token_budget(
    config: Union[Dict[str, Any], Path, str],
    max_token_budget: int = 8000,
) -> Dict[str, Any]:
    """
    Analyze token budget and footprint for an MCP configuration, file path, or JSON string.
    Computes estimated token footprint per server / tool (~4 chars per token),
    flags servers/tools exceeding thresholds or the 64-char composite name limit,
    and returns actionable optimization recommendations.
    """
    raw_data: Any = None
    if isinstance(config, Path):
        if not config.is_file():
            return {
                "total_estimated_tokens": 0,
                "budget_limit": max_token_budget,
                "within_budget": False,
                "servers": {},
                "recommendations": [f"Configuration file not found: {config}"],
            }
        try:
            raw_data = parse_jsonc(config.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "total_estimated_tokens": 0,
                "budget_limit": max_token_budget,
                "within_budget": False,
                "servers": {},
                "recommendations": [f"Malformed JSON in configuration file: {exc}"],
            }
    elif isinstance(config, str):
        is_path = False
        try:
            p = Path(config)
            if p.is_file():
                is_path = True
                try:
                    raw_data = parse_jsonc(p.read_text(encoding="utf-8"))
                except Exception as exc:
                    return {
                        "total_estimated_tokens": 0,
                        "budget_limit": max_token_budget,
                        "within_budget": False,
                        "servers": {},
                        "recommendations": [f"Malformed JSON in configuration file: {exc}"],
                    }
        except Exception:
            is_path = False

        if not is_path:
            stripped = config.strip()
            if not stripped:
                return {
                    "total_estimated_tokens": 0,
                    "budget_limit": max_token_budget,
                    "within_budget": True,
                    "servers": {},
                    "recommendations": ["Empty configuration provided."],
                }
            try:
                raw_data = parse_jsonc(stripped)
            except Exception as exc:
                return {
                    "total_estimated_tokens": 0,
                    "budget_limit": max_token_budget,
                    "within_budget": False,
                    "servers": {},
                    "recommendations": [f"Malformed JSON configuration: {exc}"],
                }
    elif isinstance(config, dict):
        raw_data = config
    elif config is None:
        return {
            "total_estimated_tokens": 0,
            "budget_limit": max_token_budget,
            "within_budget": True,
            "servers": {},
            "recommendations": ["Empty configuration provided."],
        }
    else:
        return {
            "total_estimated_tokens": 0,
            "budget_limit": max_token_budget,
            "within_budget": False,
            "servers": {},
            "recommendations": [f"Invalid configuration type: {type(config).__name__}"],
        }

    if not isinstance(raw_data, dict):
        return {
            "total_estimated_tokens": 0,
            "budget_limit": max_token_budget,
            "within_budget": False,
            "servers": {},
            "recommendations": ["Configuration root must be a JSON object."],
        }

    if "mcpServers" in raw_data and isinstance(raw_data["mcpServers"], dict):
        servers_map = raw_data["mcpServers"]
    else:
        servers_map = raw_data

    servers_result: Dict[str, Any] = {}
    recommendations: List[str] = []
    total_tokens = 0

    for srv_name, srv_cfg in servers_map.items():
        srv_str = str(srv_name)
        if not isinstance(srv_cfg, dict):
            servers_result[srv_str] = {
                "tool_count": 0,
                "max_tool_name_length": 0,
                "char_footprint": 0,
                "estimated_tokens": 0,
                "within_budget": True,
                "exceeds_64_char_limit": False,
                "tools": {},
                "warnings": [f"Server '{srv_str}' configuration must be an object"],
            }
            recommendations.append(f"Server '{srv_str}' is invalid; must be an object configuration.")
            continue

        tools_field = srv_cfg.get("tools")
        tool_records: Dict[str, Any] = {}
        max_tool_name_len = 0
        srv_exceeds_64 = False

        if isinstance(tools_field, list):
            for t in tools_field:
                if isinstance(t, dict):
                    tname = str(t.get("name") or "unnamed_tool")
                    tdesc = str(t.get("description") or "")
                    t_chars = len(json.dumps(t, ensure_ascii=False))
                    t_tokens = (t_chars + 3) // 4
                elif isinstance(t, str):
                    tname = t
                    tdesc = ""
                    t_chars = len(tname)
                    t_tokens = (t_chars + 3) // 4
                else:
                    tname = str(t)
                    tdesc = ""
                    t_chars = len(tname)
                    t_tokens = (t_chars + 3) // 4

                comp_name = f"mcp_{srv_str}_{tname}"
                comp_len = len(comp_name)
                t_exceeds_64 = comp_len > 64 or len(tname) > 64
                if t_exceeds_64:
                    srv_exceeds_64 = True

                if len(tname) > max_tool_name_len:
                    max_tool_name_len = len(tname)

                tool_records[tname] = {
                    "composite_identifier": comp_name,
                    "identifier_length": comp_len,
                    "exceeds_64_char": t_exceeds_64,
                    "char_footprint": t_chars,
                    "estimated_tokens": t_tokens,
                    "description_length": len(tdesc),
                }

                if len(tdesc) > 500:
                    recommendations.append(
                        f"Tool '{tname}' in server '{srv_str}' has a verbose description ({len(tdesc)} chars). "
                        f"Trimming to <=200 chars can save ~{(len(tdesc) - 200) // 4} tokens."
                    )
        elif isinstance(tools_field, dict):
            for tname, tval in tools_field.items():
                tname_str = str(tname)
                tdesc = ""
                if isinstance(tval, dict):
                    tdesc = str(tval.get("description") or "")
                    t_chars = len(json.dumps(tval, ensure_ascii=False)) + len(tname_str)
                else:
                    t_chars = len(str(tval)) + len(tname_str)
                t_tokens = (t_chars + 3) // 4

                comp_name = f"mcp_{srv_str}_{tname_str}"
                comp_len = len(comp_name)
                t_exceeds_64 = comp_len > 64 or len(tname_str) > 64
                if t_exceeds_64:
                    srv_exceeds_64 = True

                if len(tname_str) > max_tool_name_len:
                    max_tool_name_len = len(tname_str)

                tool_records[tname_str] = {
                    "composite_identifier": comp_name,
                    "identifier_length": comp_len,
                    "exceeds_64_char": t_exceeds_64,
                    "char_footprint": t_chars,
                    "estimated_tokens": t_tokens,
                    "description_length": len(tdesc),
                }

                if len(tdesc) > 500:
                    recommendations.append(
                        f"Tool '{tname_str}' in server '{srv_str}' has a verbose description ({len(tdesc)} chars). "
                        f"Trimming to <=200 chars can save ~{(len(tdesc) - 200) // 4} tokens."
                    )
        else:
            prefix_len = len(f"mcp_{srv_str}_")
            if prefix_len >= 64:
                srv_exceeds_64 = True

        srv_char_footprint = len(json.dumps(srv_cfg, ensure_ascii=False))
        srv_tokens = (srv_char_footprint + 3) // 4
        total_tokens += srv_tokens

        srv_within_budget = srv_tokens <= max_token_budget

        warnings: List[str] = []
        if srv_exceeds_64:
            warnings.append(
                f"Server '{srv_str}' has tool identifiers exceeding the 64-character Antigravity limit."
            )
            recommendations.append(
                f"Shorten server name '{srv_str}' or long tool identifiers to keep composite 'mcp_{srv_str}_<tool>' <= 64 chars."
            )

        if len(tool_records) > 20:
            warnings.append(f"Server '{srv_str}' defines {len(tool_records)} tools.")
            recommendations.append(
                f"Server '{srv_str}' has {len(tool_records)} tools. Consider chunking into domain-specific servers."
            )

        if srv_tokens > (max_token_budget // 2):
            warnings.append(
                f"Server '{srv_str}' consumes {srv_tokens} tokens (>50% of total budget {max_token_budget})."
            )
            recommendations.append(
                f"Server '{srv_str}' consumes {srv_tokens} tokens ({srv_tokens * 100 // max_token_budget}% of budget). "
                f"Prune redundant inputSchema parameters or lazy-load tools."
            )

        servers_result[srv_str] = {
            "tool_count": len(tool_records),
            "max_tool_name_length": max_tool_name_len,
            "char_footprint": srv_char_footprint,
            "estimated_tokens": srv_tokens,
            "within_budget": srv_within_budget,
            "exceeds_64_char_limit": srv_exceeds_64,
            "tools": tool_records,
            "warnings": warnings,
        }

    within_budget = total_tokens <= max_token_budget
    if not within_budget:
        recommendations.insert(
            0,
            f"Total estimated token footprint ({total_tokens}) exceeds maximum budget ({max_token_budget}). "
            f"Reduce schema complexity, trim long descriptions, or prune unused MCP servers."
        )

    deduped_recommendations: List[str] = []
    seen_recs: Set[str] = set()
    for r in recommendations:
        if r not in seen_recs:
            seen_recs.add(r)
            deduped_recommendations.append(r)

    return {
        "total_estimated_tokens": total_tokens,
        "budget_limit": max_token_budget,
        "within_budget": within_budget,
        "servers": servers_result,
        "recommendations": deduped_recommendations,
    }


# Boilerplate prefix patterns to strip deterministically
_BOILERPLATE_PREFIXES = [
    # Tool-level introductions
    re.compile(
        r"^(?:this\s+)?(?:tool|function|method|endpoint|service|routine|api)\s+"
        r"(?:allows\s+(?:you|the\s+user)\s+to|is\s+used\s+to|allows\s+to|is\s+designed\s+to|serves\s+to|will|can)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:used\s+to|allows\s+(?:you|the\s+user)\s+to|provides\s+(?:the\s+ability\s+to|a\s+way\s+to))\s*",
        re.IGNORECASE,
    ),
    # Parameter-level intros
    re.compile(
        r"^(?:an?|the)\s+(?:optional|required)?\s*"
        r"(?:string|boolean|integer|number|array|object|float|dict|list|mapping)\s+"
        r"(?:representing|specifying|indicating|denoting|holding|defining|containing|providing|which\s+is|that\s+is)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:a|an|the)\s+(?:parameter|argument|field|property|flag|value)\s+"
        r"(?:that|which)?\s*(?:specifies|indicates|represents|defines|holds|determines|denotes)?\s*",
        re.IGNORECASE,
    ),
    # Disclaimers / notes
    re.compile(
        r"^(?:please\s+note\s+that|note:|notice:|important:)\s*",
        re.IGNORECASE,
    ),
]


def _compact_text(text: str, is_property: bool = False) -> str:
    """Compact a single description string cleanly and deterministically."""
    if not text or not isinstance(text, str):
        return text

    cleaned = text.strip()

    # Flatten redundant whitespace, line breaks, HTML tags, and markdown bold/italic
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"[*_]{1,3}", "", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

    # Iteratively strip matched boilerplate prefixes
    changed = True
    while changed:
        changed = False
        for pattern in _BOILERPLATE_PREFIXES:
            new_text = pattern.sub("", cleaned).strip()
            if new_text != cleaned:
                cleaned = new_text
                changed = True

    # Strip redundant leading articles if followed by noun
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.IGNORECASE).strip()

    # Extract first sentence
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    first_sentence = sentences[0].strip() if sentences else cleaned

    # Sentence length bounds: tools <= 110 chars, properties <= 65 chars
    max_len = 65 if is_property else 110

    if len(first_sentence) > max_len:
        truncated = first_sentence[: max_len - 3]
        last_space = truncated.rfind(" ")
        if last_space > 20:
            truncated = truncated[:last_space]
        first_sentence = truncated.rstrip(",;:- ") + "..."

    # Ensure capitalized start and trailing punctuation
    if first_sentence:
        first_sentence = first_sentence[0].upper() + first_sentence[1:]
        if not first_sentence.endswith((".", "!", "?", "...")):
            first_sentence += "."

    return first_sentence


def _compact_schema_node(node: Any, is_property: bool = False) -> Any:
    """Recursively traverse schema dictionary and compact description values."""
    if isinstance(node, dict):
        compacted_dict: Dict[str, Any] = {}
        for key, val in node.items():
            if key == "description" and isinstance(val, str):
                compacted_dict[key] = _compact_text(val, is_property=is_property)
            elif key == "properties" and isinstance(val, dict):
                compacted_props = {
                    p_name: _compact_schema_node(p_val, is_property=True)
                    for p_name, p_val in val.items()
                }
                compacted_dict[key] = compacted_props
            elif key == "tools" and isinstance(val, list):
                compacted_dict[key] = [
                    _compact_schema_node(t, is_property=False) for t in val
                ]
            else:
                compacted_dict[key] = _compact_schema_node(val, is_property=is_property)
        return compacted_dict

    if isinstance(node, list):
        return [_compact_schema_node(item, is_property=is_property) for item in node]

    return node


def compact_mcp_schema_descriptions(
    schema: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Recursively compact verbose descriptions in an MCP schema."""
    if not isinstance(schema, dict) or not schema:
        return schema if isinstance(schema, dict) else {}, {
            "original_chars": 0,
            "compacted_chars": 0,
            "reduction_pct": 0.0,
            "original_tokens": 0,
            "compacted_tokens": 0,
            "tokens_saved": 0,
        }

    original_copy = copy.deepcopy(schema)
    compacted = _compact_schema_node(original_copy, is_property=False)

    orig_json = json.dumps(original_copy, sort_keys=True)
    comp_json = json.dumps(compacted, sort_keys=True)

    original_chars = len(orig_json)
    compacted_chars = len(comp_json)

    if original_chars > 0 and original_chars > compacted_chars:
        reduction_pct = round(
            ((original_chars - compacted_chars) / original_chars) * 100.0, 2
        )
    else:
        reduction_pct = 0.0

    original_tokens = (original_chars + 3) // 4
    compacted_tokens = (compacted_chars + 3) // 4
    tokens_saved = max(0, original_tokens - compacted_tokens)

    telemetry: Dict[str, Any] = {
        "original_chars": original_chars,
        "compacted_chars": compacted_chars,
        "reduction_pct": reduction_pct,
        "original_tokens": original_tokens,
        "compacted_tokens": compacted_tokens,
        "tokens_saved": tokens_saved,
    }

    return compacted, telemetry


def optimize_mcp_config_tokens(
    config: Union[Dict[str, Any], Path, str, None],
    token_budget: int = 4000,
    max_token_budget: Optional[int] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Automated MCP Config Optimizer & Schema Compaction Pipeline.

    Pairs analyze_mcp_token_budget with compact_mcp_schema_descriptions
    to auto-shrink over-budget MCP server manifests while preserving 100% of
    functional JSON Schema types, properties, and constraints.

    Returns:
        Tuple of (optimized_config, summary_dict).
    """
    effective_budget = max_token_budget if max_token_budget is not None else token_budget

    parsed: Any = None
    if config is None:
        return {}, {
            "token_budget": effective_budget,
            "original_tokens": 0,
            "optimized_tokens": 0,
            "tokens_saved": 0,
            "reduction_pct": 0.0,
            "servers_count": 0,
            "recommendations": ["No configuration provided."],
        }
    elif isinstance(config, Path):
        if not config.is_file():
            return {}, {
                "token_budget": effective_budget,
                "original_tokens": 0,
                "optimized_tokens": 0,
                "tokens_saved": 0,
                "reduction_pct": 0.0,
                "servers_count": 0,
                "recommendations": [f"Configuration file not found: {config}"],
            }
        try:
            parsed = parse_jsonc(config.read_text(encoding="utf-8"))
        except Exception:
            return {}, {
                "token_budget": effective_budget,
                "original_tokens": 0,
                "optimized_tokens": 0,
                "tokens_saved": 0,
                "reduction_pct": 0.0,
                "servers_count": 0,
                "recommendations": ["Malformed JSON in configuration file."],
            }
    elif isinstance(config, str):
        stripped = config.strip()
        if not stripped:
            return {}, {
                "token_budget": effective_budget,
                "original_tokens": 0,
                "optimized_tokens": 0,
                "tokens_saved": 0,
                "reduction_pct": 0.0,
                "servers_count": 0,
                "recommendations": ["Empty configuration provided."],
            }
        is_file = False
        try:
            p = Path(stripped)
            if p.is_file():
                is_file = True
                parsed = parse_jsonc(p.read_text(encoding="utf-8"))
        except Exception:
            is_file = False

        if not is_file:
            try:
                parsed = parse_jsonc(stripped)
            except Exception:
                return {}, {
                    "token_budget": effective_budget,
                    "original_tokens": 0,
                    "optimized_tokens": 0,
                    "tokens_saved": 0,
                    "reduction_pct": 0.0,
                    "servers_count": 0,
                    "recommendations": ["Malformed JSON string provided."],
                }
    elif isinstance(config, dict):
        parsed = copy.deepcopy(config)
    else:
        return {}, {
            "token_budget": effective_budget,
            "original_tokens": 0,
            "optimized_tokens": 0,
            "tokens_saved": 0,
            "reduction_pct": 0.0,
            "servers_count": 0,
            "recommendations": [f"Invalid configuration type: {type(config).__name__}"],
        }

    if not isinstance(parsed, dict) or not parsed:
        return {} if not isinstance(parsed, dict) else parsed, {
            "token_budget": effective_budget,
            "original_tokens": 0,
            "optimized_tokens": 0,
            "tokens_saved": 0,
            "reduction_pct": 0.0,
            "servers_count": 0,
            "recommendations": ["Empty configuration."],
        }

    # Analyze original budget
    analysis_before = analyze_mcp_token_budget(parsed, max_token_budget=effective_budget)
    orig_tokens = analysis_before.get("total_estimated_tokens", 0)

    # Compact schema descriptions across all servers/tools
    compacted_cfg, telemetry = compact_mcp_schema_descriptions(parsed)

    # Analyze optimized budget
    analysis_after = analyze_mcp_token_budget(compacted_cfg, max_token_budget=effective_budget)
    opt_tokens = analysis_after.get("total_estimated_tokens", 0)
    tokens_saved = max(0, orig_tokens - opt_tokens)

    if orig_tokens > 0 and orig_tokens > opt_tokens:
        reduction_pct = round(((orig_tokens - opt_tokens) / orig_tokens) * 100.0, 2)
    else:
        reduction_pct = 0.0

    srv_count = len(compacted_cfg.get("mcpServers", compacted_cfg)) if isinstance(compacted_cfg, dict) else 0

    summary = {
        "token_budget": effective_budget,
        "original_tokens": orig_tokens,
        "optimized_tokens": opt_tokens,
        "tokens_saved": tokens_saved,
        "reduction_pct": reduction_pct,
        "servers_count": srv_count,
        "recommendations": analysis_after.get("recommendations", []),
        "within_budget": analysis_after.get("within_budget", True),
    }

    return compacted_cfg, summary

