# MCP Server Onboarding (v1)

This document explains how a customer points an MCP client (VS Code, Cursor, or another MCP-compatible tool) at their APC MCP server.

---

## v1: service-account bearer token

The MCP server sits behind the platform's nginx `auth_request` gate, which resolves every request's `Authorization` header through Houston's `/v1/authorization/agent` endpoint (see [architecture.md](architecture.md)). v1 supports exactly one credential shape for this: a Houston service-account API key, sent as a static bearer token.

1. Create a service account in the workspace (or deployment) the agent should act as, and generate a key for it. The agent's tool calls are scoped to whatever that service account is permitted to do — no separate agent permission model exists (see the `apc-mcp-server` design doc's Out of Scope section).
2. Configure the MCP client with:
   - **URL**: `https://mcp-server.<your-base-domain>/mcp`
   - **Header**: `Authorization: Bearer <service-account-key>`

Example client config (shape varies by client — this is the VS Code `mcp.json` form):

```json
{
  "servers": {
    "apc": {
      "url": "https://mcp-server.example.astronomer.io/mcp",
      "headers": {
        "Authorization": "Bearer <service-account-key>"
      }
    }
  }
}
```

A revoked or expired key stops working on the next call, bounded by the auth gate's cache TTL (`mcpServer.authCache.validFailure` in `charts/astronomer/values.yaml`, 1 minute by default) — not instantly, since the gate caches a successful check for a short window rather than re-authenticating Houston on every single call.

## Not yet supported

OAuth 2.1 with dynamic client registration is targeted for v1.1 and is out of scope here.
