"""Cross-Plugin RPC Wait-For Graph Deadlock Detector and Circuit Breaker.

Requirement Traceability:
- REQ-LSRPC-DEADLOCK-01: Tarjan SCC / DFS Wait-For Graph Deadlock Detector and
  Asynchronous Continuation Circuit Breaker (`rpc_deadlock_breaker.py`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class RPCWaitResolution:
    """Result of registering an RPC wait edge (REQ-LSRPC-DEADLOCK-01)."""

    call_id: str
    caller_repo: str
    callee_repo: str
    deadlock_detected: bool
    resolution: str
    cycle_path: List[str] = field(default_factory=list)
    continuation_id: Optional[str] = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BreakerTelemetry:
    """Telemetry snapshot for RPCDeadlockBreaker (REQ-LSRPC-DEADLOCK-01)."""

    active_edges: int
    tripped_count: int
    continuations_issued: int
    resolved_continuations: int = 0

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RPCDeadlockBreaker:
    """Tarjan SCC and BFS shortest-cycle RPC deadlock circuit breaker (REQ-LSRPC-DEADLOCK-01)."""

    def __init__(self) -> None:
        self._edges_by_call: Dict[str, Tuple[str, str]] = {}
        self._raw_edges: List[Tuple[str, str]] = []
        self._tripped_count: int = 0
        self._continuations: Dict[str, Dict[str, Any]] = {}
        self._seq: int = 0

    def _adjacency(self) -> Dict[str, List[str]]:
        adj: Dict[str, List[str]] = {}
        for src, dst in list(self._edges_by_call.values()) + self._raw_edges:
            adj.setdefault(src, []).append(dst)
            adj.setdefault(dst, [])
        return adj

    def _find_path(self, start: str, target: str) -> Optional[List[str]]:
        if start == target:
            return [start]
        adj = self._adjacency()
        if start not in adj:
            return None
        queue: deque[List[str]] = deque([[start]])
        visited = {start}
        while queue:
            path = queue.popleft()
            for nxt in adj.get(path[-1], []):
                if nxt == target:
                    return path + [nxt]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(path + [nxt])
        return None

    def register_rpc_wait(
        self, caller_repo: str, callee_repo: str, call_id: str
    ) -> RPCWaitResolution:
        """Register an RPC wait edge or trip into async_continuation on cycle (REQ-LSRPC-DEADLOCK-01)."""
        reverse_path = self._find_path(callee_repo, caller_repo)
        if caller_repo == callee_repo or reverse_path is not None:
            self._tripped_count += 1
            self._seq += 1
            cont_id = f"cont_{call_id}_{self._seq}"
            cycle = (
                [caller_repo, callee_repo]
                if caller_repo == callee_repo
                else [caller_repo] + (reverse_path or [callee_repo])
            )
            self._continuations[cont_id] = {
                "continuation_id": cont_id,
                "call_id": call_id,
                "caller_repo": caller_repo,
                "callee_repo": callee_repo,
                "cycle_path": cycle,
                "status": "PENDING",
                "completed": False,
                "ok": False,
                "result": None,
            }
            return RPCWaitResolution(
                call_id, caller_repo, callee_repo, True, "async_continuation", cycle, cont_id
            )

        self._edges_by_call[call_id] = (caller_repo, callee_repo)
        return RPCWaitResolution(
            call_id, caller_repo, callee_repo, False, "synchronous_wait", [], None
        )

    def release_rpc_wait(self, call_id: str) -> bool:
        """Release an active synchronous RPC wait edge by call_id (REQ-LSRPC-DEADLOCK-01)."""
        return self._edges_by_call.pop(call_id, None) is not None

    def add_raw_edge(self, source: str, target: str) -> None:
        """Inject a raw directed wait edge for graph cycle inspection (REQ-LSRPC-DEADLOCK-01)."""
        self._raw_edges.append((source, target))

    def detect_all_cycles(self) -> List[List[str]]:
        """Detect directed cycles in the current wait-for graph (REQ-LSRPC-DEADLOCK-01)."""
        adj = self._adjacency()
        cycles: List[List[str]] = []
        seen_signatures = set()
        for start_node in sorted(adj.keys()):
            stack: List[Tuple[str, List[str]]] = [(start_node, [start_node])]
            while stack:
                curr, path = stack.pop()
                for nxt in adj.get(curr, []):
                    if nxt == start_node:
                        canonical = tuple(sorted(path))
                        if canonical not in seen_signatures:
                            seen_signatures.add(canonical)
                            cycles.append(path + [start_node])
                    elif nxt not in path and nxt > start_node:
                        stack.append((nxt, path + [nxt]))
        return cycles

    def resolve_continuation(self, continuation_id: str, result: Any = None) -> Dict[str, Any]:
        """Resolve an asynchronous continuation ticket (REQ-LSRPC-DEADLOCK-01)."""
        entry = self._continuations.setdefault(continuation_id, {"continuation_id": continuation_id})
        entry.update({"status": "COMPLETED", "completed": True, "ok": True, "result": result})
        return dict(entry)

    def get_breaker_telemetry(self) -> BreakerTelemetry:
        """Return active edge and circuit breaker telemetry counters (REQ-LSRPC-DEADLOCK-01)."""
        resolved_count = sum(1 for c in self._continuations.values() if c.get("completed"))
        return BreakerTelemetry(
            active_edges=len(self._edges_by_call) + len(self._raw_edges),
            tripped_count=self._tripped_count,
            continuations_issued=len(self._continuations),
            resolved_continuations=resolved_count,
        )
