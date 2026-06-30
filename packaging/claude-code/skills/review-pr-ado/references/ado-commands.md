# ADO command cookbook

Every command this skill needs. No `gh`, no `github.com`. Run from inside a local clone/worktree.

## Table of contents
- [Resolve coordinates](#resolve-coordinates)
- [This project's known coordinates](#this-projects-known-coordinates)
- [PR metadata](#pr-metadata)
- [Fetch the diff](#fetch-the-diff)
- [List comment threads (eligibility / dedupe)](#list-comment-threads)
- [Post a review comment](#post-a-review-comment)
- [Citation URL format](#citation-url-format)
- [Finding concurrent PRs on the same file](#finding-concurrent-prs-on-the-same-file)

## Resolve coordinates

Most `az repos` commands auto-detect the repo from the local git context, but `az devops invoke`
needs **project** and **repositoryId** explicitly. Resolve them from the PR itself — robust and
generic across any ADO repo:

```bash
ORG="https://dev.azure.com/<organization>"          # from `git remote -v` (dev.azure.com/<org>/...)
az repos pr show --id <PR> --org "$ORG" \
  --query '{project:repository.project.name, repoId:repository.id, repoName:repository.name, web:repository.webUrl}' -o json
```

Derive `<organization>` from the git remote if unknown:
```bash
git remote -v   # https://dev.azure.com/<ORG>/<PROJECT>/_git/<REPO>  (PROJECT/REPO may be URL-encoded, e.g. %20 for space)
```

## Caching coordinates (optional)

To skip resolution on every call, set `ADO_ORG` (and `ADO_PROJECT`) in the MCP server env — the
installer bakes these in via `--org`/`--project`. The `repositoryId` is always resolved from the PR
(`ado_pr_show` → `repositoryId`), so you never need to hardcode it.

Example shape (substitute your own):
- ORG: `https://dev.azure.com/<your-org>`
- project: `<Your Project>`
- web base: `https://dev.azure.com/<your-org>/<Your%20Project>/_git/<Your%20Repo>`

## PR metadata

```bash
az repos pr show --id <PR> --org "$ORG" \
  --query '{title:title, status:status, isDraft:isDraft, mergeStatus:mergeStatus,
            source:sourceRefName, target:targetRefName,
            lastMergeSourceCommit:lastMergeSourceCommit.commitId,
            lastMergeTargetCommit:lastMergeTargetCommit.commitId}' -o json
```
- `status` must be `active` and `isDraft` false to proceed.
- `lastMergeSourceCommit` / `lastMergeTargetCommit` are the server's merge-preview commits — handy
  for a clean diff (the target commit is the effective merge base).

## Fetch the diff

```bash
SRC=<lastMergeSourceCommit>
TGT=<lastMergeTargetCommit>          # effective merge base
git fetch origin "$SRC" 2>&1 | tail -1
git fetch origin "$(echo <sourceRefName> | sed 's#refs/heads/##')" 2>&1 | tail -1   # optional, by branch
BASE=$(git merge-base "$SRC" "$TGT")
git diff --stat "$BASE".."$SRC"      # changed files
git diff "$BASE".."$SRC" -- <path>   # full diff for a file
git show "$SRC:<path>"               # full post-PR file content (with exact formatting / line numbers via `grep -n`)
```
Pass the diff **inline** to review subagents so they don't each re-fetch; let them run
`git show "$SRC:<path>"` only if they need full-file context.

## List comment threads

For eligibility (already reviewed?) and to avoid double-posting:

```bash
az devops invoke --area git --resource pullRequestThreads \
  --route-parameters project="<PROJECT>" repositoryId=<REPO_ID> pullRequestId=<PR> \
  --org "$ORG" --api-version 7.1 --http-method GET \
  | python3 -c "import sys,json; d=json.load(sys.stdin); ts=d.get('value',[]); print('threads:',len(ts)); [print('-',(t.get('comments') or [{}])[0].get('content','')[:80]) for t in ts]"
```
A prior thread starting with `### Code review` authored by you means it's already reviewed.

## Post a review comment

Use the bundled script (handles JSON escaping + the invoke call):

```bash
python3 <skill-dir>/scripts/post_pr_comment.py \
  --org "$ORG" --project "<PROJECT>" --repo-id <REPO_ID> --pr <PR> \
  --content-file /path/to/comment.md
```
It prints the new `threadId`. Then read the thread back (GET above) to confirm it landed.

Raw equivalent (if you must, body must be JSON `{"comments":[{"parentCommentId":0,"content":"...","commentType":1}],"status":1}`):
```bash
az devops invoke --area git --resource pullRequestThreads \
  --route-parameters project="<PROJECT>" repositoryId=<REPO_ID> pullRequestId=<PR> \
  --org "$ORG" --api-version 7.1 --http-method POST --in-file body.json
```

To anchor a comment to a specific file+line instead of a general PR comment, add a
`threadContext` to the body:
```json
{"comments":[{"parentCommentId":0,"content":"...","commentType":1}],"status":1,
 "threadContext":{"filePath":"/azure-pipelines.yml",
   "rightFileStart":{"line":14,"offset":1},"rightFileEnd":{"line":18,"offset":1}}}
```

## Citation URL format

ADO file link at a specific commit + line range (use in the review output):
```
https://dev.azure.com/<ORG>/<PROJECT_ENC>/_git/<REPO_ENC>?path=/<file>&version=GC<full-sha>&line=<start>&lineEnd=<end>&lineStartColumn=1&lineEndColumn=1&type=2&lineStyle=plain
```
- `<PROJECT_ENC>`/`<REPO_ENC>` are URL-encoded (space → `%20`).
- `version=GC<full-sha>` pins the blob to the PR head commit (always use the full 40-char SHA).
- Link another PR as: `https://dev.azure.com/<ORG>/<PROJECT_ENC>/_git/<REPO_ENC>/pullrequest/<id>`

## Finding concurrent PRs on the same file

A high-value, easy-to-miss check (esp. for shared files like `azure-pipelines.yml`, lockfiles,
shared configs). List active PRs and inspect whether any other one rewrites a file this PR also
changes:

```bash
az repos pr list --org "$ORG" --project "<PROJECT>" --status active \
  --query '[].{id:pullRequestId, title:title, src:sourceRefName}' -o json
# For a candidate other PR, diff its head against main for the shared file:
git fetch origin <other-source-branch> 2>&1 | tail -1
git show <other-head-sha>:<path> | head -40    # compare structure / pool / stage names
```
If two active PRs both fully rewrite the same file from the same base, they cannot both merge
cleanly — flag it and recommend rebasing one onto the other.
