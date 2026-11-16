---
name: start-repo-from-thread
description: Start a new repository from one or more ChatGPT conversations. Asks whether the repo should be public or private, creates it, imports each thread into context/ as agent context, and writes a README and CLAUDE.md that point at them. Use when the user says "start a repo from this thread", "new repo from these ChatGPT chats", "spin this conversation out into a project", or gives chatgpt.com links together with a request for a new repo.
---

# Start a repo from ChatGPT thread(s)

A ChatGPT thread is often where a project starts: the idea, the scoping, the
first decisions. This skill turns one or more threads into a new repository
whose first commit is that background, so the next agent opens the repo and
already knows why it exists.

It composes `conversation-to-context` (the import) with repo creation. It does
not replace it: for an existing repo, use `conversation-to-context` directly.

## Inputs

- One or more thread sources: `chatgpt.com/c/…` URLs, `/share/` links, or
  conversations from an export archive.
- A repo name, if the user gave one. Otherwise propose one from the threads.

## Steps

1. **Ask public or private.** Always ask; never default silently. Use one
   question with both options and a short note on the trade-off: a public repo
   publishes the transcripts, so personal threads suit private, or public after
   `redact-conversation`. Ask the name in the same question round if not given.
   Follow the user's own naming and location conventions (their CLAUDE.md or
   standing instructions) over anything generic.

2. **Capture each thread** — see `import-chatgpt-conversation` — into a scratch
   directory outside any repo (e.g. `$(mktemp -d)`), so nothing lands in a git
   tree before the repo exists. Captured bodies go to disk, never through a
   tool result. With several threads, capture them one after another in the
   same browser tab.

3. **Propose the name** if none was given: derive it from the threads' titles
   and first user turn, the subject at maximum specificity. Confirm it in step
   1's question if possible, so the user is asked once.

4. **Create the repo** with the chosen visibility, then clone it to the user's
   usual location:
   ```bash
   gh repo create <owner>/<Name> --<public|private> \
     --description "<one line from the threads>" --clone
   ```
   If `gh` is unavailable, use whatever GitHub tool the session has, then
   `git clone`.

5. **Import into `context/`** — follow `conversation-to-context` for each
   thread, with `$ROOT` set to the new clone. Filenames stay
   `context/chatgpt-<YYYY-MM-DD>-<slug>.md`, one per thread.
   - **Public repo:** offer `redact-conversation` on each thread before it is
     written, and do not commit until the user has seen what is going public.
   - **Private repo:** the transcripts are the point of the repo; commit them.
     `conversation-to-context`'s "tracked context/ is about to be committed"
     confirmation is already answered by this skill's purpose — do not re-ask.
   - Canvas docs, code and images: run `extract-artifacts` into
     `context/artifacts/<slug>/`.

6. **Write the orientation files**, short and factual:
   - `README.md`: title, one-paragraph purpose drawn from the threads, a
     "Background" list linking each `context/` file with its date and title.
   - `CLAUDE.md`: what the repo is for, that `context/` holds the originating
     ChatGPT threads (the human is labelled `User`), and which thread holds the
     latest decisions if they differ. Note open questions the threads left
     unresolved — that is usually the first job.

7. **Commit and push**: one commit, e.g. `Start from ChatGPT thread(s): <titles>`.
   Stage the specific paths (`context/`, `README.md`, `CLAUDE.md`), not `-A`.

8. **Report** the repo URL, its visibility, and the list of imported threads
   with turn counts. Flag any thread whose normalize step wrote `.unhandled`
   content, and run the leftover-markup grep from `import-chatgpt-conversation`
   on each transcript before committing: rich UI answers (product cards,
   citation pills) are new, and markup that leaks through does not warn.

## Traps

- Creating the repo before capture succeeds leaves an empty repo behind when
  the browser route fails. Capture first (step 2), create second (step 4).
- Do not summarise the threads into the README instead of importing them. The
  README orients; the transcripts are the record.
- Several threads on the same subject belong in one repo. Threads on clearly
  different subjects are different repos — say so and ask, rather than merging
  them.
