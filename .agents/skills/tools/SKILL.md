---
name: tools
description: Use when writing, editing, or reviewing command-line tools and helper scripts in this repo (things in bin/). Covers where tools live, argument parsing with --help, and the rule that a tool must not perform destructive or state-mutating operations by default.
---

# Writing tools in `bin/`

Repo tooling (setup scripts, one-off utilities, anything a human or CI invokes directly) lives in `bin/` and follows a few rules so tools are discoverable, self-documenting, and safe to run by accident.

---

## Critical Rules

1. **Tools live in `bin/`** as executable scripts: a shebang (`#!/usr/bin/env python3` for Python) plus `chmod +x`. Python tools run via `uv run bin/<tool>.py`.
2. **Every tool parses arguments with `argparse`** (or the language equivalent) so `--help` works and every argument is self-documenting. Parse arguments as the *first* thing `main()` does.
3. **`--help` and insufficient/invalid arguments must do no work.** They print usage and exit before any side effect. argparse gives this for free as long as parsing happens before any side-effecting code.
4. **A tool must not perform a destructive or state-mutating operation by default.** Merely running it (or running it to read `--help`) must not create/delete Kubernetes objects, write/delete files, call external services, or change the active context.

---

## Non-destructive by default

The failure mode to design against: someone runs `bin/some-tool.py` (or `bin/some-tool.py --help`) expecting it to be inert or to print help, and instead it mutates whatever ambient context it finds — the current kube context, the current directory, a live cluster.

The rule that prevents it: **do not give a safe-looking default to any argument that determines *where* a mutation lands** (a namespace, a cluster, a path, a target host). Make those arguments **required with no default**, so a bare or accidental invocation aborts before doing anything.

With `argparse`, a `required=True` argument with no default means:

- `tool` (no args) → prints usage to stderr and exits non-zero, *before* `main()` reaches any side effect.
- `tool --help` → prints help and exits 0.
- `tool --namespace foo ...` → runs, because the caller was explicit about the target.

### Worked example: `bin/setup-forgejo-ca.py`

This script creates and deletes Kubernetes Secrets in a cluster. It originally defaulted its namespaces (`astronomer`, `git-forgejo`). Running `bin/setup-forgejo-ca.py --help` to read the help text would instead have run the whole thing against the reader's *current* kube context — a potentially destructive surprise.

The fix was to make the namespaces **required, with no defaults**:

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform-namespace", required=True, help="...")
    parser.add_argument("--forgejo-namespace", required=True, help="...")
    return parser.parse_args()

def main() -> None:
    args = parse_args()          # aborts here on a bare run or --help, before any kubectl
    ...                          # cluster mutations only happen after this line
```

Now `--help` and a bare run both abort before touching the cluster, and any real run has to name its target namespaces on purpose.

### Automation still works

Making the target arguments required does not break automated callers — it just moves the intent to the caller, where it belongs. The automated invocation passes the values explicitly. For example, the git-sync-private-ca scenario's `pre_helm_scripts` entry names the namespaces:

```yaml
pre_helm_scripts:
  - bin/setup-forgejo-ca.py --platform-namespace astronomer --forgejo-namespace git-forgejo
```

---

## Checklist for a new or edited tool

- [ ] Lives in `bin/`, is executable, has the right shebang.
- [ ] Uses `argparse`; `--help` works and does nothing else.
- [ ] Arguments that decide *where* a mutation lands are `required` with no default.
- [ ] Side effects run only after arguments parse successfully.
- [ ] Fails loudly on error (non-zero exit), and is idempotent (safe to re-run) where practical.
- [ ] Callers (CI, scenario manifests, other scripts) pass the required arguments explicitly.
