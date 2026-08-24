#!/usr/bin/env python3
"""Render a normalized conversation to PDF via Typst.

Each turn's Markdown body is converted to Typst by pandoc, then wrapped in a
#turn(...) call from templates/transcript.typ. Turns are split by this script
rather than recovered from the output with a show-rule, so styling never
depends on parsing heading text back out of rendered content.

All bodies go through pandoc in ONE call, separated by a sentinel, because
34 separate pandoc invocations cost about 20x a single one. The split is
asserted against the turn count, so a sentinel that failed to survive the
round trip fails loudly instead of silently merging two people's words.

Requires: pandoc (>= 3.0, for the typst writer) and typst on PATH.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_conversation import collect_sources, demote_headings  # noqa: E402

SENTINEL = "zzTURNBREAKzz9f3a"


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise SystemExit(
            f"error: {tool} not found on PATH.\n"
            f"  pandoc: apt install pandoc  (needs >= 3.0 for the typst writer)\n"
            f"  typst:  https://github.com/typst/typst/releases")
    return path


def md_to_typst_batch(bodies: list[str]) -> list[str]:
    """Convert many Markdown bodies to Typst in a single pandoc call."""
    need("pandoc")
    joined = f"\n\n{SENTINEL}\n\n".join(b if b.strip() else "_(no text content)_"
                                        for b in bodies)
    proc = subprocess.run(
        ["pandoc", "--from", "markdown-raw_html", "--to", "typst", "--wrap=preserve"],
        input=joined, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"error: pandoc failed:\n{proc.stderr}")

    parts = [p.strip() for p in proc.stdout.split(SENTINEL)]
    if len(parts) != len(bodies):
        raise SystemExit(
            f"error: turn separator did not survive conversion "
            f"({len(parts)} fragments for {len(bodies)} turns). "
            f"Refusing to emit a transcript with misattributed turns.")
    return parts


def typst_str(value) -> str:
    return json.dumps("" if value is None else str(value))


def build_typst(doc: dict, *, user_label: str, assistant_label: str,
                sources_mode: str, timestamps: bool, template: str,
                paper: str) -> str:
    turns = doc["turns"]
    bodies = md_to_typst_batch(
        [demote_headings(t["text"].strip(), 2) for t in turns])

    c, s = doc["conversation"], doc["stats"]
    out: list[str] = [
        f'#import {typst_str(template)}: *',
        "",
        "#show: conversation.with(",
        f'  title: {typst_str(c.get("title") or "ChatGPT conversation")},',
        f'  date_held: {typst_str(c.get("date_held"))},',
        f'  model: {typst_str(c.get("default_model"))},',
        f'  user_label: {typst_str(user_label)},',
        f'  assistant_label: {typst_str(assistant_label)},',
        f'  turns: {s.get("total_turns", 0)},',
        f'  user_messages: {s.get("user_messages", 0)},',
        f'  assistant_messages: {s.get("assistant_messages", 0)},',
        f'  source_url: {typst_str(doc["source"].get("url"))},',
        f'  captured_at: {typst_str((doc["source"].get("captured_at") or "")[:10])},',
        f'  redacted: {"true" if doc.get("redaction") else "false"},',
        f'  paper: {typst_str(paper)},',
        ")",
        "",
    ]

    for turn, body in zip(turns, bodies):
        if turn["role"] == "user":
            kind, label = "user", user_label
        elif turn["role"] == "assistant":
            kind, label = "assistant", assistant_label
        else:
            kind, label = "other", (turn.get("author_name") or turn["role"].title())

        stamp = ""
        if timestamps and turn.get("created_at"):
            stamp = turn["created_at"][:16].replace("T", " ")

        out.append(f'#turn(kind: {typst_str(kind)}, label: {typst_str(label)}, '
                   f'stamp: {typst_str(stamp)})[')
        out.append(body)
        for art in turn.get("artifacts") or []:
            name = art.get("name") or art.get("pointer") or ""
            out.append(f'#artifact(kind: {typst_str(art.get("kind"))}, '
                       f'name: {typst_str(name)})')
        out.append("]")
        out.append("")

    if sources_mode != "none":
        srcs = collect_sources(doc)
        if srcs:
            out.append("#sources((")
            for src in srcs:
                out.append(f'  (n: {src["n"]}, title: {typst_str(src["title"])}, '
                           f'url: {typst_str(src["url"])}),')
            out.append("))")

    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="normalized conversation JSON")
    ap.add_argument("--out", "-o", required=True, help="output PDF path")
    ap.add_argument("--user-label", default="User")
    ap.add_argument("--assistant-label", default="ChatGPT")
    ap.add_argument("--sources", dest="sources_mode", default="section",
                    choices=["section", "none"])
    ap.add_argument("--timestamps", action="store_true")
    ap.add_argument("--paper", default="a4")
    ap.add_argument("--template", help="path to transcript.typ "
                                       "(default: ../templates/transcript.typ)")
    ap.add_argument("--keep-typst", help="also write the intermediate .typ here")
    args = ap.parse_args()

    need("typst")
    doc = json.loads(Path(args.input).read_text(encoding="utf-8"))

    template = Path(args.template) if args.template else \
        Path(__file__).parent.parent / "templates" / "transcript.typ"
    template = template.resolve()
    if not template.exists():
        raise SystemExit(f"error: template not found: {template}")

    src = build_typst(doc, user_label=args.user_label,
                      assistant_label=args.assistant_label,
                      sources_mode=args.sources_mode,
                      timestamps=args.timestamps,
                      template=template.name,
                      paper=args.paper)

    out_pdf = Path(args.out).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    # Compile beside the template so the #import resolves by plain filename.
    work = template.parent / f".build-{out_pdf.stem}.typ"
    work.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run(["typst", "compile", str(work), str(out_pdf)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            if args.keep_typst:
                Path(args.keep_typst).write_text(src, encoding="utf-8")
            raise SystemExit(f"error: typst compile failed:\n{proc.stderr}")
    finally:
        if args.keep_typst:
            Path(args.keep_typst).write_text(src, encoding="utf-8")
        work.unlink(missing_ok=True)

    size = out_pdf.stat().st_size
    print(f"{out_pdf}: {size:,} bytes, {doc['stats']['total_turns']} turns",
          file=sys.stderr)


if __name__ == "__main__":
    main()
