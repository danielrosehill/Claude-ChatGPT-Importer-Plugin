---
name: capture-via-dom
description: Fallback capture of a ChatGPT conversation by scraping the rendered DOM with scrolling. Use only when capture-via-api fails. Lossy - no timestamps, branches, tool messages or artifact payloads.
---

# Capture by scraping the DOM

**Fallback only.** Use after `capture-via-api` has actually failed, not
instead of trying it. When you use this route, tell the user the capture is
lossy and why.

## Why it is lossy

The message list is virtualised. On a 34-message thread only about five
messages exist in the DOM at any scroll position, and `data-testid` indices
start wherever the viewport happens to be — `conversation-turn-6`, not `-1`.
A single-pass `querySelectorAll` therefore returns a handful of messages and
looks like a complete short conversation. That is the failure worth guarding
against: it does not error, it just silently returns a fraction.

The script scrolls the container from the top and accumulates by
`data-message-id`, which handles the virtualisation. It still cannot recover:

- per-message timestamps (`created_at` is `null` throughout)
- alternate branches from edited or regenerated turns
- hidden and tool messages
- canvas document payloads — only the rendered preview text survives
- image asset pointers and citation URLs as structured data

## Steps

1. Ensure the conversation tab is open and fully loaded.
2. Read `${CLAUDE_PLUGIN_ROOT}/scripts/browser/capture-via-dom.js` and pass it
   to `javascript_tool`. Scrolling takes several seconds on a long thread.
3. The download it writes is **already normalized** — it is emitted in the
   normalizer's schema. Skip `normalize_conversation.py` and go straight to a
   renderer.

## Verifying the capture

Scroll capture is the kind of thing that half-works. Before rendering, sanity
check:

```bash
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); s=d['stats']; \
print(s['total_turns'],'turns',s['user_messages'],'user',s['assistant_messages'],'assistant')" <file>
```

Compare against what the user says the thread contains, and against the turn
counter visible in the ChatGPT UI. If the count looks short, scroll to the top
of the thread manually and re-run rather than accepting it.

`stats.capture_is_lossy` is `true` in every file this route produces, and
`unhandled` carries a note explaining what is missing. Leave both in place —
they are how a later reader knows the transcript is partial.
