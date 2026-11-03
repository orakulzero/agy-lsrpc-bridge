"""Zero-Copy Shared-Memory AST Delta Ring Buffer (REQ-LSRPC-SHM-01).

Provides AST symbol diffing (`compute_ast_delta`) and an IPC ring buffer
backed by `multiprocessing.shared_memory` (`SharedMemoryASTRingBuffer`)
for low-latency cross-process AST delta streaming.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from multiprocessing import shared_memory
import struct
from typing import Any
import contextlib


@dataclass(frozen=True)
class ASTNodeDelta:
    """Represents a single symbol-level AST change (REQ-LSRPC-SHM-01)."""

    file_path: str
    symbol_name: str
    change_type: str
    start_line: int
    end_line: int
    ast_digest: str


def _extract_top_level_symbols(source: str) -> dict[str, tuple[int, int, str]]:
    """Parse Python source and map top-level symbol names to (start_line, end_line, ast_digest)."""
    tree = ast.parse(source)
    symbols: dict[str, tuple[int, int, str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start_line = max(1, int(getattr(node, "lineno", 1)))
            end_line = max(start_line, int(getattr(node, "end_lineno", start_line)))
            canonical = ast.dump(node, annotate_fields=True, include_attributes=False)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
            symbols[node.name] = (start_line, end_line, digest)
    return symbols


def compute_ast_delta(
    before_src: str,
    after_src: str,
    file_path: str = "module.py",
) -> list[ASTNodeDelta]:
    """Compute symbol-level AST deltas between two Python source snapshots (REQ-LSRPC-SHM-01)."""
    before_map = _extract_top_level_symbols(before_src)
    after_map = _extract_top_level_symbols(after_src)

    deltas: list[ASTNodeDelta] = []
    seen: set[str] = set()

    for sym_name, (start_line, end_line, after_digest) in after_map.items():
        seen.add(sym_name)
        if sym_name not in before_map:
            change_type = "added"
        else:
            _, _, before_digest = before_map[sym_name]
            change_type = "unchanged" if before_digest == after_digest else "modified"
        deltas.append(
            ASTNodeDelta(
                file_path=file_path,
                symbol_name=sym_name,
                change_type=change_type,
                start_line=start_line,
                end_line=end_line,
                ast_digest=after_digest,
            )
        )

    for sym_name, (start_line, end_line, before_digest) in before_map.items():
        if sym_name not in seen:
            deltas.append(
                ASTNodeDelta(
                    file_path=file_path,
                    symbol_name=sym_name,
                    change_type="removed",
                    start_line=start_line,
                    end_line=end_line,
                    ast_digest=before_digest,
                )
            )

    return deltas


class SharedMemoryASTRingBuffer:
    """Fixed-slot shared-memory ring buffer for ASTNodeDelta frames (REQ-LSRPC-SHM-01)."""

    def __init__(self, capacity_slots: int = 16, slot_size: int = 2048) -> None:
        """Initialize shared memory ring buffer with fixed slot geometry (REQ-LSRPC-SHM-01)."""
        if capacity_slots <= 0 or slot_size <= 16:
            raise ValueError("capacity_slots must be > 0 and slot_size must be > 16")
        self.capacity_slots = int(capacity_slots)
        self.slot_size = int(slot_size)
        self._total_bytes = self.capacity_slots * self.slot_size
        self._write_seq = 0
        self._closed = False
        self._shm: shared_memory.SharedMemory | None = shared_memory.SharedMemory(
            create=True, size=self._total_bytes
        )

    def serialize_delta(self, delta: ASTNodeDelta) -> bytes:
        """Serialize an ASTNodeDelta into compact UTF-8 JSON bytes (REQ-LSRPC-SHM-01)."""
        payload = {
            "f": delta.file_path,
            "s": delta.symbol_name,
            "c": delta.change_type,
            "l0": delta.start_line,
            "l1": delta.end_line,
            "d": delta.ast_digest,
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    def deserialize_delta(self, raw: bytes) -> ASTNodeDelta:
        """Deserialize compact UTF-8 JSON bytes back into an ASTNodeDelta (REQ-LSRPC-SHM-01)."""
        obj = json.loads(raw.decode("utf-8"))
        return ASTNodeDelta(
            file_path=str(obj["f"]),
            symbol_name=str(obj["s"]),
            change_type=str(obj["c"]),
            start_line=int(obj["l0"]),
            end_line=int(obj["l1"]),
            ast_digest=str(obj["d"]),
        )

    def publish_delta(self, delta: ASTNodeDelta) -> int:
        """Write an ASTNodeDelta into the next ring buffer slot and return its sequence number (REQ-LSRPC-SHM-01)."""
        if self._closed or self._shm is None:
            raise RuntimeError("SharedMemoryASTRingBuffer is closed")
        raw = self.serialize_delta(delta)
        if len(raw) + 4 > self.slot_size:
            raise ValueError(f"Serialized delta ({len(raw)} bytes) exceeds slot_size ({self.slot_size})")

        seq = self._write_seq
        slot_offset = (seq % self.capacity_slots) * self.slot_size
        buf = self._shm.buf
        struct.pack_into(">I", buf, slot_offset, len(raw))
        buf[slot_offset + 4 : slot_offset + 4 + len(raw)] = raw
        self._write_seq += 1
        return seq

    def consume_delta(self, seq: int) -> ASTNodeDelta:
        """Read an ASTNodeDelta from the ring buffer by sequence number (REQ-LSRPC-SHM-01)."""
        if self._closed or self._shm is None:
            raise RuntimeError("SharedMemoryASTRingBuffer is closed")
        oldest_seq = max(0, self._write_seq - self.capacity_slots)
        if seq < oldest_seq or seq >= self._write_seq:
            raise IndexError(f"Sequence {seq} outside retained window [{oldest_seq}, {self._write_seq})")

        slot_offset = (seq % self.capacity_slots) * self.slot_size
        buf = self._shm.buf
        (length,) = struct.unpack_from(">I", buf, slot_offset)
        raw = bytes(buf[slot_offset + 4 : slot_offset + 4 + length])
        return self.deserialize_delta(raw)

    def drain_latest(self, limit: int = 10) -> list[ASTNodeDelta]:
        """Return up to `limit` most recently published ASTNodeDelta items in order (REQ-LSRPC-SHM-01)."""
        if limit <= 0 or self._write_seq == 0:
            return []
        available = min(limit, self._write_seq, self.capacity_slots)
        start_seq = self._write_seq - available
        return [self.consume_delta(seq) for seq in range(start_seq, self._write_seq)]

    def stats(self) -> dict[str, Any]:
        """Return ring buffer telemetry statistics (REQ-LSRPC-SHM-01)."""
        return {
            "total_published": self._write_seq,
            "capacity_slots": self.capacity_slots,
            "slot_size": self.slot_size,
            "retained_slots": min(self._write_seq, self.capacity_slots),
        }

    def close(self) -> None:
        """Release and unlink the underlying shared memory segment idempotently (REQ-LSRPC-SHM-01)."""
        if self._closed:
            return
        self._closed = True
        if self._shm is not None:
            with contextlib.suppress(Exception):
                self._shm.close()
            with contextlib.suppress(Exception):
                self._shm.unlink()
            self._shm = None
