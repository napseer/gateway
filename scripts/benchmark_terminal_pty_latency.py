#!/usr/bin/env python3
"""Benchmark gateway-side PTY echo latency and output flush policy costs."""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "resources" / "scripts"))

from terminal.pty_manager import PtySessionManager  # noqa: E402


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((pct / 100.0) * len(ordered)))
    return ordered[index]


def summary(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(percentile(values, 50), 3),
        "p95_ms": round(percentile(values, 95), 3),
        "p99_ms": round(percentile(values, 99), 3),
        "max_ms": round(max(values) if values else 0.0, 3),
        "mean_ms": round(statistics.mean(values) if values else 0.0, 3),
    }


def benchmark_pty_echo(iterations: int) -> dict[str, float]:
    manager = PtySessionManager(ring_chunks=max(iterations * 2, 128))
    info = manager.open("cat", rows=24, cols=80)
    terminal_id = info.terminal_id
    latencies: list[float] = []
    pending: dict[bytes, float] = {}
    received = bytearray()

    def on_output(_terminal_id: str, _seq: int, data: bytes) -> None:
        received.extend(data)
        for marker, start in list(pending.items()):
            if marker in received:
                latencies.append((time.perf_counter() - start) * 1000)
                del pending[marker]

    unsubscribe = manager.subscribe(terminal_id, on_output)
    try:
        for index in range(iterations):
            marker = f"n{index:04d}".encode("ascii")
            pending[marker] = time.perf_counter()
            manager.write(terminal_id, marker + b"\n", input_seq=index + 1)
            deadline = time.perf_counter() + 2
            while marker in pending and time.perf_counter() < deadline:
                time.sleep(0.0005)
            if marker in pending:
                raise TimeoutError(f"timed out waiting for echo {marker!r}")
    finally:
        unsubscribe()
        manager.close(terminal_id)
    return summary(latencies)


def flush_policy_cost(iterations: int, immediate_bytes: int, timer_ms: int) -> dict[str, int | float]:
    immediate_flushes = 0
    timer_flushes = 0
    bulk_flushes = 0
    buffered = 0
    timer_pending = False
    chunks = [1, 2, 8, 32, 128, 512, 4096]
    start = time.perf_counter()
    for index in range(iterations):
        size = chunks[index % len(chunks)]
        buffered += size
        if size <= immediate_bytes:
            immediate_flushes += 1
            buffered = 0
            timer_pending = False
        elif buffered >= 4096:
            bulk_flushes += 1
            buffered = 0
            timer_pending = False
        elif not timer_pending:
            timer_flushes += 1
            timer_pending = timer_ms > 0
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "immediate_bytes": immediate_bytes,
        "timer_ms": timer_ms,
        "elapsed_ms": round(elapsed_ms, 3),
        "immediate_flushes": immediate_flushes,
        "timer_flushes": timer_flushes,
        "bulk_flushes": bulk_flushes,
    }


def main() -> None:
    iterations = int(os.environ.get("NAPSEER_TERMINAL_BENCH_ITERATIONS", "250"))
    immediate_bytes = int(os.environ.get("NAPSEER_GATEWAY_PTY_IMMEDIATE_FLUSH_BYTES", "256"))
    timer_ms = int(os.environ.get("NAPSEER_GATEWAY_PTY_INTERACTIVE_FLUSH_MS", "0"))
    result = {
        "iterations": iterations,
        "gateway": {
            "pty_echo_cat": benchmark_pty_echo(iterations),
            "flush_policy": flush_policy_cost(iterations * 20, immediate_bytes, timer_ms),
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
