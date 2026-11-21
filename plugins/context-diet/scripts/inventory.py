#!/usr/bin/env python3
"""Inventory what Claude Code loads into context for a project, and how often each item was used.

Reads (never writes):
  - ~/.claude/projects/<encoded-project-dir>/**/*.jsonl  (session transcripts)
  - ~/.claude/settings.json, <project>/.claude/settings.json, <project>/.claude/settings.local.json
  - ~/.claude/plugins/installed_plugins.json

Prints one JSON document to stdout. Standard library only.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home()
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude"))

SKILL_LINE = re.compile(r"^- (\S+): (.*)$")
COMMAND_NAME = re.compile(r"<command-name>/?([^<\s]+)</command-name>")


def encode_project_dir(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def iter_records(path: Path):
    try:
        with path.open() as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def tokens(chars: int) -> int:
    return round(chars / 4)


def apply_delta(current: set, attachment: dict, added_key: str, removed_key: str):
    current.update(attachment.get(added_key) or [])
    current.difference_update(attachment.get(removed_key) or [])


def read_loaded(session: Path) -> dict:
    """Rebuild what the latest session had loaded, from its attachment records."""
    skills = {}
    deferred_tools, mcp_servers, agents = set(), set(), set()
    mcp_blocks, agent_lines = {}, {}
    for rec in iter_records(session):
        if rec.get("type") != "attachment":
            continue
        att = rec.get("attachment") or {}
        kind = att.get("type")
        if kind == "skill_listing":
            skills = {}
            for line in (att.get("content") or "").splitlines():
                m = SKILL_LINE.match(line)
                if m:
                    skills[m.group(1)] = len(line)
                elif skills and line.strip():
                    last = next(reversed(skills))
                    skills[last] += len(line)
        elif kind == "deferred_tools_delta":
            apply_delta(deferred_tools, att, "addedNames", "removedNames")
        elif kind == "mcp_instructions_delta":
            apply_delta(mcp_servers, att, "addedNames", "removedNames")
            for name, block in zip(att.get("addedNames") or [], att.get("addedBlocks") or []):
                mcp_blocks[name] = len(block)
        elif kind == "agent_listing_delta":
            apply_delta(agents, att, "addedTypes", "removedTypes")
            for line in att.get("addedLines") or []:
                m = re.match(r"^- ([^:]+):", line)
                if m:
                    agent_lines[m.group(1)] = len(line)
    return {
        "session": session.name,
        "skills": [{"name": n, "approx_tokens": tokens(c)} for n, c in skills.items()],
        "deferred_tools": sorted(deferred_tools),
        "mcp_servers_with_instructions": [
            {"name": n, "approx_tokens": tokens(mcp_blocks.get(n, 0))} for n in sorted(mcp_servers)
        ],
        "agents": [{"name": n, "approx_tokens": tokens(agent_lines.get(n, 0))} for n in sorted(agents)],
    }


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_usage(transcripts: list) -> dict:
    counts = defaultdict(Counter)
    last = defaultdict(dict)
    sessions = set()

    def hit(kind, name, ts):
        counts[kind][name] += 1
        if ts and ts > last[kind].get(name, ""):
            last[kind][name] = ts

    for path in transcripts:
        for rec in iter_records(path):
            msg = rec.get("message") or {}
            ts = rec.get("timestamp", "")
            if rec.get("sessionId"):
                sessions.add(rec["sessionId"])
            content = msg.get("content")
            if rec.get("type") == "user":
                for name in COMMAND_NAME.findall(text_of(content)):
                    hit("slash_commands", name, ts)
            if rec.get("type") != "assistant" or not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                inp = block.get("input") or {}
                hit("tools", name, ts)
                if name == "Skill" and inp.get("skill"):
                    hit("skills", inp["skill"], ts)
                elif name in ("Agent", "Task") and inp.get("subagent_type"):
                    hit("agents", inp["subagent_type"], ts)
                elif name.startswith("mcp__"):
                    hit("mcp_servers", name.split("__")[1], ts)

    return {
        "sessions_scanned": len(sessions),
        **{
            kind: [{"name": n, "count": c, "last_used": last[kind].get(n, "")[:10]} for n, c in counter.most_common()]
            for kind, counter in counts.items()
        },
    }


def read_settings(project: Path) -> dict:
    keys = ("enabledPlugins", "skillOverrides", "disabledMcpjsonServers", "enabledMcpjsonServers")
    out = {}
    for scope, path in (
        ("user", CLAUDE_DIR / "settings.json"),
        ("project", project / ".claude" / "settings.json"),
        ("local", project / ".claude" / "settings.local.json"),
    ):
        data = load_json(path) or {}
        entry = {k: data[k] for k in keys if k in data}
        deny = (data.get("permissions") or {}).get("deny")
        if deny:
            entry["permissions.deny"] = deny
        out[scope] = {"path": str(path), **entry}
    return out


def read_plugins() -> list:
    data = load_json(CLAUDE_DIR / "plugins" / "installed_plugins.json") or {}
    result = []
    for key, installs in (data.get("plugins") or {}).items():
        for inst in installs:
            root = Path(inst.get("installPath", ""))
            skills_dir = root / "skills"
            skills = sorted(p.name for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []
            manifest = load_json(root / ".claude-plugin" / "plugin.json") or {}
            mcp = load_json(root / ".mcp.json") or {}
            mcp_servers = sorted((mcp.get("mcpServers") or mcp or {}).keys()) if isinstance(mcp, dict) else []
            if isinstance(manifest.get("mcpServers"), dict):
                mcp_servers = sorted(set(mcp_servers) | set(manifest["mcpServers"]))
            result.append({
                "id": key,
                "scope": inst.get("scope"),
                "project": inst.get("projectPath"),
                "skills": skills,
                "mcp_servers": mcp_servers,
                "has_hooks": (root / "hooks").is_dir(),
                "has_agents": (root / "agents").is_dir(),
            })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-dir", default=os.getcwd(), help="project root (default: cwd)")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()

    transcript_dir = CLAUDE_DIR / "projects" / encode_project_dir(project)
    transcripts = sorted(transcript_dir.rglob("*.jsonl")) if transcript_dir.is_dir() else []
    main_sessions = sorted(transcript_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) if transcripts else []

    loaded = None
    for session in main_sessions:
        candidate = read_loaded(session)
        if candidate["skills"] or candidate["deferred_tools"]:
            loaded = candidate
            break

    json.dump({
        "project_dir": str(project),
        "transcript_dir": str(transcript_dir) if transcripts else None,
        "loaded_in_latest_session": loaded,
        "usage": read_usage(transcripts),
        "settings": read_settings(project),
        "installed_plugins": read_plugins(),
    }, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
