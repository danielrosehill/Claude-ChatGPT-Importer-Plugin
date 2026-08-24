---
name: render-typst-pdf
description: Render a ChatGPT conversation as a styled PDF using a Typst template, with colour-coded user and assistant turns, a metadata cover block, artifact callouts and a sources page. Use when the user wants a PDF, a document to read or share, or to be identified by their own name.
---

# Render to PDF (Typst)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_pdf.py" <normalized.json> \
  -o <out.pdf> --user-label "Daniel" --timestamps
```

Requires `pandoc` (>= 3.0, for the typst writer) and `typst` on PATH. The script
checks both and tells you what is missing.

## Choosing the speaker's name

This is the renderer where identity is a real choice. `--user-label` sets what
appears on every human turn and in the cover block.

- `User` — neutral, right for anything machine-facing or shared onward.
- A real name (`Daniel`) — right for a personal archive or a document going to
  someone who knows the participants.

**Ask which one the user wants** if they have not said, rather than defaulting
to their name. A transcript that leaves this machine with a real name on it is
harder to walk back than one that does not. `--assistant-label` works the same
way and defaults to `ChatGPT`.

## What the template produces

- Cover block: title, date held, model, per-speaker message counts, source URL,
  capture date, and a `REDACTED` badge if the conversation went through
  `redact-conversation`.
- Each turn as a tinted, left-ruled block — indigo for the human, teal for the
  assistant, amber for anything else — with the speaker label and optional time.
- Artifacts as amber callout boxes naming the kind and the document name.
- Sources on their own final page, numbered, with live links.

Layout lives in `${CLAUDE_PLUGIN_ROOT}/templates/transcript.typ`. Edit colours
and fonts there. Pass `--template <path>` to use a different one, and
`--paper us-letter` for US paper.

## How it works, and the one trap

Each turn's Markdown body is converted to Typst by pandoc, then wrapped in a
`#turn(...)` call. Turns are split by the script, not recovered afterwards with
a show-rule that parses heading text — so styling never depends on guessing
which speaker a heading belonged to.

All bodies go through pandoc in one call separated by a sentinel, because one
invocation per turn costs roughly twenty times as much. The script asserts that
the split count matches the turn count and aborts if it does not, rather than
emitting a transcript with two people's words in one block.

Use `--keep-typst <path>` to inspect the generated Typst when a compile fails.

## Image artifacts

A ChatGPT asset pointer (`file-service://file-...`) is an internal reference,
not a path. It is deliberately **not** rendered as an image — doing so makes
Typst try to open it as a file and abort the whole document. Images appear as
artifact callouts naming the pointer. To embed them for real, the asset has to
be downloaded first and `local_path` set on the artifact record.
