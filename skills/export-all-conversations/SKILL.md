---
name: export-all-conversations
description: Batch-export a whole ChatGPT history (every chat, archived chats and chats inside Projects, all workspaces the login sees) from a logged-in chatgpt.com tab, then build one Parquet table with a row per conversation and a date column, optionally pushed to a private Hugging Face dataset. Use on "export all my ChatGPT chats", "batch export", "mine my ChatGPT history", "make a dataset of my chats", or when the official export is slow or refused.
---

# Export every conversation

The web app's own backend lists and serves conversations; `scripts/browser/capture-all-via-api.js` walks it from
inside the tab (session token, `ChatGPT-Account-Id` per workspace) and saves JSONL files through browser downloads.
No message body passes through the agent's context.

## Steps

1. Load the browser tools in one ToolSearch; open a fresh tab on `https://chatgpt.com/`.
2. Paste the script into `javascript_tool` with `OPTS.limit: 20`. It returns at once; poll
   `JSON.stringify(window.__cgx.progress())`. Check the files arrived (find them by name; Chrome's download
   directory is not always `~/Downloads`) and build a test table (step 4).
3. Re-run with `limit: 0`. Speed seen 2026-11-22: ~0.6 s per conversation at concurrency 3, delay 250 ms,
   so ~12,000 chats take about 2 hours. Keep the tab open; don't navigate it. Raw size is ~250 KB per chat on average.
4. Move the files out of the download folder, then:
   ```bash
   uv run --script scripts/build_dataset.py chatgpt-export-<run>-*.jsonl --out chats.parquet --tz <zone> \
     [--merge previous.parquet] [--push <user>/<private-dataset>]
   ```
   Report rows, date range, `by_source`, normalize errors and export failures (the `-000` manifest lists them).
5. Incremental later: `OPTS.updatedAfter: '<ISO date of last run>'`, then `--merge` into the previous table.

## Endpoints (observed 2026-11-22)

| What | Request |
|---|---|
| Workspaces | `GET /backend-api/accounts/check/v4-2023-04-27` (can list one workspace twice; dedupe by `account_id`) |
| List | `GET /backend-api/conversations?offset=N&limit=100&order=updated&is_archived=false\|true`; `total` is a running count, not the real total, so stop on a short page |
| Projects | `GET /backend-api/gizmos/snorlax/sidebar?conversations_per_gizmo=0[&cursor=]`, then `GET /backend-api/gizmos/<id>/conversations?cursor=0` |
| One chat | `GET /backend-api/conversation/<id>` (same payload as `capture-via-api`) |

Headers: `Authorization: Bearer <accessToken from /api/auth/session>`, `ChatGPT-Account-Id: <account id>`. On 401
the script refreshes the token; on 429/5xx it backs off exponentially.

## Privacy

The output is the user's entire history. Never commit it; push only to a private dataset (`build_dataset.py`
refuses an existing public repo). A Team/Business workspace lists only the logged-in member's own chats here, not
other members'.
