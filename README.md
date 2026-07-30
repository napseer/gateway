# Napseer Gateway

Gateway runtime source for Napseer.

This repository is the canonical source for:

- Gateway service runtime.
- Local terminal/chat execution managers.
- Relay listener behavior.
- Gateway vault and passphrase handling.
- Gateway Docker image and gateway runtime tests.

Current state:

- `resources/scripts/napseer_mcp_server.py` contains the gateway service runtime
  while compatibility decomposition continues.
- `resources/scripts/terminal/` contains the terminal runtime helpers.
- `scripts/` contains gateway-focused smoke and runtime tests.
- `Dockerfile` copies repository-owned runtime files into a digest-pinned base
  image. It performs no live Napseer API download during the build.

The backend remains the protocol and compatibility source of truth through `/v1/gateway-protocol`.
