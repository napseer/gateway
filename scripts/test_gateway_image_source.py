#!/usr/bin/env python3
"""Verify that the gateway image is built from pinned repository source."""

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

assert "FROM registry.fedoraproject.org/fedora:42@sha256:" in dockerfile
assert "COPY resources/scripts/napseer_mcp_server.py" in dockerfile
assert "COPY resources/scripts/terminal/" in dockerfile
assert "/v1/scripts" not in dockerfile
assert "nap_install.py" not in dockerfile
assert "urllib.request" not in dockerfile
assert 'CMD ["python3", "/opt/napseer/napseer_mcp_server.py"' in dockerfile

print("ok: gateway image uses pinned repository-owned source")
