#!/usr/bin/env python3
"""Install the ado-pr-review MCP server into every AI coding agent on this machine.

The MCP server is the portable core: Claude Code, Codex, OpenCode, Gemini CLI, Cline, and Kiro
all speak MCP, so registering one stdio server makes the ADO PR tools available in all of them.
This installer wires the server into each tool's native config (merge-safe / idempotent / backed
up) and drops a `review-pr-ado` command prompt where the tool has a simple command mechanism.

Usage:
    python3 install.py                 # detect installed tools, wire each one
    python3 install.py --print         # write nothing; print every config snippet
    python3 install.py --only codex,gemini
    python3 install.py --force         # install even for tools not detected
    python3 install.py --org https://dev.azure.com/<org> --project "<project>"

Safety: existing JSON configs are backed up to `<file>.ado-bak` before the first edit, and a config
that is not valid JSON is left untouched (the installer reports it so you can add the snippet by
hand). Re-running updates the `ado-pr-review` entry in place — never duplicates it.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server", "ado_mcp_server.py")
PLAYBOOK = os.path.join(HERE, "playbook", "REVIEW-PLAYBOOK.md")
NAME = "ado-pr-review"
HOME = os.path.expanduser("~")


def _stable_python():
    """A stable python3 to bake into tool configs. The server is stdlib-only, so any python3>=3.8
    works; prefer the always-present system interpreter over an ephemeral one (e.g. Xcode's)."""
    for cand in ("/usr/bin/python3", shutil.which("python3"), sys.executable):
        if cand and os.path.exists(cand):
            return cand
    return "python3"


PY = _stable_python()
ALL_TOOLS = ["claude", "codex", "opencode", "gemini", "cline", "kiro"]


def detect(tool):
    """Is the tool plausibly installed on this machine? (config dir or binary present)"""
    if tool == "claude":
        return bool(shutil.which("claude"))
    if tool == "codex":
        return os.path.isdir(os.path.join(HOME, ".codex")) or bool(shutil.which("codex"))
    if tool == "opencode":
        return os.path.isdir(os.path.join(HOME, ".config", "opencode")) or bool(shutil.which("opencode"))
    if tool == "gemini":
        return os.path.isdir(os.path.join(HOME, ".gemini")) or bool(shutil.which("gemini"))
    if tool == "cline":
        return os.path.isdir(os.path.dirname(_cline_settings_path()))
    if tool == "kiro":
        return os.path.isdir(os.path.join(HOME, ".kiro")) or bool(shutil.which("kiro"))
    return False


def prompt_body(args_placeholder):
    return (
        f"Review the Azure DevOps pull request {args_placeholder} using the ado-pr-review playbook.\n\n"
        f"Follow the procedure in {PLAYBOOK} exactly. Use the MCP tools from the `{NAME}` server "
        "(ado_pr_show, ado_pr_changed_files, ado_pr_threads_list, ado_pr_list_active) to gather "
        "context; run the multi-lens review plus adversarial 0-100 scoring; keep only findings "
        "scored >= 80; verify each survivor with a real tool call; then present the findings.\n\n"
        "Dry-run by DEFAULT: present findings only. Post to the PR (ado_pr_thread_post) ONLY if the "
        "user passed --post.\n"
    )


def env_block(org, project):
    e = {}
    if org:
        e["ADO_ORG"] = org
    if project:
        e["ADO_PROJECT"] = project
    return e


def std_mcp_entry(env):
    e = {"command": PY, "args": [SERVER]}
    if env:
        e["env"] = env
    return e


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def merge_json(cfg, mutate):
    """Merge into a JSON config, backing it up first and refusing to clobber unparseable files.

    Returns None on success or an error string (so the caller can report it)."""
    existing = {}
    if os.path.exists(cfg):
        try:
            with open(cfg, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return f"{cfg} is not valid JSON ({e}); add the snippet manually to avoid clobbering it"
        backup = cfg + ".ado-bak"
        if not os.path.exists(backup):
            shutil.copy2(cfg, backup)
    if not isinstance(existing, dict):
        return f"{cfg} top-level is not a JSON object; add the snippet manually"
    mutate(existing)
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return None


# --------------------------------------------------------------------------- per-tool installers
def do_claude(env, do_write):
    """Claude Code: user-scope MCP server via the CLI (the richer path is the bundled plugin)."""
    snippet = {"mcpServers": {NAME: std_mcp_entry(env)}}
    if not shutil.which("claude"):
        return ("skip", "claude CLI not found (or install the bundled plugin under packaging/claude-code)", snippet)
    if not do_write:
        return ("print", "claude mcp add-json -s user ado-pr-review '<json>'", snippet)
    import subprocess
    subprocess.run(["claude", "mcp", "remove", "-s", "user", NAME], capture_output=True, text=True)
    p = subprocess.run(["claude", "mcp", "add-json", "-s", "user", NAME, json.dumps(std_mcp_entry(env))],
                       capture_output=True, text=True)
    return ("ok" if p.returncode == 0 else "error", (p.stdout or p.stderr).strip()[:200], snippet)


def do_codex(env, do_write):
    """Codex CLI: ~/.codex/config.toml -> [mcp_servers.ado-pr-review] (TOML)."""
    cfg = os.path.join(HOME, ".codex", "config.toml")
    lines = [f"\n[mcp_servers.{NAME}]", f'command = "{PY}"', f'args = ["{SERVER}"]']
    if env:
        lines.append("env = { " + ", ".join(f'{k} = "{v}"' for k, v in env.items()) + " }")
    block = "\n".join(lines) + "\n"
    snippet = block.strip()
    if not do_write:
        return ("print", f"append to {cfg}", snippet)
    existing = ""
    if os.path.exists(cfg):
        with open(cfg, encoding="utf-8") as f:
            existing = f.read()
        if f"[mcp_servers.{NAME}]" in existing:
            return ("exists", f"{NAME} already in config.toml (edit manually to change)", snippet)
        if not os.path.exists(cfg + ".ado-bak"):
            shutil.copy2(cfg, cfg + ".ado-bak")
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    with open(cfg, "a", encoding="utf-8") as f:
        f.write(block)
    write_file(os.path.join(HOME, ".codex", "prompts", "review-pr-ado.md"), prompt_body("$ARGUMENTS"))
    return ("ok", f"appended to {cfg} + prompt ~/.codex/prompts/review-pr-ado.md", snippet)


def do_opencode(env, do_write):
    """OpenCode: ~/.config/opencode/opencode.json -> mcp.<name> {type:local, command:[...]}."""
    cfg = os.path.join(HOME, ".config", "opencode", "opencode.json")
    entry = {"type": "local", "command": [PY, SERVER], "enabled": True}
    if env:
        entry["environment"] = env
    snippet = {"$schema": "https://opencode.ai/config.json", "mcp": {NAME: entry}}
    if not do_write:
        return ("print", f"merge mcp.{NAME} into {cfg}", snippet)

    def mut(d):
        d.setdefault("$schema", "https://opencode.ai/config.json")
        d.setdefault("mcp", {})[NAME] = entry
    err = merge_json(cfg, mut)
    if err:
        return ("error", err, snippet)
    write_file(os.path.join(HOME, ".config", "opencode", "command", "review-pr-ado.md"), prompt_body("$ARGUMENTS"))
    return ("ok", f"merged into {cfg} + command review-pr-ado.md", snippet)


def do_gemini(env, do_write):
    """Gemini CLI: ~/.gemini/settings.json -> mcpServers.<name>; + a TOML command."""
    cfg = os.path.join(HOME, ".gemini", "settings.json")
    snippet = {"mcpServers": {NAME: std_mcp_entry(env)}}
    if not do_write:
        return ("print", f"merge mcpServers.{NAME} into {cfg}", snippet)
    err = merge_json(cfg, lambda d: d.setdefault("mcpServers", {}).__setitem__(NAME, std_mcp_entry(env)))
    if err:
        return ("error", err, snippet)
    toml_cmd = f'description = "ADO PR review"\nprompt = """\n{prompt_body("{{args}}")}"""\n'
    write_file(os.path.join(HOME, ".gemini", "commands", "review-pr-ado.toml"), toml_cmd)
    return ("ok", f"merged into {cfg} + command review-pr-ado.toml", snippet)


def _cline_settings_path():
    return os.path.join(HOME, "Library", "Application Support", "Code", "User", "globalStorage",
                        "saoudrizwan.claude-dev", "settings", "cline_mcp_settings.json")


def do_cline(env, do_write):
    """Cline (VS Code): cline_mcp_settings.json -> mcpServers.<name>."""
    cfg = _cline_settings_path()
    entry = std_mcp_entry(env)
    entry.update({"disabled": False, "autoApprove": []})
    snippet = {"mcpServers": {NAME: entry}}
    if not do_write:
        return ("print", f"merge mcpServers.{NAME} into {cfg}", snippet)
    if not os.path.isdir(os.path.dirname(cfg)):
        return ("skip", "Cline settings dir not found (open VS Code + Cline once, or add the snippet manually)", snippet)
    err = merge_json(cfg, lambda d: d.setdefault("mcpServers", {}).__setitem__(NAME, entry))
    return ("error", err, snippet) if err else ("ok", f"merged into {cfg}", snippet)


def do_kiro(env, do_write):
    """Kiro: ~/.kiro/settings/mcp.json -> mcpServers.<name>."""
    cfg = os.path.join(HOME, ".kiro", "settings", "mcp.json")
    entry = std_mcp_entry(env)
    entry.update({"disabled": False,
                  "autoApprove": ["ado_pr_show", "ado_pr_changed_files", "ado_pr_threads_list", "ado_pr_list_active"]})
    snippet = {"mcpServers": {NAME: entry}}
    if not do_write:
        return ("print", f"merge mcpServers.{NAME} into {cfg}", snippet)
    err = merge_json(cfg, lambda d: d.setdefault("mcpServers", {}).__setitem__(NAME, entry))
    return ("error", err, snippet) if err else ("ok", f"merged into {cfg}", snippet)


HANDLERS = {
    "claude": do_claude, "codex": do_codex, "opencode": do_opencode,
    "gemini": do_gemini, "cline": do_cline, "kiro": do_kiro,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", dest="print_only", action="store_true", help="print snippets, write nothing")
    ap.add_argument("--only", help="comma-separated subset of: " + ",".join(ALL_TOOLS))
    ap.add_argument("--force", action="store_true", help="install even for tools not detected on this machine")
    ap.add_argument("--org", default=os.environ.get("ADO_ORG", ""), help="default ADO org URL baked into the server env")
    ap.add_argument("--project", default=os.environ.get("ADO_PROJECT", ""), help="default ADO project name")
    a = ap.parse_args()

    if not os.path.exists(SERVER):
        print(f"ERROR: server not found at {SERVER}", file=sys.stderr)
        return 1

    env = env_block(a.org, a.project)
    tools = [t.strip() for t in a.only.split(",")] if a.only else ALL_TOOLS
    do_write = not a.print_only

    print("ado-pr-review installer")
    print(f"  server : {SERVER}")
    print(f"  python : {PY}")
    print(f"  env    : {env or '(none — pass --org/--project to bake defaults)'}")
    print(f"  mode   : {'WRITE' if do_write else 'PRINT-ONLY'}\n")

    forced = bool(a.only) or a.force
    for t in tools:
        h = HANDLERS.get(t)
        if not h:
            print(f"[{t}] unknown tool"); continue
        if do_write and not forced and not detect(t):
            print(f"[{t}] skip: not detected (use --only {t} or --force to install anyway)")
            continue
        try:
            status, msg, snippet = h(env, do_write)
        except Exception as e:  # noqa: BLE001
            status, msg, snippet = "error", str(e), None
        print(f"[{t}] {status}: {msg}")
        if a.print_only and snippet is not None:
            txt = snippet if isinstance(snippet, str) else json.dumps(snippet, indent=2, ensure_ascii=False)
            print("\n".join("    " + ln for ln in txt.splitlines()))
            print()

    if do_write:
        print("\nDone. Restart each tool (or reload its MCP config) to pick up the server.")
        print("Verify the `ado-pr-review` tools appear in any MCP client (ado_pr_show, ...).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
