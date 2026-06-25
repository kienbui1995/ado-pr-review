---
name: review-pr-ado
description: >-
  Code review an Azure DevOps (ADO) pull request. Use whenever the user asks to review a PR,
  code-review a pull request, critique/check an ADO PR, runs /review-pr-ado, or gives a PR number
  with review intent. ADO repos are NOT on GitHub — there is no `gh`; this skill drives review
  through the bundled `ado-pr-review` MCP server (ado_pr_show / ado_pr_changed_files /
  ado_pr_threads_list / ado_pr_list_active / ado_pr_thread_post) with local `git` for diff bodies.
  It runs a multi-lens parallel review via the bundled ado-review-* agents, adversarially scores
  each finding 0-100, keeps only high-confidence (>=80) issues, and — dry-run by default — posts a
  review comment only when --post is passed.
---

# review-pr-ado (Claude Code plugin)

Disciplined PR review for **Azure DevOps** repos. The capability layer is the bundled MCP server
`ado-pr-review`; the workflow is the shared playbook. This skill wires them together and dispatches
the bundled lens agents in parallel.

## MCP tools (from the bundled server)
- `ado_pr_show` — PR metadata (status, draft, branches, merge commits, project, repo id). Start here.
- `ado_pr_changed_files` — files changed by the PR.
- `ado_pr_threads_list` — existing comment threads (eligibility / no double-post).
- `ado_pr_list_active` — active PRs (concurrent-PR / merge-conflict check).
- `ado_pr_thread_post` — post the review comment. **Outward-facing** — only on `--post`.

If the MCP server isn't loaded, every call has a raw `az` equivalent in
`references/ado-commands.md`. Diff **bodies** come from local `git` (see references) — the MCP
server returns changed-file *lists*, not diff text.

## Arguments
- PR id (accept `1234`, `#1234`, or an ADO PR URL — extract the number).
- `--post` → publish the comment. **Default is dry-run**: present findings, post nothing.

## Workflow
Make a todo list from these steps.

1. **Eligibility** — `ado_pr_show`. Skip (say why) if abandoned/completed, draft, automated/trivial,
   or already reviewed (a prior `### Code review` thread in `ado_pr_threads_list`). Else stop.
2. **Gather** — read the repo-root `CLAUDE.md`/`AGENTS.md` (+ any in touched dirs); `ado_pr_changed_files`
   to scope lenses; fetch the diff via local `git` using `lastMergeSourceCommit`/`lastMergeTargetCommit`
   from `ado_pr_show` (see `references/ado-commands.md`); write a 2-3 sentence summary.
3. **Multi-lens review** — dispatch the bundled agents **in parallel**, each with the diff inline,
   scaling to PR size. Agents: `ado-review-guidance`, `ado-review-bugs`, `ado-review-history`,
   `ado-review-comments`, `ado-review-tenant`. Each returns issues + a one-line reason.
4. **Score** — for each distinct finding, dispatch `ado-review-scorer` (cheap/skeptical) to score it
   0-100 with the rubric in `references/review-lenses.md`. De-duplicate first.
5. **Filter** — keep only **≥ 80**. Nothing clears? Report "no issues" plainly.
6. **Verify survivors** — re-confirm each high-impact claim with a real tool/command before posting.
7. **Re-check eligibility** — `ado_pr_show` + `ado_pr_threads_list` again.
8. **Deliver** — dry-run: present findings (format below). `--post`: `ado_pr_thread_post`, then read
   back via `ado_pr_threads_list` to confirm.

Full lens checklists, the multi-tenant rules, the scoring rubric, and the **known ADO false
positives** (e.g. `pr:` YAML trigger is a no-op on Azure Repos) live in `references/review-lenses.md`.
ADO/`az`/`git` command cookbook + citation URL format: `references/ado-commands.md`.

## Output format
Brief, no emojis (except footer). Cite each finding with an ADO file link at the head commit; link
any referenced PR by its ADO URL.

```
### Code review

Found N issues:

1. <brief description> (<reason>)

<ADO file link with path + line range at the head commit SHA>

🤖 Generated with ado-pr-review
```

No issues clear the filter:

```
### Code review

No issues found. Checked for bugs, CLAUDE.md/AGENTS.md compliance, tenant isolation, and ADO/CI pitfalls.

🤖 Generated with ado-pr-review
```
