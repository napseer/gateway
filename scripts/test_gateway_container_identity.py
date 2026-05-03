#!/usr/bin/env python3
"""Smoke-test persisted gateway container identity behavior."""

import importlib.util
import json
import os
import pathlib
import sys
import tempfile


def load_module():
    script_path = pathlib.Path(__file__).resolve().parents[1] / "resources" / "scripts" / "napseer_mcp_server.py"
    sys.path.insert(0, str(script_path.parent))
    spec = importlib.util.spec_from_file_location("napseer_mcp_server", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def run():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.pop("NAPSEER_GATEWAY_CONTAINER_UUID", None)
        os.environ.pop("NAPSEER_CONTAINER_UUID", None)
        state_dir = pathlib.Path(tmp) / ".napseer"
        mod.AUTH_DIR = state_dir
        mod.AUTH_PATH = state_dir / "auth.json"
        mod.VAULT_PATH = state_dir / "vault.json"
        mod.CONTAINER_IDENTITY_PATH = state_dir / "container-identity.json"
        mod.AUTH = {}
        mod.BASE_URL = "https://api.test"
        mod.DEFAULT_PROJECT_ID = None
        mod.TOKEN = None
        mod.VAULT_SECRETS = {}

        first = mod.ensure_container_uuid()
        second = mod.ensure_container_uuid()
        assert_equal(second, first, "container uuid persists")
        payload = json.loads(mod.CONTAINER_IDENTITY_PATH.read_text(encoding="utf-8"))
        assert_equal(payload["container_uuid"], first, "container uuid file content")

        env_dir = pathlib.Path(tmp) / "env-state"
        env_uuid = "2a164e32-9d98-4b4e-9ad8-eed7307a5b08"
        mod.AUTH_DIR = env_dir
        mod.CONTAINER_IDENTITY_PATH = env_dir / "container-identity.json"
        os.environ["NAPSEER_GATEWAY_CONTAINER_UUID"] = env_uuid
        assert_equal(mod.ensure_container_uuid(), env_uuid, "env container uuid")
        env_payload = json.loads(mod.CONTAINER_IDENTITY_PATH.read_text(encoding="utf-8"))
        assert_equal(env_payload["container_uuid"], env_uuid, "env container uuid is persisted")
        os.environ.pop("NAPSEER_GATEWAY_CONTAINER_UUID", None)

        mod.AUTH_DIR = state_dir
        mod.CONTAINER_IDENTITY_PATH = state_dir / "container-identity.json"
        calls = []
        mod.vault_exists = lambda: False
        mod.gateway_setup = lambda payload: {"status": "configured"}
        mod.ensure_local_files = lambda: state_dir / "id_ed25519"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAAexample\n", encoding="utf-8")
        mod.request_json = lambda method, path, payload=None, **kwargs: calls.append((method, path, payload)) or {
            "registration": {
                "id": "reg_1",
                "project_id": "proj_1",
                "agent_id": "agt_1",
                "display_name": "gw",
                "device_fingerprint": "device",
                "root_path": "/workspace",
            },
            "activation_token": "npa_1",
        }
        mod.save_auth = lambda updates: None

        result = mod.gateway_service_preregister({
            "bootstrap_token": "npb_test",
            "passphrase": "pw",
            "display_name": "gw",
            "root_path": "/workspace",
            "device_fingerprint": "device",
        })
        assert_equal(result["status"], "pending_review", "preregister result")
        request_payload = calls[0][2]
        assert_equal(request_payload["container_uuid"], first, "request container uuid")
        assert_equal(request_payload["labels"]["container_uuid"], first, "label container uuid")
        assert_equal(request_payload["metadata"]["container_uuid"], first, "metadata container uuid")

    print("ok: gateway container identity smoke passed")


if __name__ == "__main__":
    run()
