---
name: redact-conversation
description: Redact identifying detail from an imported ChatGPT conversation before sharing or committing it. Runs a deterministic pattern pass over the user's prompts, then a judgement pass for names, places and employers. Use when a transcript needs sanitizing.
---

# Redact a conversation

Two passes. The script does what regex can decide; you do what it cannot.
Running only the script and calling the transcript redacted is the failure mode
to avoid — it catches email addresses and misses "my manager Sarah at Acme".

## Pass 1 — deterministic

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact_conversation.py" \
  <normalized.json> -o <redacted.json>
```

Catches, with validation rather than shape-matching alone: API keys and tokens,
email addresses, IBANs, payment cards (Luhn-checked), Israeli ID numbers
(check-digit verified), phone numbers, IPv4 addresses, and URLs carrying auth
tokens.

Placeholders are consistent — the same address becomes `[EMAIL_1]` everywhere,
so a transcript that refers back to something still reads coherently.

Defaults to user turns only, on the theory that what leaks is what the human
typed. Pass `--scope all` when the assistant quoted the user back, which it
often does.

`--kinds EMAIL,PHONE` narrows the pass. `--report <path>` writes a log of what
was replaced. Avoid `--keep-values` unless you have a reason — it writes the
original secrets to disk.

### Known limit of pass 1

Adjacent unpunctuated numbers are ambiguous — `+972 54-123-4567 4111 1111 1111
1111` has no boundary a parser can see, and neither could a person. Both values
are still redacted, but the split between them may land in the wrong place, so
the placeholder kinds can be mislabelled. Prose with normal punctuation is
handled correctly.

## Pass 2 — judgement

The script cannot decide these. Read the redacted JSON and edit `turns[].text`
directly:

- personal names, and the relationships that identify someone without naming
  them ("my sister's landlord")
- employers, clients, schools, named projects
- home addresses, workplaces, distinctive locations
- medical, legal and financial specifics
- dates precise enough to identify an event
- anything the user has said is sensitive

Use the same `[KIND_N]` placeholder style so both passes read alike, and keep
one placeholder per real-world entity. After editing, set
`redaction.judgement_pass_applied` to `true` and add a `judgement_notes` line
saying what categories you removed.

## Then render

Renderers pick the redaction record up automatically — Markdown front matter
gets `redacted: true` and the PDF cover gets a `REDACTED` badge. Do not
hand-strip that; a sanitized transcript that does not announce itself as
sanitized invites someone to treat it as complete.

## Before you report it done

Grep the rendered output for what should be gone:

```bash
grep -nEi '@|[0-9]{3}[- ][0-9]{3}|sk-|ghp_' <out.md> | head
```

Say plainly which pass you ran. If you ran only pass 1, say the transcript is
pattern-redacted but not reviewed for names — the user may be about to send it
somewhere on the strength of your answer.
