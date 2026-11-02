"""Locked Agile V (P30) Verification Suite for Cross-Plugin RPC Deadlock Circuit Breaker.

Requirement Traceability:
- REQ-LSRPC-DEADLOCK-01: Tarjan SCC / DFS Wait-For Graph Deadlock Detector and
  Asynchronous Continuation Circuit Breaker (`rpc_deadlock_breaker.py`)

Hygiene: 100% English-only (0 Cyrillic characters).
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agy_lsrpc_bridge.rpc_deadlock_breaker import RPCDeadlockBreaker  # noqa: E402


def _field(obj: Any, name: str) -> Any:
    """Extract field from dict or dataclass/object transparently."""
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def test_acyclic_rpc_wait_registration_and_release() -> None:
    """REQ-LSRPC-DEADLOCK-01: Verify acyclic RPC wait registration, synchronous resolution, and edge release."""
    breaker = RPCDeadlockBreaker()
    r1 = breaker.register_rpc_wait(
        caller_repo="gemini_local_ui",
        callee_repo="agy-lsrpc-bridge",
        call_id="call_1",
    )
    r2 = breaker.register_rpc_wait(
        caller_repo="agy-lsrpc-bridge",
        callee_repo="agy-doctor-mux",
        call_id="call_2",
    )

    for res in (r1, r2):
        assert _field(res, "deadlock_detected") is False
        assert _field(res, "resolution") == "synchronous_wait"
        assert _field(res, "cycle_path") == []

    released = breaker.release_rpc_wait("call_1")
    assert released is True

    telemetry = breaker.get_breaker_telemetry()
    assert _field(telemetry, "active_edges") == 1


def test_direct_two_repo_circular_rpc_deadlock_breaker() -> None:
    """REQ-LSRPC-DEADLOCK-01: Verify direct two-repo circular wait trips circuit breaker into async_continuation."""
    breaker = RPCDeadlockBreaker()
    r1 = breaker.register_rpc_wait(
        caller_repo="repo_a",
        callee_repo="repo_b",
        call_id="call_1",
    )
    assert _field(r1, "deadlock_detected") is False

    r2 = breaker.register_rpc_wait(
        caller_repo="repo_b",
        callee_repo="repo_a",
        call_id="call_2",
    )
    assert _field(r2, "deadlock_detected") is True
    cycle_path = _field(r2, "cycle_path")
    assert "repo_a" in cycle_path
    assert "repo_b" in cycle_path
    assert _field(r2, "resolution") == "async_continuation"

    cont_id = _field(r2, "continuation_id")
    assert isinstance(cont_id, str) and cont_id.startswith("cont_")

    # Cycle-inducing edge must not remain in the active wait-for graph
    assert breaker.detect_all_cycles() == []


def test_multi_hop_three_repo_cycle_detection() -> None:
    """REQ-LSRPC-DEADLOCK-01: Verify 3-hop circular RPC dependency chain trips circuit breaker."""
    breaker = RPCDeadlockBreaker()
    r1 = breaker.register_rpc_wait(caller_repo="repo_a", callee_repo="repo_b", call_id="c1")
    r2 = breaker.register_rpc_wait(caller_repo="repo_b", callee_repo="repo_c", call_id="c2")
    assert _field(r1, "deadlock_detected") is False
    assert _field(r2, "deadlock_detected") is False

    r3 = breaker.register_rpc_wait(caller_repo="repo_c", callee_repo="repo_a", call_id="c3")
    assert _field(r3, "deadlock_detected") is True
    cycle_path = _field(r3, "cycle_path")
    assert len(cycle_path) >= 3
    for node in ("repo_a", "repo_b", "repo_c"):
        assert node in cycle_path
    assert _field(r3, "resolution") == "async_continuation"


def test_self_dependency_loop_rejected_immediately() -> None:
    """REQ-LSRPC-DEADLOCK-01: Verify self-loop RPC dependency is immediately tripped as deadlock."""
    breaker = RPCDeadlockBreaker()
    res = breaker.register_rpc_wait(
        caller_repo="repo_x",
        callee_repo="repo_x",
        call_id="call_self",
    )
    assert _field(res, "deadlock_detected") is True
    assert _field(res, "resolution") == "async_continuation"
    assert "repo_x" in _field(res, "cycle_path")


def test_detect_all_cycles_on_injected_graph() -> None:
    """REQ-LSRPC-DEADLOCK-01: Verify detect_all_cycles identifies elementary cycles on raw directed edges."""
    breaker = RPCDeadlockBreaker()
    breaker.add_raw_edge("node_1", "node_2")
    breaker.add_raw_edge("node_2", "node_3")
    breaker.add_raw_edge("node_3", "node_1")

    cycles = breaker.detect_all_cycles()
    assert isinstance(cycles, list)
    assert len(cycles) >= 1
    flattened = {n for cyc in cycles for n in cyc}
    assert {"node_1", "node_2", "node_3"}.issubset(flattened)


def test_breaker_telemetry_and_continuation_resolution() -> None:
    """REQ-LSRPC-DEADLOCK-01: Verify telemetry counters and asynchronous continuation completion."""
    breaker = RPCDeadlockBreaker()
    breaker.register_rpc_wait(caller_repo="svc_1", callee_repo="svc_2", call_id="w1")
    tripped = breaker.register_rpc_wait(caller_repo="svc_2", callee_repo="svc_1", call_id="w2")
    cont_id = _field(tripped, "continuation_id")

    telemetry = breaker.get_breaker_telemetry()
    assert _field(telemetry, "active_edges") == 1
    assert _field(telemetry, "tripped_count") >= 1
    assert _field(telemetry, "continuations_issued") >= 1

    resolved = breaker.resolve_continuation(cont_id, result={"ok": True})
    if isinstance(resolved, dict):
        assert resolved.get("status") in ("COMPLETED", "RESOLVED", True) or resolved.get("completed") is True or resolved.get("ok") is True
    else:
        assert bool(resolved) is True
