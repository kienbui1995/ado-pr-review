#!/usr/bin/env python3
"""Smoke test for the MCP server protocol layer — no `az`/network required.

Verifies the JSON-RPC handshake, that all tools are advertised, and that an unknown method errors.
Actual tool calls need an authenticated `az`, so they are exercised manually / in real clients, not
in CI. Run: `python3 tests/test_server_smoke.py` (exit 0 = pass).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "server", "ado_mcp_server.py")
EXPECTED_TOOLS = {
    "ado_pr_show", "ado_pr_list_active", "ado_pr_changed_files",
    "ado_pr_threads_list", "ado_pr_thread_post",
}


def drive(messages):
    inp = "".join(json.dumps(m) + "\n" for m in messages)
    p = subprocess.run([sys.executable, SERVER], input=inp, capture_output=True, text=True, timeout=30)
    return [json.loads(line) for line in p.stdout.splitlines() if line.strip()], p.stderr


def main():
    resps, stderr = drive([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "no/such/method"},
    ])
    by_id = {r.get("id"): r for r in resps}

    assert not stderr.strip(), f"server wrote to stderr: {stderr!r}"
    assert by_id[1]["result"]["serverInfo"]["name"] == "ado-pr-review", "bad serverInfo"
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert names == EXPECTED_TOOLS, f"tools mismatch: {names ^ EXPECTED_TOOLS}"
    for t in by_id[2]["result"]["tools"]:
        assert t.get("inputSchema", {}).get("type") == "object", f"{t['name']} missing inputSchema"
    assert "error" in by_id[3] and by_id[3]["error"]["code"] == -32601, "unknown method should error -32601"

    print(f"OK — handshake + {len(names)} tools advertised + error path correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
