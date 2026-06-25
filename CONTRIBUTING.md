# Contributing

Thanks for your interest! This project is small and dependency-free on purpose — keep it that way.

## Layout

```
server/ado_mcp_server.py   the MCP server (stdlib only; the single source of truth)
playbook/                  the tool-agnostic review procedure + lens checklists + az cookbook
scripts/                   standalone helpers (post a PR comment from the CLI)
install.py                 wires the server into each agent's config (merge-safe, backed up)
packaging/claude-code/     the Claude Code plugin (bundles copies of the above — see "Syncing")
tests/                     protocol smoke test (no `az`/network needed)
```

## Dev setup

No install needed — it's pure Python stdlib. You need Python ≥3.9. To exercise the live ADO tools
you also need the `az` CLI + the `azure-devops` extension, authenticated.

```bash
python3 tests/test_server_smoke.py      # protocol handshake + tools advertised
python3 install.py --print              # preview every tool's config snippet (writes nothing)
```

## Syncing the plugin

`packaging/claude-code/` bundles copies of the server, playbook docs, and post script so the plugin
is self-contained when installed from a marketplace. After editing anything under `server/`,
`playbook/`, or `scripts/`, re-sync:

```bash
bash tools/sync-plugin.sh
```

CI does not auto-sync; please run it and commit the result so the plugin stays current.

## Adding a review lens

Lenses are just prompts. To add one to the Claude plugin, drop an agent under
`packaging/claude-code/agents/` (frontmatter `name`/`description`/`tools`/`model` + a focused system
prompt) and reference it from the skill's step 3. For other tools, add its checklist to your
`AGENTS.md` / steering file. Keep the `playbook/review-lenses.md` "known false positives" list
honest — precision is the whole point.

## Style

- stdlib only in the server and installer — no third-party runtime deps.
- Surface failures as data (the server returns tool errors, never crashes the stdio loop).
- `ruff` clean (CI runs it). Match the surrounding style.

## PRs

Small, focused PRs. Run the smoke test before opening one. Describe what you changed and why.
