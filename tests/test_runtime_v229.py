"""Locked Agile V verification suite for Antigravity v2.29.0 LSRPC runtime contracts (REQ-LSRPC-V229-01)."""

from __future__ import annotations

import agy_lsrpc_bridge
from agy_lsrpc_bridge.runtime_v229 import (
    RESTRICTED_V229_MUTATION_RPCS,
    RuntimeV229Inspector,
    format_customization_and_sidecar_links,
    guard_restricted_lsrpc_mutation,
    validate_v229_plugin_metadata,
)


def test_req_lsrpc_v229_01_validate_author_homepage_and_repository_metadata() -> None:
    """Verify REQ-LSRPC-V229-01 plugin manifest author, homepage, and repository schema checks."""
    assert getattr(agy_lsrpc_bridge, "__v3_generation__", None) == "3.0.0"
    assert agy_lsrpc_bridge.RuntimeV229Inspector is RuntimeV229Inspector
    assert agy_lsrpc_bridge.validate_v229_plugin_metadata is validate_v229_plugin_metadata

    valid_manifest = {
        "name": "sample-plugin",
        "description": "Sample v2.29 plugin",
        "author": {"name": "Team", "url": "https://example.com"},
        "homepage": "https://example.com/docs",
        "repository": {"type": "git", "url": "https://github.com/example/plugin.git"},
    }
    valid_res = validate_v229_plugin_metadata(valid_manifest)
    assert valid_res["requirement_id"] == "REQ-LSRPC-V229-01"
    assert valid_res["valid"] is True
    assert valid_res["errors"] == []

    invalid_homepage = {
        "name": "sample-plugin",
        "author": {"name": "Team", "url": "https://example.com"},
        "homepage": "http://insecure.local",
        "repository": {"type": "git", "url": "https://github.com/example/plugin.git"},
    }
    res_home = validate_v229_plugin_metadata(invalid_homepage)
    assert res_home["valid"] is False
    assert len(res_home["errors"]) > 0

    invalid_author = {
        "name": "sample-plugin",
        "author": {"name": ""},
        "homepage": "https://example.com/docs",
        "repository": {"type": "git", "url": "https://github.com/example/plugin.git"},
    }
    res_author = validate_v229_plugin_metadata(invalid_author)
    assert res_author["valid"] is False
    assert len(res_author["errors"]) > 0

    invalid_repo = {
        "name": "sample-plugin",
        "author": {"name": "Team"},
        "homepage": "https://example.com/docs",
        "repository": {"type": "svn", "url": "ftp://bad"},
    }
    res_repo = validate_v229_plugin_metadata(invalid_repo)
    assert res_repo["valid"] is False
    assert len(res_repo["errors"]) > 0


def test_req_lsrpc_v229_01_customization_dir_links_and_sidecar_pills() -> None:
    """Verify REQ-LSRPC-V229-01 customization://<install_dir> and sidecar:// pill formatting."""
    assert (
        agy_lsrpc_bridge.format_customization_and_sidecar_links
        is format_customization_and_sidecar_links
    )
    links = format_customization_and_sidecar_links(
        install_dir="-1870732469773246571",
        sidecar_id="my-plugin/panel",
        view_path="host.html?view=auxpane",
        label="My Panel",
    )
    assert links["customization_link"] == "[My Panel](customization://-1870732469773246571)"
    assert "plugin://" not in links["customization_link"]
    assert links["sidecar_pill"] == "[My Panel](sidecar://my-plugin/panel/host.html?view=auxpane)"


def test_req_lsrpc_v229_01_restricted_mutation_rpc_guard() -> None:
    """Verify REQ-LSRPC-V229-01 restricted mutation RPC guard and RuntimeV229Inspector facade."""
    assert agy_lsrpc_bridge.RESTRICTED_V229_MUTATION_RPCS == RESTRICTED_V229_MUTATION_RPCS
    assert agy_lsrpc_bridge.guard_restricted_lsrpc_mutation is guard_restricted_lsrpc_mutation

    for restricted_rpc in ("JetboxWriteState", "DeletePlugin", "InstallCustomization"):
        assert restricted_rpc in RESTRICTED_V229_MUTATION_RPCS
        verdict = guard_restricted_lsrpc_mutation(restricted_rpc)
        assert verdict["allowed_in_subprocess"] is False

    read_verdict = guard_restricted_lsrpc_mutation("GetAllPlugins")
    assert read_verdict["allowed_in_subprocess"] is True

    inspector = RuntimeV229Inspector()
    meta_check = inspector.validate_metadata(
        {
            "author": {"name": "Team", "url": "https://example.com"},
            "homepage": "https://example.com/docs",
            "repository": {"type": "git", "url": "https://github.com/example/plugin.git"},
        }
    )
    assert meta_check["valid"] is True

    built_links = inspector.build_links(
        install_dir="-1870732469773246571",
        sidecar_id="my-plugin/panel",
        view_path="host.html?view=auxpane",
        label="My Panel",
    )
    assert built_links["customization_link"] == "[My Panel](customization://-1870732469773246571)"

    rpc_policy = inspector.check_rpc_policy("JetboxWriteState")
    assert rpc_policy["allowed_in_subprocess"] is False
