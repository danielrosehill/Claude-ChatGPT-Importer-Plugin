# ChatGPT Importer — Claude Code plugin

Import a ChatGPT conversation into local files: capture it from the browser,
normalize it, and render Markdown, JSON or a styled PDF with user and assistant
turns marked, artifacts identified and conversation metadata recorded.

Built for the case where a ChatGPT thread holds decisions or background that a
repository does not, and the point is to get it somewhere the next agent will
read it.

## Pipeline

```
capture ──> raw JSON ──> normalize_conversation.py ──> normalized JSON ──┬─> render_conversation.py  (Markdown)
                                                                        ├─> render_pdf.py           (PDF via Typst)
                                                                        └─> redact_conversation.py  (then render)
```

The normalized JSON is the artifact worth keeping. It holds turn roles,
timestamps, artifacts, citations and stats together, and every renderer reads it.

## Capture routes

| Input | Route | Completeness |
|---|---|---|
| `chatgpt.com/c/<id>` | Authenticated backend API, run in the page | Complete |
| `chatgpt.com/share/<id>` | Same, no token | Complete |
| Export `.zip` | Local file, no browser | Complete, plus real image files |
| API route broken | DOM scrape with scrolling | Lossy — no timestamps, branches or artifact payloads |

## Skills

| Skill | Does |
|---|---|
| `import-chatgpt-conversation` | Entry point — picks the route, runs the pipeline |
| `conversation-to-context` | Import into `context/` in the current repo as agent context |
| `capture-via-api` | Primary browser capture |
| `capture-via-dom` | Fallback scrape |
| `import-export-archive` | Bulk import from an account export |
| `render-markdown` | Markdown with front matter, stats and sources |
| `render-typst-pdf` | Styled PDF, configurable speaker identity |
| `redact-conversation` | Two-pass redaction |
| `extract-sources` | De-duplicated citation list |
| `extract-artifacts` | Save canvas documents and code as files |

## Metadata recorded

Every import captures the date the conversation was held, its duration, model,
total turns, user and assistant message counts, character counts per speaker,
artifact and citation counts, and whether the thread contained abandoned edit
branches.

## Requirements

- Capture: Chrome with the Claude in Chrome extension, logged in to ChatGPT.
- Normalize and Markdown: **Python 3.9+, stdlib only.** No venv.
- PDF: `pandoc` >= 3.0 (for the typst writer) and `typst`.

## Privacy

Conversations are private by default and nothing captured is committed. The
`.gitignore` covers the usual output paths (`imports/`, `out/`, `context/`
transcripts, `conversations.json`).

Captured bodies are written to disk rather than returned through the tool
result, so a long private thread does not end up copied into an agent
transcript. Only a summary comes back.

`redact-conversation` runs a validated pattern pass — keys, emails, IBANs,
Luhn-checked cards, check-digit-verified Israeli IDs, phones, IPs — and then
prompts for the judgement pass that regex cannot do.

## Format notes

The ChatGPT conversation format is reverse-engineered and undocumented.
`references/chatgpt-conversation-format.md` records what was verified against a
live account on 2026-08-24, what was inferred, and the traps — chiefly that
`mapping` is a DAG containing abandoned branches, and that the rendered DOM is
virtualised so a single-pass scrape silently returns a fraction of the thread.

## Testing

```bash
./tests/run.sh
```

Runs the whole pipeline against `fixtures/sample-conversation.json`, a wholly
synthetic conversation exercising branching, hidden messages, canvas artifacts,
image pointers, citations and an unknown content type.
