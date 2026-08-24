# ChatGPT Importer — working notes

Claude Code plugin that imports ChatGPT conversations into local files.
See `README.md` for what it does and `references/chatgpt-conversation-format.md`
for the reverse-engineered format.

## Before changing anything

Run the tests. They encode the bugs this pipeline has actually had:

```bash
./tests/run.sh
```

`fixtures/sample-conversation.json` is wholly synthetic. **Never replace it
with a real conversation** — it is the one JSON file in this repo that is
committed.

## Rules that are not obvious from the code

- **Never commit an imported conversation.** `.gitignore` covers the usual
  output paths; check before staging regardless.
- **Captured bodies go to disk, never through a tool result.** Returning a
  conversation copies a private thread into an agent transcript and spends a
  large amount of context. Capture snippets return a summary only.
- **`mapping` is a DAG.** Do not replace the parent-link branch walk in
  `normalize_conversation.py` with a flat iteration over `mapping.values()` —
  that pulls in abandoned edit branches and produces a transcript in which the
  user contradicts themselves.
- **Unknown content types go to `.unhandled`, never dropped.** A silently
  shorter transcript is the failure mode that nobody notices.
- **Stdlib only** for `normalize_conversation.py`, `render_conversation.py`,
  `redact_conversation.py` and `split_export_archive.py`. The importer has to
  run without a venv. Only `render_pdf.py` may shell out, to pandoc and typst.

## Traps already paid for

- `mcp__claude-in-chrome__javascript_tool` does not await the last expression.
  A bare `(async () => {...})()` serializes as `{}`. Capture snippets start
  with `await`.
- Chrome's download directory is a per-profile setting and is not reliably
  `~/Downloads` (it was `~/Desktop` where this was developed). Locate captured
  files by name and mtime.
- The ChatGPT DOM is virtualised — about 5 of 34 messages exist at any scroll
  position, and `data-testid` indices reflect scroll, not thread position. A
  single-pass scrape returns a fraction and does not error.
- ChatGPT writes its own `##` headings inside answers; `demote_headings` pushes
  them below the turn level so the outline still marks turn boundaries.
- Asset pointers (`file-service://…`) are not paths. Emitting them as markdown
  images makes pandoc/Typst try to open them and abort the render.
- `render_pdf.py` batches all turns through one pandoc call with a sentinel and
  asserts the split count. Do not relax that assertion — it is what stops two
  speakers' words merging into one block.
- In `redact_conversation.py`, the scan is a manual `search(text, pos)` loop,
  not `finditer`. On a validation failure it retries from `start+1`, because
  finditer resumes past the whole rejected span and a greedy match straddling
  two adjacent numbers would swallow the second one unexamined.
