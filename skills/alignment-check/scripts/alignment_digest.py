#!/usr/bin/env python3
"""Print a compact, epic-grouped digest of open tickets plus structural alignment flags,
so an agent can review a large backlog against goals without reading every CSV column.
Standard library only.

Structural flags (no judgment needed):
  no_parent        ticket has no epic / parent / milestone
  parent_closed    its epic or milestone is already done
  parent_missing   it points to an epic that is not in the export
  high_no_parent   high priority but not tied to any epic
  no_labels        no labels and no components

Usage:
  alignment_digest.py backlog.csv                         # digest to stdout
  alignment_digest.py backlog.csv --flags-out flags.csv   # also write structural flags
  alignment_digest.py backlog.csv --epic PROJ-12          # one epic only
  alignment_digest.py backlog.csv --desc-chars 300        # more context per ticket
"""
import argparse
import csv
import sys
from collections import defaultdict

HIGH = ("highest", "high", "critical", "blocker", "urgent", "p0", "p1", "sev0", "sev1")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backlog", help="normalized backlog CSV")
    ap.add_argument("--flags-out", help="write structural flags CSV here")
    ap.add_argument("--epic", help="only show tickets under this epic/milestone ('none' for unparented)")
    ap.add_argument("--desc-chars", type=int, default=160, help="description characters per ticket (default 160)")
    args = ap.parse_args()

    with open(args.backlog, newline="", encoding="utf-8-sig") as f:
        tickets = list(csv.DictReader(f))
    if tickets and "status_category" not in tickets[0]:
        sys.exit(f"{args.backlog}: not a normalized backlog. Run backlog-ingest/scripts/normalize.py first.")
    by_key = {t["key"]: t for t in tickets}
    epic_like = {t["epic"] for t in tickets if t["epic"]}

    groups, flags = defaultdict(list), []
    for t in tickets:
        if t["status_category"] == "done" or t["key"] in epic_like or t["type"].lower() == "epic":
            continue
        found = []
        if not t["epic"]:
            found.append("no_parent")
            if any(h in t["priority"].lower() for h in HIGH):
                found.append("high_no_parent")
        elif t["epic_status_category"] == "done":
            found.append("parent_closed")
        elif t["source"] == "jira" and t["epic"] not in by_key:
            found.append("parent_missing")
        if not t["labels"] and not t["components"]:
            found.append("no_labels")
        for name in found:
            flags.append({"key": t["key"], "flag": name, "epic": t["epic"], "priority": t["priority"], "title": t["title"]})
        groups[t["epic"] or "none"].append((t, found))

    order = sorted(groups, key=lambda e: (e == "none", e))
    if args.epic:
        order = [e for e in order if e == args.epic]
    for epic in order:
        head = by_key.get(epic)
        label = f"{epic} — {head['title']} [{head['status']}]" if head else epic
        print(f"\n## {label if epic != 'none' else 'No epic / milestone'}  ({len(groups[epic])} open)")
        for t, found in groups[epic]:
            desc = t["description"][: args.desc_chars]
            tag = f"  ⚑ {','.join(found)}" if found else ""
            print(f"- {t['key']} | {t['type']} | {t['priority'] or '-'} | {t['labels'] or '-'} | {t['title']}{tag}")
            if desc:
                print(f"    {desc}")

    counts = defaultdict(int)
    for fl in flags:
        counts[fl["flag"]] += 1
    print("\nStructural flags: " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"), file=sys.stderr)
    if args.flags_out:
        with open(args.flags_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["key", "flag", "epic", "priority", "title"])
            w.writeheader()
            w.writerows(flags)
        print(f"Wrote {args.flags_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
