"""Antigravity Marketplace v2.28.1 Manifest & Bundle Validator (REQ-LSRPC-MKT-01)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from agy_lsrpc_bridge.validator import parse_jsonc

ALLOWED_PLUGIN_JSON_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "logo",
        "suggestedPrompts",
        "displayName",
        "version",
        "author",
        "homepage",
        "repository",
        "disabled",
    }
)

ALLOWED_LOGO_EXTENSIONS: frozenset[str] = frozenset(
    {".svg", ".png", ".jpg", ".jpeg", ".webp"}
)
KEBAB_CASE_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


@dataclass(frozen=True)
class MarketplaceManifestAudit:
    """@requirement("REQ-LSRPC-MKT-01") Immutable audit result for an Antigravity v2.28.1 plugin manifest."""

    valid: bool
    plugin_name: str
    unknown_top_level_keys: list[str]
    errors: list[str]
    warnings: list[str]
    prompt_count: int
    has_valid_logo: bool


class MarketplaceV228Validator:
    """@requirement("REQ-LSRPC-MKT-01") Validator for Antigravity Marketplace v2.28.1 plugin bundles."""

    @staticmethod
    def _resolve_manifest_path(pdir: Path) -> Path | None:
        root_manifest = pdir / "plugin.json"
        if root_manifest.is_file():
            return root_manifest
        cursor_manifest = pdir / ".Cursor-plugin" / "plugin.json"
        if cursor_manifest.is_file():
            return cursor_manifest
        return None

    def validate_plugin_bundle(self, plugin_dir: Path | str) -> MarketplaceManifestAudit:
        """@requirement("REQ-LSRPC-MKT-01") Validate a plugin directory against Antigravity v2.28.1 Marketplace rules."""
        pdir = Path(plugin_dir).resolve()
        errors: list[str] = []
        warnings: list[str] = []
        unknown_keys: list[str] = []
        plugin_name = pdir.name
        prompt_count = 0
        has_valid_logo = False

        manifest_path = self._resolve_manifest_path(pdir)
        if manifest_path is None:
            errors.append(f"Missing required plugin.json in {pdir.name}")
            return MarketplaceManifestAudit(
                valid=False,
                plugin_name=plugin_name,
                unknown_top_level_keys=unknown_keys,
                errors=errors,
                warnings=warnings,
                prompt_count=prompt_count,
                has_valid_logo=has_valid_logo,
            )

        try:
            raw_manifest: Any = parse_jsonc(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw_manifest, dict):
                errors.append("plugin.json root must be a JSON object")
                manifest: dict[str, Any] = {}
            else:
                manifest = raw_manifest
        except Exception as exc:
            errors.append(f"Invalid JSON in plugin.json: {exc}")
            manifest = {}

        for key in manifest:
            key_str = str(key)
            if key_str not in ALLOWED_PLUGIN_JSON_KEYS:
                unknown_keys.append(key_str)
                errors.append(f"Unknown top-level key '{key_str}' in plugin.json")

        raw_name = manifest.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            plugin_name = raw_name.strip()
            if not KEBAB_CASE_NAME_RE.fullmatch(raw_name):
                errors.append(
                    f"Field 'name' ('{raw_name}') must be lowercase kebab-case matching ^[a-z0-9]+(-[a-z0-9]+)*$"
                )
        else:
            errors.append("Field 'name' is required and must be a non-empty lowercase kebab-case string")

        raw_desc = manifest.get("description")
        if not isinstance(raw_desc, str) or not raw_desc.strip():
            errors.append("Field 'description' is required and must be a non-empty string")

        if "logo" in manifest:
            raw_logo = manifest.get("logo")
            if not isinstance(raw_logo, str) or not raw_logo.strip():
                errors.append("Field 'logo' must be a non-empty relative path string")
            else:
                logo_str = raw_logo.strip()
                is_url = logo_str.lower().startswith(("http://", "https://"))
                is_abs = (
                    logo_str.startswith(("/", "\\"))
                    or bool(WINDOWS_DRIVE_RE.match(logo_str))
                    or Path(logo_str).is_absolute()
                    or ".." in Path(logo_str).parts
                )
                ext = Path(logo_str).suffix.lower()
                if is_url or is_abs:
                    errors.append(f"Field 'logo' ('{logo_str}') must be a relative path inside the plugin directory")
                elif ext not in ALLOWED_LOGO_EXTENSIONS:
                    errors.append(f"Field 'logo' ('{logo_str}') has unsupported extension '{ext}'")
                elif not (pdir / logo_str).is_file():
                    errors.append(f"Logo file does not exist inside plugin bundle: '{logo_str}'")
                else:
                    has_valid_logo = True
        else:
            warnings.append("Field 'logo' is missing; recommended for Marketplace display")

        if "suggestedPrompts" in manifest:
            raw_prompts = manifest.get("suggestedPrompts")
            if not isinstance(raw_prompts, list):
                errors.append("Field 'suggestedPrompts' must be a list of 1..3 non-empty strings")
            else:
                if len(raw_prompts) < 1 or len(raw_prompts) > 3:
                    errors.append(f"Field 'suggestedPrompts' must contain 1..3 items (got {len(raw_prompts)})")
                valid_prompts = 0
                for idx, prompt in enumerate(raw_prompts):
                    if not isinstance(prompt, str) or not prompt.strip():
                        errors.append(f"Field 'suggestedPrompts[{idx}]' must be a non-empty string")
                    else:
                        valid_prompts += 1
                prompt_count = valid_prompts

        return MarketplaceManifestAudit(
            valid=len(errors) == 0,
            plugin_name=plugin_name,
            unknown_top_level_keys=unknown_keys,
            errors=errors,
            warnings=warnings,
            prompt_count=prompt_count,
            has_valid_logo=has_valid_logo,
        )

    def detect_global_name_collisions(self, plugin_dirs: list[Path | str]) -> dict[str, list[str]]:
        """@requirement("REQ-LSRPC-MKT-01") Detect duplicate plugin names across multiple plugin directories."""
        by_name: dict[str, list[str]] = {}
        for item in plugin_dirs:
            pdir = Path(item).resolve()
            manifest_path = self._resolve_manifest_path(pdir)
            if manifest_path is None:
                continue
            try:
                data = parse_jsonc(manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    raw_name = data.get("name")
                    if isinstance(raw_name, str) and raw_name.strip():
                        by_name.setdefault(raw_name.strip(), []).append(pdir.name)
            except Exception:
                continue
        return {name: dirs for name, dirs in by_name.items() if len(dirs) > 1}
