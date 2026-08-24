#!/usr/bin/env python3
"""List or extract conversations from an official ChatGPT data export.

The export arrives as a zip from Settings > Data controls > Export data, with
conversations.json at the root: a flat array of conversation objects in the same
shape as the backend API returns, minus the auth-only fields.

Typical use is two-step. List first, because an export holds every conversation
the account has ever had and you almost never want all of them:

    split_export_archive.py export.zip --list
    split_export_archive.py export.zip --match "onboarding" --out-dir ./raw

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def load(source: Path) -> list[dict]:
    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as z:
            names = [n for n in z.namelist() if n.endswith("conversations.json")]
            if not names:
                raise SystemExit(
                    f"error: no conversations.json inside {source.name}. "
                    f"Contents: {', '.join(z.namelist()[:8])}")
            with z.open(names[0]) as fh:
                data = json.load(fh)
    else:
        data = json.loads(source.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise SystemExit("error: expected a list of conversations")
    return data


def slugify(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return (slug[:60] or fallback)


def summarize(conv: dict, i: int) -> dict:
    mapping = conv.get("mapping") or {}
    roles: dict[str, int] = {}
    for node in mapping.values():
        role = ((node.get("message") or {}).get("author") or {}).get("role")
        if role:
            roles[role] = roles.get(role, 0) + 1
    ts = conv.get("create_time")
    return {
        "index": i,
        "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                if ts else "unknown",
        "title": conv.get("title") or "(untitled)",
        "id": conv.get("conversation_id") or conv.get("id"),
        "nodes": len(mapping),
        "user": roles.get("user", 0),
        "assistant": roles.get("assistant", 0),
        "model": conv.get("default_model_slug"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive", type=Path, help="export .zip or conversations.json")
    ap.add_argument("--list", action="store_true", help="list conversations and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable listing")
    ap.add_argument("--match", help="case-insensitive regex over the title")
    ap.add_argument("--id", help="exact conversation id")
    ap.add_argument("--index", type=int, help="positional index from --list")
    ap.add_argument("--since", help="only conversations created on/after YYYY-MM-DD")
    ap.add_argument("--out-dir", type=Path, help="write each match as its own JSON")
    args = ap.parse_args()

    convs = load(args.archive)
    rows = [summarize(c, i) for i, c in enumerate(convs)]

    keep = list(range(len(convs)))
    if args.match:
        rx = re.compile(args.match, re.I)
        keep = [i for i in keep if rx.search(rows[i]["title"])]
    if args.id:
        keep = [i for i in keep if rows[i]["id"] == args.id]
    if args.index is not None:
        keep = [i for i in keep if i == args.index]
    if args.since:
        keep = [i for i in keep if rows[i]["date"] >= args.since]

    if args.list or not args.out_dir:
        selected = [rows[i] for i in keep]
        if args.json:
            print(json.dumps(selected, indent=2, ensure_ascii=False))
        else:
            print(f"{len(selected)} of {len(convs)} conversation(s)\n")
            for r in selected:
                print(f"[{r['index']:>4}] {r['date']}  {r['user']:>3}u/{r['assistant']:<3}a  "
                      f"{r['title'][:60]}")
            if not args.list:
                print("\nPass --out-dir to extract, or --index/--match to narrow.",
                      file=sys.stderr)
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i in keep:
        conv = convs[i]
        conv.setdefault("conversation_id", rows[i]["id"])
        name = f"{rows[i]['date']}-{slugify(rows[i]['title'], f'conversation-{i}')}.json"
        path = args.out_dir / name
        path.write_text(json.dumps(conv, ensure_ascii=False), encoding="utf-8")
        written.append(str(path))

    print(json.dumps({"written": len(written), "files": written}, indent=2))


if __name__ == "__main__":
    main()
