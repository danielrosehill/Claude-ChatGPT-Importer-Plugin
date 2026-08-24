---
name: extract-artifacts
description: Pull generated documents, canvas docs, code blocks, images and attachments out of an imported ChatGPT conversation and save them as real files. Use when a conversation produced a document, code, or images worth keeping separately.
---

# Extract artifacts

A canvas document quoted inside a transcript is much harder to use than one
sitting on disk as a file. This saves them out.

## What the normalizer detects

| Kind | Where it comes from | Recoverable content |
|---|---|---|
| `canvas_document` | Messages addressed to `canmore.create_textdoc` / `update_textdoc` | Full text, name, doc type |
| `code_block` | Fenced blocks of 5+ lines in assistant answers | Language and line count; body is in the turn text |
| `generated_image` | `image_asset_pointer` from `dalle`/image tools | Pointer only — see below |
| `image` | Images the user uploaded | Pointer, dimensions |
| `generated_file` | Code interpreter output files | Name and file id |
| `attachment` | Files the user uploaded | Name, MIME type, size |

## Listing them

```bash
python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
for a in d['artifacts']:
    print(f\"turn {a['turn_index']:>3}  {a['kind']:<18} {a.get('name') or a.get('pointer') or ''}\")
" <normalized.json>
```

## Saving canvas documents

These carry their full text and are the ones actually worth extracting:

```bash
python3 -c "
import json,sys,re,pathlib
d=json.load(open(sys.argv[1])); out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True,exist_ok=True)
n=0
for a in d['artifacts']:
    if a['kind']!='canvas_document' or not a.get('content'): continue
    slug=re.sub(r'[^a-z0-9]+','-',(a.get('name') or 'document').lower()).strip('-')
    ext='.md' if (a.get('doc_type') or '').startswith('document') else '.txt'
    p=out/f\"{a['turn_index']:03d}-{slug}{ext}\"; p.write_text(a['content']); n+=1
    print(p)
print(f'{n} document(s)')
" <normalized.json> <out-dir>
```

Where a document was created then updated, each operation is a separate
artifact and later ones may hold only a diff (`updates`) rather than the whole
text. Prefer the last artifact with non-empty `content`, and say so if all you
have is a diff.

## Images and files

`file-service://file-...` is an internal reference, not a URL — it cannot be
fetched with `curl` and it is not a path. Downloading it needs an authenticated
call to the file-download endpoint from inside the browser session, which this
plugin does not currently implement. Report images as present-but-not-downloaded
rather than implying the pointer is a usable link.

If the user needs the images, the reliable route today is the official account
export, which bundles them as real files alongside `conversations.json` — see
`import-export-archive`.
