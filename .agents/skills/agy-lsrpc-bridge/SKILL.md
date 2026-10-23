---
name: agy-lsrpc-bridge
description: >-
  Antigravity Language Server ConnectRPC Bridge, Context-Flood-Safe Plugin Inventory
  (GetAllPlugins), Live Plugin Toggler (JetboxWriteState), Safe Uninstaller (DeletePlugin),
  and Native Antigravity 2.0 Plugin Validator & Scaffolder.
---

# Antigravity Language Server ConnectRPC Bridge (`agy-lsrpc-bridge`)

Provides direct programmatic and CLI control over the Antigravity Language Server
(`exa.language_server_pb.LanguageServerService`) with offline filesystem fallback.

## Key Capabilities

1. **Context-Flood-Safe Inventory (`status` / `list`)**:
   - Raw `GetAllPlugins` inlines full `SKILL.md` texts (>16KB per plugin).
   - `agy-lsrpc-bridge` strips all markdown bodies and outputs compact metadata keyed on the true install directory (`dir`), plus clickable `[<name>](customization://<dir>)` links.
   - Automatically falls back to local filesystem inspection (`~/.gemini/config/plugins` and `config.json`) when the Language Server HTTP endpoint is offline.
2. **Live Lifecycle Management (`enable` / `disable` / `uninstall` / `install`)**:
   - Resolves targets by `dir` or `name` so `JetboxWriteState` always mutates the true install directory key (`dir`), taking effect live without an IDE restart.
   - **Built-in Guard**: Blocks uninstalling `/builtin/plugins/` bundles.
   - **Stale-Disabled Guard**: Automatically re-enables a disabled plugin via `JetboxWriteState(enabled=True)` before calling `DeletePlugin` so no orphan disabled state remains in `config.json`.
3. **Antigravity 2.0 Plugin Validator & Scaffolder (`validate` / `scaffold` / `consolidate`)**:
   - Validates JSONC `plugin.json` top-level fields (`name`, `displayName`, `description`, `version`, `logo`, `suggestedPrompts`, `disabled`), root-level `hooks.json` placement, frontmatter-free `rules/AGENTS.md`, and prefixed `mcp_config.json` server names.

## CLI Usage

```bash
# Check Language Server health and compact plugin inventory
python -m agy_lsrpc_bridge.cli status --json

# Live-enable or disable a plugin without restarting Antigravity
python -m agy_lsrpc_bridge.cli enable <plugin-name-or-dir> --json
python -m agy_lsrpc_bridge.cli disable <plugin-name-or-dir> --json

# Validate an Antigravity 2.0 plugin directory
python -m agy_lsrpc_bridge.cli validate ./plugins/my-plugin --json

# Scaffold a new spec-compliant Antigravity 2.0 plugin
python -m agy_lsrpc_bridge.cli scaffold --target-root ./plugins --name my-plugin --description "My plugin bundle" --include-hooks --include-mcp --json
```
