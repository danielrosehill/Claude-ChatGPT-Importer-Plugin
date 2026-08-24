#!/usr/bin/env python3
"""Render a normalized conversation to Markdown, Typst, or plain text.

Input is the output of normalize_conversation.py. Speaker labels are
configurable because the same transcript gets used two ways: fed to an agent as
context (where "User:" is the clearest possible label) and read by a person
(where their own name reads better).

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime

# --------------------------------------------------------------- sources

def collect_sources(doc: dict) -> list[dict]:
    """Every distinct source the assistant cited, in first-reference order."""
    seen: dict[str, dict] = {}
    for turn in doc["turns"]:
        for c in turn.get("citations") or []:
            url = c.get("url")
            if not url or url in seen:
                continue
            seen[url] = {
                "n": len(seen) + 1,
                "url": url,
                "title": (c.get("title") or url).strip(),
                "first_turn": turn["index"],
            }
    return list(seen.values())


# --------------------------------------------------------------- markdown

def demote_headings(text: str, min_level: int) -> str:
    """Push headings inside a message below the turn heading.

    ChatGPT answers routinely contain their own `##` headings. Emitted as-is
    under a `##` turn heading they become siblings of it, so the document
    outline stops showing where turns begin and any heading-based splitter
    mis-slices the transcript. Fenced code is left alone.
    """
    out, in_fence, fence = [], False, ""
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            out.append(line)
            continue
        if not in_fence:
            m = re.match(r"^(#{1,6})(\s+)(.*)$", line)
            if m:
                level = max(len(m.group(1)) + min_level, min_level)
                out.append("#" * min(level, 6) + m.group(2) + m.group(3))
                continue
        out.append(line)
    return "\n".join(out)


def md_front_matter(doc: dict, user_label: str, assistant_label: str) -> str:
    c, s = doc["conversation"], doc["stats"]
    fm = {
        "title": c.get("title"),
        "source": "ChatGPT",
        "conversation_id": doc["source"].get("conversation_id"),
        "url": doc["source"].get("url"),
        "date_held": c.get("date_held"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "model": c.get("default_model"),
        "models_used": c.get("models_used"),
        "total_turns": s.get("total_turns"),
        "user_messages": s.get("user_messages"),
        "assistant_messages": s.get("assistant_messages"),
        "artifacts": s.get("artifacts"),
        "duration_minutes": s.get("duration_minutes"),
        "captured_at": doc["source"].get("captured_at"),
        "speaker_labels": {"user": user_label, "assistant": assistant_label},
    }
    if doc.get("redaction"):
        fm["redacted"] = True
        fm["redaction_count"] = doc["redaction"].get("count")

    lines = ["---"]
    for k, v in fm.items():
        if v is None or v == []:
            continue
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(json.dumps(x) for x in v)}]")
        elif isinstance(v, dict):
            lines.append(f"{k}:")
            for kk, vv in v.items():
                lines.append(f"  {kk}: {json.dumps(vv)}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {json.dumps(str(v))}")
    lines.append("---")
    return "\n".join(lines)


def md_summary_block(doc: dict) -> str:
    c, s = doc["conversation"], doc["stats"]
    rows = [
        ("Date held", c.get("date_held") or "unknown"),
        ("Model", c.get("default_model") or "unknown"),
        ("Turns", s.get("total_turns")),
        ("User messages", s.get("user_messages")),
        ("Assistant messages", s.get("assistant_messages")),
    ]
    if s.get("duration_minutes") is not None:
        rows.append(("Duration", f"{s['duration_minutes']} min"))
    if s.get("artifacts"):
        rows.append(("Artifacts", s["artifacts"]))
    if s.get("has_alternate_branches"):
        rows.append(("Note", f"{s['branch_points']} edit/regenerate branch point(s) "
                             f"existed; the displayed branch was rendered"))
    body = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return f"| | |\n|---|---|\n{body}"


def render_markdown(doc: dict, *, user_label: str, assistant_label: str,
                    front_matter: bool, summary: bool, sources_mode: str,
                    heading_level: int, timestamps: bool) -> str:
    h = "#" * heading_level
    out: list[str] = []

    if front_matter:
        out.append(md_front_matter(doc, user_label, assistant_label))
        out.append("")

    title = doc["conversation"].get("title") or "ChatGPT conversation"
    out.append(f"{'#' * max(1, heading_level - 1)} {title}")
    out.append("")

    if summary:
        out.append(md_summary_block(doc))
        out.append("")

    sources = collect_sources(doc) if sources_mode != "none" else []
    url_to_n = {s["url"]: s["n"] for s in sources}

    for turn in doc["turns"]:
        label = user_label if turn["role"] == "user" else (
            assistant_label if turn["role"] == "assistant" else turn["role"].title())

        suffix = ""
        if timestamps and turn.get("created_at"):
            suffix = f" — {turn['created_at'][:19].replace('T', ' ')} UTC"
        if turn["role"] == "assistant" and turn.get("model"):
            suffix += f" ({turn['model']})"

        out.append(f"{h} {label}{suffix}")
        out.append("")
        text = demote_headings(turn["text"].strip(), heading_level)

        if sources_mode == "footnotes" and turn.get("citations"):
            marks = "".join(f"[^{url_to_n[c['url']]}]"
                            for c in turn["citations"] if c.get("url") in url_to_n)
            if marks:
                text = f"{text}{marks}"
        out.append(text if text else "_(no text content)_")
        out.append("")

        for art in turn.get("artifacts") or []:
            out.append(format_artifact_md(art))
            out.append("")

    if sources and sources_mode in ("section", "footnotes"):
        out.append(f"{'#' * max(1, heading_level - 1)} Sources")
        out.append("")
        for s in sources:
            if sources_mode == "footnotes":
                out.append(f"[^{s['n']}]: [{s['title']}]({s['url']})")
            else:
                out.append(f"{s['n']}. [{s['title']}]({s['url']}) "
                           f"— first cited in turn {s['first_turn']}")
        out.append("")

    if doc.get("unhandled"):
        out.append("<!-- importer note: "
                   f"{len(doc['unhandled'])} content block(s) of an unrecognised type "
                   "were encountered; see .unhandled in the normalized JSON -->")

    return "\n".join(out).rstrip() + "\n"


def format_artifact_md(art: dict) -> str:
    kind = art.get("kind")
    if kind == "canvas_document":
        name = art.get("name") or "untitled"
        body = art.get("content")
        head = f"> **📄 Canvas document ({art.get('operation')}): {name}**"
        if body:
            return f"{head}\n\n<details>\n<summary>{name}</summary>\n\n{body}\n\n</details>"
        return head
    if kind in ("generated_image", "image"):
        # Only emit real image syntax once the asset has been fetched to disk.
        if art.get("local_path"):
            return f"![{art.get('name') or 'image'}]({art['local_path']})"
        return f"> **🖼 Image artifact** — `{art.get('pointer')}` " \
               f"({art.get('width')}×{art.get('height')}) " \
               f"— not downloaded; see download-assets"
    if kind == "generated_file":
        return f"> **📎 Generated file** — {art.get('name')} (`{art.get('pointer')}`)"
    if kind == "attachment":
        return f"> **📎 Attachment** — {art.get('name')} " \
               f"({art.get('mime_type')}, {art.get('size_bytes')} bytes)"
    if kind == "code_block":
        return f"> _(code block above: {art.get('language') or 'plain'}, " \
               f"{art.get('lines')} lines)_"
    return f"> **Artifact** — {json.dumps(art)}"


# ------------------------------------------------------------------ typst

def typst_escape(s: str) -> str:
    for ch in ("\\", "$", "#", "@", "<", ">", "*", "_", "`"):
        s = s.replace(ch, "\\" + ch)
    return s


def render_typst(doc: dict, *, user_label: str, assistant_label: str,
                 sources_mode: str, timestamps: bool, template: str) -> str:
    c, s = doc["conversation"], doc["stats"]
    sources = collect_sources(doc) if sources_mode != "none" else []

    def meta(k, v):
        return f'  {k}: {json.dumps(str(v))},' if v is not None else ""

    head = [
        f'#import "{template}": conversation',
        "",
        "#show: conversation.with(",
        meta("title", c.get("title") or "ChatGPT conversation"),
        meta("date_held", c.get("date_held") or ""),
        meta("model", c.get("default_model") or ""),
        meta("user_label", user_label),
        meta("assistant_label", assistant_label),
        meta("turns", s.get("total_turns")),
        meta("user_messages", s.get("user_messages")),
        meta("assistant_messages", s.get("assistant_messages")),
        meta("source_url", doc["source"].get("url") or ""),
        meta("captured_at", (doc["source"].get("captured_at") or "")[:10]),
        f'  redacted: {"true" if doc.get("redaction") else "false"},',
        ")",
        "",
    ]
    body = [l for l in head if l != ""]

    for turn in doc["turns"]:
        who = "user" if turn["role"] == "user" else "assistant"
        stamp = (turn.get("created_at") or "")[:19].replace("T", " ") if timestamps else ""
        body.append(f'#turn(kind: "{who}", stamp: {json.dumps(stamp)})[')
        body.append(typst_escape(turn["text"].strip()) or "_(no text content)_")
        for art in turn.get("artifacts") or []:
            body.append("")
            body.append(f'#artifact(kind: "{art.get("kind")}", '
                        f'name: {json.dumps(str(art.get("name") or art.get("pointer") or ""))})')
        body.append("]")
        body.append("")

    if sources:
        body.append("#sources((")
        for src in sources:
            body.append(f'  (n: {src["n"]}, title: {json.dumps(src["title"])}, '
                        f'url: {json.dumps(src["url"])}),')
        body.append("))")

    return "\n".join(body) + "\n"


# ------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="normalized conversation JSON ('-' for stdin)")
    ap.add_argument("--out", "-o", help="output file (default: stdout)")
    ap.add_argument("--format", "-f", default="markdown",
                    choices=["markdown", "typst", "text"])
    ap.add_argument("--user-label", default="User",
                    help='how to name the human speaker (e.g. "User", "Daniel")')
    ap.add_argument("--assistant-label", default="ChatGPT")
    ap.add_argument("--sources", dest="sources_mode", default="section",
                    choices=["section", "footnotes", "none"],
                    help="how to present cited sources (default: section at end)")
    ap.add_argument("--no-front-matter", action="store_true")
    ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--timestamps", action="store_true",
                    help="show a per-turn timestamp")
    ap.add_argument("--heading-level", type=int, default=2,
                    help="markdown heading level for each turn (default 2)")
    ap.add_argument("--typst-template", default="template.typ")
    args = ap.parse_args()

    text = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    doc = json.loads(text)
    if doc.get("schema_version") != "1":
        print(f"warning: unexpected schema_version {doc.get('schema_version')!r}",
              file=sys.stderr)

    if args.format == "typst":
        out = render_typst(doc, user_label=args.user_label,
                           assistant_label=args.assistant_label,
                           sources_mode=args.sources_mode,
                           timestamps=args.timestamps,
                           template=args.typst_template)
    else:
        out = render_markdown(doc, user_label=args.user_label,
                              assistant_label=args.assistant_label,
                              front_matter=not args.no_front_matter,
                              summary=not args.no_summary,
                              sources_mode=args.sources_mode,
                              heading_level=args.heading_level,
                              timestamps=args.timestamps)
        if args.format == "text":
            out = re.sub(r"^---\n.*?\n---\n", "", out, flags=re.S)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"{args.out}: {len(out)} bytes, "
              f"{doc['stats']['total_turns']} turns", file=sys.stderr)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
