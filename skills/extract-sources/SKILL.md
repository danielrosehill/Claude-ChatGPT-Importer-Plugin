---
name: extract-sources
description: Collect the sources a ChatGPT conversation cited into a de-duplicated list, as a sources section, footnotes, or a standalone bibliography. Use when the user wants the references, links or citations from a chat.
---

# Extract cited sources

When ChatGPT searches the web, each answer carries citation metadata. The
normalizer keeps it per turn; this pulls it together.

## In a rendered transcript

Already handled — `--sources` controls the presentation:

- `section` (default): numbered list at the end, each noting the turn where it
  was first cited.
- `footnotes`: markers on the citing turns plus footnote definitions at the end.
- `none`: drop them.

## As a standalone list

```bash
python3 -c "
import json,sys
sys.path.insert(0,'${CLAUDE_PLUGIN_ROOT}/scripts')
from render_conversation import collect_sources
d=json.load(open(sys.argv[1]))
for s in collect_sources(d):
    print(f\"{s['n']}. {s['title']} — {s['url']} (turn {s['first_turn']})\")
" <normalized.json>
```

Sources are de-duplicated on URL and numbered in first-reference order, so the
numbering is stable across all three presentations.

## What to check

A count of zero means one of two different things, and they are worth telling
apart before reporting "no sources":

- the conversation genuinely never used web search, or
- the capture route could not carry citations. `capture-via-dom` never
  produces them, and its output always has `stats.capture_is_lossy: true`.

Check that flag before concluding the conversation was uncited.

Citations come from two places in the raw metadata — `citations` and
`search_result_groups` — and a search-heavy answer usually populates both with
overlapping entries. That is why de-duplication happens on URL rather than on
position.

Sources carry titles as ChatGPT recorded them at the time. Do not fetch the
URLs to "verify" or improve the titles unless the user asks; the point is what
the conversation cited, not what the page says now.
