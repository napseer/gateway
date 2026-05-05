import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path


def load_gateway_module():
    module_path = Path(__file__).resolve().parents[1] / "resources" / "scripts" / "napseer_mcp_server.py"
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("napseer_mcp_server", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_args(module):
    assert module.gateway_terminal_route_args(
        {"type": "terminal.key", "terminal_id": " %2 "},
        {"target": "napseer:0.0"},
    ) == {"terminal_id": "%2", "remote_authenticated": True}

    assert module.gateway_terminal_route_args(
        {"type": "terminal.key"},
        {"target": "napseer:1.0"},
    ) == {
        "tmux_target": "napseer:1.0",
        "_internal_target": True,
        "remote_authenticated": True,
    }


def test_output_payload(module):
    assert module.gateway_terminal_output_payload(
        {"type": "terminal.status", "status": "connected"},
        "%2",
    ) == {"type": "terminal.status", "status": "connected"}

    assert module.gateway_terminal_output_payload(
        {"type": "terminal.output", "data": "ready"},
        "%2",
    ) == {
        "type": "terminal.output",
        "data": "ready",
        "terminal_id": "%2",
        "selected_terminal_id": "%2",
    }


def test_gateway_key_routes_to_terminal_id(module):
    calls = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_windows(remote_authenticated=False):
        assert remote_authenticated is True
        return [
            {"id": "%1", "name": "agent", "index": "0", "target": "napseer:0.0", "active": True},
            {"id": "%2", "name": "codex", "index": "1", "target": "napseer:1.0", "active": False},
        ]

    def fake_tmux_run(args, timeout=10):
        calls.append(args)
        return Result()

    module.gateway_tmux_windows = fake_windows
    module.tmux_run = fake_tmux_run

    module.gateway_terminal_key({"terminal_id": "%2", "text": "x", "remote_authenticated": True})
    assert calls[-1] == ["send-keys", "-t", "napseer:1.0", "-l", "x"]

    module.gateway_terminal_key({
        "tmux_target": "fallback:0.0",
        "_internal_target": True,
        "text": "y",
        "remote_authenticated": True,
    })
    assert calls[-1] == ["send-keys", "-t", "fallback:0.0", "-l", "y"]


def test_close_selected_pty_switches_to_existing_terminal(module):
    closed = []
    opened = []

    class FakePtyManager:
        def __init__(self):
            self.items = [
                SimpleNamespace(
                    terminal_id="term-1",
                    command=["sh"],
                    rows=24,
                    cols=80,
                    output_seq=0,
                    oldest_output_seq=0,
                    created_at=1,
                    last_activity=1,
                    closed=False,
                    exit_code=None,
                ),
                SimpleNamespace(
                    terminal_id="term-2",
                    command=["sh"],
                    rows=24,
                    cols=80,
                    output_seq=0,
                    oldest_output_seq=0,
                    created_at=2,
                    last_activity=2,
                    closed=False,
                    exit_code=None,
                ),
            ]

        def list(self):
            return list(self.items)

        def open(self, *args, **kwargs):
            opened.append((args, kwargs))
            terminal = SimpleNamespace(
                terminal_id="replacement",
                command=["sh"],
                rows=24,
                cols=80,
                output_seq=0,
                oldest_output_seq=0,
                created_at=3,
                last_activity=3,
                closed=False,
                exit_code=None,
            )
            self.items.append(terminal)
            return terminal

        def close(self, terminal_id):
            closed.append(terminal_id)
            self.items = [item for item in self.items if item.terminal_id != terminal_id]

    manager = FakePtyManager()
    module.gateway_pty_manager = lambda: manager
    module.gateway_tmux_windows = lambda remote_authenticated=False: []

    result = module.gateway_terminal_close({
        "terminal_id": "term-1",
        "selected_terminal_id": "term-1",
        "create_replacement": True,
        "remote_authenticated": True,
    })

    assert closed == ["term-1"]
    assert opened == []
    assert result["selected_terminal_id"] == "term-2"


def test_rotation_gate_helpers(module):
    normal = module.gateway_rotation_gate_decision("terminal.open", {"allowed_frame_mode": "normal"})
    assert normal["allowed"] is True

    rotation_allow = module.gateway_rotation_gate_decision(
        "gateway.passphrase_rotation.challenge.request",
        {"allowed_frame_mode": "rotation_only"},
    )
    assert rotation_allow["allowed"] is True

    blocked = module.gateway_rotation_gate_decision("terminal.input", {"allowed_frame_mode": "rotation_only"})
    assert blocked == {
        "allowed": False,
        "reason": "rotation_required",
        "frame_class": "terminal_or_schedule",
    }


def test_rotation_result_payload_is_secret_blind(module):
    payload = module.gateway_rotation_result_payload(
        status="anything",
        code="unexpected_sensitive_detail",
        retry_required=True,
    )
    assert payload["type"] == "gateway.passphrase_rotation.result"
    assert payload["status"] == "retry_required"
    assert payload["code"] == "rotation_retry_required"
    assert payload["retry_required"] is True
    assert "sent_at" in payload


def test_rotation_required_session_skips_terminal_and_schedule_bootstrap(module):
    class FakeSocket:
        def close(self):
            return None

    sent = []
    ws_frames = iter([
        '{"type":"spake2.message","source":"client","message":"browser"}',
        '{"type":"spake2.result","source":"client","ok":true,"client_confirmation":"ok"}',
        None,
    ])
    terminal_bootstrap_calls = []
    schedule_calls = []

    module.AUTH = {"agent_id": "agent-1", "worker_id": "worker-1"}
    module.current_project_id = lambda: "project-1"
    module.read_gateway_relay_secret = lambda: b"relay-secret"
    module.relay_ws_url = lambda project_id, session_id, ticket, socket="terminal": "ws://relay.test"
    module.ws_connect = lambda url: FakeSocket()
    module.ws_read_text = lambda sock: next(ws_frames)
    module.ws_send_text = lambda sock, text: sent.append(text)
    module.gateway_requires_passphrase_rotation = lambda: True
    module.spake2_gateway_finish = lambda secret, context, browser_message: {
        "message": "gateway-message",
        "expected_client_confirmation": "ok",
        "confirmation": "gateway-confirm",
        "secret": b"spake-secret",
    }
    module.relay_key_from_secret = lambda secret, context, direction: b"k" + direction.encode("utf-8")
    module.relay_context_hash = lambda context: "ctx"
    module.encrypt_relay_frame = (
        lambda key, session_id, payload, context_hash, relay_lane, direction, seq: (
            '{"type":"encrypted","payload":' + json.dumps(payload, separators=(",", ":")) + "}"
        )
    )
    module.gateway_terminal_backend_from_id = lambda terminal_id, remote_authenticated=False: (
        terminal_bootstrap_calls.append((terminal_id, remote_authenticated))
        or ("pty", {"id": "term-1", "target": "t", "rows": 24, "cols": 80, "output_seq": 0})
    )
    module.gateway_schedule_list = lambda args=None: (
        schedule_calls.append(args) or {"schedules": [{"id": "sched-1"}]}
    )
    module.gateway_log = lambda *args, **kwargs: None

    module.handle_gateway_relay_session({
        "project_id": "project-1",
        "session_id": "session-1",
        "request_id": "request-1",
        "relay_ticket": "ticket-1",
        "spake2_context": {},
        "client_account_id": "acct-1",
        "client_id": "client-1",
    })

    encrypted_payloads = []
    for message in sent:
        if '"type":"encrypted"' not in message:
            continue
        payload_text = message.split('"payload":', 1)[1][:-1]
        encrypted_payloads.append(json.loads(payload_text))
    encrypted_types = [item.get("type") for item in encrypted_payloads]

    assert terminal_bootstrap_calls == []
    assert schedule_calls == []
    assert "terminal.session_list" not in encrypted_types
    assert "terminal.opened" not in encrypted_types
    assert "terminal.output" not in encrypted_types
    assert "schedule.list" not in encrypted_types
    assert "gateway.passphrase_rotation.result" in encrypted_types


def main():
    module = load_gateway_module()
    test_route_args(module)
    test_output_payload(module)
    test_gateway_key_routes_to_terminal_id(module)
    test_close_selected_pty_switches_to_existing_terminal(module)
    test_rotation_gate_helpers(module)
    test_rotation_result_payload_is_secret_blind(module)
    test_rotation_required_session_skips_terminal_and_schedule_bootstrap(module)
    print("gateway remote terminal slice passed")


if __name__ == "__main__":
    main()
