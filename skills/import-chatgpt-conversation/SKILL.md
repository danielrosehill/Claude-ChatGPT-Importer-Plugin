---
name: import-chatgpt-conversation
description: Import a ChatGPT conversation into local files. Use when the user gives a chatgpt.com URL or shared link, asks to save/export/archive a ChatGPT chat, wants a transcript with user and assistant turns marked, or wants a ChatGPT thread as Markdown, JSON or PDF. Routes to the right capture and render path.
---

# Import a ChatGPT conversation

The entry point. Pick a capture route, normalize, then render. Do not
improvise a parser — the scripts exist and have been tested against the real
format.

## Pipeline

Every route converges on one intermediate file, then diverges into renderers:

```
capture ──> raw JSON ──> normalize_conversation.py ──> normalized JSON ──┬─> render_conversation.py  (Markdown)
                                                                        ├─> render_pdf.py           (PDF via Typst)
                                                                        └─> redact_conversation.py  (then render)
```

Normalized JSON is the thing to keep. It is the only format that holds turn
roles, timestamps, artifacts, citations and stats together, and every renderer
reads it.

## Choosing a capture route

| Input the user gives you | Route | Skill |
|---|---|---|
| `chatgpt.com/c/<id>` URL, or "the chat I have open" | Authenticated backend API in the browser | `capture-via-api` |
| `chatgpt.com/share/<id>` link | Same script, no token needed | `capture-via-api` |
| An export `.zip` or `conversations.json` | Local file, no browser | `import-export-archive` |
| API route failed or was removed | DOM scrape | `capture-via-dom` |

Always try `capture-via-api` first for a URL. It returns the complete thread
including branches, timestamps and artifact payloads. The DOM route is lossy
and is a fallback, not an alternative — see `capture-via-dom` for what it
cannot get.

## Then decide the output

Ask only if the user has not already implied it:

- **Into a repo as agent context** → use `conversation-to-context`. This is the
  common case. Label the human `User`, write Markdown to `context/`.
- **A document to read or send** → `render-typst-pdf`.
- **A Markdown file** → `render-markdown`.
- **Sanitized before it leaves the machine** → `redact-conversation` first.

If the conversation contains generated documents or images, mention
`extract-artifacts`; canvas documents are worth saving as their own files.

## Steps

1. Capture. Note the reported turn counts.
2. Normalize:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/normalize_conversation.py" \
     <raw.json> -o <normalized.json> --url "<source url>"
   ```
   The script prints `N turns (U user / A assistant), K artifacts` to stderr.
   **Check that against what the capture reported.** A mismatch means the
   branch walk picked a different leaf, not that messages vanished.
3. Render.
4. Tell the user the output path, the turn counts, and the date the
   conversation was held.

## Things that will bite you

- **`mapping` is a DAG, not a list.** It contains abandoned edit branches and
  regenerated answers that were never part of the thread the user saw.
  Iterating `mapping.values()` produces a transcript that reads as if the user
  said contradictory things. The normalizer walks parent links from
  `current_node`; do not replace that with a flat iteration.
- **Never commit an imported conversation.** The plugin's `.gitignore` covers
  the usual output paths, but check before staging anything.
- If `normalize_conversation.py` warns about unhandled content blocks, look at
  `.unhandled` in the output. It means OpenAI shipped a content type the
  importer does not know, and something is missing from the transcript.
