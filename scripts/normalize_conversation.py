#!/usr/bin/env python3
"""Normalize a raw ChatGPT conversation into a stable, renderer-friendly shape.

Input  : the JSON returned by /backend-api/conversation/<id>, a /share/ payload,
         or one element of conversations.json from an official account export.
Output : normalized JSON (schema_version 1) on stdout or at --out.

The raw format is a DAG, not a list. `mapping` holds every node ever created,
including abandoned edit branches and regenerated answers. Iterating over
mapping.values() therefore yields messages that were never part of the thread
the user actually saw. This walks parent links back from a leaf instead.

Stdlib only, by design: the importer must run without a venv.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1"

# Roles that carry conversation content the reader wants to see by default.
VISIBLE_ROLES = {"user", "assistant"}


# ---------------------------------------------------------------- utilities

def iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def first_of(d: dict, *keys, default=None):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return default


# ------------------------------------------------------------ branch walking

def resolve_leaf(mapping: dict, current_node: str | None) -> str | None:
    """Pick the leaf whose branch we render.

    Prefers the conversation's own current_node (what the UI last displayed).
    Falls back to the leaf with the newest message, which is what an export
    archive needs when current_node is absent or dangling.
    """
    if current_node and current_node in mapping:
        return current_node

    best, best_t = None, -1.0
    for nid, node in mapping.items():
        if node.get("children"):
            continue
        msg = node.get("message") or {}
        t = msg.get("create_time") or 0
        if t > best_t:
            best, best_t = nid, t
    return best


def walk_branch(mapping: dict, leaf: str | None) -> list[str]:
    """Return node ids from root to leaf, following parent links."""
    path: list[str] = []
    seen: set[str] = set()
    node_id = leaf
    while node_id and node_id in mapping:
        if node_id in seen:  # defensive: malformed export with a parent cycle
            break
        seen.add(node_id)
        path.append(node_id)
        node_id = mapping[node_id].get("parent")
    path.reverse()
    return path


def count_branch_points(mapping: dict) -> int:
    return sum(1 for n in mapping.values() if len(n.get("children") or []) > 1)


# --------------------------------------------------------- content rendering

def render_content(content: dict, unhandled: list) -> tuple[str, list[dict]]:
    """Flatten a message's content block to text plus structured extras.

    Returns (text, inline_assets). Unknown content types are recorded in
    `unhandled` rather than silently dropped, so a format change surfaces as a
    visible gap instead of a shorter transcript nobody notices.
    """
    ctype = content.get("content_type")
    assets: list[dict] = []

    if ctype == "text":
        return "\n".join(p for p in content.get("parts") or [] if isinstance(p, str)), assets

    if ctype == "multimodal_text":
        chunks: list[str] = []
        for part in content.get("parts") or []:
            if isinstance(part, str):
                chunks.append(part)
            elif isinstance(part, dict):
                ptype = part.get("content_type")
                if ptype == "image_asset_pointer":
                    assets.append({
                        "kind": "image",
                        "pointer": part.get("asset_pointer"),
                        "width": part.get("width"),
                        "height": part.get("height"),
                        "size_bytes": part.get("size_bytes"),
                    })
                    # Deliberately NOT markdown image syntax: an asset pointer
                    # is a ChatGPT-internal reference, not a path. Emitting
                    # ![](file-service://...) makes pandoc/Typst try to open it
                    # as a file and abort the render. The pointer is preserved
                    # in the artifact record; download_assets.py can resolve it.
                    ref = (part.get("asset_pointer") or "").rsplit("/", 1)[-1]
                    chunks.append(f"[image: {ref}]")
                elif ptype == "audio_transcription":
                    chunks.append(part.get("text", ""))
                elif ptype in ("audio_asset_pointer",
                               "real_time_user_audio_video_asset_pointer"):
                    assets.append({"kind": "audio", "pointer": part.get("asset_pointer")})
                else:
                    unhandled.append({"where": "multimodal_part", "content_type": ptype,
                                      "keys": sorted(part.keys())})
        return "\n".join(c for c in chunks if c), assets

    if ctype == "code":
        lang = content.get("language") or ""
        return f"```{lang}\n{content.get('text', '')}\n```", assets

    if ctype == "execution_output":
        return f"```\n{content.get('text', '')}\n```", assets

    if ctype == "thoughts":
        out = []
        for t in content.get("thoughts") or []:
            summary = t.get("summary") or ""
            body = t.get("content") or ""
            out.append(f"**{summary}**\n\n{body}" if summary else body)
        return "\n\n".join(out), assets

    if ctype == "reasoning_recap":
        return content.get("content", ""), assets

    if ctype == "tether_browsing_display":
        return first_of(content, "result", "summary", default=""), assets

    if ctype == "tether_quote":
        return (f"> [{content.get('title', '')}]({content.get('url', '')})\n"
                f"> {content.get('text', '')}"), assets

    if ctype == "sonic_webpage":
        return (f"[{content.get('title', '')}]({content.get('url', '')})\n"
                f"{first_of(content, 'text', 'snippet', default='')}"), assets

    if ctype == "system_error":
        return f"[system error: {content.get('name', '')}] {content.get('text', '')}", assets

    if ctype == "user_editable_context":
        parts = []
        if content.get("user_profile"):
            parts.append(f"About the user:\n{content['user_profile']}")
        if content.get("user_instructions"):
            parts.append(f"Custom instructions:\n{content['user_instructions']}")
        return "\n\n".join(parts), assets

    # Unknown shape. Salvage anything text-like, but flag it loudly.
    unhandled.append({"where": "content", "content_type": ctype,
                      "keys": sorted(content.keys())})
    salvage = content.get("text")
    if not salvage and isinstance(content.get("parts"), list):
        salvage = "\n".join(p for p in content["parts"] if isinstance(p, str))
    return salvage or "", assets


# ------------------------------------------------------------- artifacts

CANVAS_RECIPIENTS = ("canmore.create_textdoc", "canmore.update_textdoc")


def extract_artifacts(msg: dict, text: str, assets: list[dict]) -> list[dict]:
    """Identify generated documents, images and files attached to one message."""
    found: list[dict] = []
    author = msg.get("author") or {}
    recipient = msg.get("recipient") or ""
    name = author.get("name") or ""
    meta = msg.get("metadata") or {}

    # Canvas / textdoc. The tool call payload is JSON inside a code block.
    if recipient in CANVAS_RECIPIENTS or name in CANVAS_RECIPIENTS:
        payload = None
        body = (msg.get("content") or {}).get("text") or ""
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            m = re.search(r"\{.*\}", body, re.S)
            if m:
                try:
                    payload = json.loads(m.group(0))
                except ValueError:
                    payload = None
        if isinstance(payload, dict):
            found.append({
                "kind": "canvas_document",
                "operation": "update" if "update" in (recipient or name) else "create",
                "name": payload.get("name"),
                "doc_type": payload.get("type"),
                "content": payload.get("content"),
                "updates": payload.get("updates"),
            })
        else:
            found.append({"kind": "canvas_document", "operation": "unparsed",
                          "raw": body[:2000]})

    # Generated images (DALL-E / gpt-image) arrive as asset pointers.
    for asset in assets:
        if asset.get("kind") == "image":
            found.append({
                "kind": "generated_image" if name.startswith("dalle") else "image",
                "pointer": asset.get("pointer"),
                "width": asset.get("width"),
                "height": asset.get("height"),
            })

    # Code interpreter output files.
    agg = meta.get("aggregate_result") or {}
    for f in agg.get("jupyter_messages", []) if isinstance(agg, dict) else []:
        pass  # jupyter_messages carry display data, not files; ignored on purpose
    for f in (agg.get("files") or []) if isinstance(agg, dict) else []:
        found.append({"kind": "generated_file", "name": f.get("name"),
                      "pointer": f.get("id") or f.get("file_id")})

    # Files the user uploaded.
    for att in meta.get("attachments") or []:
        found.append({"kind": "attachment", "name": att.get("name"),
                      "pointer": att.get("id"), "mime_type": att.get("mime_type"),
                      "size_bytes": att.get("size")})

    # A fenced code block written straight into a normal answer.
    if not found and msg.get("author", {}).get("role") == "assistant":
        for m in re.finditer(r"```(\w+)?\n(.*?)```", text, re.S):
            body = m.group(2)
            if body.count("\n") >= 4:  # skip one-liners and inline snippets
                found.append({"kind": "code_block", "language": m.group(1),
                              "lines": body.count("\n") + 1})

    return found


def extract_citations(msg: dict) -> list[dict]:
    out = []
    meta = msg.get("metadata") or {}
    for c in meta.get("citations") or []:
        md = (c.get("metadata") or {})
        out.append({"title": md.get("title"), "url": md.get("url"),
                    "text": md.get("text")})
    for group in meta.get("search_result_groups") or []:
        for entry in group.get("entries") or []:
            out.append({"title": entry.get("title"), "url": entry.get("url"),
                        "text": entry.get("snippet")})
    # De-duplicate on URL, preserving order.
    seen, uniq = set(), []
    for c in out:
        if c["url"] and c["url"] not in seen:
            seen.add(c["url"])
            uniq.append(c)
    return uniq


# ------------------------------------------------------------- main pipeline

def normalize(raw: dict, source_kind: str, source_url: str | None,
              include_hidden: bool, include_tools: bool) -> dict:
    mapping = raw.get("mapping") or {}
    if not mapping:
        raise SystemExit("error: no 'mapping' in input — is this a ChatGPT conversation payload?")

    leaf = resolve_leaf(mapping, raw.get("current_node"))
    path = walk_branch(mapping, leaf)

    unhandled: list[dict] = []
    turns: list[dict] = []
    artifacts: list[dict] = []
    models: set[str] = set()
    skipped = {"hidden": 0, "tool": 0, "empty": 0, "system": 0}

    for node_id in path:
        msg = (mapping[node_id] or {}).get("message")
        if not msg:
            continue  # the synthetic root node has no message

        author = msg.get("author") or {}
        role = author.get("role")
        meta = msg.get("metadata") or {}
        hidden = bool(meta.get("is_visually_hidden_from_conversation"))
        content = msg.get("content") or {}

        text, assets = render_content(content, unhandled)
        msg_artifacts = extract_artifacts(msg, text, assets)

        if hidden and not include_hidden:
            skipped["hidden"] += 1
            continue
        if role == "system" and not include_hidden:
            skipped["system"] += 1
            continue
        if role in ("tool", "system") and not include_tools and not msg_artifacts:
            skipped["tool"] += 1
            continue
        if not text.strip() and not msg_artifacts:
            skipped["empty"] += 1
            continue

        model = meta.get("model_slug") or meta.get("default_model_slug")
        if model and role == "assistant":
            models.add(model)

        turn = {
            "index": len(turns) + 1,
            "role": role,
            "author_name": author.get("name"),
            "message_id": msg.get("id") or node_id,
            "created_at": iso(msg.get("create_time")),
            "model": model if role == "assistant" else None,
            "channel": msg.get("channel"),
            "recipient": msg.get("recipient"),
            "content_type": content.get("content_type"),
            "hidden": hidden,
            "excluded_from_context": msg.get("weight") == 0,
            "text": text,
            "artifacts": msg_artifacts,
            "citations": extract_citations(msg),
        }
        turns.append(turn)
        for a in msg_artifacts:
            artifacts.append({**a, "turn_index": turn["index"],
                              "message_id": turn["message_id"]})

    times = [t["created_at"] for t in turns if t["created_at"]]
    first_at, last_at = (times[0], times[-1]) if times else (None, None)
    duration_min = None
    if first_at and last_at:
        delta = datetime.fromisoformat(last_at) - datetime.fromisoformat(first_at)
        duration_min = round(delta.total_seconds() / 60, 1)

    n_user = sum(1 for t in turns if t["role"] == "user")
    n_asst = sum(1 for t in turns if t["role"] == "assistant")

    created = iso(raw.get("create_time"))
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "kind": source_kind,
            "conversation_id": raw.get("conversation_id"),
            "url": source_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        "conversation": {
            "title": raw.get("title"),
            "created_at": created,
            "updated_at": iso(raw.get("update_time")),
            "date_held": (created or "")[:10] or None,
            "default_model": raw.get("default_model_slug"),
            "models_used": sorted(models),
            "is_archived": raw.get("is_archived"),
            "is_starred": raw.get("is_starred"),
            "gizmo_id": raw.get("gizmo_id"),
        },
        "stats": {
            "total_turns": len(turns),
            "user_messages": n_user,
            "assistant_messages": n_asst,
            "other_messages": len(turns) - n_user - n_asst,
            "user_chars": sum(len(t["text"]) for t in turns if t["role"] == "user"),
            "assistant_chars": sum(len(t["text"]) for t in turns if t["role"] == "assistant"),
            "artifacts": len(artifacts),
            "citations": sum(len(t["citations"]) for t in turns),
            "first_message_at": first_at,
            "last_message_at": last_at,
            "duration_minutes": duration_min,
            "nodes_in_mapping": len(mapping),
            "nodes_on_rendered_branch": len(path),
            "branch_points": count_branch_points(mapping),
            "has_alternate_branches": count_branch_points(mapping) > 0,
            "skipped": skipped,
        },
        "turns": turns,
        "artifacts": artifacts,
        "unhandled": unhandled,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="raw conversation JSON (or '-' for stdin)")
    ap.add_argument("--out", "-o", help="write normalized JSON here (default: stdout)")
    ap.add_argument("--url", help="source URL, recorded in the output")
    ap.add_argument("--source-kind", default="backend_api",
                    choices=["backend_api", "shared_link", "export_archive", "dom_scrape"])
    ap.add_argument("--include-hidden", action="store_true",
                    help="keep system prompts, memory injections and hidden messages")
    ap.add_argument("--include-tools", action="store_true",
                    help="keep tool call/result messages that carry no artifact")
    ap.add_argument("--index", type=int,
                    help="when input is an export array, which conversation to take")
    args = ap.parse_args()

    text = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    raw = json.loads(text)

    if isinstance(raw, list):
        if args.index is None:
            raise SystemExit(f"error: input holds {len(raw)} conversations; "
                             f"pass --index N (see split_export_archive.py to list them)")
        raw = raw[args.index]

    result = normalize(raw, args.source_kind, args.url,
                       args.include_hidden, args.include_tools)

    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        s = result["stats"]
        print(f"{args.out}: {s['total_turns']} turns "
              f"({s['user_messages']} user / {s['assistant_messages']} assistant), "
              f"{s['artifacts']} artifacts", file=sys.stderr)
        if result["unhandled"]:
            print(f"warning: {len(result['unhandled'])} unhandled content blocks "
                  f"— see .unhandled in the output", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
