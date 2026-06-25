#!/usr/bin/env python3
"""Universal Azure DevOps PR-review MCP server.

A dependency-free Model Context Protocol server (JSON-RPC 2.0 over stdio) that exposes
Azure DevOps pull-request operations to any MCP-capable agent — Claude Code, Codex, OpenCode,
Gemini CLI, Cline, Kiro, etc. It shells out to the already-authenticated `az` CLI (azure-devops
extension), so there is no PAT to manage and no third-party Python package to install: stdlib only.

Tools
-----
- ado_pr_show            : PR metadata (status, draft, branches, merge commits, project, repo id)
- ado_pr_list_active     : active PRs in a project (powers the concurrent-PR / merge-conflict check)
- ado_pr_changed_files   : files changed by a PR (path + change type)
- ado_pr_threads_list    : existing comment threads (eligibility / avoid double-posting)
- ado_pr_thread_post     : post a markdown review comment (general or anchored to file+line)

Config (env)
------------
- ADO_ORG      default organization URL, e.g. https://dev.azure.com/your-org
- ADO_PROJECT  default project name, e.g. "Your Project"
- AZ_BIN       override path to the `az` binary (else resolved from PATH / common locations)

Every tool also accepts an explicit `org` (and where relevant `project`) argument that overrides
the env default, so the same server works across multiple ADO organizations.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "ado-pr-review", "version": "0.1.0"}
DEFAULT_ORG = os.environ.get("ADO_ORG", "")
DEFAULT_PROJECT = os.environ.get("ADO_PROJECT", "")

# ADO commentThreadStatus enum
THREAD_STATUS = {"active": 1, "fixed": 2, "wontfix": 3, "closed": 4, "bydesign": 5, "pending": 6}


# ----------------------------------------------------------------------------- az helpers
def _az_bin():
    return os.environ.get("AZ_BIN") or shutil.which("az") or "/opt/homebrew/bin/az"


def _run_az(args, in_file=None):
    cmd = [_az_bin()] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(
            "`az` CLI not found. Install Azure CLI + the azure-devops extension and authenticate "
            "(`az devops login`), or set AZ_BIN to the binary path."
        )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"az failed (exit {proc.returncode}): {msg[:600]}")
    return proc.stdout


def _az_json(args):
    out = _run_az(args + ["-o", "json"]).strip()
    return json.loads(out) if out else None


def _org(args):
    org = args.get("org") or DEFAULT_ORG
    if not org:
        raise RuntimeError(
            "No Azure DevOps organization configured. Set ADO_ORG (e.g. "
            "https://dev.azure.com/your-org) in the MCP server env, or pass `org` to the tool."
        )
    return org


def _resolve_coords(pr_id, org):
    """Return (project_name, repository_id) for a PR — needed by the git-area REST calls."""
    d = _az_json(["repos", "pr", "show", "--id", str(pr_id), "--org", org])
    if not d:
        raise RuntimeError(f"PR {pr_id} not found in {org}")
    repo = d.get("repository") or {}
    project = (repo.get("project") or {}).get("name")
    return project, repo.get("id"), d


def _invoke(method, resource, route, org, in_file=None, query=None):
    args = [
        "devops", "invoke", "--area", "git", "--resource", resource,
        "--route-parameters", *[f"{k}={v}" for k, v in route.items()],
        "--org", org, "--api-version", "7.1", "--http-method", method,
    ]
    if in_file:
        args += ["--in-file", in_file]
    if query:
        args += ["--query", query]
    return _az_json(args)


# ----------------------------------------------------------------------------- tool impls
def t_pr_show(a):
    org = _org(a)
    d = _az_json(["repos", "pr", "show", "--id", str(a["pr_id"]), "--org", org])
    if not d:
        raise RuntimeError(f"PR {a['pr_id']} not found")
    repo = d.get("repository") or {}
    out = {
        "id": d.get("pullRequestId"),
        "title": d.get("title"),
        "description": d.get("description"),
        "status": d.get("status"),
        "isDraft": d.get("isDraft"),
        "mergeStatus": d.get("mergeStatus"),
        "createdBy": (d.get("createdBy") or {}).get("displayName"),
        "sourceRef": d.get("sourceRefName"),
        "targetRef": d.get("targetRefName"),
        "lastMergeSourceCommit": (d.get("lastMergeSourceCommit") or {}).get("commitId"),
        "lastMergeTargetCommit": (d.get("lastMergeTargetCommit") or {}).get("commitId"),
        "reviewers": [r.get("displayName") for r in (d.get("reviewers") or [])],
        "project": (repo.get("project") or {}).get("name"),
        "repositoryId": repo.get("id"),
        "repositoryName": repo.get("name"),
        "webUrl": repo.get("webUrl"),
    }
    return json.dumps(out, indent=2, ensure_ascii=False)


def t_pr_list_active(a):
    org = _org(a)
    project = a.get("project") or DEFAULT_PROJECT
    if not project:
        raise RuntimeError("project required (pass `project` or set ADO_PROJECT)")
    args = ["repos", "pr", "list", "--org", org, "--project", project, "--status", "active"]
    if a.get("top"):
        args += ["--top", str(a["top"])]
    rows = _az_json(args) or []
    out = [{
        "id": r.get("pullRequestId"),
        "title": r.get("title"),
        "sourceRef": r.get("sourceRefName"),
        "targetRef": r.get("targetRefName"),
        "createdBy": (r.get("createdBy") or {}).get("displayName"),
        "isDraft": r.get("isDraft"),
    } for r in rows]
    return json.dumps(out, indent=2, ensure_ascii=False)


def t_pr_changed_files(a):
    org = _org(a)
    project, repo_id, _ = _resolve_coords(a["pr_id"], org)
    route = {"project": project, "repositoryId": repo_id, "pullRequestId": a["pr_id"]}
    iters = _invoke("GET", "pullRequestIterations", route, org) or {}
    values = iters.get("value", iters if isinstance(iters, list) else [])
    if not values:
        return json.dumps([], indent=2)
    last_id = max(v.get("id", 0) for v in values)
    route2 = dict(route, iterationId=last_id)
    changes = _invoke("GET", "pullRequestIterationChanges", route2, org) or {}
    entries = changes.get("changeEntries", changes.get("value", []))
    out = []
    for e in entries:
        item = e.get("item") or {}
        path = item.get("path") or e.get("originalPath")
        if path and not item.get("isFolder"):
            out.append({"path": path, "changeType": e.get("changeType")})
    return json.dumps({"iterationId": last_id, "files": out}, indent=2, ensure_ascii=False)


def t_pr_threads_list(a):
    org = _org(a)
    project, repo_id, _ = _resolve_coords(a["pr_id"], org)
    route = {"project": project, "repositoryId": repo_id, "pullRequestId": a["pr_id"]}
    data = _invoke("GET", "pullRequestThreads", route, org) or {}
    threads = data.get("value", [])
    out = []
    for t in threads:
        comments = t.get("comments") or []
        first = comments[0] if comments else {}
        out.append({
            "threadId": t.get("id"),
            "status": t.get("status"),
            "commentCount": len(comments),
            "author": (first.get("author") or {}).get("displayName"),
            "snippet": (first.get("content") or "")[:120],
            "filePath": (t.get("threadContext") or {}).get("filePath"),
        })
    return json.dumps(out, indent=2, ensure_ascii=False)


def t_pr_thread_post(a):
    org = _org(a)
    content = a.get("content")
    if not content or not str(content).strip():
        raise RuntimeError("content (markdown body) is required and must be non-empty")
    project, repo_id, _ = _resolve_coords(a["pr_id"], org)
    status = THREAD_STATUS.get((a.get("status") or "active").lower(), 1)
    body = {"comments": [{"parentCommentId": 0, "content": content, "commentType": 1}], "status": status}
    if a.get("file_path") and a.get("line_start"):
        end = a.get("line_end") or a["line_start"]
        body["threadContext"] = {
            "filePath": a["file_path"],
            "rightFileStart": {"line": int(a["line_start"]), "offset": 1},
            "rightFileEnd": {"line": int(end), "offset": 1},
        }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(body, tf)
        body_path = tf.name
    try:
        route = {"project": project, "repositoryId": repo_id, "pullRequestId": a["pr_id"]}
        resp = _invoke("POST", "pullRequestThreads", route, org, in_file=body_path) or {}
    finally:
        try:
            os.unlink(body_path)
        except OSError:
            pass
    comment = (resp.get("comments") or [{}])[0]
    return json.dumps({
        "threadId": resp.get("id"),
        "commentId": comment.get("id"),
        "status": resp.get("status"),
        "published": comment.get("publishedDate"),
        "author": (comment.get("author") or {}).get("displayName"),
    }, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------------- tool registry
def _pr_arg():
    return {"pr_id": {"type": ["integer", "string"], "description": "pull request id"}}


def _org_arg():
    return {"org": {"type": "string", "description": "ADO org URL (default ADO_ORG)"}}


TOOLS = [
    {
        "name": "ado_pr_show",
        "description": "Fetch Azure DevOps pull-request metadata: status, isDraft, title/description, "
                       "source/target branches, merge-preview commits, reviewers, and the project + "
                       "repository id. Start every review here (eligibility + coordinates).",
        "inputSchema": {"type": "object", "properties": {**_pr_arg(), **_org_arg()}, "required": ["pr_id"]},
        "_fn": t_pr_show,
    },
    {
        "name": "ado_pr_list_active",
        "description": "List active (open) pull requests in a project. Use to detect a concurrent PR "
                       "rewriting the same file as the PR under review — a guaranteed merge conflict is "
                       "a high-value finding.",
        "inputSchema": {"type": "object", "properties": {
            **_org_arg(),
            "project": {"type": "string", "description": "project name (default ADO_PROJECT)"},
            "top": {"type": "integer", "description": "max results"},
        }},
        "_fn": t_pr_list_active,
    },
    {
        "name": "ado_pr_changed_files",
        "description": "List the files changed by a pull request (path + change type) via the latest "
                       "iteration. Use to scope which review lenses matter. For full diff bodies, use "
                       "local git in the repo clone.",
        "inputSchema": {"type": "object", "properties": {**_pr_arg(), **_org_arg()}, "required": ["pr_id"]},
        "_fn": t_pr_changed_files,
    },
    {
        "name": "ado_pr_threads_list",
        "description": "List existing comment threads on a pull request (id, status, author, snippet, "
                       "anchored file). Use for eligibility: detect a prior '### Code review' comment so "
                       "you don't double-post.",
        "inputSchema": {"type": "object", "properties": {**_pr_arg(), **_org_arg()}, "required": ["pr_id"]},
        "_fn": t_pr_threads_list,
    },
    {
        "name": "ado_pr_thread_post",
        "description": "Post a markdown comment as a new thread on a pull request. Optionally anchor it "
                       "to a file + line range (right/after side). This is outward-facing and public — "
                       "only call it when the user has approved posting (e.g. a --post flag).",
        "inputSchema": {"type": "object", "properties": {
            **_pr_arg(), **_org_arg(),
            "content": {"type": "string", "description": "markdown comment body"},
            "status": {"type": "string", "enum": sorted(THREAD_STATUS), "description": "thread status (default active)"},
            "file_path": {"type": "string", "description": "anchor file, e.g. /azure-pipelines.yml"},
            "line_start": {"type": "integer", "description": "anchor start line (right side)"},
            "line_end": {"type": "integer", "description": "anchor end line (defaults to line_start)"},
        }, "required": ["pr_id", "content"]},
        "_fn": t_pr_thread_post,
    },
]
_TOOLS_PUBLIC = [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]
_DISPATCH = {t["name"]: t["_fn"] for t in TOOLS}


# ----------------------------------------------------------------------------- JSON-RPC loop
def _send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _reply(rid, result):
    _send({"jsonrpc": "2.0", "id": rid, "result": result})


def _error(rid, code, message):
    _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def _handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        params = req.get("params") or {}
        _reply(rid, {
            "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return  # notifications: no response
    elif method == "ping":
        _reply(rid, {})
    elif method == "tools/list":
        _reply(rid, {"tools": _TOOLS_PUBLIC})
    elif method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = _DISPATCH.get(name)
        if fn is None:
            _reply(rid, {"content": [{"type": "text", "text": f"ERROR: unknown tool {name}"}], "isError": True})
            return
        try:
            text = fn(args)
            _reply(rid, {"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as e:  # noqa: BLE001 — surface any failure as a tool error, never crash the server
            _reply(rid, {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True})
    elif rid is not None:
        _error(rid, -32601, f"Method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            _handle(req)
        except Exception as e:  # noqa: BLE001
            if isinstance(req, dict) and req.get("id") is not None:
                _error(req["id"], -32603, f"Internal error: {e}")


if __name__ == "__main__":
    main()
