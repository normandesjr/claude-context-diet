# claude-context-diet

Every skill description, MCP instruction block and plugin Claude Code loads costs tokens on **every turn**. Most projects carry many that never fire. `context-diet` inventories what a project loads, measures what was actually used from its session transcripts, and lets you pick what to turn off.

## Install

```
/plugin marketplace add normandesjr/claude-context-diet
/plugin install context-diet@claude-context-diet
```

## Use

In the project you want to trim:

```
/context-diet:diet
```

1. **Inventory**: lists loaded skills, plugins, MCP servers and agents, with approximate token cost.
2. **Classify**: cut / keep / ask, from usage counts and last-used dates in `~/.claude/projects/<project>/*.jsonl` (subagents included). With little history, it judges by the repo's stack.
3. **Choose**: you pick per group; you pick the scope (project, local or user).
4. **Apply**: merges into the settings file, showing a diff first. Hooks, allow rules and other keys are preserved.
5. **Verify**: restart and run `/context`.

Rerun after Claude Code updates or new plugins; only new items need a decision.

The skill is user-invoked (`disable-model-invocation: true`), so it adds no context load of its own.

## What it changes

| Item | Setting |
| --- | --- |
| Skill | `skillOverrides[name] = "off"` (or `"name-only"`) |
| Plugin | `enabledPlugins["plugin@marketplace"] = false` |
| `.mcp.json` server | `disabledMcpjsonServers` |
| Other MCP server / tool | `permissions.deny` |

## Scripts

Standard-library Python 3, usable on their own:

- `plugins/context-diet/scripts/inventory.py --project-dir <dir>`: JSON report, read-only.
- `plugins/context-diet/scripts/apply.py --scope project|local|user [--skill-off X] [--plugin-off P@M] [--deny mcp__S] [--mcp-off S] [--dry-run]`

## Limits

- The transcript format is internal to Claude Code and may change; the inventory degrades to settings + plugins when it does.
- Token counts are estimates (characters / 4). `/context` is the real measure.
- Core tools (Bash, Read, Edit...) and the base system prompt are out of scope.
- Denying a claude.ai connector's tools may leave its server instruction block in context; check `/context`.

## License

MIT
