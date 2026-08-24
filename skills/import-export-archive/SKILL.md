---
name: import-export-archive
description: Import conversations from an official ChatGPT data export zip or conversations.json. Use for bulk import, for old or deleted conversations, or when the browser route is unavailable. Also the only route that carries generated images as real files.
---

# Import from an account export

The export comes from ChatGPT **Settings → Data controls → Export data**, and
arrives by email as a zip. `conversations.json` at its root is a flat array of
conversations in the same shape the backend API returns.

Use this route for bulk work, for anything no longer in the sidebar, and when
images matter — the zip bundles them as real files, which the browser route
cannot retrieve.

## List before extracting

An export holds every conversation the account has ever had. Do not extract all
of them because a script can:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/split_export_archive.py" export.zip --list
```

```
1483 of 1483 conversation(s)

[   0] 2026-08-24   17u/17 a  Quarterly planning notes
[   1] 2026-08-21    4u/5  a  Sample onboarding conversation
```

Narrow with `--match "<regex over title>"`, `--since YYYY-MM-DD`, `--id <uuid>`
or `--index N`. Add `--json` for machine-readable output.

Conversation titles are themselves personal. When the user is looking for one
thread, filter to it rather than printing the whole listing into the
transcript.

## Extract, then normalize

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/split_export_archive.py" export.zip \
  --match "onboarding" --out-dir ./raw

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/normalize_conversation.py" \
  ./raw/2026-08-21-sample-onboarding-conversation.json \
  --source-kind export_archive -o ./normalized.json
```

Files are named `<date>-<title-slug>.json`. `normalize_conversation.py` also
takes the raw array directly with `--index N`, which saves a step for a
one-off.

Then render as usual — `render-markdown`, `render-typst-pdf`, or
`conversation-to-context`.

## Differences from the browser route

- `current_node` is sometimes absent or points at a node that is not in the
  export. The normalizer falls back to the newest leaf, which is nearly always
  the same branch; on a heavily edited thread it may not be. Check
  `stats.branch_points`.
- Model slugs are sparser on older conversations, so `models_used` can be short
  or empty for anything predating that field.
- Images referenced by asset pointers exist as files elsewhere in the zip.
  Matching them up by pointer id is not automated here; unzip and look for the
  file id if the user needs them.

## Bulk import

For many conversations, loop over the extracted files. Two things to hold onto:
write outputs somewhere git-ignored, and do not print titles in bulk. If the
user wants hundreds imported into a repo, confirm the destination is ignored
before starting rather than after.
