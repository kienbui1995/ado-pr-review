#!/usr/bin/env bash
# Sync the canonical sources into the self-contained Claude Code plugin.
# The plugin bundles copies of the server + playbook docs + post script so it works standalone
# when installed from a marketplace. Run this after editing any canonical file under
# server/, playbook/, or scripts/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN="$ROOT/packaging/claude-code"
SKILL="$PLUGIN/skills/review-pr-ado"

cp "$ROOT/server/ado_mcp_server.py"        "$PLUGIN/server/ado_mcp_server.py"
cp "$ROOT/playbook/ado-commands.md"        "$SKILL/references/ado-commands.md"
cp "$ROOT/playbook/review-lenses.md"       "$SKILL/references/review-lenses.md"
cp "$ROOT/scripts/post_pr_comment.py"      "$SKILL/scripts/post_pr_comment.py"
echo "synced canonical sources -> packaging/claude-code/"
