#!/usr/bin/env python3
"""Compute staleness signals for open tickets in a normalized backlog CSV. Standard library only.

Input: the backlog.csv written by backlog-ingest/scripts/normalize.py.
Optional: merged pull requests, to catch work that shipped but whose ticket was never closed:
  gh pr list --state merged --limit 1000 --json number,title,body,headRefName,mergedAt,url,closingIssuesReferences > prs.json

Usage:
  stale_signals.py backlog.csv --out signals.csv
  stale_signals.py backlog.csv --prs prs.json --stale-days 90 --inactive "alice;bob" --out signals.csv
  stale_signals.py backlog.csv --today 2026-10-24      # reproducible runs
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys

JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")
GH_REF = re.compile(r"(?:(?<![\w/])([\w.-]+/[\w.-]+))?#(\d+)\b")
CLOSING = re.compile(r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b[:\s]+", re.I)


def days_between(a, b):
    return (b - dt.date.fromisoformat(a)).days if a else None


def load_backlog(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and "status_category" not in rows[0]:
        sys.exit(f"{path}: not a normalized backlog. Run backlog-ingest/scripts/normalize.py first.")
    return rows


def merged_pr_refs(paths):
    """Map ticket key -> (strength, pr_url). strength 'closes' beats 'mentions'."""
    refs = {}

    def add(key, strength, url):
        if refs.get(key, ("",))[0] != "closes":
            refs[key] = (strength, url)

    for path in paths:
        with open(path, encoding="utf-8-sig") as f:
            prs = json.load(f)
        for pr in prs:
            if not pr.get("mergedAt"):
                continue
            url = pr.get("url", "")
            m = re.search(r"github\.com/([^/]+/[^/]+)/pull/", url)
            repo = m.group(1) if m else ""
            text = f"{pr.get('title', '')}\n{pr.get('body') or ''}"
            for key in set(JIRA_KEY.findall(f"{text}\n{(pr.get('headRefName') or '').upper()}")):
                add(key, "mentions", url)
            for ref in pr.get("closingIssuesReferences") or []:
                rrepo = repo
                r = ref.get("repository") or {}
                if r.get("name") and (r.get("owner") or {}).get("login"):
                    rrepo = f"{r['owner']['login']}/{r['name']}"
                if ref.get("url"):
                    m2 = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", ref["url"])
                    if m2:
                        rrepo, num = m2.group(1), m2.group(2)
                        add(f"{rrepo}#{num}", "closes", url)
                        continue
                if ref.get("number"):
                    add(f"{rrepo}#{ref['number']}", "closes", url)
            for match in GH_REF.finditer(text):
                rrepo = match.group(1) or repo
                before = text[max(0, match.start() - 12):match.start()]
                add(f"{rrepo}#{match.group(2)}", "closes" if CLOSING.search(before) else "mentions", url)
            # A Jira key preceded by a closing keyword is also a strong signal.
            for match in JIRA_KEY.finditer(text):
                if CLOSING.search(text[max(0, match.start() - 12):match.start()]):
                    add(match.group(1), "closes", url)
    return refs


def signals_for(t, today, args, pr_refs, merged_urls, inactive):
    out = []  # (name, detail, weight)
    last_touch = max(t["updated"], t["last_comment_at"])
    idle = days_between(last_touch, today)
    age = days_between(t["created"], today)

    ref = pr_refs.get(t["key"])
    if not ref:
        # GitHub issues list their closing PRs; any of those that merged counts.
        linked = [u for u in t.get("linked_prs", "").split(";") if u in merged_urls]
        if linked:
            ref = ("closes", linked[0])
    if ref:
        out.append(("merged_pr", f"{ref[0]} {ref[1]}", 3 if ref[0] == "closes" else 2))

    blockers = [l.split(":") for l in t["links"].split(";") if l.lower().startswith("blocks:inward:")]
    if blockers and all(len(b) > 3 and b[3] == "done" for b in blockers):
        out.append(("blockers_resolved", ",".join(b[2] for b in blockers), 2))
    if t["epic"] and t["epic_status_category"] == "done":
        out.append(("parent_closed", t["epic"], 2))
    if t["status_category"] == "in_progress" and idle is not None and idle >= args.wip_days:
        out.append(("zombie_wip", f"{t['status']} {idle}d idle", 2))
    if idle is not None and idle >= args.stale_days:
        out.append(("no_update", f"{idle}d", 2 if idle >= 2 * args.stale_days else 1))
    if int(t["sprint_count"] or 0) >= args.carryover:
        out.append(("carryover", f"{t['sprint_count']} sprints", 2))
    owners = [a for a in t["assignee"].split(";") if a]
    gone = [a for a in owners if a.lower() in inactive]
    if gone:
        out.append(("inactive_assignee", ",".join(gone), 2))
    if not owners and age is not None and age >= args.old_days:
        out.append(("unowned_old", f"{age}d old", 1))
    if t["due"] and t["due"] < today.isoformat():
        out.append(("past_due", t["due"], 1))
    if not t["description"].strip() and not int(t["comment_count"] or 0):
        out.append(("thin", "no description or comments", 1))
    return out, idle, age


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backlog", help="normalized backlog CSV")
    ap.add_argument("--out", required=True, help="signals CSV to write")
    ap.add_argument("--prs", action="append", default=[], help="gh pr list JSON (repeatable)")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--stale-days", type=int, default=60, help="idle days before no_update fires (default 60)")
    ap.add_argument("--wip-days", type=int, default=14, help="idle days for an in-progress ticket (default 14)")
    ap.add_argument("--old-days", type=int, default=180, help="age for unowned_old (default 180)")
    ap.add_argument("--carryover", type=int, default=3, help="sprint count for carryover (default 3)")
    ap.add_argument("--inactive", default="", help="semicolon-separated assignees who left or are inactive")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    inactive = {a.strip().lower() for a in args.inactive.split(";") if a.strip()}
    pr_refs = merged_pr_refs(args.prs)
    merged_urls = {url for _, url in pr_refs.values()}
    tickets = load_backlog(args.backlog)

    rows, counts = [], {}
    open_count = 0
    for t in tickets:
        if t["status_category"] == "done":
            continue
        open_count += 1
        sig, idle, age = signals_for(t, today, args, pr_refs, merged_urls, inactive)
        if not sig:
            continue
        for name, _, _ in sig:
            counts[name] = counts.get(name, 0) + 1
        rows.append({
            "key": t["key"], "title": t["title"], "status": t["status"], "assignee": t["assignee"],
            "idle_days": "" if idle is None else idle, "age_days": "" if age is None else age,
            "score": sum(w for _, _, w in sig),
            "signals": "; ".join(f"{n}({d})" for n, d, _ in sig), "url": t["url"],
        })
    rows.sort(key=lambda r: (-r["score"], -(r["idle_days"] or 0)))

    cols = ["key", "title", "status", "assignee", "idle_days", "age_days", "score", "signals", "url"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"Open tickets: {open_count}; flagged: {len(rows)} ({100 * len(rows) // max(open_count, 1)}%)")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<18} {n}")
    if rows:
        print("Top candidates:")
        for r in rows[:10]:
            print(f"  {r['score']:>2}  {r['key']:<22} {r['title'][:50]:<50}  {r['signals']}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
