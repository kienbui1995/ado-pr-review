# Review lenses & known false positives

Per-lens checklists for the parallel review (step 3) and the curated false-positive list the
scorer (step 4) uses to kill noise. The **ADO pipeline gotchas** below are generic and apply to any
Azure DevOps repo; the project-specific lens is an **example** you adapt to your codebase.

## Secrets & CI/infra (generic)
- **No committed real secrets** (`.env`, API keys, tokens). Credentials should come from a service
  connection / pipeline secret / env var, not inline YAML. *Exception:* local test-only credentials
  that match a committed test compose file (e.g. `user:pass@localhost` in `docker-compose.test.yml`)
  are not real secrets — don't flag them (see false positives).
- High-risk actions (deploys, data deletion) should stay behind human approval.

## Example: a project-specific lens (customize this)

Add a lens that encodes *your* project's non-negotiable invariants. The example below is for a
multi-tenant SaaS — replace it with whatever your repo's rules are (or delete it). The point is to
teach the reviewer your domain's worst-case bug so it gets caught.

> **Multi-tenant isolation** *(example)* — a tenant data leak is the most serious thing the review
> can catch. Flag anything that goes **fail-open**: a query/write that bypasses the tenant-scoped
> repository, a new tenant-owned table with no row-level-security migration, a vector/blob/cache
> path that proceeds without a tenant context, or auth that resolves a user across tenants.

To wire a custom lens into the Claude plugin, add an agent under `agents/` and reference it from the
skill; for other tools, add its checklist to your `AGENTS.md` / steering file.

## ADO pipeline / infra gotchas (generic — feed these to the scorer)

These cause the most false positives and the most missed real issues on `azure-pipelines.yml` and
related files.

- **`pr:` YAML trigger is a NO-OP on Azure Repos Git.** Adding or removing a `pr:` block does **not**
  change whether PRs run CI — PR validation is governed by **Branch Policy → Build Validation** in
  project settings. So "this PR removes `pr:` → PRs won't run CI" is a **false positive**. (The same
  `pr:` block *does* work on GitHub/Bitbucket-hosted pipelines — but not on Azure Repos.)
- **Pool semantics**: `pool: { vmImage: ubuntu-latest }` = Microsoft-hosted, clean ephemeral agent.
  `pool: { name: X }` = a **self-hosted** private pool — different environment, possible stale state,
  and it runs (possibly untrusted) code on internal infra. A comment claiming "Microsoft-hosted
  ubuntu-latest" over a `name:`-style pool is a **real** comment-vs-code contradiction.
- **Concurrent rewrites**: when a PR rewrites a shared pipeline/config/lock file, check for another
  **active** PR rewriting the same file (`ado_pr_list_active`). Two full rewrites from the same base
  = guaranteed merge conflict — a real, high-value finding.
- **Stage isolation**: stages on different pools get fresh checkouts, but within one pipeline run
  every stage checks out the same `Build.SourceVersion`, so "the built image may not match the
  tested commit" is usually a **false positive** (same commit SHA across stages).

## Known false positives (drop or score low)

The review's value is precision. Kill these unless there's specific evidence otherwise:
- **Pre-existing issues** — a problem on a line the PR only *moved* or didn't meaningfully change.
  A diff that shows `-X` then `+X` (relocation) is not a newly-introduced issue.
- **Local test-infra credentials** matching the committed test compose file — not real secrets.
- **Removing the `pr:` YAML trigger** on Azure Repos — no-op (see above).
- **"Tested code ≠ pushed image"** across pipeline stages — same `Build.SourceVersion`.
- **Divergence from an aspirational design-doc spec** not implemented anywhere yet — real as a
  follow-up, not a blocking defect in *this* PR. Score ~35, don't post.
- Anything a **linter / typechecker / CI** would catch (imports, types, formatting, broken tests).
- **General code-quality / coverage / docs** complaints not specifically mandated by your guidance.
- **Intentional changes** that are obviously the point of the PR (the *stale comment* about such a
  change may still be a finding, though).

## Scaling the fan-out

- Tiny PR (1 file, < ~100 lines): the bug + guidance lenses, plus the project lens if relevant — 2-3 agents.
- App/domain change (repos/models/migrations): always add the project-specific lens, plus history + comments.
- CI/infra (`azure-pipelines.yml`, Docker, compose): bug + comment + secrets lenses + the ADO gotchas + the concurrent-PR check.
- "Audit thoroughly": the full set, and consider 3 adversarial scorers per finding with a majority vote.
