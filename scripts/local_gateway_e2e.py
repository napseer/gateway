#!/usr/bin/env python3
import base64
import json
import os
import secrets
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.parse

import requests


API_BASE = os.environ.get("NAPSEER_E2E_API_BASE", "http://127.0.0.1:3000")
KEYCLOAK_BASE = os.environ.get("NAPSEER_E2E_KEYCLOAK_BASE", "http://localhost:18080")
KEYCLOAK_HOST_HEADER = os.environ.get("NAPSEER_E2E_KEYCLOAK_HOST")
OPERATOR_USERNAME = os.environ.get("NAPSEER_E2E_USERNAME", "local-operator")
OPERATOR_PASSWORD = os.environ.get("NAPSEER_E2E_PASSWORD", "napseer-password")


def request_json(method, path, token=None, payload=None, headers=None):
    req_headers = {"accept": "application/json", **(headers or {})}
    if token:
        req_headers["authorization"] = f"Bearer {token}"
    if payload is not None:
        req_headers["content-type"] = "application/json"
    response = requests.request(
        method,
        f"{API_BASE}{path}",
        headers=req_headers,
        data=json.dumps(payload) if payload is not None else None,
        timeout=15,
    )
    try:
        data = response.json()
    except Exception:
        data = {"body": response.text}
    if not response.ok:
        raise RuntimeError(f"{method} {path} failed with {response.status_code}: {data}")
    return data


def get_operator_token():
    response = requests.post(
        f"{KEYCLOAK_BASE}/realms/napseer/protocol/openid-connect/token",
        headers={
            **({"host": KEYCLOAK_HOST_HEADER} if KEYCLOAK_HOST_HEADER else {}),
            "content-type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "password",
            "client_id": "napseer-frontend",
            "username": OPERATOR_USERNAME,
            "password": OPERATOR_PASSWORD,
        },
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(f"failed to get Keycloak token: {response.status_code} {response.text}")
    return response.json()["access_token"]


def enroll_worker():
    with tempfile.TemporaryDirectory() as tempdir:
        key_path = os.path.join(tempdir, "gateway_ed25519")
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key_path],
            check=True,
        )
        with open(f"{key_path}.pub", "r", encoding="utf-8") as handle:
            public_key = handle.read().strip()
        challenge = request_json(
            "POST",
            "/v1/enrollment/challenges",
            payload={
                "public_key": public_key,
                "worker_name": "local-e2e-gateway",
                "device_fingerprint": f"local-e2e-{secrets.token_hex(4)}",
                "root_path": f"/tmp/napseer-local-e2e-{secrets.token_hex(4)}",
                "worker_capabilities": {"gateway": True, "e2e": True},
            },
        )
        signature = subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", key_path, "-n", "napseer"],
            input=challenge["challenge_text"],
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        verified = request_json(
            "POST",
            "/v1/enrollment/verify",
            payload={"challenge_id": challenge["challenge_id"], "signature": signature},
        )
        return verified


def create_project(worker_token):
    return request_json(
        "POST",
        "/v1/projects",
        token=worker_token,
        payload={
            "slug": f"local-gateway-e2e-{secrets.token_hex(4)}",
            "name": "Local Gateway E2E",
            "description": "Isolated compose gateway relay E2E project",
        },
        headers={"Idempotency-Key": f"local-gateway-e2e-{secrets.token_hex(8)}"},
    )


def claim_worker_account(worker_token, operator_token):
    claim = request_json(
        "POST",
        "/v1/account/claim-links",
        token=worker_token,
        payload={"return_url": "http://localhost:4321/claimed"},
    )
    claim_token = claim["claim_url"].rstrip("/").split("/")[-1]
    return request_json(
        "POST",
        f"/v1/account/claim-links/{urllib.parse.quote(claim_token)}/complete",
        token=operator_token,
    )


class WebSocketClient:
    def __init__(self, url, headers=None, origin="http://localhost:3000"):
        self.url = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((self.url.hostname, self.url.port or 80), timeout=10)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        path = self.url.path or "/"
        if self.url.query:
            path = f"{path}?{self.url.query}"
        host = self.url.netloc
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            f"Origin: {origin}",
        ]
        for name, value in (headers or {}).items():
            lines.append(f"{name}: {value}")
        lines.extend(["", ""])
        self.sock.sendall("\r\n".join(lines).encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError(f"websocket upgrade failed: {response.decode('utf-8', 'replace')}")

    def send_text(self, value):
        data = value.encode("utf-8")
        header = bytearray([0x81])
        if len(data) < 126:
            header.append(0x80 | len(data))
        elif len(data) <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(data)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(data)))
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_text(self, timeout=10):
        self.sock.settimeout(timeout)
        while True:
            first = self._read_exact(2)
            opcode = first[0] & 0x0F
            masked = bool(first[1] & 0x80)
            length = first[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x1:
                return payload.decode("utf-8")
            if opcode == 0x8:
                raise RuntimeError("websocket closed")
            if opcode == 0x9:
                self._send_pong(payload)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

    def _read_exact(self, length):
        chunks = []
        remaining = length
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("websocket closed while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _send_pong(self, payload):
        header = bytearray([0x8A, 0x80 | len(payload)])
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)


def expect_ws_json(ws, predicate, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = json.loads(ws.recv_text(timeout=max(0.2, deadline - time.time())))
        if predicate(value):
            return value
    raise RuntimeError("expected websocket JSON frame was not received")


def wait_for_session_status(project_id, session_id, token, expected, timeout=10):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = request_json("GET", f"/v1/projects/{project_id}/gateway-sessions/{session_id}", token=token)
        if last["status"] == expected:
            return last
        time.sleep(0.2)
    raise RuntimeError(f"gateway session did not reach {expected}: {last}")


def run():
    operator_token = get_operator_token()
    operator_account = request_json("GET", "/v1/account", token=operator_token)
    enrolled = enroll_worker()
    worker_token = enrolled["token"]["access_token"]
    worker = enrolled["worker"]
    project = create_project(worker_token)

    offline = requests.post(
        f"{API_BASE}/v1/projects/{project['id']}/gateways/{worker['agent_id']}/connect",
        headers={"authorization": f"Bearer {operator_token}", "content-type": "application/json"},
        data=json.dumps({"client_id": "local-e2e-offline"}),
        timeout=15,
    )
    if offline.status_code not in (404, 409):
        raise RuntimeError(f"offline connect should fail, got {offline.status_code}: {offline.text}")

    claim = claim_worker_account(worker_token, operator_token)
    projects = request_json("GET", "/v1/projects", token=operator_token)
    if not any(item["id"] == project["id"] for item in projects["items"]):
        raise RuntimeError("claimed operator cannot see worker-created project")

    listener_url = (
        f"ws://127.0.0.1:3000/v1/projects/{project['id']}"
        f"/gateways/{urllib.parse.quote(worker['agent_id'])}/listener"
    )
    listener = WebSocketClient(listener_url, headers={"Authorization": f"Bearer {worker_token}"})
    listener_state = {}

    def listener_loop():
        request = json.loads(listener.recv_text(timeout=15))
        listener_state["request"] = request
        listener.send_text(json.dumps({"type": "connect.accept", "request_id": request["request_id"]}))

    thread = threading.Thread(target=listener_loop, daemon=True)
    thread.start()

    connect = request_json(
        "POST",
        f"/v1/projects/{project['id']}/gateways/{worker['agent_id']}/connect",
        token=operator_token,
        payload={"client_id": "local-e2e-client", "metadata": {"source": "local_gateway_e2e.py"}},
    )
    thread.join(timeout=10)
    if "request" not in listener_state:
        raise RuntimeError("gateway listener did not receive connect.request")

    session_id = connect["session"]["id"]
    gateway_ticket = listener_state["request"]["relay_ticket"]
    client_ticket = connect["ticket"]
    relay_base = f"ws://127.0.0.1:3000/v1/projects/{project['id']}/gateway-sessions/{session_id}/relay"
    client_ws = WebSocketClient(f"{relay_base}?ticket={urllib.parse.quote(client_ticket)}")
    gateway_ws = WebSocketClient(f"{relay_base}?ticket={urllib.parse.quote(gateway_ticket)}")

    client_ws.send_text(json.dumps({
        "type": "spake2.result",
        "source": "browser",
        "session_id": session_id,
        "ok": True,
        "client_confirmation": "local-e2e-client-confirmation"
    }))
    gateway_ws.send_text(json.dumps({
        "type": "spake2.result",
        "source": "gateway",
        "session_id": session_id,
        "ok": True,
        "gateway_confirmation": "local-e2e-gateway-confirmation"
    }))
    opened = wait_for_session_status(project["id"], session_id, operator_token, "open")

    client_frame = {
        "type": "encrypted",
        "alg": "AES-GCM-256",
        "session_id": session_id,
        "context_hash": "local-e2e-context",
        "direction": "client_to_gateway",
        "seq": 1,
        "nonce": base64.b64encode(secrets.token_bytes(12)).decode("ascii"),
        "ciphertext": base64.b64encode(b"opaque-client-frame").decode("ascii"),
    }
    client_ws.send_text(json.dumps(client_frame))
    gateway_seen = expect_ws_json(
        gateway_ws,
        lambda value: value.get("type") == "encrypted"
        and value.get("direction") == "client_to_gateway"
        and value.get("seq") == 1,
    )

    gateway_frame = {
        **client_frame,
        "direction": "gateway_to_client",
        "seq": 2,
        "nonce": base64.b64encode(secrets.token_bytes(12)).decode("ascii"),
        "ciphertext": base64.b64encode(b"opaque-gateway-frame").decode("ascii"),
    }
    gateway_ws.send_text(json.dumps(gateway_frame))
    client_seen = expect_ws_json(
        client_ws,
        lambda value: value.get("type") == "encrypted"
        and value.get("direction") == "gateway_to_client"
        and value.get("seq") == 2,
    )

    client_ws.close()
    gateway_ws.close()
    listener.close()

    print(json.dumps({
        "status": "ok",
        "operator_account_id": operator_account["id"],
        "claim_account_id": claim["account_id"],
        "project_id": project["id"],
        "worker_id": worker["id"],
        "gateway_agent_id": worker["agent_id"],
        "session_id": session_id,
        "offline_connect_status": offline.status_code,
        "open_status": opened["status"],
        "gateway_received": {
            "direction": gateway_seen["direction"],
            "seq": gateway_seen["seq"],
        },
        "client_received": {
            "direction": client_seen["direction"],
            "seq": client_seen["seq"],
        },
    }, indent=2))


if __name__ == "__main__":
    run()
