---
name: render-markdown
description: Render a normalized ChatGPT conversation to Markdown with user and assistant turns marked, YAML front matter, a stats block and a sources section. Use after capturing and normalizing a conversation.
---

# Render to Markdown

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_conversation.py" <normalized.json> \
  --user-label "User" --assistant-label "ChatGPT" -o <out.md>
```

## Options that matter

| Flag | Use it for |
|---|---|
| `--user-label` | `User` for agent context, a real name for something a person reads |
| `--sources section\|footnotes\|none` | `section` lists sources at the end (default); `footnotes` also marks the turns that cited them |
| `--timestamps` | Per-turn time — useful for a long thread, noise for a short one |
| `--no-front-matter` | Pasting into an existing document |
| `--no-summary` | Drop the stats table |
| `--heading-level N` | Turn heading depth, default 2 |
| `--format text` | Strip front matter, keep the body |

## Output shape

```
---
title: ...            date_held: 2026-08-24
total_turns: 34       user_messages: 17      assistant_messages: 17
model: gpt-5-6        url: ...               captured_at: ...
---

# <title>
<stats table>

## User
...
## ChatGPT (gpt-5-6)
...
## Sources
1. [Title](url) — first cited in turn 4
```

## Headings inside messages

ChatGPT writes its own `##` headings inside answers. Emitted as-is under a `##`
turn heading they become siblings of it, and the document outline stops showing
where turns begin — any heading-based splitter then mis-slices the transcript.
The renderer demotes in-message headings below the turn level automatically,
skipping fenced code. If you change `--heading-level`, demotion follows it; you
do not need to compensate.

## Checking the result

Turn headings should equal `total_turns`:

```bash
grep -c '^## ' <out.md>
```

If that number exceeds the turn count, demotion did not run — the transcript is
still readable but is no longer safe to split on headings.
