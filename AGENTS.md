# Agent Instructions

This file is bootstrap guidance only. Napseer is the canonical project memory source.

## Operating Order

For non-trivial work:

1. Consult BotAI MCP for read-only advisory guidance.
2. Query Napseer for current project memory.
3. Inspect this repository or runtime before changing anything.
4. Make the smallest scoped change that satisfies the task.
5. Verify with focused proof.
6. Record durable outcomes in Napseer when behavior, product direction, security, plans, or operations change.

## Memory Source

Use Napseer as the only project memory source. Do not create scattered Markdown files for internal project understanding. Repository Markdown is only for bootstrap instructions or intentional public/versioned documentation.

Start with:

- `/rules/memory-source-policy`
- `/documentation/features/gateway-terminal`
- `/indexes/gateway-terminal-system`
- `/documentation/product/ideal-mcp-and-cli`
- `/documentation/security/overview`

## Repository Scope

This repository owns the gateway runtime implementation, terminal/chat execution managers, local gateway tools, service entrypoint, Docker image, and gateway tests. The backend owns relay/control-plane contracts, and the CLI owns operator installation and command UX.

Live gateway chat relay remains disabled until the separate peer-ticket delivery, listener dispatch, chat frame schema, and UI integration are implemented together. Current cloud chat work uses encrypted REST chat storage.

When gateway behavior changes, update the relevant Napseer feature, security, plan, or implementation-note node in the same work and verify with focused gateway tests.
