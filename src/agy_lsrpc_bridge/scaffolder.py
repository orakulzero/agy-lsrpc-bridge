"""
src/agy_lsrpc_bridge/scaffolder.py
Antigravity 2.0 Native Plugin Scaffolder & Loose Customization Consolidator.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional


def _strip_yaml_frontmatter(markdown_text: str) -> str:
    """Remove leading YAML frontmatter (`--- ... ---`) from markdown rule files."""
    stripped = markdown_text.lstrip()
    if not stripped.startswith("---"):
        return markdown_text.strip() + "\n"
    match = re.match(r"^---\r?\n.*?\r?\n---\r?\n?", stripped, flags=re.DOTALL)
    if match:
        return stripped[match.end() :].lstrip()
    return markdown_text.strip() + "\n"


def _default_logo_svg(plugin_name: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <rect x="14" y="14" width="100" height="100" rx="22" fill="#0f172a" stroke="#38bdf8" stroke-width="6"/>
  <path d="M38 64 L56 44 L56 56 L90 56 L90 72 L56 72 L56 84 Z" fill="#38bdf8"/>
  <circle cx="88" cy="42" r="8" fill="#34d399"/>
  <title>{plugin_name}</title>
</svg>
"""


def scaffold_plugin(
    target_root: Path,
    name: str,
    description: str,
    display_name: Optional[str] = None,
    include_hooks: bool = False,
    include_mcp: bool = False,
    version: str = "1.0.0",
) -> Path:
    """
    Generate a complete, spec-compliant Antigravity 2.0 plugin bundle at `<target_root>/<name>/`.
    """
    clean_name = re.sub(r"[^a-z0-9-]+", "-", (name or "").strip().lower()).strip("-")
    if not clean_name:
        raise ValueError("Plugin name must contain lowercase alphanumeric characters")

    clean_desc = (description or "").strip() or f"{clean_name} Antigravity plugin bundle."
    clean_display = (
        (display_name or "").strip()
        or " ".join(part.capitalize() for part in clean_name.split("-"))
    )

    pdir = Path(target_root).resolve() / clean_name
    (pdir / "assets").mkdir(parents=True, exist_ok=True)
    (pdir / "rules").mkdir(parents=True, exist_ok=True)
    (pdir / "skills" / clean_name).mkdir(parents=True, exist_ok=True)
    (pdir / "agents").mkdir(parents=True, exist_ok=True)

    # 1. assets/logo.svg (128x128 square SVG with ~10% margin)
    (pdir / "assets" / "logo.svg").write_text(
        _default_logo_svg(clean_name), encoding="utf-8"
    )

    # 2. plugin.json (strictly allowed top-level fields only)
    manifest: Dict[str, Any] = {
        "name": clean_name,
        "displayName": clean_display,
        "description": clean_desc,
        "version": version,
        "logo": "assets/logo.svg",
        "suggestedPrompts": [
            f"Run {clean_name} status and diagnostics",
            f"Execute {clean_name} workflow on the active workspace",
            f"Validate {clean_name} configuration",
        ],
    }
    (pdir / "plugin.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 3. README.md
    readme = f"""# {clean_display} (`{clean_name}`)

{clean_desc}

## Components
- **Skill**: `skills/{clean_name}/SKILL.md`
- **Agent**: `agents/{clean_name}-agent.md`
- **Operational Rules**: `rules/AGENTS.md`
"""
    (pdir / "README.md").write_text(readme, encoding="utf-8")

    # 4. rules/AGENTS.md (plain markdown, zero YAML frontmatter)
    rules_md = f"""# {clean_display} Operational Rules

1. Maintain 100% English-only source, documentation, and commit messages.
2. Enforce dynamic relative paths and never commit personal credentials or local user paths.
3. Follow the `{clean_name}` skill workflow when operating in this domain.
"""
    (pdir / "rules" / "AGENTS.md").write_text(rules_md, encoding="utf-8")

    # 5. skills/<name>/SKILL.md
    skill_md = f"""---
name: {clean_name}
description: {clean_desc}
---

# {clean_display} (`{clean_name}`)

{clean_desc}

## Workflow
1. Inspect current workspace state.
2. Execute the `{clean_name}` operations deterministically.
3. Verify output with automated checks before concluding.
"""
    (pdir / "skills" / clean_name / "SKILL.md").write_text(
        skill_md, encoding="utf-8"
    )

    # 6. agents/<name>-agent.md
    agent_md = f"""---
description: Autonomous specialist agent for {clean_display} ({clean_name}).
---

# {clean_display} Specialist Agent

You are the specialized autonomous agent for `{clean_name}`. Follow `skills/{clean_name}/SKILL.md` and `rules/AGENTS.md` strictly.
"""
    (pdir / "agents" / f"{clean_name}-agent.md").write_text(
        agent_md, encoding="utf-8"
    )

    # 7. Optional root-level hooks.json
    if include_hooks:
        hooks_data = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python -m agy_doctor_mux dispatch SessionStart",
                                "timeout": 5,
                            }
                        ],
                    }
                ]
            }
        }
        (pdir / "hooks.json").write_text(
            json.dumps(hooks_data, indent=2) + "\n", encoding="utf-8"
        )

    # 8. Optional mcp_config.json with plugin-name prefix
    if include_mcp:
        mcp_data = {
            "mcpServers": {
                f"{clean_name}-server": {
                    "command": "python",
                    "args": ["-m", clean_name.replace("-", "_")],
                    "timeout_ms": 15000,
                }
            }
        }
        (pdir / "mcp_config.json").write_text(
            json.dumps(mcp_data, indent=2) + "\n", encoding="utf-8"
        )

    return pdir


def consolidate_loose_customizations(
    plugin_dir: Path,
    skill_dirs: Optional[List[Path]] = None,
    rule_files: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """
    Consolidate standalone skill directories and rule files into an existing plugin bundle.
    Strips any YAML frontmatter from rule files when merging into `rules/AGENTS.md`.
    """
    pdir = Path(plugin_dir).resolve()
    if not (pdir / "plugin.json").is_file():
        raise FileNotFoundError(f"Target plugin directory missing plugin.json: {pdir}")

    consolidated_skills: List[str] = []
    for sdir in skill_dirs or []:
        src_skill = Path(sdir).resolve()
        if not src_skill.is_dir() or not (src_skill / "SKILL.md").is_file():
            continue
        dest_skill = pdir / "skills" / src_skill.name
        if dest_skill.exists():
            shutil.rmtree(dest_skill)
        shutil.copytree(src_skill, dest_skill)
        consolidated_skills.append(src_skill.name)

    consolidated_rules: List[str] = []
    if rule_files:
        rules_dir = pdir / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        agents_md_path = rules_dir / "AGENTS.md"
        existing_text = ""
        if agents_md_path.is_file():
            existing_text = _strip_yaml_frontmatter(
                agents_md_path.read_text(encoding="utf-8")
            ).rstrip()

        merged_blocks: List[str] = [existing_text] if existing_text else []
        for rfile in rule_files:
            rpath = Path(rfile).resolve()
            if not rpath.is_file():
                continue
            clean_rule = _strip_yaml_frontmatter(
                rpath.read_text(encoding="utf-8")
            ).strip()
            if clean_rule:
                merged_blocks.append(clean_rule)
                consolidated_rules.append(rpath.name)

        agents_md_path.write_text(
            "\n\n".join(merged_blocks).rstrip() + "\n", encoding="utf-8"
        )

    return {
        "ok": True,
        "plugin_dir": str(pdir),
        "consolidated_skills": consolidated_skills,
        "consolidated_rules": consolidated_rules,
    }
