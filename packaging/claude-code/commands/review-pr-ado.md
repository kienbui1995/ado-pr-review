---
description: Code review an Azure DevOps pull request (dry-run; pass --post to publish)
---

Review the Azure DevOps pull request `$ARGUMENTS` using the **review-pr-ado** skill.

Invoke the review-pr-ado skill and follow its workflow exactly: use the `ado-pr-review` MCP tools
(ado_pr_show, ado_pr_changed_files, ado_pr_threads_list, ado_pr_list_active) plus local git for the
diff, dispatch the bundled ado-review-* lens agents in parallel, adversarially score findings, keep
only those scored >= 80, verify them, and present the results.

Dry-run by default — present findings only. Post to the PR (ado_pr_thread_post) ONLY if the
arguments include `--post`.
