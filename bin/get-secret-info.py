#!/usr/bin/env python3
"""
Fetch and display Kubernetes secret data in a compact columnar format.

For each secret, prints a comma-separated line of:
  name=<name>,resourceVersion=<resourceVersion>,data.<key>=<decoded value>,...

All values under `data` are base64-decoded before printing.

Supports optional watch mode (-w) which streams updates as secrets change,
and label selectors (-l) to filter secrets. When no secret name is given,
all secrets in the namespace are printed.
"""

import argparse
import base64
import json
import subprocess
import sys


def print_secret(secret):
    name = secret.get("metadata", {}).get("name", "<not found>")
    resource_version = secret.get("metadata", {}).get("resourceVersion", "<not found>")

    parts = [f"name={name}", f"resourceVersion={resource_version}"]
    for key, value in (secret.get("data") or {}).items():
        decoded = base64.b64decode(value).decode()
        parts.append(f"data.{key}={decoded}")

    print(",".join(parts), flush=True)


def main():  # noqa: C901
    parser = argparse.ArgumentParser(description="Print resourceVersion and data.connection from a Kubernetes secret")
    parser.add_argument("name", nargs="?", default=None, help="Secret name (omit to list all secrets)")
    parser.add_argument("-n", "--namespace", help="Namespace")
    parser.add_argument("--context", help="Kubernetes context")
    parser.add_argument("--kubeconfig", help="Path to kubeconfig file")
    parser.add_argument("-l", "--selector", help="Label selector (e.g. app=foo)")
    parser.add_argument("-w", "--watch", action="store_true", help="Watch for changes (streams output)")
    parser.add_argument("--debug", action="store_true", help="Print the kubectl command before running it")
    args = parser.parse_args()

    cmd = ["kubectl", "get", "secret"] + ([args.name] if args.name else []) + ["-o", "json"]
    if args.namespace:
        cmd.extend(["-n", args.namespace])
    if args.context:
        cmd.extend(["--context", args.context])
    if args.kubeconfig:
        cmd.extend(["--kubeconfig", args.kubeconfig])
    if args.selector:
        cmd.extend(["-l", args.selector])
    if args.watch:
        cmd.append("--watch")

    if args.debug:
        print(f"+ {' '.join(cmd)}", file=sys.stderr, flush=True)

    if not args.watch:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)

        payload = json.loads(result.stdout)
        if payload.get("kind") == "SecretList":
            for secret in payload.get("items", []):
                print_secret(secret)
        else:
            print_secret(payload)
    else:
        # kubectl -o json --watch emits pretty-printed JSON objects concatenated together.
        # Parse by tracking brace depth to detect document boundaries.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        try:
            buf = []
            depth = 0
            in_string = False
            escape_next = False
            for line in iter(proc.stdout.readline, ""):
                for ch in line:
                    if escape_next:
                        escape_next = False
                    elif ch == "\\" and in_string:
                        escape_next = True
                    elif ch == '"':
                        in_string = not in_string
                    elif not in_string:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                    buf.append(ch)
                    if depth == 0 and buf:
                        text = "".join(buf).strip()
                        if text:
                            doc = json.loads(text)
                            print_secret(doc)
                        buf = []
        except KeyboardInterrupt:
            proc.terminate()
        finally:
            proc.wait()
            if proc.returncode and proc.returncode != 0:
                err = proc.stderr.read()
                if err:
                    print(err, file=sys.stderr)
                sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
