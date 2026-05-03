#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "resources", "scripts"))

from terminal.pty_manager import PtySessionManager  # noqa: E402


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def wait_for_output(manager: PtySessionManager, terminal_id: str, needle: bytes) -> bytes:
    deadline = time.time() + 5.0
    while time.time() < deadline:
        attach = manager.attach(terminal_id)
        data = b"".join(chunk.data for chunk in attach.chunks)
        if needle in data:
            return data
        time.sleep(0.05)
    return b""


def main() -> int:
    manager = PtySessionManager(ring_chunks=16)
    info = manager.open(command=["/bin/sh"], rows=12, cols=40)
    terminal_id = info.terminal_id
    try:
        if not manager.write(terminal_id, b"printf 'NAPSEER_PTY_OK\\n'\n", input_seq=1):
            fail("initial write was not accepted")
        output = wait_for_output(manager, terminal_id, b"NAPSEER_PTY_OK")
        if b"NAPSEER_PTY_OK" not in output:
            fail("expected shell output was not captured")

        resized = manager.resize(terminal_id, rows=30, cols=100)
        if resized.rows != 30 or resized.cols != 100:
            fail("resize metadata was not updated")

        replay = manager.attach(terminal_id, last_output_seq=0)
        if not replay.chunks:
            fail("attach did not replay buffered output")

        if manager.write(terminal_id, b"ignored\n", input_seq=1):
            fail("duplicate input_seq was accepted")

        listed = manager.list()
        if not any(item.terminal_id == terminal_id for item in listed):
            fail("terminal was not returned by list()")
    finally:
        manager.close(terminal_id)

    if manager.list():
        fail("terminal remained listed after close")

    print("terminal PTY manager slice OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
