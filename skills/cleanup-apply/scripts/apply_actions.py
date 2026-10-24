#!/usr/bin/env python3
"""Apply human-approved backlog cleanup actions to Jira and/or GitHub Issues. Standard library
only (GitHub goes through the `gh` CLI; Jira through its REST API v2, which Cloud and Data
Center both support).

Dry run is the default: nothing changes until --execute is passed. Only rows whose
`approved` column is yes/y/true run. Before each change the ticket is re-fetched; if it was
updated after the backlog snapshot (someone touched it since triage) it is skipped unless
--allow-changed is given. Every attempt is appended to an audit log with an undo hint.

actions.csv columns: key,action,target,resolution,comment,reason,source,confidence,approved
  actions: keep | close | close-duplicate | link | comment | move | relabel | unassign | reassign
  see references/actions.md for what each one does on each platform.

Jira auth (environment):
  JIRA_URL=https://yourco.atlassian.net
  JIRA_EMAIL + JIRA_API_TOKEN   (Cloud)      or      JIRA_PAT   (Data Center personal access token)
GitHub auth: whatever `gh auth status` shows.

Usage:
  apply_actions.py pm/backlog/actions.csv --backlog pm/backlog/backlog.csv               # dry run
  apply_actions.py pm/backlog/actions.csv --backlog pm/backlog/backlog.csv --execute --limit 1
  apply_actions.py pm/backlog/actions.csv --backlog pm/backlog/backlog.csv --execute
  apply_actions.py ... --execute --only PROJ-12 --only acme/web#88
"""
import argparse
import base64
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

ACTIONS = {"keep", "close", "close-duplicate", "link", "comment", "move", "relabel", "unassign", "reassign"}
NEEDS_TARGET = {"close-duplicate", "link", "move", "relabel", "reassign"}
NEEDS_COMMENT = {"close", "close-duplicate", "comment"}
JIRA_RESOLUTIONS = {"done": "Done", "wont-do": "Won't Do", "obsolete": "Won't Do", "cannot-reproduce": "Cannot Reproduce", "duplicate": "Duplicate"}
GH_KEY = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
AUDIT_COLS = ["timestamp", "key", "action", "target", "result", "detail", "previous", "undo"]


class Skip(Exception):
    pass


# ---------------------------------------------------------------- GitHub

def gh(*args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return p.stdout


def gh_ref(key, default_repo=""):
    m = GH_KEY.match(key)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^#?(\d+)$", key)
    if m and default_repo:
        return default_repo, m.group(1)
    raise ValueError(f"'{key}' is not a GitHub issue key like owner/repo#123")


def gh_state(key):
    repo, num = gh_ref(key)
    data = json.loads(gh("issue", "view", num, "-R", repo, "--json", "state,updatedAt,assignees,labels,milestone"))
    return {
        "updated": data["updatedAt"][:10], "done": data["state"] == "CLOSED", "status": data["state"],
        "assignee": ";".join(a["login"] for a in data.get("assignees") or []),
        "labels": ";".join(l["name"] for l in data.get("labels") or []),
        "parent": (data.get("milestone") or {}).get("title", ""),
    }


def gh_apply(row, prev):
    repo, num = gh_ref(row["key"])
    action, target, comment = row["action"], row["target"], row["comment"]
    base = ["-R", repo]
    if action == "close":
        reason = "completed" if row["resolution"] in ("", "done") else "not planned"
        gh("issue", "close", num, *base, "--reason", reason, "--comment", comment)
        return f"closed as {reason}", f"gh issue reopen {num} -R {repo}"
    if action == "close-duplicate" and JIRA_KEY.match(target):
        # Canonical ticket lives in Jira: GitHub can't link to it, so say so in the closing comment.
        gh("issue", "close", num, *base, "--reason", "not planned", "--comment", f"{comment}\n\nDuplicate of {target}")
        return f"closed as not planned, duplicate of {target} (cross-platform)", f"gh issue reopen {num} -R {repo}"
    if action == "close-duplicate":
        trepo, tnum = gh_ref(target, repo)
        dup_of = tnum if trepo == repo else f"https://github.com/{trepo}/issues/{tnum}"
        gh("issue", "comment", num, *base, "--body", comment)
        try:
            gh("issue", "close", num, *base, "--duplicate-of", dup_of)
        except RuntimeError as e:
            if "unknown flag" not in str(e):
                raise
            # Older gh: GitHub still marks it a duplicate from a "Duplicate of #N" comment.
            gh("issue", "comment", num, *base, "--body", f"Duplicate of {target if trepo != repo else '#' + tnum}")
            gh("issue", "close", num, *base, "--reason", "not planned")
        return f"closed as duplicate of {target}", f"gh issue reopen {num} -R {repo}"
    if action == "link":
        body = (comment + "\n\n" if comment else "") + f"Related to {target}"
        gh("issue", "comment", num, *base, "--body", body)
        return f"linked to {target} (comment)", "delete the comment in the GitHub UI"
    if action == "comment":
        gh("issue", "comment", num, *base, "--body", comment)
        return "commented", "delete the comment in the GitHub UI"
    if action == "move":
        gh("issue", "edit", num, *base, "--milestone", target)
        undo = f"gh issue edit {num} -R {repo} " + (f"--milestone '{prev['parent']}'" if prev["parent"] else "--remove-milestone")
        return f"milestone -> {target}", undo
    if action == "relabel":
        add, remove = parse_relabel(target)
        args = [x for l in add for x in ("--add-label", l)] + [x for l in remove for x in ("--remove-label", l)]
        gh("issue", "edit", num, *base, *args)
        inverse = [f"--remove-label '{l}'" for l in add] + [f"--add-label '{l}'" for l in remove]
        return f"labels {target}", f"gh issue edit {num} -R {repo} " + " ".join(inverse)
    if action in ("unassign", "reassign"):
        old = [a for a in prev["assignee"].split(";") if a]
        args = [x for a in old for x in ("--remove-assignee", a)]
        if action == "reassign":
            args += ["--add-assignee", target]
        if args:
            gh("issue", "edit", num, *base, *args)
        undo = f"gh issue edit {num} -R {repo} " + " ".join(f"--add-assignee {a}" for a in old)
        return ("unassigned" if action == "unassign" else f"assigned to {target}"), undo
    raise ValueError(action)


# ---------------------------------------------------------------- Jira

class Jira:
    def __init__(self, transition_name, epic_field):
        self.url = os.environ.get("JIRA_URL", "").rstrip("/")
        if not self.url:
            sys.exit("Set JIRA_URL (and JIRA_EMAIL + JIRA_API_TOKEN, or JIRA_PAT) to act on Jira tickets.")
        if os.environ.get("JIRA_PAT"):
            self.auth = f"Bearer {os.environ['JIRA_PAT']}"
            self.cloud = False
        elif os.environ.get("JIRA_EMAIL") and os.environ.get("JIRA_API_TOKEN"):
            token = base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
            self.auth = f"Basic {token}"
            self.cloud = True
        else:
            sys.exit("Set JIRA_EMAIL + JIRA_API_TOKEN (Cloud) or JIRA_PAT (Data Center).")
        self.transition_name = transition_name
        self.epic_field = epic_field

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            f"{self.url}/rest/api/2/{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": self.auth, "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} {method} {path}: {e.read().decode(errors='replace')[:300]}")

    def state(self, key):
        f = self.call("GET", f"issue/{key}?fields=updated,status,assignee,labels,parent")["fields"]
        assignee = f.get("assignee") or {}
        return {
            "updated": (f.get("updated") or "")[:10], "status": f["status"]["name"],
            "done": f["status"].get("statusCategory", {}).get("key") == "done",
            "assignee": assignee.get("accountId") or assignee.get("name") or "",
            "labels": ";".join(f.get("labels") or []), "parent": (f.get("parent") or {}).get("key", ""),
        }

    def close(self, key, resolution):
        transitions = self.call("GET", f"issue/{key}/transitions")["transitions"]
        if self.transition_name:
            pick = [t for t in transitions if t["name"].lower() == self.transition_name.lower()]
        else:
            pick = [t for t in transitions if t.get("to", {}).get("statusCategory", {}).get("key") == "done"]
        if not pick:
            names = ", ".join(t["name"] for t in transitions) or "none"
            raise Skip(f"no closing transition available (available: {names}); pass --jira-close-transition")
        tid = pick[0]["id"]
        name = JIRA_RESOLUTIONS.get(resolution or "done", resolution)
        try:
            self.call("POST", f"issue/{key}/transitions", {"transition": {"id": tid}, "fields": {"resolution": {"name": name}}})
            return f"transitioned '{pick[0]['name']}', resolution {name}"
        except RuntimeError as e:
            if "HTTP 400" not in str(e):
                raise
            # Resolution isn't on this workflow's transition screen; close without it.
            self.call("POST", f"issue/{key}/transitions", {"transition": {"id": tid}})
            return f"transitioned '{pick[0]['name']}' (resolution not settable on this workflow)"

    def user(self, who):
        return {"accountId": who} if self.cloud else {"name": who}

    def apply(self, row, prev):
        key, action, target, comment = row["key"], row["action"], row["target"], row["comment"]
        reopen = f"transition {key} back to '{prev['status']}' in Jira"
        if action == "close":
            self.call("POST", f"issue/{key}/comment", {"body": comment})
            return self.close(key, row["resolution"]), reopen
        if action in ("close-duplicate", "link") and not JIRA_KEY.match(target):
            # Target is a GitHub issue: Jira can't link to it natively, so reference it in a comment.
            phrase = "Duplicate of" if action == "close-duplicate" else "Related to"
            self.call("POST", f"issue/{key}/comment", {"body": f"{comment}\n\n{phrase} {target}".strip()})
            if action == "link":
                return f"referenced {target} (cross-platform comment)", "delete the comment in Jira"
            return f"duplicate of {target} (cross-platform); " + self.close(key, "duplicate"), reopen
        if action == "close-duplicate":
            # The inwardIssue takes the outward phrase: <key> "duplicates" <target>.
            self.call("POST", "issueLink", {"type": {"name": "Duplicate"}, "inwardIssue": {"key": key}, "outwardIssue": {"key": target}})
            self.call("POST", f"issue/{key}/comment", {"body": comment})
            return f"linked as duplicate of {target}; " + self.close(key, "duplicate"), reopen + "; delete the Duplicate link"
        if action == "link":
            self.call("POST", "issueLink", {"type": {"name": "Relates"}, "inwardIssue": {"key": key}, "outwardIssue": {"key": target}})
            if comment:
                self.call("POST", f"issue/{key}/comment", {"body": comment})
            return f"linked (relates) to {target}", "delete the link in Jira"
        if action == "comment":
            self.call("POST", f"issue/{key}/comment", {"body": comment})
            return "commented", "delete the comment in Jira"
        if action == "move":
            field = self.epic_field or "parent"
            value = target if self.epic_field else {"key": target}
            self.call("PUT", f"issue/{key}", {"fields": {field: value}})
            return f"{field} -> {target}", f"set {field} back to '{prev['parent'] or 'empty'}'"
        if action == "relabel":
            add, remove = parse_relabel(target)
            self.call("PUT", f"issue/{key}", {"update": {"labels": [{"add": l} for l in add] + [{"remove": l} for l in remove]}})
            return f"labels {target}", f"relabel {key} with the inverse of '{target}'"
        if action in ("unassign", "reassign"):
            self.call("PUT", f"issue/{key}", {"fields": {"assignee": None if action == "unassign" else self.user(target)}})
            return ("unassigned" if action == "unassign" else f"assigned to {target}"), f"reassign {key} to '{prev['assignee'] or 'nobody'}'"
        raise ValueError(action)


# ---------------------------------------------------------------- common

def parse_relabel(target):
    parts = [p.strip() for p in target.split(";") if p.strip()]
    bad = [p for p in parts if p[0] not in "+-"]
    if bad:
        raise ValueError(f"relabel target must look like '+label;-label', got '{target}'")
    return [p[1:] for p in parts if p[0] == "+"], [p[1:] for p in parts if p[0] == "-"]


def platform(key, backlog):
    if key in backlog:
        return backlog[key]["source"]
    if GH_KEY.match(key):
        return "github"
    if JIRA_KEY.match(key):
        return "jira"
    return ""


def validate(rows, backlog):
    problems = []
    for n, r in enumerate(rows, start=2):
        a = r["action"]
        if a not in ACTIONS:
            problems.append(f"line {n}: unknown action '{a}'")
        if a in NEEDS_TARGET and not r["target"]:
            problems.append(f"line {n}: {a} needs a target")
        if a in NEEDS_COMMENT and not r["comment"]:
            problems.append(f"line {n}: {a} needs a comment explaining why (it is what the reporter sees)")
        if not platform(r["key"], backlog):
            problems.append(f"line {n}: cannot tell whether '{r['key']}' is Jira or GitHub")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("actions", help="actions CSV")
    ap.add_argument("--backlog", help="normalized backlog CSV the actions were proposed from (enables the changed-since check)")
    ap.add_argument("--execute", action="store_true", help="actually make changes (default is a dry run)")
    ap.add_argument("--only", action="append", default=[], help="only this key (repeatable)")
    ap.add_argument("--limit", type=int, help="stop after this many changes (use 1 for a canary run)")
    ap.add_argument("--allow-changed", action="store_true", help="act even if the ticket changed after the snapshot")
    ap.add_argument("--audit", help="audit log CSV (default: audit-log.csv next to the actions file)")
    ap.add_argument("--jira-close-transition", default="", help="Jira transition name to close with (default: first one into a Done category)")
    ap.add_argument("--jira-epic-field", default="", help="custom field for Epic Link on Jira Data Center (default: parent)")
    args = ap.parse_args()

    with open(args.actions, newline="", encoding="utf-8-sig") as f:
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    backlog = {}
    if args.backlog:
        with open(args.backlog, newline="", encoding="utf-8-sig") as f:
            backlog = {t["key"]: t for t in csv.DictReader(f)}

    approved = [r for r in rows if r.get("approved", "").lower() in ("yes", "y", "true", "approved")]
    if args.only:
        approved = [r for r in approved if r["key"] in args.only]
    problems = validate(approved, backlog)
    if problems:
        sys.exit("Fix these rows first:\n  " + "\n  ".join(problems))
    pending = len(rows) - len([r for r in rows if r.get("approved", "").lower() in ("yes", "y", "true", "approved", "no", "n", "false")])
    print(f"{len(rows)} proposed, {len(approved)} approved to run" + (f", {pending} still awaiting a decision" if pending else ""))

    if not args.execute:
        for r in approved:
            extra = f" -> {r['target']}" if r["target"] else ""
            res = f" [{r['resolution']}]" if r["resolution"] else ""
            print(f"  DRY RUN  {platform(r['key'], backlog):<6} {r['key']:<24} {r['action']}{extra}{res}")
            if r["comment"]:
                print(f"           comment: {r['comment'][:110]}")
        print("\nNothing changed. Re-run with --execute (try --limit 1 first) to apply.")
        return

    jira = Jira(args.jira_close_transition, args.jira_epic_field) if any(platform(r["key"], backlog) == "jira" and r["action"] != "keep" for r in approved) else None
    audit_path = args.audit or os.path.join(os.path.dirname(os.path.abspath(args.actions)), "audit-log.csv")
    new_file = not os.path.exists(audit_path)
    touched, changes, tally = set(), 0, {}
    with open(audit_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=AUDIT_COLS)
        if new_file:
            w.writeheader()
        for r in approved:
            if args.limit is not None and changes >= args.limit:
                break
            entry = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "key": r["key"], "action": r["action"],
                     "target": r["target"], "previous": "", "undo": ""}
            try:
                if r["action"] == "keep":
                    entry.update(result="ok", detail="kept: " + (r["reason"] or "reviewed"))
                else:
                    src = platform(r["key"], backlog)
                    prev = gh_state(r["key"]) if src == "github" else jira.state(r["key"])
                    entry["previous"] = json.dumps(prev, ensure_ascii=False)
                    snap = backlog.get(r["key"], {}).get("updated", "")
                    if snap and prev["updated"] > snap and r["key"] not in touched and not args.allow_changed:
                        raise Skip(f"changed since snapshot ({snap} -> {prev['updated']}); re-triage or pass --allow-changed")
                    if prev["done"] and r["action"] in ("close", "close-duplicate"):
                        raise Skip(f"already closed ({prev['status']})")
                    detail, undo = gh_apply(r, prev) if src == "github" else jira.apply(r, prev)
                    entry.update(result="ok", detail=detail, undo=undo)
                    touched.add(r["key"])
                    changes += 1
            except Skip as e:
                entry.update(result="skipped", detail=str(e))
            except (RuntimeError, ValueError) as e:
                entry.update(result="failed", detail=str(e))
            w.writerow(entry)
            f.flush()
            tally[entry["result"]] = tally.get(entry["result"], 0) + 1
            print(f"  {entry['result'].upper():<8} {r['key']:<24} {r['action']:<16} {entry['detail'][:90]}")
    print(f"\n{', '.join(f'{k} {v}' for k, v in sorted(tally.items())) or 'nothing run'}. Audit log: {audit_path}")
    if tally.get("failed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
