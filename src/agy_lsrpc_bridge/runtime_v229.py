"""Antigravity v2.29.0 LSRPC runtime metadata, customization link, and mutation RPC contracts (REQ-LSRPC-V229-01)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIREMENT_ID = "REQ-LSRPC-V229-01"

RESTRICTED_V229_MUTATION_RPCS: frozenset[str] = frozenset(
    {
        "JetboxWriteState",
        "DeletePlugin",
        "InstallCustomization",
    }
)


def validate_v229_plugin_metadata(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate REQ-LSRPC-V229-01 plugin manifest author, homepage, and repository schema."""
    errors: list[str] = []

    if not isinstance(manifest, Mapping):
        return {
            "requirement_id": REQUIREMENT_ID,
            "valid": False,
            "errors": ["Manifest must be a mapping."],
        }

    author = manifest.get("author")
    if not isinstance(author, Mapping):
        errors.append("Field 'author' must be an object containing at least 'name'.")
    else:
        author_name = author.get("name")
        if not isinstance(author_name, str) or not author_name.strip():
            errors.append("Field 'author.name' must be a non-empty string.")
        author_url = author.get("url")
        if author_url is not None and (
            not isinstance(author_url, str) or not author_url.startswith("https://")
        ):
            errors.append("Field 'author.url' must be an HTTPS URL when provided.")

    homepage = manifest.get("homepage")
    if not isinstance(homepage, str) or not homepage.startswith("https://"):
        errors.append("Field 'homepage' must be a valid HTTPS URL.")

    repository = manifest.get("repository")
    if not isinstance(repository, Mapping):
        errors.append("Field 'repository' must be an object with 'type' and 'url'.")
    else:
        repo_type = repository.get("type")
        repo_url = repository.get("url")
        if repo_type != "git":
            errors.append("Field 'repository.type' must equal 'git'.")
        if not isinstance(repo_url, str) or not (
            repo_url.startswith("https://") or repo_url.startswith("git+https://")
        ):
            errors.append("Field 'repository.url' must be an HTTPS git URL.")

    return {
        "requirement_id": REQUIREMENT_ID,
        "valid": len(errors) == 0,
        "errors": errors,
    }


def format_customization_and_sidecar_links(
    install_dir: str,
    sidecar_id: str,
    view_path: str = "host.html?view=auxpane",
    label: str = "Plugin",
) -> dict[str, str]:
    """Build v2.29.0 customization://<install_dir> and sidecar:// markdown pills (REQ-LSRPC-V229-01)."""
    clean_dir = str(install_dir).strip().strip("/")
    clean_sidecar = str(sidecar_id).strip().strip("/")
    clean_view = str(view_path).strip().lstrip("/")
    clean_label = str(label).strip() or "Plugin"

    return {
        "requirement_id": REQUIREMENT_ID,
        "customization_link": f"[{clean_label}](customization://{clean_dir})",
        "sidecar_pill": f"[{clean_label}](sidecar://{clean_sidecar}/{clean_view})",
    }


def guard_restricted_lsrpc_mutation(rpc_name: str) -> dict[str, Any]:
    """Check whether an LSRPC method is restricted in v2.29.0 subprocess contexts (REQ-LSRPC-V229-01)."""
    clean_rpc = str(rpc_name).strip()
    is_restricted = clean_rpc in RESTRICTED_V229_MUTATION_RPCS
    return {
        "requirement_id": REQUIREMENT_ID,
        "rpc_name": clean_rpc,
        "allowed_in_subprocess": not is_restricted,
        "reason": (
            f"RPC '{clean_rpc}' is restricted to host UI in v2.29.0."
            if is_restricted
            else f"RPC '{clean_rpc}' is permitted in subprocess context."
        ),
    }


class RuntimeV229Inspector:
    """Facade for Antigravity v2.29.0 LSRPC metadata, link, and mutation policy checks (REQ-LSRPC-V229-01)."""

    requirement_id: str = REQUIREMENT_ID

    def validate_metadata(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Validate plugin manifest author, homepage, and repository metadata."""
        return validate_v229_plugin_metadata(manifest)

    def build_links(
        self,
        install_dir: str,
        sidecar_id: str,
        view_path: str = "host.html?view=auxpane",
        label: str = "Plugin",
    ) -> dict[str, str]:
        """Format customization:// and sidecar:// links for v2.29.0 UI surfaces."""
        return format_customization_and_sidecar_links(
            install_dir=install_dir,
            sidecar_id=sidecar_id,
            view_path=view_path,
            label=label,
        )

    def check_rpc_policy(self, rpc_name: str) -> dict[str, Any]:
        """Evaluate whether the target LSRPC call is permitted from a subprocess."""
        return guard_restricted_lsrpc_mutation(rpc_name)
