---
name: capture-via-api
description: Capture a ChatGPT conversation as raw JSON by calling the authenticated backend API from inside the browser tab. Use when importing from a chatgpt.com/c/ URL or a /share/ link. This is the primary, complete capture route.
---

# Capture via the backend API

Runs a fetch in the page's own context, so it inherits the logged-in session.
Returns the complete conversation: every message, timestamps, model slugs,
tool calls, artifact payloads and all branches.

## Steps

1. Load the browser tools in one call:
   ```
   ToolSearch "select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool"
   ```
2. `tabs_context_mcp` for tab ids, then `tabs_create_mcp` for a fresh tab
   unless the user asked to use one they already have open.
3. `navigate` to the conversation URL. Wait for it to settle.
4. Read `${CLAUDE_PLUGIN_ROOT}/scripts/browser/capture-via-api.js` and pass its
   contents to `javascript_tool`.
5. The snippet returns a JSON summary and writes the conversation to the
   browser's download directory.

## Reading the result

Success looks like:

```json
{"ok":true,"filename":"chatgpt-conversation-<id>.json","bytes":126173,
 "nodes":35,"roles":{"user":17,"assistant":17},"branch_points":0,"leaves":1}
```

Only the summary comes back. The conversation body goes to disk on purpose —
returning it would copy a private thread into the transcript and spend a large
amount of context on something no one needs to read in-band.

`branch_points > 0` means the thread has edited or regenerated turns. The
normalizer renders the branch the UI last displayed and reports the rest in
`stats`. Say so when reporting, because the user may want a different branch.

## Finding the downloaded file

**Do not assume `~/Downloads`.** Chrome's download directory is a per-profile
setting and is not always the default — `~/Desktop` is a common alternative.
Locate the file by name instead:

```bash
find ~ -maxdepth 3 -name 'chatgpt-conversation-*.json' -mmin -3 2>/dev/null
```

Move it out of the download directory before working on it — those folders get
cleaned, and the file is private.

## Failure modes

| Returned | Meaning | Do next |
|---|---|---|
| `{}` | The snippet lost its `await` prefix | Re-run with the file's exact contents |
| `not_authenticated` | No `accessToken` from `/api/auth/session` | Ask the user to log in to chatgpt.com in this Chrome profile; do not attempt to log in yourself |
| `http_401` / `http_403` | Token expired, or the conversation belongs to another account | Ask the user to reload the tab |
| `http_404` | Wrong id, or a deleted conversation | Re-check the URL |
| `not_on_a_conversation_page` | Tab is on the chat list, not a thread | Navigate to the `/c/<id>` URL |
| `no_mapping_in_payload` | Response shape changed | Fall back to `capture-via-dom` and flag that the API route needs updating |

Never enter credentials. If the account is logged out, that is the user's job.
