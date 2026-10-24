"""
src/agy_lsrpc_bridge/client.py
ConnectRPC Client for Antigravity Language Server (`exa.language_server_pb.LanguageServerService`).
Provides:
- Context-flood-safe `list_plugins()` (strips raw inlined SKILL.md / agent / rule bodies)
- Offline filesystem fallback when Language Server HTTP endpoint is unreachable
- True install-directory (`dir`) resolution (`resolve_plugin_dir`)
- Live plugin toggling via `JetboxWriteState` + atomic `config.json` update
- Safe uninstall (`DeletePlugin`) with Built-in Protection Guard and Stale-Disabled Re-Enable Guard
- Marketplace customization installation (`InstallCustomization`)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Set
import urllib.error
import urllib.request

from agy_lsrpc_bridge.validator import parse_jsonc

TransportCallable = Callable[
    [str, str, Dict[str, str], Optional[Dict[str, Any]]], Any
]

SERVICE_PREFIX = "exa.language_server_pb.LanguageServerService"
_LS_ADDR_ENV = "ANTI" + "GRAVITY_LS_ADDRESS"
_CSRF_ENV = "ANTI" + "GRAVITY_CSRF_TOKEN"


def _default_config_root() -> Path:
    env_cfg = os.environ.get("AGY_CONFIG_ROOT", "").strip()
    if env_cfg:
        return Path(env_cfg).resolve()
    return (Path.home() / ".gemini" / "config").resolve()


def _extract_last_segment(raw_path: str) -> str:
    norm = str(raw_path or "").replace("\\", "/").rstrip("/")
    if not norm:
        return ""
    return norm.rsplit("/", 1)[-1]


def _is_builtin_path(raw_path: str) -> bool:
    norm = str(raw_path or "").replace("\\", "/").lower()
    return "/builtin/plugins/" in norm


class LSRPCClient:
    """ConnectRPC client for Antigravity Language Server with offline filesystem fallback."""

    def __init__(
        self,
        address: Optional[str] = None,
        csrf_token: Optional[str] = None,
        config_root: Optional[Path] = None,
        transport: Optional[TransportCallable] = None,
        timeout_sec: float = 4.0,
    ) -> None:
        raw_addr = (
            address
            or os.environ.get(_LS_ADDR_ENV, "").strip()
            or "localhost:5387"
        )
        if raw_addr.startswith("http://"):
            raw_addr = raw_addr[len("http://") :]
        elif raw_addr.startswith("https://"):
            raw_addr = raw_addr[len("https://") :]
        self.address = raw_addr.rstrip("/")
        self.csrf_token = (
            csrf_token
            if csrf_token is not None
            else os.environ.get(_CSRF_ENV, "").strip()
        )
        self.config_root = Path(config_root).resolve() if config_root else _default_config_root()
        self.transport = transport or self._urllib_transport
        self.timeout_sec = timeout_sec

    def _urllib_transport(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]],
    ) -> Any:
        data: Optional[bytes] = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
        req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace").strip()
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"raw": raw}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {err_body}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Language Server unreachable at {url}: {exc}") from exc

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.csrf_token:
            headers["x-codeium-csrf-token"] = self.csrf_token
        return headers

    def healthz(self) -> Dict[str, Any]:
        """Check Language Server `/healthz` endpoint."""
        url = f"http://{self.address}/healthz"
        try:
            resp = self.transport("GET", url, self._build_headers(), None)
            return {
                "ok": True,
                "address": self.address,
                "live_rpc": True,
                "response": resp,
            }
        except Exception as exc:
            return {
                "ok": False,
                "address": self.address,
                "live_rpc": False,
                "error": str(exc),
            }

    def call_rpc(
        self,
        method_name: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke a ConnectRPC method on `exa.language_server_pb.LanguageServerService`."""
        url = f"http://{self.address}/{SERVICE_PREFIX}/{method_name}"
        body = payload if payload is not None else {}
        res = self.transport("POST", url, self._build_headers(), body)
        return res if isinstance(res, dict) else {"result": res}

    def _compact_rpc_plugin_entry(self, raw_plugin: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = str(raw_plugin.get("path") or "")
        dir_name = _extract_last_segment(raw_path) or str(raw_plugin.get("name") or "unknown")
        name = str(raw_plugin.get("name") or dir_name)
        disabled = bool(raw_plugin.get("disabled", False))
        is_global = bool(raw_plugin.get("isGlobal", True))
        is_builtin = _is_builtin_path(raw_path)

        raw_skills = raw_plugin.get("skills") or []
        skills: List[str] = []
        for s in raw_skills:
            if isinstance(s, dict) and s.get("name"):
                skills.append(str(s["name"]))
            elif isinstance(s, str):
                skills.append(s)

        raw_agents = raw_plugin.get("agents") or []
        agents: List[str] = []
        for a in raw_agents:
            if isinstance(a, dict) and a.get("name"):
                agents.append(str(a["name"]))
            elif isinstance(a, str):
                agents.append(a)

        raw_rules = raw_plugin.get("rules") or []
        rules: List[str] = []
        for r in raw_rules:
            if isinstance(r, dict):
                rpath = r.get("absolutePath") or r.get("path")
                if rpath:
                    rules.append(str(rpath))
            elif isinstance(r, str):
                rules.append(r)

        hooks_json = raw_plugin.get("hooksJson")
        has_hooks = bool(hooks_json and str(hooks_json).strip())

        raw_mcp = raw_plugin.get("mcpServers")
        mcp_names: List[str] = []
        if isinstance(raw_mcp, list):
            for m in raw_mcp:
                if isinstance(m, dict) and m.get("name"):
                    mcp_names.append(str(m["name"]))
                elif isinstance(m, str):
                    mcp_names.append(m)
        elif isinstance(raw_mcp, dict):
            mcp_names.extend(str(k) for k in raw_mcp.keys())

        return {
            "name": name,
            "dir": dir_name,
            "path": raw_path,
            "disabled": disabled,
            "isGlobal": is_global,
            "isBuiltin": is_builtin,
            "skills": skills,
            "agents": agents,
            "rules": rules,
            "hooks": has_hooks,
            "mcp": mcp_names,
            "customizationLink": f"[{name}](customization://{dir_name})",
        }

    def _read_local_config_json(self) -> Dict[str, Any]:
        cfg_file = self.config_root / "config.json"
        if not cfg_file.is_file():
            return {}
        try:
            data = parse_jsonc(cfg_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_local_config_json_atomic(self, data: Dict[str, Any]) -> None:
        self.config_root.mkdir(parents=True, exist_ok=True)
        cfg_file = self.config_root / "config.json"
        serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            prefix=".config_", suffix=".json.tmp", dir=str(self.config_root)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(serialized)
            os.replace(tmp_name, cfg_file)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    def _scan_filesystem_plugins(self) -> List[Dict[str, Any]]:
        cfg = self._read_local_config_json()
        plugins_cfg = (cfg.get("plugins") or {}) if isinstance(cfg, dict) else {}
        plugins_root = self.config_root / "plugins"
        items: List[Dict[str, Any]] = []
        if not plugins_root.is_dir():
            return items

        for pdir in sorted(plugins_root.iterdir(), key=lambda p: p.name):
            if not pdir.is_dir():
                continue
            manifest_file = pdir / "plugin.json"
            if not manifest_file.is_file():
                continue
            try:
                manifest = parse_jsonc(manifest_file.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    manifest = {}
            except Exception:
                manifest = {}

            dir_name = pdir.name
            name = str(manifest.get("name") or dir_name)

            # Precedence: config.json wins over plugin.json 'disabled'
            if dir_name in plugins_cfg and isinstance(plugins_cfg[dir_name], dict):
                enabled_val = plugins_cfg[dir_name].get("enabled")
                disabled = not bool(enabled_val) if enabled_val is not None else bool(manifest.get("disabled", False))
            else:
                disabled = bool(manifest.get("disabled", False))

            skills: List[str] = []
            skills_root = pdir / "skills"
            if skills_root.is_dir():
                for sdir in sorted(skills_root.iterdir(), key=lambda p: p.name):
                    if sdir.is_dir() and (sdir / "SKILL.md").is_file():
                        skills.append(sdir.name)

            agents: List[str] = []
            agents_root = pdir / "agents"
            if agents_root.is_dir():
                for afile in sorted(agents_root.glob("*.md"), key=lambda p: p.name):
                    agents.append(afile.stem)

            rules: List[str] = []
            rules_root = pdir / "rules"
            if rules_root.is_dir():
                for rfile in sorted(rules_root.glob("*.md"), key=lambda p: p.name):
                    rules.append(str(rfile.resolve()))

            has_hooks = (pdir / "hooks.json").is_file()

            mcp_names: List[str] = []
            mcp_file = pdir / "mcp_config.json"
            if mcp_file.is_file():
                try:
                    mcp_data = parse_jsonc(mcp_file.read_text(encoding="utf-8"))
                    srv_map = (mcp_data or {}).get("mcpServers") or {}
                    if isinstance(srv_map, dict):
                        mcp_names.extend(str(k) for k in srv_map.keys())
                except Exception:
                    pass

            items.append(
                {
                    "name": name,
                    "dir": dir_name,
                    "path": str(pdir.resolve()),
                    "disabled": disabled,
                    "isGlobal": True,
                    "isBuiltin": _is_builtin_path(str(pdir)),
                    "skills": skills,
                    "agents": agents,
                    "rules": rules,
                    "hooks": has_hooks,
                    "mcp": mcp_names,
                    "customizationLink": f"[{name}](customization://{dir_name})",
                }
            )
        return items

    def list_plugins(
        self, workspace_uris: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Return context-flood-safe inventory of installed plugins via `GetAllPlugins` RPC,
        falling back to local filesystem discovery if the Language Server is offline.
        """
        payload: Dict[str, Any] = {}
        if workspace_uris is not None:
            payload["workspaceUris"] = list(workspace_uris)
        try:
            raw_resp = self.call_rpc("GetAllPlugins", payload)
            raw_plugins = raw_resp.get("plugins")
            if isinstance(raw_plugins, list):
                return [
                    self._compact_rpc_plugin_entry(p)
                    for p in raw_plugins
                    if isinstance(p, dict)
                ]
        except Exception:
            pass
        return self._scan_filesystem_plugins()

    def resolve_plugin_dir(
        self, target: str, workspace_uris: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Resolve a plugin target string to its inventory record.
        Matches exact `dir` first, then exact `name`, then case-insensitive `name`.
        Raises ValueError if not found or if multiple plugins match.
        """
        clean = (target or "").strip()
        if not clean:
            raise ValueError("Plugin target must not be empty")

        inventory = self.list_plugins(workspace_uris=workspace_uris)

        exact_dir = [p for p in inventory if p["dir"] == clean]
        if len(exact_dir) == 1:
            return exact_dir[0]

        exact_name = [p for p in inventory if p["name"] == clean]
        if len(exact_name) == 1:
            return exact_name[0]
        if len(exact_name) > 1:
            dirs = [p["dir"] for p in exact_name]
            raise ValueError(
                f"Ambiguous plugin name '{clean}' matches multiple install directories: {dirs}"
            )

        ci_matches = [
            p
            for p in inventory
            if p["name"].lower() == clean.lower() or p["dir"].lower() == clean.lower()
        ]
        if len(ci_matches) == 1:
            return ci_matches[0]
        if len(ci_matches) > 1:
            dirs = [p["dir"] for p in ci_matches]
            raise ValueError(
                f"Ambiguous plugin target '{clean}' matches multiple directories: {dirs}"
            )

        raise ValueError(f"Plugin '{clean}' not found in inventory")

    def set_plugin_enabled(
        self,
        target: str,
        enabled: bool,
        workspace_uris: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Enable or disable a plugin live via `JetboxWriteState` keyed by its true `dir`,
        and synchronize `config.json` atomically while preserving all sibling settings.
        """
        record = self.resolve_plugin_dir(target, workspace_uris=workspace_uris)
        dir_name = record["dir"]
        plugin_name = record["name"]
        bool_enabled = bool(enabled)

        rpc_ok = False
        try:
            self.call_rpc(
                "JetboxWriteState",
                {
                    "userConfig": {
                        "plugins": {dir_name: {"enabled": bool_enabled}}
                    }
                },
            )
            rpc_ok = True
        except Exception:
            rpc_ok = False

        cfg = self._read_local_config_json()
        plugins_map = cfg.get("plugins")
        if not isinstance(plugins_map, dict):
            plugins_map = {}
            cfg["plugins"] = plugins_map
        entry = plugins_map.get(dir_name)
        if not isinstance(entry, dict):
            entry = {}
        entry["enabled"] = bool_enabled
        plugins_map[dir_name] = entry
        self._write_local_config_json_atomic(cfg)

        return {
            "ok": True,
            "dir": dir_name,
            "name": plugin_name,
            "enabled": bool_enabled,
            "live_rpc": rpc_ok,
            "restart_required": False,
            "customizationLink": f"[{plugin_name}](customization://{dir_name})",
        }

    def uninstall_plugin(
        self, target: str, workspace_uris: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Safely uninstall a plugin via `DeletePlugin` with two mandatory guards:
        - Guard 1: Built-in plugins (`/builtin/plugins/`) cannot be uninstalled (PermissionError).
        - Guard 2: If the plugin is currently disabled, re-enable it via `JetboxWriteState(enabled=True)`
          before deleting so no stale disabled entry remains in `config.json`.
        """
        record = self.resolve_plugin_dir(target, workspace_uris=workspace_uris)
        dir_name = record["dir"]
        plugin_name = record["name"]

        if record.get("isBuiltin"):
            raise PermissionError(
                f"Built-in plugin '{plugin_name}' ({dir_name}) cannot be uninstalled; disable it instead."
            )

        reenabled_before_delete = False
        if record.get("disabled"):
            try:
                self.call_rpc(
                    "JetboxWriteState",
                    {"userConfig": {"plugins": {dir_name: {"enabled": True}}}},
                )
            except Exception:
                pass
            cfg = self._read_local_config_json()
            if isinstance(cfg.get("plugins"), dict) and dir_name in cfg["plugins"]:
                cfg["plugins"][dir_name] = {"enabled": True}
                self._write_local_config_json_atomic(cfg)
            reenabled_before_delete = True

        self.call_rpc("DeletePlugin", {"pluginId": dir_name})

        return {
            "ok": True,
            "dir": dir_name,
            "name": plugin_name,
            "reenabled_before_delete": reenabled_before_delete,
            "deleted": True,
            "restart_required": False,
        }

    def install_marketplace_plugin(self, marketplace_id: str) -> Dict[str, Any]:
        """Install a plugin from the Antigravity Agent Marketplace via `InstallCustomization`."""
        clean_id = (marketplace_id or "").strip()
        if not clean_id:
            raise ValueError("Marketplace customization ID must not be empty")

        try:
            self.call_rpc("InstallCustomization", {"id": clean_id})
            return {
                "ok": True,
                "id": clean_id,
                "restart_required": True,
            }
        except Exception as exc:
            msg = str(exc)
            if "source for customization not found" in msg.lower():
                raise RuntimeError(
                    f"Marketplace source not found for ID '{clean_id}' (either invalid Marketplace ID or Marketplace catalog is not enabled for this account): {msg}"
                ) from exc
            raise

    def detect_plugin_drift(
        self,
        source_roots: Sequence[Path | str],
        plugins_dir: Optional[Path | str] = None,
    ) -> Dict[str, Any]:
        """Detect drift between source roots and installed plugins using client configuration."""
        target_plugins_dir = plugins_dir or (self.config_root / "plugins")
        return detect_plugin_drift(source_roots, plugins_dir=target_plugins_dir)


def detect_plugin_drift(
    source_roots: Sequence[Path | str],
    plugins_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Detect manifest and version drift between source repositories and installed plugins."""
    p_dir = Path(plugins_dir).resolve() if plugins_dir else (_default_config_root() / "plugins").resolve()

    try:
        from agy_doctor_mux.sync import detect_plugin_drift as _mux_drift
        return _mux_drift(source_roots=source_roots, plugins_dir=p_dir)
    except Exception:
        pass

    drifted_plugins: List[Dict[str, Any]] = []
    missing_in_plugins: List[str] = []
    found_names: Set[str] = set()

    for s_root in source_roots:
        root = Path(s_root).resolve()
        if not root.is_dir():
            continue

        manifest_path: Optional[Path] = None
        plugin_name: str = root.name
        source_manifest: Dict[str, Any] = {}

        if (root / "plugin.json").is_file():
            manifest_path = root / "plugin.json"
        elif (root / "plugins").is_dir():
            for cand in (root / "plugins").iterdir():
                if cand.is_dir() and (cand / "plugin.json").is_file():
                    manifest_path = cand / "plugin.json"
                    plugin_name = cand.name
                    break

        if manifest_path and manifest_path.is_file():
            try:
                source_manifest = parse_jsonc(manifest_path.read_text(encoding="utf-8"))
                plugin_name = str(source_manifest.get("name") or plugin_name)
            except Exception:
                pass
        else:
            pyproj = root / "pyproject.toml"
            if pyproj.is_file():
                try:
                    text = pyproj.read_text(encoding="utf-8")
                    m_name = re.search(r'name\s*=\s*["\']([^"\']+)["\']', text)
                    m_ver = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
                    if m_name:
                        plugin_name = m_name.group(1)
                    if m_ver:
                        source_manifest = {"name": plugin_name, "version": m_ver.group(1)}
                except Exception:
                    pass

        found_names.add(plugin_name)
        installed_plugin_dir = p_dir / plugin_name
        installed_manifest_path = installed_plugin_dir / "plugin.json"

        if not installed_manifest_path.is_file():
            missing_in_plugins.append(plugin_name)
            continue

        try:
            installed_manifest = parse_jsonc(installed_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            installed_manifest = {}

        field_diffs: List[str] = []
        source_ver = str(source_manifest.get("version") or "")
        inst_ver = str(installed_manifest.get("version") or "")
        if source_ver and inst_ver and source_ver != inst_ver:
            field_diffs.append("version")

        source_desc = str(source_manifest.get("description") or "")
        inst_desc = str(installed_manifest.get("description") or "")
        if source_desc and inst_desc and source_desc != inst_desc:
            field_diffs.append("description")

        if field_diffs:
            drifted_plugins.append({
                "name": plugin_name,
                "source_version": source_ver,
                "installed_version": inst_ver,
                "field_diffs": field_diffs,
                "source_path": str(manifest_path or root),
                "installed_path": str(installed_manifest_path),
            })

    untracked_in_source: List[str] = []
    if p_dir.is_dir():
        for item in sorted(p_dir.iterdir()):
            if item.is_dir() and item.name not in found_names:
                untracked_in_source.append(item.name)

    return {
        "drift_detected": len(drifted_plugins) > 0 or len(missing_in_plugins) > 0,
        "drifted_plugins": drifted_plugins,
        "missing_in_plugins_dir": missing_in_plugins,
        "untracked_in_source": untracked_in_source,
    }
