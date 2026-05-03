# Napseer Gateway

Gateway runtime source for Napseer.

This repository is intended to become the canonical source for:

- Gateway service runtime.
- Local terminal/chat execution managers.
- Relay listener behavior.
- Gateway vault and passphrase handling.
- Gateway Docker image and gateway runtime tests.

Current state:

- `resources/scripts/napseer_mcp_server.py` is still the pre-split runtime script copied from the backend.
- `resources/scripts/terminal/` contains the terminal runtime helpers.
- `scripts/` contains gateway-focused smoke and runtime tests.
- `Dockerfile` installs the published `nap` command and runs gateway service mode.

The backend remains the protocol and compatibility source of truth through `/v1/gateway-protocol`.
