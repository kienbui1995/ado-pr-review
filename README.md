# ado-pr-review

[![ci](https://github.com/kienbui1995/ado-pr-review/actions/workflows/ci.yml/badge.svg)](https://github.com/kienbui1995/ado-pr-review/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Azure DevOps pull-request code review for **any MCP-capable AI coding agent** — Claude Code, Codex,
OpenCode, Gemini CLI, Cline, Kiro, and friends.

```bash
git clone https://github.com/kienbui1995/ado-pr-review
cd ado-pr-review
python3 install.py --org https://dev.azure.com/your-org --project "Your Project"
```

## Architecture — one core, many wrappers

```
            ┌──────────────────────────────┐
            │   server/ado_mcp_server.py    │   ← the portable core (stdlib only, shells to `az`)
            │   MCP tools: ado_pr_show, …    │     works in EVERY MCP client
            └──────────────┬───────────────┘
                           │ registered into each tool's config (install.py)
   ┌─────────┬─────────┬───┴─────┬─────────┬─────────┐
 Claude     Codex    OpenCode   Gemini    Cline      Kiro
 (plugin)  (config.toml)(opencode.json)(settings.json)(mcp_settings)(.kiro/settings)
   │
   └── playbook/REVIEW-PLAYBOOK.md  ← the shared review procedure every wrapper points to
```

- **MCP server** (`server/ado_mcp_server.py`) is the capability layer. It exposes:
  `ado_pr_show`, `ado_pr_list_active`, `ado_pr_changed_files`, `ado_pr_threads_list`,
  `ado_pr_thread_post`. No PAT, no pip installs — it reuses your authenticated `az` CLI.
- **Playbook** (`playbook/REVIEW-PLAYBOOK.md` + `review-lenses.md` + `ado-commands.md`) is the
  tool-agnostic review procedure: multi-lens review → adversarial 0-100 scoring → keep ≥80 →
  verify → post. Dry-run by default.
- **Per-tool wrappers** register the server and add a `review-pr-ado` command/skill.

## Prerequisites

- `az` CLI + the `azure-devops` extension, authenticated (`az devops login`).
- `python3` (≥3.8; the server is stdlib-only — system python is fine).

## Quick install (all detected tools)

```bash
python3 install.py --org https://dev.azure.com/<org> --project "<project>"
```

It detects which agents are installed, registers the MCP server in each (merge-safe, backed up to
`<config>.ado-bak`, idempotent), and drops a `review-pr-ado` command where the tool supports one.
Preview without writing:

```bash
python3 install.py --print        # show every snippet, change nothing
python3 install.py --only codex,gemini
python3 install.py --force         # install even for undetected tools
```

Restart each tool afterwards so it loads the server.

## Per-tool manual setup

If you'd rather wire it by hand, point `command` at `server/ado_mcp_server.py`.

**Claude Code** — install the bundled plugin (richest: skill + lens agents + command + MCP):
```
/plugin marketplace add /path/to/ado-pr-review/packaging/claude-code
/plugin install ado-pr-review@ado-pr-review
```
…or just the server: `claude mcp add-json -s user ado-pr-review '{"command":"python3","args":["<repo>/server/ado_mcp_server.py"]}'`

**Codex** — `~/.codex/config.toml`:
```toml
[mcp_servers.ado-pr-review]
command = "python3"
args = ["<repo>/server/ado_mcp_server.py"]
env = { ADO_ORG = "https://dev.azure.com/<org>", ADO_PROJECT = "<project>" }
```

**OpenCode** — `~/.config/opencode/opencode.json`:
```json
{ "$schema": "https://opencode.ai/config.json",
  "mcp": { "ado-pr-review": {
    "type": "local",
    "command": ["python3", "<repo>/server/ado_mcp_server.py"],
    "enabled": true,
    "environment": { "ADO_ORG": "https://dev.azure.com/<org>" } } } }
```

**Gemini CLI** — `~/.gemini/settings.json`:
```json
{ "mcpServers": { "ado-pr-review": {
    "command": "python3", "args": ["<repo>/server/ado_mcp_server.py"],
    "env": { "ADO_ORG": "https://dev.azure.com/<org>" } } } }
```

**Cline** (VS Code) — `cline_mcp_settings.json`, and **Kiro** — `~/.kiro/settings/mcp.json`: both use
the standard `{"mcpServers": { "ado-pr-review": { "command": "python3", "args": ["…"] } }}` shape.

## Usage

In any wired tool: `review-pr-ado 1234` (or invoke the skill / `/review-pr-ado 1234`). It reviews
the PR and **prints findings only** — add `--post` to publish the comment to the PR. The agent uses
the `ado_pr_*` tools to read the PR and (only on `--post`) to comment.

## Config (env)

- `ADO_ORG` — default organization URL (the server also accepts a per-call `org`).
- `ADO_PROJECT` — default project (for `ado_pr_list_active`).
- `AZ_BIN` — path to `az` if not on PATH.

## Uninstall

Each edited config has a `<config>.ado-bak` backup. For Claude: `claude mcp remove -s user ado-pr-review`.
Remove the `[mcp_servers.ado-pr-review]` / `ado-pr-review` block from a tool's config to disable it.

## Notes / scope

- Live-tested here: the MCP server (all 5 tools) and the Claude Code packaging. The other tools'
  configs follow each project's documented MCP format — verify against your installed version.
- For diff **bodies**, the review uses local `git` in your repo clone; the MCP server returns
  changed-file *lists* (git is faster and exact for diffs).

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The server and installer are pure
Python stdlib (no runtime dependencies); please keep it that way and run `python3 tests/test_server_smoke.py`
before opening a PR.

## License

[MIT](LICENSE) © Kien Bui

