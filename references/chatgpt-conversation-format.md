# The ChatGPT conversation format

Reverse-engineered against a live account on **2026-08-24**, ChatGPT web,
model slug `gpt-5-6`. Confirmed items were observed directly in a captured
payload; inferred items are marked and were not exercised by the specimen.

## Getting a conversation

### Own conversation — confirmed

`GET /backend-api/conversation/<conversation_id>`

Needs `Authorization: Bearer <token>`, where the token comes from
`GET /api/auth/session` → `.accessToken`. Both calls must run **from a
chatgpt.com page context** so they carry the session cookies; a `curl` from the
shell gets nothing useful.

The conversation id is the last path segment of `https://chatgpt.com/c/<id>`.

### Shared link — inferred

`GET /backend-api/share/<share_id>`, no token. The payload nests the thread
one level down under `conversation` in some responses, so check for `mapping`
at the top level first and fall back. Not exercised on 2026-08-24 — creating a
share link publishes content, so it was not tested.

### Account export — confirmed by shape

Settings → Data controls → Export data produces a zip whose `conversations.json`
is a flat array of the same object, minus auth-only fields. Generated images
ship as real files in the same zip; the browser routes cannot retrieve them.

## Top-level shape

Keys observed on a real conversation object:

```
title  create_time  update_time  moderation_results  plugin_ids
conversation_id  conversation_template_id  gizmo_id  gizmo_type
is_archived  is_starred  safe_urls  blocked_urls  default_model_slug
atlas_mode_enabled  conversation_origin  is_read_only  voice  async_status
disabled_tool_ids  is_temporary_chat  is_do_not_remember  memory_scope
context_scopes  sugar_item_id  sugar_item_visible  pinned_time
is_study_mode  owner  mapping  current_node  context_truncation_continuation
```

`create_time` / `update_time` are float epoch seconds.

## `mapping` is a DAG, not a list

**This is the single thing to get right.** `mapping` is `{node_id: node}` where

```json
{"id": "...", "parent": "<node_id|null>", "children": ["<node_id>", ...],
 "message": { ... } | null}
```

It holds *every node ever created in the thread*, including branches abandoned
when the user edited a prompt or regenerated an answer. Iterating
`mapping.values()` therefore yields messages that were never part of the
conversation as displayed, and produces a transcript in which the user appears
to say contradictory things.

The displayed thread is the path from `current_node` back to the root via
`parent`. There is exactly one synthetic root node with `message: null`.

A node with `len(children) > 1` is a branch point. On the specimen: 35 nodes,
35 on the rendered branch, 0 branch points, 1 leaf.

For an export where `current_node` is missing or dangling, falling back to the
leaf with the newest `create_time` recovers the same branch in nearly all
cases — but not on a heavily edited thread, so report `branch_points`.

## Message shape

```json
{
  "id": "...",
  "author": {"role": "user|assistant|system|tool", "name": null, "metadata": {}},
  "create_time": 1787543078.36,
  "content": {"content_type": "text", "parts": ["..."]},
  "status": "finished_successfully",
  "end_turn": true,
  "weight": 1,
  "recipient": "all",
  "channel": "final",
  "metadata": { ... }
}
```

Fields that change what you should do:

- **`recipient`** — `"all"` means the user sees it. Anything else is a tool
  call, and the value names the tool (`canmore.create_textdoc`,
  `python`, `web`).
- **`channel`** — `"final"` is the answer. `"analysis"` and `"commentary"`
  carry reasoning and tool chatter.
- **`weight: 0`** — present in the model's history but excluded from its
  context.
- **`metadata.is_visually_hidden_from_conversation: true`** — system prompts,
  memory injections, custom instructions. Hidden in the UI; drop by default.

`author.name` is set on tool messages and names the tool.

## Content types

Confirmed on the specimen: `text` only, with `parts` as an array of strings.

The rest were implemented from the wider format and are **inferred** — the
importer handles them and records anything it does not recognise in
`.unhandled` rather than dropping it silently:

| `content_type` | Payload |
|---|---|
| `text` | `parts: [str]` — **confirmed** |
| `multimodal_text` | `parts` mixes strings and objects (`image_asset_pointer`, `audio_transcription`, `real_time_user_audio_video_asset_pointer`) |
| `code` | `language`, `text` — tool call bodies, including canvas |
| `execution_output` | `text` |
| `thoughts` | `thoughts: [{summary, content}]` |
| `reasoning_recap` | `content` |
| `tether_browsing_display` | `result`, `summary` |
| `tether_quote` | `url`, `domain`, `title`, `text` |
| `sonic_webpage` | `url`, `title`, `text`, `snippet` |
| `system_error` | `name`, `text` |
| `user_editable_context` | `user_profile`, `user_instructions` |

## Metadata keys seen on a plain text conversation

```
can_save  citations  content_references  cot_version  default_model_slug
dictation  finish_details  image_results  is_complete
is_visually_hidden_from_conversation  message_source  message_type
model_slug  model_switcher_deny  parent_id  real_time_audio_has_video
request_id  resolved_model_slug  search_queries  search_result_groups
system_hints  trigger_async_ux  turn_exchange_id  voice_mode_message
working_turn_id  writing_blocks
conversation_context_citation_metadata_status
```

Citations arrive in two overlapping places — `citations[].metadata`
(`title`, `url`, `text`) and `search_result_groups[].entries[]`
(`title`, `url`, `snippet`). A search-heavy answer populates both, so
de-duplicate on URL rather than position.

## Artifacts

- **Canvas documents** — assistant message with `recipient`
  `canmore.create_textdoc` or `canmore.update_textdoc`, `content_type: code`,
  whose `text` is JSON: `{name, type, content}`. An update may carry `updates`
  (a diff) instead of full `content`.
- **Images** — `image_asset_pointer` parts with
  `asset_pointer: "file-service://file-XXXX"`, plus `width`/`height`/`size_bytes`.
  The pointer is an internal reference, **not a URL and not a path**. Rendering
  it as a markdown image makes pandoc/Typst try to open it as a file and abort
  the document.
- **Attachments** — `metadata.attachments: [{id, name, size, mime_type}]`.
- **Code interpreter files** — `metadata.aggregate_result.files`.

## The DOM route, and why it is a fallback

The message list is **virtualised**. On the 34-message specimen only 5
`[data-message-author-role]` elements existed at any scroll position, and
`data-testid` values started at `conversation-turn-6` rather than `-1`,
reflecting scroll position rather than thread position.

A single-pass `querySelectorAll` returns a handful of messages and looks like a
complete short conversation — it does not error. Scraping requires scrolling
from the top and accumulating by `data-message-id`.

Selectors as of 2026-08-24:

- `[data-message-author-role]` — `user` | `assistant`; also carries
  `data-message-id` and `data-message-model-slug`
- `[data-testid^="conversation-turn"]` — turn wrapper
- `.markdown.prose` — assistant answer body
- `<article>` elements are **no longer used** (count was 0)

## Environment notes

- **Chrome's download directory is not necessarily `~/Downloads`.** It is a
  per-profile setting; `~/Desktop` was the value on the machine this was
  verified against. Locate captured files by name and mtime, never by assuming
  the path.
- `mcp__claude-in-chrome__javascript_tool` does not await the value of the last
  expression. A bare `(async () => {...})()` serializes as `{}` and reads as a
  silent failure; the snippet must start with `await`.
