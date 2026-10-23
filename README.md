# `agy-lsrpc-bridge` — Antigravity Language Server ConnectRPC Bridge & Plugin Manager

`agy-lsrpc-bridge` is a zero-dependency Python library, CLI toolkit, L1 Skill, and L2 Native Plugin for Google Antigravity 2.0 (`exa.language_server_pb.LanguageServerService`).

## What Problem Does It Solve?

1. **Context-Window Flooding on `GetAllPlugins`**:
   - Calling `GetAllPlugins` directly on the Antigravity Language Server returns the **entire markdown body** of every `SKILL.md`, agent, and rule across all installed plugins (often `>100 KB` per call).
   - `agy-lsrpc-bridge` automatically strips raw markdown bodies and returns a compact, deterministic inventory with skill/agent/MCP names, hook status, and clickable `[<name>](customization://<dir>)` links.
2. **Silent Mutation Failures When Using `name` Instead of `dir`**:
   - Marketplace and local plugins are keyed by their **install directory name (`dir`)** (such as `-1870732469773246571`), not `plugin.json`'s `name`.
   - `agy-lsrpc-bridge` resolves any user-supplied name or directory ID to its canonical `dir` before calling `JetboxWriteState` or `DeletePlugin`.
3. **Stale Disabled Entries & Built-in Uninstall Hazards**:
   - Uninstalling a disabled plugin via `DeletePlugin` leaves `{"enabled": false}` in `config.json`, causing future reinstalls to silently start disabled.
   - `agy-lsrpc-bridge` enforces two pre-delete guards:
     1. Blocks uninstalling `/builtin/plugins/` bundles (`PermissionError`).
     2. Automatically re-enables a disabled plugin via `JetboxWriteState(enabled=True)` before invoking `DeletePlugin`.
4. **Antigravity 2.0 Native Plugin Validation & Scaffolding**:
   - Catches silent loader pitfalls: disallowed top-level fields in `plugin.json` (`author`, `homepage`), `hooks/hooks.json` instead of root `hooks.json`, YAML frontmatter inside `rules/AGENTS.md`, unprefixed MCP server names in `mcp_config.json`, and remote logo URLs.

## Quick Start

```bash
# 1. Check Language Server health & compact plugin inventory
python -m agy_lsrpc_bridge.cli status --json

# 2. Live-enable or disable a plugin (no IDE restart required)
python -m agy_lsrpc_bridge.cli enable agy-doctor-mux --json
python -m agy_lsrpc_bridge.cli disable agy-doctor-mux --json

# 3. Validate a plugin directory against Antigravity 2.0 loader rules
python -m agy_lsrpc_bridge.cli validate ./plugins/agy-lsrpc-bridge --json

# 4. Scaffold a new Antigravity 2.0 native plugin bundle
python -m agy_lsrpc_bridge.cli scaffold \
  --target-root ./plugins \
  --name my-custom-plugin \
  --description "Custom Antigravity 2.0 bundle" \
  --include-hooks \
  --include-mcp \
  --json
```

## License

MIT License — Copyright (c) 2026 `orakulzero`
