#!/usr/bin/env python3
"""Post a markdown comment as a new thread on an Azure DevOps pull request.

Wraps `az devops invoke ... pullRequestThreads POST` so the review skill doesn't have to
hand-build JSON / fight shell quoting each time. Reads the comment body from a file (markdown
is supported in ADO PR comments) and prints the created threadId.

Examples
--------
General PR comment (dry-run default in the skill means this only runs on `--post`):
    python3 post_pr_comment.py \
        --org https://dev.azure.com/your-org \
        --project "Your Project" \
        --repo-id <repository-guid> \
        --pr 1234 \
        --content-file /tmp/review.md

Anchored to a file + line range (right/after side of the diff):
    ... --file-path /azure-pipelines.yml --line-start 14 --line-end 18

Requires `az` with the azure-devops extension, already authenticated to the org.
"""
import argparse
import json
import subprocess
import sys
import tempfile

# ADO commentThreadStatus enum
STATUS = {"active": 1, "fixed": 2, "wontfix": 3, "closed": 4, "bydesign": 5, "pending": 6}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--org", required=True, help="https://dev.azure.com/<organization>")
    p.add_argument("--project", required=True, help="ADO project name (may contain spaces)")
    p.add_argument("--repo-id", required=True, help="repository id (GUID) — from `az repos pr show ... repository.id`")
    p.add_argument("--pr", required=True, help="pull request id")
    p.add_argument("--content-file", required=True, help="path to a markdown file with the comment body")
    p.add_argument("--status", default="active", choices=sorted(STATUS), help="thread status (default: active)")
    p.add_argument("--api-version", default="7.1")
    # optional file anchoring
    p.add_argument("--file-path", help="anchor the thread to this file (e.g. /azure-pipelines.yml)")
    p.add_argument("--line-start", type=int, help="start line on the right/after side")
    p.add_argument("--line-end", type=int, help="end line on the right/after side (defaults to line-start)")
    args = p.parse_args()

    with open(args.content_file, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.strip():
        print("ERROR: comment body is empty", file=sys.stderr)
        return 2

    body = {
        "comments": [{"parentCommentId": 0, "content": content, "commentType": 1}],
        "status": STATUS[args.status],
    }
    if args.file_path and args.line_start:
        end = args.line_end or args.line_start
        body["threadContext"] = {
            "filePath": args.file_path,
            "rightFileStart": {"line": args.line_start, "offset": 1},
            "rightFileEnd": {"line": end, "offset": 1},
        }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(body, tf)
        body_path = tf.name

    cmd = [
        "az", "devops", "invoke",
        "--area", "git", "--resource", "pullRequestThreads",
        "--route-parameters",
        f"project={args.project}", f"repositoryId={args.repo_id}", f"pullRequestId={args.pr}",
        "--org", args.org, "--api-version", args.api_version,
        "--http-method", "POST", "--in-file", body_path,
        "-o", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        print(f"ERROR: az devops invoke failed (exit {proc.returncode})", file=sys.stderr)
        return proc.returncode

    try:
        resp = json.loads(proc.stdout)
        thread_id = resp.get("id")
        comment = (resp.get("comments") or [{}])[0]
        print(json.dumps({
            "threadId": thread_id,
            "commentId": comment.get("id"),
            "status": resp.get("status"),
            "published": comment.get("publishedDate"),
            "author": (comment.get("author") or {}).get("displayName"),
        }, indent=2))
    except json.JSONDecodeError:
        print(proc.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
