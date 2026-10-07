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

A revoked or expired key keeps working until its cached success entry expires, bounded by `mcpServer.authCache.validSuccess` in `charts/astronomer/values.yaml` (5 minutes by default) — not instantly, since the gate caches a successful check rather than re-authenticating Houston on every single call. Only once that check fails does the gate cache the denial, and only then for the shorter `validFailure` window (1 minute by default).

## Tool groups

Which tools the server exposes is governed by `mcpServer.enabledGroups` in `charts/astronomer/values.yaml`, joined into the `MCP_ENABLED_GROUPS` env var. It is a replacement list, not additive: a group you do not name is not exposed. The `core` group is always on and is not listed. Two groups are exceptions to naming: `skills_load` is controlled by `mcpServer.skills.enabled` rather than listed here, and when skills are on the server also implies `airflow_read`.

Operator overrides nest under the umbrella chart's `astronomer` key, as the examples below show.

The groups:

| Group | Holds | Default |
| -- | -- | -- |
| `core` | always-on baseline tools | always on |
| `platform_read` | deployment/workspace reads | **on** |
| `platform_write` | deployment/workspace lifecycle writes | **on** |
| `platform_disruptive` | contract changes — executor, runtime, DAG mechanism | off |
| `platform_destroy` | deployment/workspace deletion | off |
| `airflow_read` | read-only Airflow diagnosis — task logs, import errors, installed providers | off |
| `airflow_destroy` | `delete_dag_run` | off |
| `skills_load` | skill delivery — the `load_skill`, `list_skills` and `read_skill_file` tools, the per-skill prompts, and the skill resources | off — see below |

Skills are toggled by a dedicated flag rather than named in `enabledGroups`:

```yaml
astronomer:
  mcpServer:
    skills:
      enabled: true
```

When on, the server also enables the read-only Airflow groups the shipped skills require (`airflow_read`, for the `debugging-dags` and `migrating-airflow-2-to-3` skills) — you do not list those yourself.

### Upgrading: `airflow_read` now holds three tools that used to be in `platform_read`

`get_task_logs`, `get_import_errors`, and `get_installed_providers` moved out of `platform_read` into the new `airflow_read` group, which is **off by default**. An install running the previous `enabledGroups: [platform_read, platform_write]` keeps a valid config but silently loses those three tools. To keep them, add `airflow_read` explicitly:

```yaml
astronomer:
  mcpServer:
    enabledGroups:
      - platform_read
      - platform_write
      - airflow_read
```

## Not yet supported

OAuth 2.1 with dynamic client registration is targeted for v1.1 and is out of scope here.
