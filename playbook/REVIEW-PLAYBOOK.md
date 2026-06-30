# ADO PR review — playbook

Tool-agnostic procedure for reviewing an **Azure DevOps** pull request. This is the shared brain:
the Claude Code skill, the Codex/OpenCode/Gemini commands, the Cline rule, and the Kiro steering
file all point at this same procedure. The *capability* (talking to ADO) comes from the bundled
**MCP server** `ado-pr-review`, which exposes these tools to whatever agent you run:

| MCP tool | Purpose |
|---|---|
| `ado_pr_show` | PR metadata (status, draft, branches, merge commits, project, repo id) — start here |
| `ado_pr_list_active` | active PRs in the project — detect a concurrent PR rewriting the same file |
| `ado_pr_changed_files` | files changed by the PR (path + change type) |
| `ado_pr_threads_list` | existing comment threads — eligibility / avoid double-posting |
| `ado_pr_thread_post` | post a markdown review comment (general or anchored to file+line) — **outward-facing** |

If your agent has no MCP support, every tool has a raw `az` equivalent in
[`ado-commands.md`](./ado-commands.md). For full diff bodies use local `git` in the repo clone
(the MCP server intentionally returns *changed-file lists*, not diff text — git is faster/exact).

## Why this shape

A good review is **high-precision**: a few verified, important findings beat a long list of
plausible-but-wrong nitpicks that erode trust. Precision comes from three habits — diverse
**parallel lenses** (each reviewer blind to the others, so different failure modes surface),
**adversarial scoring** (every candidate is scored by a skeptic that tries to refute it; only
high-confidence survives), and **independent verification before posting** (a wrong comment on
someone's PR is expensive — re-check high-impact claims with a real command first).

## Arguments

- PR id (required) — accept `1234`, `#1234`, or a full ADO pull-request URL; extract the number.
- `--post` (optional) — publish the comment. **Default is dry-run**: present findings to the user
  and post nothing. Posting is public to the whole team, so only call `ado_pr_thread_post` when
  `--post` is present (or the user explicitly approves).

## Procedure

### 1. Eligibility
`ado_pr_show`. Skip (and say why) if the PR is abandoned/completed (`status` ≠ `active`), a draft
(`isDraft`), an automated/trivial change review adds nothing to, or already reviewed by you
(check `ado_pr_threads_list` for a prior `### Code review` thread). If ineligible, stop.

### 2. Gather context
- **Guidance files**: the repo-root `CLAUDE.md`/`AGENTS.md` plus any `CLAUDE.md`/`AGENTS.md` in
  directories the PR touches — these are the rules you audit against.
- **Changed files**: `ado_pr_changed_files` to scope which lenses matter (pipeline YAML vs Python
  vs migrations need different scrutiny).
- **Diff**: in the repo clone, fetch the merge-preview commits from `ado_pr_show`
  (`lastMergeSourceCommit` / `lastMergeTargetCommit`) and `git diff base..src` — see
  [`ado-commands.md`](./ado-commands.md). Write a 2-3 sentence plain summary of the change.

### 3. Multi-lens review (parallel where the agent supports subagents)
Run independent lenses, each returning issues with a one-line reason. Scale to the PR: a tiny
one-file change needs 2-3 lenses; a broad change warrants the full set. Lenses and full
checklists are in [`review-lenses.md`](./review-lenses.md):
1. **Guidance compliance** — violations of CLAUDE.md/AGENTS.md the doc *specifically* calls out
   (quote the line). Guidance is advice for writing code; not every line applies at review time.
2. **Shallow bug scan** — read only the diff; large, real, behavior-breaking bugs. Skip nitpicks,
   style, and anything a linter/typechecker/CI catches.
3. **Git history** — `git log -p` / `git blame` the changed regions; flag regressions in light of
   *why* the code is the way it is (was this line a deliberate fix/hardening?).
4. **Prior PRs** — earlier PRs touching these files (`ado_pr_list_active` + threads, or git log);
   check whether prior review feedback still applies.
5. **Code comments** — do the changes honor nearby comment guidance? Flag comment-vs-code
   contradictions (a comment that now lies about the code).
6. **Multi-tenant isolation** *(project rule #1)* — base-repo tenant filter intact, RLS untouched,
   vector/Mongo/object/credential paths fail-closed on missing `TenantContext`. A leak is the most
   serious thing a review can catch.
7. **Secrets & CI/infra** — no committed real secrets (service connection / env, not inline). For
   pipeline files apply the **ADO gotchas** in review-lenses.md (e.g. `pr:` YAML trigger is a no-op
   on Azure Repos; `vmImage:` vs `name:` pool semantics) and run the **concurrent-PR check**
   (`ado_pr_list_active` → does another active PR rewrite a file this PR also changes?).

### 4. Adversarially score
For each distinct finding, have a skeptic score it 0-100 (try to refute: pre-existing? false
positive? not actually a bug? — feed it the ADO gotchas so it kills format false positives). Use
this rubric verbatim:
- **0** — false positive that doesn't survive light scrutiny, or pre-existing.
- **25** — might be real, might not; couldn't verify. Stylistic and not called out in CLAUDE.md.
- **50** — verified real, but a nitpick / rare / relatively unimportant.
- **75** — double-checked; very likely real and hit in practice; PR's approach insufficient;
  important and impacts functionality, OR directly named in CLAUDE.md.
- **100** — confirmed definitely real, will happen frequently; evidence directly confirms it.

De-duplicate first (same issue from three lenses = one finding).

### 5. Filter
Keep only findings **≥ 80**. If nothing clears the bar, the result is "no issues" — say so plainly.
A clean, precise review is a valid outcome; don't pad with sub-threshold noise.

### 6. Verify survivors
Re-confirm each surviving high-impact claim with a real command/tool before it can be posted
(does that conflicting PR actually exist and touch the same file? does that line really say what
the finding claims?). You are the last gate on accuracy.

### 7. Re-check eligibility
The PR may have changed — re-run `ado_pr_show` + `ado_pr_threads_list` to confirm it's still
active, not draft, not already reviewed by you.

### 8. Deliver
- **Dry-run (default)**: present findings in chat (format below); tell the user to re-run with
  `--post` to publish.
- **`--post`**: publish with `ado_pr_thread_post` (or `scripts/post_pr_comment.py`), then read the
  thread back (`ado_pr_threads_list`) to confirm it landed.

## Output format

Brief, no emojis (except the footer). Cite each finding with an ADO file link at the PR head commit
(format in [`ado-commands.md`](./ado-commands.md)); link any referenced PR by its ADO URL.

```
### Code review

Found N issues:

1. <brief description> (<reason: AGENTS.md "<quote>" | bug | git history | concurrent PR | ...>)

<ADO file link with path + line range at the head commit SHA>

🤖 Generated with ado-pr-review
```

If nothing clears the filter:

```
### Code review

No issues found. Checked for bugs, CLAUDE.md/AGENTS.md compliance, tenant isolation, and ADO/CI pitfalls.

🤖 Generated with ado-pr-review
```
