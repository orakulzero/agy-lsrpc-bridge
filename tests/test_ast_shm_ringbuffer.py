"""Locked Agile V (P30) Verification Suite for Shared-Memory AST Delta Ring Buffer.

Requirement Traceability:
- REQ-LSRPC-SHM-01: Zero-Copy Shared-Memory AST Delta Ring Buffer (`ast_shm_ringbuffer.py`)

Hygiene: 100% English-only (0 Cyrillic characters).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agy_lsrpc_bridge.ast_shm_ringbuffer import (  # noqa: E402
    ASTNodeDelta,
    SharedMemoryASTRingBuffer,
    compute_ast_delta,
)


def test_compute_ast_delta_detects_added_and_modified_symbols() -> None:
    """REQ-LSRPC-SHM-01: Verify compute_ast_delta detects added, modified, and removed AST symbols."""
    before_src = (
        "def alpha(x: int) -> int:\n"
        "    return x + 1\n\n"
        "def beta(y: int) -> int:\n"
        "    return y * 2\n\n"
        "def old_helper() -> str:\n"
        "    return 'legacy'\n"
    )
    after_src = (
        "def alpha(x: int) -> int:\n"
        "    return x + 1\n\n"
        "def beta(y: int) -> int:\n"
        "    return y * 10\n\n"
        "class GammaProcessor:\n"
        "    def run(self) -> bool:\n"
        "        return True\n"
    )
    deltas = compute_ast_delta(before_src, after_src, file_path="mod.py")
    assert isinstance(deltas, list)
    assert len(deltas) >= 3

    by_symbol = {d.symbol_name: d for d in deltas}
    for d in deltas:
        assert isinstance(d, ASTNodeDelta)
        assert d.file_path == "mod.py"
        assert d.change_type in ("added", "modified", "removed", "unchanged")
        assert d.start_line >= 1
        assert d.end_line >= d.start_line
        assert isinstance(d.ast_digest, str) and len(d.ast_digest) > 0

    assert "beta" in by_symbol and by_symbol["beta"].change_type == "modified"
    assert "GammaProcessor" in by_symbol and by_symbol["GammaProcessor"].change_type == "added"
    assert "old_helper" in by_symbol and by_symbol["old_helper"].change_type == "removed"


def test_compute_ast_delta_unchanged_returns_empty_or_unchanged() -> None:
    """REQ-LSRPC-SHM-01: Verify identical Python source produces 0 changed deltas."""
    source = (
        "def calculate(a: int, b: int) -> int:\n"
        "    return a + b\n\n"
        "class Worker:\n"
        "    pass\n"
    )
    deltas = compute_ast_delta(source, source, file_path="same.py")
    changed = [d for d in deltas if d.change_type != "unchanged"]
    assert changed == []


def test_shm_ringbuffer_write_and_read_roundtrip() -> None:
    """REQ-LSRPC-SHM-01: Verify SharedMemoryASTRingBuffer publish_delta and consume_delta roundtrip."""
    buf = SharedMemoryASTRingBuffer(capacity_slots=16, slot_size=2048)
    try:
        delta = ASTNodeDelta(
            file_path="src/engine.py",
            symbol_name="compute_metrics",
            change_type="modified",
            start_line=10,
            end_line=25,
            ast_digest="a1b2c3d4e5f60123",
        )
        seq = buf.publish_delta(delta)
        assert isinstance(seq, int) and seq >= 0

        read_back = buf.consume_delta(seq)
        assert isinstance(read_back, ASTNodeDelta)
        assert read_back.file_path == delta.file_path
        assert read_back.symbol_name == delta.symbol_name
        assert read_back.change_type == delta.change_type
        assert read_back.start_line == delta.start_line
        assert read_back.end_line == delta.end_line
        assert read_back.ast_digest == delta.ast_digest
    finally:
        buf.close()


def test_shm_ringbuffer_wrap_around_and_batch_drain() -> None:
    """REQ-LSRPC-SHM-01: Verify 20 deltas published into a 16-slot ring buffer wrap cleanly and drain_latest works."""
    buf = SharedMemoryASTRingBuffer(capacity_slots=16, slot_size=2048)
    try:
        for i in range(20):
            delta = ASTNodeDelta(
                file_path="src/stream.py",
                symbol_name=f"sym_{i}",
                change_type="modified" if i % 2 == 0 else "added",
                start_line=i * 5 + 1,
                end_line=i * 5 + 4,
                ast_digest=f"digest_{i:04d}",
            )
            buf.publish_delta(delta)

        stats = buf.stats()
        assert stats["total_published"] == 20
        assert stats["capacity_slots"] == 16

        latest = buf.drain_latest(limit=10)
        assert len(latest) == 10
        assert [d.symbol_name for d in latest] == [f"sym_{i}" for i in range(10, 20)]
    finally:
        buf.close()


def test_shm_ringbuffer_binary_compactness_and_close() -> None:
    """REQ-LSRPC-SHM-01: Verify serialize_delta produces compact UTF-8 bytes and close releases resources."""
    buf = SharedMemoryASTRingBuffer(capacity_slots=8, slot_size=1024)
    delta = ASTNodeDelta(
        file_path="src/compact.py",
        symbol_name="fast_op",
        change_type="added",
        start_line=1,
        end_line=12,
        ast_digest="deadbeefcafe0001",
    )
    raw = buf.serialize_delta(delta)
    assert isinstance(raw, bytes)
    assert 0 < len(raw) <= 512
    decoded = raw.decode("utf-8")
    assert "fast_op" in decoded

    buf.close()
    # Calling close() a second time must be safe / idempotent
    buf.close()


def test_req_lsrpc_shm_01_traceability_and_english_hygiene() -> None:
    """REQ-LSRPC-SHM-01: Verify ast_shm_ringbuffer.py contains REQ-LSRPC-SHM-01 and 0 Cyrillic characters."""
    target_file = REPO_ROOT / "src" / "agy_lsrpc_bridge" / "ast_shm_ringbuffer.py"
    assert target_file.is_file(), f"Missing target module: {target_file}"
    content = target_file.read_text(encoding="utf-8")
    assert "REQ-LSRPC-SHM-01" in content
    for ch in content:
        code = ord(ch)
        assert not (0x0400 <= code <= 0x04FF), f"Cyrillic character found: {ch!r}"
