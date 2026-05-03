#!/usr/bin/env python3
"""Smoke-test normal gateway capability registration."""

import importlib.util
import pathlib
import sys


def load_module():
    script_path = pathlib.Path(__file__).resolve().parents[1] / "resources" / "scripts" / "napseer_mcp_server.py"
    sys.path.insert(0, str(script_path.parent))
    spec = importlib.util.spec_from_file_location("napseer_mcp_server", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def run():
    mod = load_module()
    saves = []
    renewals = []

    mod.AUTH = {
        "worker_capabilities": {"local_mcp": True, "setup_script": "napseer_setup.py"},
    }
    mod.TOKEN = "np_existing"
    mod.save_auth = lambda payload: saves.append(payload) or mod.AUTH.update(payload)
    mod.renew_auth = lambda: renewals.append(dict(mod.AUTH))
    mod.gateway_log = lambda *args, **kwargs: None

    result = mod.ensure_gateway_worker_capability(refresh=True)
    assert result["status"] == "refreshed"
    assert result["worker_capabilities"]["gateway"] is True
    assert result["worker_capabilities"]["local_mcp"] is True
    assert result["worker_capabilities"]["setup_script"] == "napseer_setup.py"
    assert saves[-1]["worker_capabilities"]["gateway"] is True
    assert renewals and renewals[-1]["worker_capabilities"]["gateway"] is True

    merged = mod.gateway_worker_capabilities({"custom": "kept"})
    assert merged["gateway"] is True
    assert merged["custom"] == "kept"
    assert merged["local_mcp"] is True

    print("ok: normal gateway worker capability smoke passed")


if __name__ == "__main__":
    run()
