---
name: conversation-to-context
description: Import a ChatGPT conversation into the current repository as agent context. Use when the user wants to bring a ChatGPT thread into a project, pull a chat into context, or save a conversation for Claude to read later. Writes a Markdown transcript to context/ with the human labelled User.
---

# Import a conversation into the repo as context

The common workflow. A ChatGPT thread holds decisions and background that the
repo does not, and the point is to make it readable by whatever agent opens the
repo next.

## Conventions

- Destination is `context/` **in the repository being worked on** — the current
  working directory's repo root, not the plugin's directory. Create it if it
  does not exist.
- The human is labelled `User`, not by name. This output is for an agent, and
  `User` is unambiguous in a way a first name is not. Use a real name only if
  the user explicitly asks — that is what `render-typst-pdf` is for.
- Filename: `context/chatgpt-<YYYY-MM-DD>-<slug>.md`, date being when the
  conversation was held, not when it was imported.
- YAML front matter stays. It carries the date, model, turn counts and source
  URL, and an agent reading the file cold needs all of it.

## Steps

1. Capture and normalize — see `import-chatgpt-conversation`.

2. Find the repo root and make the folder:
   ```bash
   ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   mkdir -p "$ROOT/context"
   ```

3. Render:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_conversation.py" \
     <normalized.json> \
     --user-label "User" \
     --assistant-label "ChatGPT" \
     --sources section \
     -o "$ROOT/context/chatgpt-<date>-<slug>.md"
   ```

4. Check whether `context/` is git-ignored:
   ```bash
   git check-ignore -q "$ROOT/context" && echo IGNORED || echo TRACKED
   ```
   If it is tracked, the transcript will be committed. **Say so before staging
   it** and confirm the user wants a ChatGPT conversation in the repo history.
   If the thread is personal, offer `redact-conversation` first, or suggest
   adding `context/` to `.gitignore`.

5. If the repo has a `CLAUDE.md`, consider adding a line pointing at the new
   file, so the next agent finds it without being told. Ask first — do not
   silently edit `CLAUDE.md`.

## Keeping it useful to read

Default rendering keeps every turn. For a long thread imported purely as
background, `--no-summary` and `--heading-level 2` keep it tight. Do not
summarize the conversation into the file instead of transcribing it: the value
is the actual exchange, and a summary is something the next agent can produce
for itself but cannot reverse.

If the conversation produced canvas documents, run `extract-artifacts` and save
them next to the transcript as real files — a document quoted inside a
transcript is much harder to use than one sitting on disk.
