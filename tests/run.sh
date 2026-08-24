#!/usr/bin/env bash
# End-to-end pipeline test against the synthetic fixture.
# The fixture deliberately contains an abandoned branch, a hidden system
# message, a canvas artifact, an image pointer, a citation and an unknown
# content type — the cases that have actually broken this pipeline.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PASS=0; FAIL=0
ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }

echo "normalize"
python3 "$ROOT/scripts/normalize_conversation.py" \
  "$ROOT/fixtures/sample-conversation.json" -o "$WORK/n.json" 2>/dev/null

q(){ python3 -c "import json,sys;d=json.load(open('$WORK/n.json'));print($1)"; }

check "turn count"            "$(q "d['stats']['total_turns']")"        "7"
check "user messages"         "$(q "d['stats']['user_messages']")"      "3"
check "assistant messages"    "$(q "d['stats']['assistant_messages']")" "4"
check "abandoned branch cut"  "$(q "any('ABANDONED' in t['text'] for t in d['turns'])")" "False"
check "hidden msg skipped"    "$(q "d['stats']['skipped']['hidden']")"  "1"
check "branch point counted"  "$(q "d['stats']['branch_points']")"      "1"
check "citation captured"     "$(q "d['stats']['citations']")"          "1"
check "unknown type flagged"  "$(q "len(d['unhandled'])")"              "1"
check "canvas detected"       "$(q "sum(1 for a in d['artifacts'] if a['kind']=='canvas_document')")" "1"
check "image detected"        "$(q "sum(1 for a in d['artifacts'] if a['kind']=='image')")" "1"
check "no raw asset img tag"  "$(q "any('](file-service' in t['text'] for t in d['turns'])")" "False"
check "date held"             "$(q "d['conversation']['date_held']")"   "2025-06-15"

echo "markdown"
python3 "$ROOT/scripts/render_conversation.py" "$WORK/n.json" \
  --user-label "User" -o "$WORK/out.md" 2>/dev/null
check "turn headings == turns" "$(grep -c '^## ' "$WORK/out.md")" "7"
grep -q '^title:' "$WORK/out.md" && ok "front matter" || bad "front matter"
grep -q '^# Sources' "$WORK/out.md" && ok "sources section" || bad "sources section"
grep -q 'user_messages: 3' "$WORK/out.md" && ok "stats in front matter" || bad "stats in front matter"

echo "redaction"
python3 - "$WORK" <<'PY'
import json,sys
w=sys.argv[1]
d={"schema_version":"1","source":{},"conversation":{},"stats":{},"artifacts":[],"unhandled":[],
   "turns":[{"index":1,"role":"user","citations":[],"artifacts":[],
     "text":"Email me@example.com, call +972 54-123-4567, card 4111 1111 1111 1111, "
            "key sk-abcdefghijklmnop1234, box 10.0.0.2. Version 1.2.3 and year 2024 stay."},
    {"index":2,"role":"assistant","citations":[],"artifacts":[],"text":"me@example.com"}]}
json.dump(d,open(f"{w}/r_in.json","w"))
PY
python3 "$ROOT/scripts/redact_conversation.py" "$WORK/r_in.json" -o "$WORK/r_out.json" 2>/dev/null
r(){ python3 -c "import json;d=json.load(open('$WORK/r_out.json'));print($1)"; }
check "redaction count"      "$(r "d['redaction']['count']")" "5"
check "phone kept whole"     "$(r "'4567' in d['turns'][0]['text']")" "False"
check "card redacted"        "$(r "'CARD_1' in d['turns'][0]['text']")" "True"
check "version survives"     "$(r "'1.2.3' in d['turns'][0]['text']")" "True"
check "assistant untouched"  "$(r "'me@example.com' in d['turns'][1]['text']")" "True"

echo "export archive"
python3 -c "
import json;c=json.load(open('$ROOT/fixtures/sample-conversation.json'))
json.dump([c],open('$WORK/exp.json','w'))"
check "archive lists 1" \
  "$(python3 "$ROOT/scripts/split_export_archive.py" "$WORK/exp.json" --list --json | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')" "1"

echo "pdf"
if command -v pandoc >/dev/null && command -v typst >/dev/null; then
  if python3 "$ROOT/scripts/render_pdf.py" "$WORK/n.json" -o "$WORK/out.pdf" \
       --user-label "User" 2>/dev/null && [ -s "$WORK/out.pdf" ]; then
    ok "pdf compiles"
  else
    bad "pdf compiles"
  fi
else
  echo "  skip  pdf (pandoc/typst not installed)"
fi

echo
printf '%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
