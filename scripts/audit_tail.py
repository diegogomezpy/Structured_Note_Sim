#!/usr/bin/env python3
"""Pretty-print the generation audit trail from Cloud Run logs.

The API logs one line per model run / report export (see api/main.py:_audit):

    [report]  ts=<UTC> ip=<client IP> geo='<city, region, country · ISP · ASN>' …
    [simulate] ts=<UTC> ip=<client IP> geo='…' note='…' tickers='…' …

This wraps `gcloud logging read`, parses those lines, prints them readably, and
shows a summary (counts, unique IPs, top networks/countries) so you can spot who
is using the tool — including unauthorized/commercial use. Read-only.

Requires the gcloud CLI, authenticated with access to the project's logs
(`gcloud auth login`). Examples:

    python scripts/audit_tail.py                     # last 100, past 7 days
    python scripts/audit_tail.py --tag report -n 50  # only PDF exports
    python scripts/audit_tail.py --since 1d          # past day
    python scripts/audit_tail.py --json              # raw entries, no summary
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from collections import Counter

DEFAULT_PROJECT = "structurednotesim"
DEFAULT_SERVICE = "structured-note-sim"

# key=value where value is a Python repr string ('…' / "…") or a bare token.
_KV = re.compile(r"(\w+)=(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\S+)")
_LINE = re.compile(r"\[(simulate|report)\]\s*(.*)")


def _parse(text: str) -> dict | None:
    m = _LINE.search(text or "")
    if not m:
        return None
    out: dict = {"tag": m.group(1)}
    for k, v in _KV.findall(m.group(2)):
        if v[:1] in "\"'":
            try:
                v = ast.literal_eval(v)
            except Exception:
                v = v.strip("\"'")
        out[k] = v
    return out


def _fetch(project: str, service: str, tag: str, limit: int, since: str) -> list[dict]:
    if not shutil.which("gcloud"):
        sys.exit("error: gcloud CLI not found — install the Google Cloud SDK and `gcloud auth login`.")
    # RE2 match on the log text — unambiguous with the [tag] brackets (the `:`
    # substring operator tokenizes and drops brackets).
    tag_re = "simulate|report" if tag == "all" else tag
    flt = (f'resource.type="cloud_run_revision" '
           f'resource.labels.service_name="{service}" '
           f'textPayload=~"\\[({tag_re})\\]"')
    cmd = ["gcloud", "logging", "read", flt, "--project", project,
           "--limit", str(limit), "--freshness", since,
           "--order", "desc", "--format", "json"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        sys.exit("error: `gcloud logging read` timed out.")
    if res.returncode != 0:
        sys.exit(f"error: gcloud failed:\n{res.stderr.strip()}")
    try:
        return json.loads(res.stdout or "[]")
    except json.JSONDecodeError:
        sys.exit("error: could not parse gcloud output as JSON.")


# ── formatting ────────────────────────────────────────────────────────────────
_C = {"report": "\033[38;5;208m", "simulate": "\033[38;5;39m",
      "dim": "\033[2m", "bold": "\033[1m", "reset": "\033[0m"}


def _color(on: bool):
    return _C if on else {k: "" for k in _C}


def _print_entry(ts: str, d: dict, c: dict) -> None:
    tag = d.get("tag", "?")
    head = f"{c.get(tag, '')}{tag.upper():8}{c['reset']}"
    ip = d.get("ip", "?")
    geo = d.get("geo", "") or "—"
    print(f"{c['dim']}{ts[:19].replace('T', ' ')}Z{c['reset']}  {head}  "
          f"{c['bold']}{ip:<15}{c['reset']}  {geo}")
    bits = []
    if d.get("note"):
        bits.append(f"note={d['note']!r}")
    if d.get("tickers"):
        bits.append(d["tickers"])
    for k in ("sections", "n_paths", "engine", "lang"):
        if k in d:
            bits.append(f"{k}={d[k]}")
    if bits:
        print(f"{c['dim']}{'':21}{' · '.join(bits)}{c['reset']}")


def _summary(rows: list[tuple[str, dict]], c: dict) -> None:
    if not rows:
        return
    tags = Counter(d["tag"] for _, d in rows)
    ips = Counter(d.get("ip", "?") for _, d in rows)
    nets = Counter((d.get("geo", "") or "—").split(" · ", 1)[-1] for _, d in rows if d.get("geo"))
    ctry = Counter((d.get("geo", "").split(" · ")[0].split(", ")[-1]) for _, d in rows if d.get("geo"))
    print(f"\n{c['bold']}Summary{c['reset']}  "
          f"{sum(tags.values())} events "
          f"({tags.get('simulate', 0)} simulate, {tags.get('report', 0)} report) · "
          f"{len(ips)} unique IPs")
    if nets:
        print("  top networks:  " + " | ".join(f"{n} ({k})" for n, k in nets.most_common(5)))
    if ctry:
        print("  top countries: " + " | ".join(f"{n} ({k})" for n, k in ctry.most_common(5)))


def main() -> None:
    p = argparse.ArgumentParser(description="Pretty-print the Cloud Run generation audit trail.")
    p.add_argument("-n", "--limit", type=int, default=100, help="max entries to fetch (default 100)")
    p.add_argument("--since", default="7d", help="freshness window, e.g. 1d / 12h / 30m (default 7d)")
    p.add_argument("--tag", choices=("all", "simulate", "report"), default="all", help="filter by event type")
    p.add_argument("--project", default=DEFAULT_PROJECT, help=f"GCP project (default {DEFAULT_PROJECT})")
    p.add_argument("--service", default=DEFAULT_SERVICE, help=f"Cloud Run service (default {DEFAULT_SERVICE})")
    p.add_argument("--json", action="store_true", help="dump the parsed entries as JSON (no summary)")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    args = p.parse_args()

    entries = _fetch(args.project, args.service, args.tag, args.limit, args.since)
    rows: list[tuple[str, dict]] = []
    for e in entries:
        d = _parse(e.get("textPayload", ""))
        if d:
            rows.append((e.get("timestamp", ""), d))
    rows.reverse()  # oldest → newest for reading

    if args.json:
        print(json.dumps([{"timestamp": ts, **d} for ts, d in rows], indent=2))
        return

    if not rows:
        print(f"No [{args.tag}] audit lines in the last {args.since}.")
        return

    c = _color(sys.stdout.isatty() and not args.no_color)
    for ts, d in rows:
        _print_entry(ts, d, c)
    _summary(rows, c)


if __name__ == "__main__":
    main()
