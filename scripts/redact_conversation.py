#!/usr/bin/env python3
"""Redact identifying detail from a normalized conversation.

Two passes are needed and only the first is here. This script does the
deterministic one: patterns that are decidable by regex and therefore should
never be left to a model's judgement. The second pass — names, employers,
places, anything recognisable only in context — is judgement work and is
driven by the redact-conversation skill, which edits the JSON afterwards.

By default only user turns are touched, on the theory that what leaks is what
the human typed. Pass --scope all to redact assistant turns too, which matters
when the assistant quoted the user back.

Consistent placeholders (EMAIL_1, EMAIL_2 …) are used rather than a flat
[REDACTED], so a transcript that refers to the same address twice still reads
as referring to one address.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict

# Ordered: earlier patterns win a contested span, so put the specific first.
PATTERNS: "OrderedDict[str, re.Pattern]" = OrderedDict([
    # Secrets first — an API key can look like a lot of other things.
    ("APIKEY", re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}"
        r"|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}"
        r"|AIza[0-9A-Za-z_-]{30,})\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    # Anchored to real card groupings rather than "13-19 digits with any
    # separators": the loose form matches greedily across a phone number that
    # happens to precede a card, consumes both, fails the Luhn check, and takes
    # the real card down with it — finditer resumes past the whole bad span.
    ("CARD", re.compile(
        r"\b(?:\d{4}[ -]){3}\d{4}\b"       # 4-4-4-4
        r"|\b\d{4}[ -]\d{6}[ -]\d{5}\b"    # Amex 4-6-5
        r"|\b\d{13,19}\b")),                # unseparated
    ("ISRAELI_ID", re.compile(r"\b\d{9}\b")),                   # check-digit verified
    # IPv4 before PHONE: a dotted quad also fits the phone shape, and whichever
    # pattern is listed first claims the span.
    ("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    # The boundary guards reject a digit-bearing decimal on either side, so
    # version strings and dotted quads are skipped, while a phone number ending
    # a sentence still matches to its last digit.
    ("PHONE", re.compile(
        r"(?<!\w)(?<!\d\.)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?"
        r"\d{2,4}(?:[\s.-]\d{2,4}){1,3}(?!\w)(?!\.\d)")),
    ("URLTOKEN", re.compile(
        r"https?://[^\s)]*[?&](?:token|key|access_token|api_key|sig|signature)=[^\s&)]+")),
])


def luhn_ok(digits: str) -> bool:
    ds = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(ds) <= 19:
        return False
    total, parity = 0, len(ds) % 2
    for i, d in enumerate(ds):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def israeli_id_ok(digits: str) -> bool:
    if len(digits) != 9 or not digits.isdigit():
        return False
    total = 0
    for i, c in enumerate(digits):
        d = int(c) * (1 if i % 2 == 0 else 2)
        total += d if d < 10 else d - 9
    return total % 10 == 0


def validates(kind: str, value: str) -> bool:
    """Reject matches that fit the shape but are obviously not the thing."""
    if kind == "CARD":
        return luhn_ok(value)
    if kind == "ISRAELI_ID":
        return israeli_id_ok(value)
    if kind == "IPV4":
        return all(0 <= int(o) <= 255 for o in value.split("."))
    if kind == "PHONE":
        digits = re.sub(r"\D", "", value)
        # Too short is a date or a version; too long is an id of some other kind.
        return 7 <= len(digits) <= 15
    return True


class Redactor:
    def __init__(self, kinds: set[str]):
        self.kinds = kinds
        self.assigned: dict[tuple[str, str], str] = {}
        self.counters: dict[str, int] = {}
        self.log: list[dict] = []

    def placeholder(self, kind: str, value: str) -> str:
        key = (kind, value.strip())
        if key not in self.assigned:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            self.assigned[key] = f"[{kind}_{self.counters[kind]}]"
        return self.assigned[key]

    def apply(self, text: str, turn_index: int) -> str:
        spans: list[tuple[int, int, str, str]] = []
        for kind, pattern in PATTERNS.items():
            if kind not in self.kinds:
                continue
            # Deliberately not finditer. When a match fails validation finditer
            # resumes past the whole rejected span, so a greedy match that
            # straddles two adjacent numbers swallows the second one and it is
            # never re-examined. Retrying from start+1 keeps it in play.
            pos = 0
            while pos < len(text):
                m = pattern.search(text, pos)
                if not m:
                    break
                value = m.group(0)
                overlaps = any(s < m.end() and m.start() < e
                               for s, e, _, _ in spans)
                if validates(kind, value) and not overlaps:
                    spans.append((m.start(), m.end(), kind, value))
                    pos = m.end()
                else:
                    pos = m.start() + 1

        for start, end, kind, value in sorted(spans, reverse=True):
            ph = self.placeholder(kind, value)
            text = text[:start] + ph + text[end:]
            self.log.append({"turn": turn_index, "kind": kind, "placeholder": ph,
                             "length": len(value)})
        return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="normalized conversation JSON ('-' for stdin)")
    ap.add_argument("--out", "-o", help="output file (default: stdout)")
    ap.add_argument("--scope", default="user", choices=["user", "all"],
                    help="which turns to redact (default: user only)")
    ap.add_argument("--kinds", default=",".join(PATTERNS),
                    help="comma-separated subset of: " + ",".join(PATTERNS))
    ap.add_argument("--report", help="also write the redaction log here")
    ap.add_argument("--keep-values", action="store_true",
                    help="record redacted values in the log (writes secrets to disk)")
    args = ap.parse_args()

    kinds = {k.strip().upper() for k in args.kinds.split(",") if k.strip()}
    unknown = kinds - set(PATTERNS)
    if unknown:
        raise SystemExit(f"error: unknown kind(s): {', '.join(sorted(unknown))}")

    text = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    doc = json.loads(text)

    r = Redactor(kinds)
    for turn in doc["turns"]:
        if args.scope == "user" and turn["role"] != "user":
            continue
        turn["text"] = r.apply(turn["text"], turn["index"])

    doc["redaction"] = {
        "pass": "deterministic",
        "scope": args.scope,
        "kinds": sorted(kinds),
        "count": len(r.log),
        "by_kind": {k: sum(1 for e in r.log if e["kind"] == k)
                    for k in sorted({e["kind"] for e in r.log})},
        "judgement_pass_applied": False,
    }
    if args.keep_values:
        doc["redaction"]["map"] = {v: f"{k[0]}:{k[1]}" for k, v in r.assigned.items()}

    out = json.dumps(doc, indent=2, ensure_ascii=False)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(out + "\n")
        print(f"{args.out}: {len(r.log)} redaction(s) "
              f"{doc['redaction']['by_kind'] or '{}'}", file=sys.stderr)
    else:
        print(out)

    if args.report:
        open(args.report, "w", encoding="utf-8").write(
            json.dumps(r.log, indent=2) + "\n")


if __name__ == "__main__":
    main()
