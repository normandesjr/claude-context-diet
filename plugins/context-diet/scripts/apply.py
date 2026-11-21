#!/usr/bin/env python3
"""Merge context-diet choices into a Claude Code settings file, idempotently.

Only touches: skillOverrides, enabledPlugins, permissions.deny, disabledMcpjsonServers.
Every other key (hooks, allow rules, env...) is preserved. Prints a before/after diff.

Examples:
  apply.py --scope project --skill-off docx --skill-off pptx
  apply.py --scope user --plugin-off foo@bar --deny 'mcp__claude_ai_Gmail' --mcp-off github
  apply.py --scope project --skill-on docx --dry-run
"""

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def target(scope: str, project: Path) -> Path:
    return {
        "user": CLAUDE_DIR / "settings.json",
        "project": project / ".claude" / "settings.json",
        "local": project / ".claude" / "settings.local.json",
    }[scope]


def add_unique(items: list, values: list) -> list:
    return items + [v for v in values if v not in items]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scope", choices=("user", "project", "local"), required=True)
    p.add_argument("--project-dir", default=os.getcwd())
    p.add_argument("--skill-off", action="append", default=[], help='skillOverrides[name] = "off"')
    p.add_argument("--skill-name-only", action="append", default=[], help='skillOverrides[name] = "name-only"')
    p.add_argument("--skill-on", action="append", default=[], help="remove the skillOverrides entry")
    p.add_argument("--plugin-off", action="append", default=[], help="enabledPlugins[plugin@marketplace] = false")
    p.add_argument("--plugin-on", action="append", default=[], help="enabledPlugins[plugin@marketplace] = true")
    p.add_argument("--deny", action="append", default=[], help="append to permissions.deny (tool or mcp__server)")
    p.add_argument("--undeny", action="append", default=[], help="remove from permissions.deny")
    p.add_argument("--mcp-off", action="append", default=[], help="append to disabledMcpjsonServers")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    path = target(a.scope, Path(a.project_dir).resolve())
    before_text = path.read_text() if path.exists() else "{}\n"
    try:
        data = json.loads(before_text)
    except ValueError as exc:
        sys.exit(f"{path} is not valid JSON: {exc}")

    original_keys = set(data)
    original_deny = "deny" in (data.get("permissions") or {})
    overrides = data.setdefault("skillOverrides", {})
    for name in a.skill_off:
        overrides[name] = "off"
    for name in a.skill_name_only:
        overrides[name] = "name-only"
    for name in a.skill_on:
        overrides.pop(name, None)

    plugins = data.setdefault("enabledPlugins", {})
    for pid in a.plugin_off:
        plugins[pid] = False
    for pid in a.plugin_on:
        plugins[pid] = True

    perms = data.setdefault("permissions", {})
    deny = add_unique(perms.get("deny", []), a.deny)
    perms["deny"] = [d for d in deny if d not in a.undeny]

    if a.mcp_off:
        data["disabledMcpjsonServers"] = add_unique(data.get("disabledMcpjsonServers", []), a.mcp_off)

    # Drop only the empty containers this run created; keep the user's own.
    for key in ("skillOverrides", "enabledPlugins"):
        if not data[key] and key not in original_keys:
            del data[key]
    if not perms["deny"] and not original_deny:
        del perms["deny"]
    if not perms and "permissions" not in original_keys:
        del data["permissions"]

    after_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    diff = "".join(difflib.unified_diff(
        before_text.splitlines(True), after_text.splitlines(True), str(path), str(path) + " (new)"))
    print(diff or f"{path}: no change")
    if diff and not a.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after_text)
        print(f"written: {path}")


if __name__ == "__main__":
    main()
