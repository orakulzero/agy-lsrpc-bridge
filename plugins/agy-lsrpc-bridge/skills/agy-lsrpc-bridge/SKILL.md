---
name: agy-lsrpc-bridge
description: >-
  Antigravity Language Server ConnectRPC Bridge, Context-Flood-Safe Plugin Inventory
  (GetAllPlugins), Live Plugin Toggler (JetboxWriteState), Safe Uninstaller (DeletePlugin),
  and Native Antigravity 2.0 Plugin Validator & Scaffolder.
---

# Antigravity Language Server ConnectRPC Bridge (`agy-lsrpc-bridge`)

Use `python -m agy_lsrpc_bridge.cli` to manage Antigravity plugins over ConnectRPC (`exa.language_server_pb.LanguageServerService`) or local fallback:

- `status --json`: Check `/healthz` and list compact plugin metadata.
- `enable <target> --json` / `disable <target> --json`: Live-toggle plugins via `JetboxWriteState` keyed by install `dir`.
- `uninstall <target> --json`: Safely uninstall with Built-in and Stale-Disabled guards.
- `validate <plugin_dir> --json`: Audit a plugin bundle against Antigravity 2.0 loader rules.
- `scaffold --target-root <dir> --name <name> --description <desc> --json`: Generate a compliant plugin bundle.
