---
name: diet
description: Trim the skills, plugins and MCP servers this project loads into context, keeping what the user picks.
disable-model-invocation: true
---

Put the project on a context **diet**: every always-loaded skill description, MCP instruction block and plugin costs tokens on every turn. The user decides what stays; the transcripts supply the evidence.

## 1. Inventory

Run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/inventory.py --project-dir "$PWD"` and read its JSON:

- `loaded_in_latest_session`: what the last session actually carried, with approximate tokens per item.
- `usage`: call counts and last-used date per skill, slash command, agent, MCP server and tool, across every transcript of this project (subagents included).
- `settings`: the current `skillOverrides`, `enabledPlugins`, `permissions.deny` and `disabledMcpjsonServers` at user, project and local scope.
- `installed_plugins`: each plugin with the skills and MCP servers it brings.

Add what the script cannot see: your own listings in this session (skills, deferred tools, MCP server instructions, agent types). Your context is the ground truth for what is loaded right now.

Done when every loaded item has a row: name, kind, source (built-in, user, project, plugin id, MCP server), approx tokens, uses, last used.

## 2. Classify

Sort each row into one bucket:

- **cut**: zero uses, or none in the last 60 days.
- **keep**: used recently.
- **ask**: rarely used, or `usage.sessions_scanned` is under 10. With thin history, judge by the project's stack instead: read the repo root (manifests, languages, file types) and mark as **cut** what the stack never needs (office documents in a backend repo, browser automation in a CLI).

Items this project's own `.claude/skills/` defines start as **keep**; the team put them there.

## 3. Choose

Show the table grouped by bucket, with the token total each bucket would free. Then use `AskUserQuestion` with `multiSelect: true`, one question per bucket (split a bucket over several questions when it passes 4 options), asking which items to turn off; **cut** items are labelled `(Recommended)`.

Ask the scope once: **project** (`.claude/settings.json`, committed, shared with the team), **local** (`.claude/settings.local.json`, only this user), or **user** (`~/.claude/settings.json`, every project). Suggest **user** for items unused in every project the user works on.

Done when the user has answered every question.

## 4. Apply

Map each chosen item to one `apply.py` flag:

| Item | Flag | Effect |
| --- | --- | --- |
| Skill (non-plugin) | `--skill-off <name>` | `skillOverrides[name] = "off"` |
| Skill to keep invocable by `/name` only | `--skill-name-only <name>` | description stays out of context |
| Plugin (with all its skills, MCP, hooks) | `--plugin-off <plugin@marketplace>` | `enabledPlugins[id] = false` |
| MCP server from `.mcp.json` | `--mcp-off <server>` | `disabledMcpjsonServers` |
| MCP server or tool from elsewhere (claude.ai connectors) | `--deny mcp__<server>` | `permissions.deny` |

Plugin skills ignore `skillOverrides`; turn off the whole plugin. An empty `enabledPlugins: {}` disables nothing; each plugin needs an explicit `false`.

Run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/apply.py --scope <scope> --project-dir "$PWD" <flags> --dry-run`, show the diff, then run it again without `--dry-run` once the user confirms.

## 5. Verify

Tell the user to restart Claude Code (or `/clear`) and run `/context` to compare the before and after. Rerun this skill whenever a Claude Code update or a new plugin adds items: the existing overrides stay, and only the new rows need a decision.
