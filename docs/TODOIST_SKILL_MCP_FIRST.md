# Todoist Skill - MCP-First SKILL.md Snippet

Copy this into your Todoist skill's SKILL.md on the Pi to prioritize MCP tools over exec.

**Location on Pi:** `~/.nanobot/workspace/skills/todoist/SKILL.md`

---

## Replace or add this section

```markdown
## Tool Usage (MCP preferred)

**Always use MCP tools first** for listing and managing tasks:

| Use case | MCP tool | When to use |
|----------|----------|-------------|
| Tasks due today | `mcp_todoist_list_tasks_today` | "What's due today?" |
| Tasks due this week | `mcp_todoist_list_tasks_this_week` | "Tasks due tomorrow?", "What's due this week?" |
| Overdue tasks | `mcp_todoist_list_tasks_overdue` | "What's overdue?" |
| Create task | `mcp_todoist_create_task` | "Add a task..." |
| Create reminder | `mcp_todoist_create_reminder_task` | "Remind me to..." |
| List projects | `mcp_todoist_list_projects` | "What projects do I have?" |

**Use exec only** when MCP tools do not cover the request (e.g. custom filters, advanced queries not exposed as MCP tools).
```

---

## Full SKILL.md example

If you want to replace the entire SKILL.md, ensure it has:

1. Frontmatter with `name` and `description`
2. MCP tool guidance (above) as the primary section
3. Exec fallback as secondary, with a note like: "If MCP tools are unavailable, run: `python run.py list_tasks_by_query \"<query>\""`

---

## Optional: System prompt tweak

If the skill's SKILL.md alone doesn't change behavior, add this to your nanobot system prompt in `~/.nanobot/config.json` (inside `agents.defaults.system`):

```
- For Todoist task listing, always use MCP tools (mcp_todoist_list_tasks_today, mcp_todoist_list_tasks_this_week, mcp_todoist_list_tasks_overdue) instead of exec. Use exec only when no MCP tool fits the request.
```

---

## Apply on the Pi

```bash
# SSH to Pi, then:
nano ~/.nanobot/workspace/skills/todoist/SKILL.md
# Paste the MCP-first section, save, then:
sudo systemctl restart nanobot.service
```
