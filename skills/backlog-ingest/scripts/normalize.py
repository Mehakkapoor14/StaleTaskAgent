#!/usr/bin/env python3
"""Normalize Jira and GitHub Issues exports into one backlog CSV. Standard library only.

Accepted inputs (format is detected per file, several files can be merged):
  Jira CSV export      Filters -> Export -> CSV (all fields). Repeated columns (Labels,
                       Sprint, Comment, Component/s, issue links) are handled.
  Jira JSON            Output of /rest/api/2|3/search (a {"issues": [...]} page) or a
                       JSON list of issue objects, e.g. saved from an Atlassian MCP tool.
  GitHub issues JSON   gh issue list --state all --limit 1000 --json \
                         number,title,body,state,stateReason,labels,assignees,author,\
                         createdAt,updatedAt,closedAt,milestone,comments,url,\
                         closedByPullRequestsReferences

Usage:
  normalize.py jira-export.csv --out pm/backlog/backlog.csv
  normalize.py issues.json other-repo.json jira.json --out pm/backlog/backlog.csv
  normalize.py jira.json --epic-field customfield_10014 --out backlog.csv   # Data Center Epic Link
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys

COLUMNS = [
    "key", "source", "url", "title", "type", "status", "status_category", "resolution",
    "priority", "assignee", "reporter", "labels", "components", "epic", "epic_status_category",
    "sprints", "sprint_count", "due", "created", "updated", "comment_count", "last_comment_at",
    "links", "linked_prs", "last_comments", "description",
]
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
DESC_LIMIT = 2000
COMMENT_LIMIT = 400
DATE_FORMATS = [
    "%d/%b/%y %I:%M %p", "%d/%b/%Y %I:%M %p", "%d/%b/%y %H:%M", "%d/%b/%Y %H:%M",
    "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%d.%m.%Y %H:%M",
    "%d/%b/%y", "%d/%b/%Y", "%Y-%m-%d", "%m/%d/%Y",
]
DONE_WORDS = ("done", "closed", "resolved", "released", "complete", "cancel", "won't", "wont", "rejected", "duplicate")
WIP_WORDS = ("progress", "review", "testing", "qa", "doing", "develop", "blocked", "verify")


def parse_date(text):
    """Return YYYY-MM-DD for the many date formats Jira and GitHub emit, or ''."""
    text = (text or "").strip()
    if not text:
        return ""
    iso = re.match(r"^(\d{4}-\d{2}-\d{2})[T ]", text + " ")
    if iso:
        return iso.group(1)
    for f in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, f).date().isoformat()
        except ValueError:
            pass
    return ""


def category_from_name(status, explicit=""):
    explicit = (explicit or "").lower()
    if explicit in ("new", "to do", "todo"):
        return "todo"
    if explicit in ("indeterminate", "in progress"):
        return "in_progress"
    if explicit in ("done", "complete"):
        return "done"
    s = (status or "").lower()
    if any(w in s for w in DONE_WORDS):
        return "done"
    if any(w in s for w in WIP_WORDS):
        return "in_progress"
    return "todo"


def clip(text, limit):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def adf_text(node):
    """Flatten Atlassian Document Format (API v3) into plain text."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(adf_text(n) for n in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if node.get("type") in ("mention", "emoji"):
            return node.get("attrs", {}).get("text", "")
        return " ".join(adf_text(n) for n in node.get("content", []))
    return ""


def summarize_comments(comments):
    """comments: list of (date, author, body), any order. Returns count, last date, last-3 text."""
    comments = sorted(comments, key=lambda c: c[0])
    last = comments[-3:]
    text = " || ".join(f"[{d} {a}] {clip(b, COMMENT_LIMIT)}" for d, a, b in last)
    return len(comments), (comments[-1][0] if comments else ""), text


def blank():
    return {c: "" for c in COLUMNS}


# ---------------------------------------------------------------- Jira CSV

def load_jira_csv(path, base_url):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            sys.exit(f"{path}: empty CSV.")
        rows = list(reader)
    if "Issue key" not in header:
        sys.exit(f"{path}: not a Jira export (no 'Issue key' column).")

    def values(row, *names):
        out = []
        for i, h in enumerate(header):
            if h in names and i < len(row) and row[i].strip():
                out.append(row[i].strip())
        return out

    def first(row, *names):
        v = values(row, *names)
        return v[0] if v else ""

    # Cloud exports put the parent's numeric id in "Parent"; map ids back to keys.
    id_to_key = {first(r, "Issue id"): first(r, "Issue key") for r in rows if first(r, "Issue id")}
    tickets = []
    for row in rows:
        t = blank()
        t["key"] = first(row, "Issue key")
        if not t["key"]:
            continue
        t["source"] = "jira"
        if base_url:
            t["url"] = f"{base_url.rstrip('/')}/browse/{t['key']}"
        t["title"] = first(row, "Summary")
        t["description"] = clip(first(row, "Description"), DESC_LIMIT)
        t["type"] = first(row, "Issue Type")
        t["status"] = first(row, "Status")
        t["status_category"] = category_from_name(t["status"], first(row, "Status Category"))
        t["resolution"] = first(row, "Resolution")
        t["priority"] = first(row, "Priority")
        t["assignee"] = first(row, "Assignee")
        t["reporter"] = first(row, "Reporter")
        t["labels"] = ";".join(values(row, "Labels"))
        t["components"] = ";".join(values(row, "Component/s", "Components"))
        epic = first(row, "Parent key", "Custom field (Epic Link)", "Epic Link", "Parent")
        epic = id_to_key.get(epic, epic)
        t["epic"] = epic if KEY_RE.match(epic) else ""
        sprints = values(row, "Sprint")
        t["sprints"] = ";".join(sprints)
        t["sprint_count"] = str(len(sprints))
        t["due"] = parse_date(first(row, "Due Date", "Due date"))
        t["created"] = parse_date(first(row, "Created"))
        t["updated"] = parse_date(first(row, "Updated"))
        comments = []
        for c in values(row, "Comment"):
            # Jira writes comments as "date;author;body".
            parts = c.split(";", 2)
            if len(parts) == 3:
                comments.append((parse_date(parts[0]), parts[1], parts[2]))
            else:
                comments.append(("", "", c))
        t["comment_count"], t["last_comment_at"], t["last_comments"] = summarize_comments(comments)
        links = []
        for i, h in enumerate(header):
            m = re.match(r"^(Inward|Outward) issue link \((.+)\)$", h)
            if m and i < len(row) and row[i].strip():
                links.append(f"{m.group(2)}:{m.group(1).lower()}:{row[i].strip()}:")
        t["links"] = ";".join(links)
        tickets.append(t)
    return tickets


# ---------------------------------------------------------------- Jira JSON

def sprint_names(value):
    names = []
    for s in value if isinstance(value, list) else []:
        if isinstance(s, dict) and "name" in s and ("boardId" in s or "state" in s):
            names.append(s["name"])
        elif isinstance(s, str):
            m = re.search(r"name=([^,\]]+)", s)  # Data Center serializes sprints as strings
            if m:
                names.append(m.group(1))
    return names


def load_jira_json(issues, base_url, epic_field):
    tickets = []
    for issue in issues:
        f = issue.get("fields", {})
        t = blank()
        t["key"] = issue["key"]
        t["source"] = "jira"
        if base_url:
            t["url"] = f"{base_url.rstrip('/')}/browse/{issue['key']}"
        elif issue.get("self"):
            t["url"] = issue["self"].split("/rest/")[0] + "/browse/" + issue["key"]
        t["title"] = f.get("summary") or ""
        t["description"] = clip(adf_text(f.get("description")), DESC_LIMIT)
        t["type"] = (f.get("issuetype") or {}).get("name", "")
        status = f.get("status") or {}
        t["status"] = status.get("name", "")
        t["status_category"] = category_from_name(t["status"], (status.get("statusCategory") or {}).get("key", ""))
        t["resolution"] = (f.get("resolution") or {}).get("name", "")
        t["priority"] = (f.get("priority") or {}).get("name", "")
        t["assignee"] = (f.get("assignee") or {}).get("displayName", "")
        t["reporter"] = (f.get("reporter") or {}).get("displayName", "")
        t["labels"] = ";".join(f.get("labels") or [])
        t["components"] = ";".join(c.get("name", "") for c in f.get("components") or [])
        parent = f.get("parent") or {}
        if parent.get("key"):
            t["epic"] = parent["key"]
            pstatus = (parent.get("fields") or {}).get("status") or {}
            t["epic_status_category"] = category_from_name(pstatus.get("name", ""), (pstatus.get("statusCategory") or {}).get("key", "")) if pstatus else ""
        elif epic_field and isinstance(f.get(epic_field), str):
            t["epic"] = f[epic_field]
        sprints = []
        for name, value in f.items():
            if name.startswith("customfield_"):
                sprints += sprint_names(value)
        t["sprints"] = ";".join(sprints)
        t["sprint_count"] = str(len(sprints))
        t["due"] = parse_date(f.get("duedate"))
        t["created"] = parse_date(f.get("created"))
        t["updated"] = parse_date(f.get("updated"))
        raw = (f.get("comment") or {}).get("comments", [])
        comments = [(parse_date(c.get("created")), (c.get("author") or {}).get("displayName", ""), adf_text(c.get("body"))) for c in raw]
        t["comment_count"], t["last_comment_at"], t["last_comments"] = summarize_comments(comments)
        if (f.get("comment") or {}).get("total"):
            t["comment_count"] = f["comment"]["total"]
        links = []
        for link in f.get("issuelinks") or []:
            kind = (link.get("type") or {}).get("name", "")
            for direction in ("inward", "outward"):
                other = link.get(f"{direction}Issue")
                if other:
                    ostatus = (other.get("fields") or {}).get("status") or {}
                    cat = category_from_name(ostatus.get("name", ""), (ostatus.get("statusCategory") or {}).get("key", "")) if ostatus else ""
                    # An "inwardIssue" entry means this issue carries the inward phrase ("is blocked by").
                    links.append(f"{kind}:{direction}:{other.get('key', '')}:{cat}")
        t["links"] = ";".join(links)
        tickets.append(t)
    return tickets


# ---------------------------------------------------------------- GitHub

PRIORITY_LABEL = re.compile(r"^(p[0-4]|priority[:/ -]?.+|sev[0-4]|critical|urgent)$", re.I)
TYPE_LABELS = {"bug": "Bug", "enhancement": "Feature", "feature": "Feature", "documentation": "Docs", "docs": "Docs", "chore": "Chore", "epic": "Epic"}


def load_github(issues):
    tickets = []
    for issue in issues:
        t = blank()
        m = re.search(r"github\.com/([^/]+/[^/]+)/(?:issues|pull)/(\d+)", issue.get("url", ""))
        t["key"] = f"{m.group(1)}#{m.group(2)}" if m else f"#{issue['number']}"
        t["source"] = "github"
        t["url"] = issue.get("url", "")
        t["title"] = issue.get("title", "")
        t["description"] = clip(issue.get("body"), DESC_LIMIT)
        labels = [l.get("name", "") for l in issue.get("labels") or []]
        t["labels"] = ";".join(labels)
        t["type"] = next((TYPE_LABELS[l.lower()] for l in labels if l.lower() in TYPE_LABELS), "Issue")
        t["priority"] = next((l for l in labels if PRIORITY_LABEL.match(l)), "")
        state = (issue.get("state") or "").upper()
        project_status = ""
        for item in issue.get("projectItems") or []:
            project_status = ((item.get("status") or {}).get("name") or project_status)
        if state == "CLOSED":
            t["status"] = "Closed"
            t["status_category"] = "done"
            t["resolution"] = (issue.get("stateReason") or "").replace("_", " ").lower()
        else:
            t["status"] = project_status or "Open"
            in_progress = any(w in (project_status or "").lower() for w in WIP_WORDS) or any("progress" in l.lower() for l in labels)
            t["status_category"] = "in_progress" if in_progress else "todo"
        t["assignee"] = ";".join(a.get("login", "") for a in issue.get("assignees") or [])
        t["reporter"] = (issue.get("author") or {}).get("login", "")
        milestone = issue.get("milestone") or {}
        t["epic"] = milestone.get("title", "")
        if milestone.get("state"):
            t["epic_status_category"] = "done" if milestone["state"].upper() == "CLOSED" else "todo"
        t["due"] = parse_date(milestone.get("dueOn"))
        t["created"] = parse_date(issue.get("createdAt"))
        t["updated"] = parse_date(issue.get("updatedAt"))
        comments = [(parse_date(c.get("createdAt")), (c.get("author") or {}).get("login", ""), c.get("body", "")) for c in issue.get("comments") or []]
        t["comment_count"], t["last_comment_at"], t["last_comments"] = summarize_comments(comments)
        t["linked_prs"] = ";".join(p.get("url", "") for p in issue.get("closedByPullRequestsReferences") or [])
        tickets.append(t)
    return tickets


# ---------------------------------------------------------------- main

def load_any(path, base_url, epic_field):
    if path.lower().endswith(".csv"):
        return load_jira_csv(path, base_url)
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict) and "issues" in data:
        return load_jira_json(data["issues"], base_url, epic_field)
    if isinstance(data, list) and data:
        if "fields" in data[0] and "key" in data[0]:
            return load_jira_json(data, base_url, epic_field)
        if "number" in data[0]:
            return load_github(data)
    if isinstance(data, list) and not data:
        return []
    sys.exit(f"{path}: unrecognized format (expected Jira CSV/JSON or gh issue list JSON).")


def link_statuses(tickets):
    """Fill missing link-target status categories from tickets present in the same backlog."""
    cat = {t["key"]: t["status_category"] for t in tickets}
    for t in tickets:
        if t["epic"] and not t["epic_status_category"] and t["epic"] in cat:
            t["epic_status_category"] = cat[t["epic"]]
        if not t["links"]:
            continue
        fixed = []
        for link in t["links"].split(";"):
            kind, direction, key, c = (link.split(":") + ["", "", "", ""])[:4]
            fixed.append(f"{kind}:{direction}:{key}:{c or cat.get(key, '')}")
        t["links"] = ";".join(fixed)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="Jira CSV/JSON and/or gh issue list JSON files")
    ap.add_argument("--out", required=True, help="normalized backlog CSV to write")
    ap.add_argument("--jira-url", default="", help="Jira base URL, used to build ticket links")
    ap.add_argument("--epic-field", default="", help="custom field id holding the Epic Link (Jira Data Center)")
    args = ap.parse_args()

    tickets, seen = [], set()
    for path in args.inputs:
        loaded = load_any(path, args.jira_url, args.epic_field)
        for t in loaded:
            if t["key"] in seen:
                continue
            seen.add(t["key"])
            tickets.append(t)
        print(f"{path}: {len(loaded)} tickets")
    link_statuses(tickets)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(tickets)

    by_cat = {}
    for t in tickets:
        by_cat[t["status_category"]] = by_cat.get(t["status_category"], 0) + 1
    undated = sum(1 for t in tickets if not t["updated"])
    print(f"Wrote {args.out}: {len(tickets)} tickets ({', '.join(f'{k} {v}' for k, v in sorted(by_cat.items()))})")
    if undated:
        print(f"WARNING: {undated} tickets have no parseable 'updated' date; staleness checks will skip them.")


if __name__ == "__main__":
    main()
