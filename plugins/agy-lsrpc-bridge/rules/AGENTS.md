# Antigravity LSRPC Bridge & Plugin Manager Operational Rules

1. Maintain 100% English-only source, documentation, and commit messages.
2. Enforce dynamic relative paths and never commit personal credentials or local user paths.
3. Never read raw `GetAllPlugins` RPC responses unfiltered; always use `agy-lsrpc-bridge` compaction to prevent context flooding.
4. Always key `JetboxWriteState` and `DeletePlugin` mutations on the plugin's install directory (`dir`), never the manifest `name`.
