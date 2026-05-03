#!/usr/bin/env python3
"""Smoke-test gateway relay AES-GCM without requiring Node.js."""

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
    zero_key = bytes.fromhex("00" * 32)
    zero_nonce = bytes.fromhex("00" * 12)

    packed = mod.aes_gcm_encrypt(zero_key, zero_nonce, b"", b"")
    assert packed.hex() == "530f8afbc74536b9a963b4f1c4cb738b"
    assert mod.aes_gcm_decrypt(zero_key, zero_nonce, b"", packed) == b""

    packed = mod.aes_gcm_encrypt(zero_key, zero_nonce, b"", bytes(16))
    assert packed.hex() == "cea7403d4d606b6e074ec5d3baf39d18d0d1c8a799996bf0265b98b5d48ab919"
    assert mod.aes_gcm_decrypt(zero_key, zero_nonce, b"", packed) == bytes(16)

    key = bytes.fromhex("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308")
    nonce = bytes.fromhex("cafebabefacedbaddecaf888")
    aad = bytes.fromhex("feedfacedeadbeeffeedfacedeadbeefabaddad2")
    plaintext = bytes.fromhex("d9313225f88406e5a55909c5aff5269a")
    packed = mod.aes_gcm_encrypt(key, nonce, aad, plaintext)
    assert packed[:16].hex() == "522dc1f099567d07f47f37a32a84427d"
    assert mod.aes_gcm_decrypt(key, nonce, aad, packed) == plaintext

    print("ok: gateway relay crypto smoke passed")


if __name__ == "__main__":
    run()
