# /// script
# requires-python = ">=3.11"
# dependencies = ["pyarrow>=15", "huggingface_hub>=0.24"]
# ///
"""Batch export (capture-all-via-api.js JSONL) -> one Parquet table, one row per conversation; optional private HF push.

    uv run --script build_dataset.py chatgpt-export-<run>-*.jsonl --out chats.parquet [--tz Asia/Jerusalem] \
        [--merge previous.parquet] [--keep-raw] [--push user/dataset-name]

Columns: conversation_id, title, date (local YYYY-MM-DD of create_time), create_time, update_time, last_message_at,
account_id, source (list | archived | project:<gizmo id>), project_id, default_model, models_used, turns,
user_messages, assistant_messages, user_chars, assistant_chars, has_branches, markdown (rendered thread, no front
matter), normalized (normalize_conversation.py JSON as a string), exported_at, [raw].

--merge keeps rows from an earlier table that this run did not re-export, and replaces those it did (incremental
runs with OPTS.updatedAfter). --push uploads data/chats.parquet to a PRIVATE dataset repo (created if missing;
an existing public repo is refused). The manifest file (…-000.jsonl) is read for failures and reported, not stored.
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from normalize_conversation import normalize  # noqa: E402
from render_conversation import render_markdown  # noqa: E402


def local_date(ts, tz):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        d = datetime.fromtimestamp(ts, timezone.utc)
    else:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return d.astimezone(tz).date().isoformat()


def iso(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, timezone.utc).isoformat()
    return str(ts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tz", default="UTC")
    ap.add_argument("--merge")
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--push")
    a = ap.parse_args()
    import pyarrow as pa, pyarrow.parquet as pq

    tz = ZoneInfo(a.tz)
    exported_at = datetime.now(timezone.utc).isoformat()
    rows, failed, errors, seen = [], [], [], set()
    for path in a.inputs:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                raw = json.loads(line)
                if raw.get("manifest"):
                    failed += raw.get("failed", [])
                    continue
                cid = raw.get("conversation_id") or raw.get("id")
                if cid in seen:
                    continue
                seen.add(cid)
                try:
                    doc = normalize(raw, "backend_api", f"https://chatgpt.com/c/{cid}", False, False)
                    md = render_markdown(doc, user_label="User", assistant_label="ChatGPT", front_matter=False,
                                         summary=False, sources_mode="section", heading_level=2, timestamps=True)
                except (Exception, SystemExit) as e:  # keep going; report at the end
                    errors.append({"id": cid, "error": str(e)[:200]})
                    continue
                c, s = doc["conversation"], doc["stats"]
                src = raw.get("_source") or "list"
                row = {
                    "conversation_id": cid, "title": c.get("title"),
                    "date": local_date(raw.get("create_time"), tz),
                    "create_time": iso(raw.get("create_time")), "update_time": iso(raw.get("update_time")),
                    "last_message_at": s.get("last_message_at"),
                    "account_id": raw.get("_account_id"), "source": src,
                    "project_id": src.split(":", 1)[1] if src.startswith("project:") else raw.get("gizmo_id"),
                    "default_model": c.get("default_model"), "models_used": json.dumps(c.get("models_used") or []),
                    "turns": s.get("total_turns"), "user_messages": s.get("user_messages"),
                    "assistant_messages": s.get("assistant_messages"), "user_chars": s.get("user_chars"),
                    "assistant_chars": s.get("assistant_chars"), "has_branches": bool(s.get("has_alternate_branches")),
                    "markdown": md, "normalized": json.dumps(doc, ensure_ascii=False), "exported_at": exported_at,
                }
                if a.keep_raw:
                    row["raw"] = line.strip()
                rows.append(row)

    if a.merge and os.path.exists(a.merge):
        old = pq.read_table(a.merge).to_pylist()
        kept = [r for r in old if r["conversation_id"] not in seen]
        rows = kept + rows
        print(f"merge: kept {len(kept)} rows from {a.merge}", file=sys.stderr)
    rows.sort(key=lambda r: (r["create_time"] or ""), reverse=True)
    pq.write_table(pa.Table.from_pylist(rows), a.out, compression="zstd")
    dates = sorted(r["date"] for r in rows if r["date"])
    report = {"out": a.out, "rows": len(rows), "normalize_errors": len(errors), "export_failures": len(failed),
              "date_range": [dates[0], dates[-1]] if dates else None,
              "by_source": {k: sum(1 for r in rows if r["source"].split(":")[0] == k) for k in ("list", "archived", "project")}}
    print(json.dumps(report, indent=1))
    if errors:
        json.dump(errors, open(a.out + ".errors.json", "w"), indent=1)
    if a.push:
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ.get("HF_TOKEN"))
        try:
            info = api.dataset_info(a.push)
            if not info.private:
                sys.exit(f"refusing to push: {a.push} exists and is public")
        except Exception as e:
            if "404" not in str(e) and "not found" not in str(e).lower():
                raise
            api.create_repo(a.push, repo_type="dataset", private=True)
        api.upload_file(path_or_fileobj=a.out, path_in_repo="data/chats.parquet", repo_id=a.push, repo_type="dataset",
                        commit_message=f"{len(rows)} conversations, exported {exported_at[:10]}")
        print(f"pushed to https://huggingface.co/datasets/{a.push} (private)", file=sys.stderr)


if __name__ == "__main__":
    main()
