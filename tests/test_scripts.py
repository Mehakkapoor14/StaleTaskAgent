#!/usr/bin/env python3
"""End-to-end tests for the skill scripts against the synthetic backlog in examples/.
Standard library only. Run from the repo root:  python3 -m unittest discover tests

The fixtures plant known problems (see examples/README.md); these tests check each script
finds them, and that apply_actions.py talks to fake `gh` and fake Jira correctly.
"""
import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples")
SKILLS = os.path.join(ROOT, "skills")
TODAY = "2026-10-24"


def run(script, *args, env=None, check=True):
    p = subprocess.run([sys.executable, os.path.join(SKILLS, script), *args], capture_output=True, text=True, env=env)
    if check and p.returncode != 0:
        raise AssertionError(f"{script} failed:\n{p.stdout}\n{p.stderr}")
    return p


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.backlog = os.path.join(cls.tmp, "backlog.csv")
        run("backlog-ingest/scripts/normalize.py", os.path.join(EX, "jira-export.csv"), os.path.join(EX, "github-issues.json"),
            "--jira-url", "https://acme.atlassian.net", "--out", cls.backlog)
        cls.tickets = {t["key"]: t for t in read(cls.backlog)}

    def test_normalize(self):
        t = self.tickets
        self.assertEqual(len(t), 28)
        self.assertEqual(t["PORT-14"]["epic"], "PORT-3")              # numeric Parent id mapped to key
        self.assertEqual(t["PORT-14"]["epic_status_category"], "done")
        self.assertEqual(t["PORT-20"]["sprint_count"], "4")           # repeated Sprint columns
        self.assertEqual(t["PORT-21"]["links"], "Blocks:inward:PORT-22:done")
        self.assertEqual(t["PORT-17"]["updated"], "2026-08-01")       # Jira dd/Mon/yy dates
        self.assertEqual(t["acme/portal-web#108"]["status_category"], "in_progress")
        self.assertEqual(t["acme/portal-web#104"]["status_category"], "done")
        self.assertEqual(t["PORT-10"]["url"], "https://acme.atlassian.net/browse/PORT-10")

    def test_normalize_jira_json(self):
        page = {"issues": [{"key": "OPS-7", "self": "https://acme.atlassian.net/rest/api/3/issue/1007", "fields": {
            "summary": "Rotate TLS certs", "issuetype": {"name": "Task"},
            "status": {"name": "Waiting for vendor", "statusCategory": {"key": "indeterminate"}},
            "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Certs expire in March."}]}]},
            "parent": {"key": "OPS-1", "fields": {"status": {"name": "Closed", "statusCategory": {"key": "done"}}}},
            "customfield_10020": [{"id": 1, "name": "Ops 3", "state": "closed", "boardId": 4}, {"id": 2, "name": "Ops 4", "state": "active", "boardId": 4}],
            "issuelinks": [{"type": {"name": "Blocks"}, "inwardIssue": {"key": "OPS-2", "fields": {"status": {"name": "Done", "statusCategory": {"key": "done"}}}}}],
            "comment": {"total": 1, "comments": [{"created": "2026-03-02T10:00:00.000+0000", "author": {"displayName": "Ana"}, "body": "Vendor contacted."}]},
            "created": "2026-01-05T09:00:00.000+0000", "updated": "2026-03-02T10:00:00.000+0000", "labels": ["infra"]}}]}
        src, out = os.path.join(self.tmp, "jira.json"), os.path.join(self.tmp, "jira-backlog.csv")
        with open(src, "w") as f:
            json.dump(page, f)
        run("backlog-ingest/scripts/normalize.py", src, "--out", out)
        t = read(out)[0]
        self.assertEqual((t["status_category"], t["epic"], t["epic_status_category"]), ("in_progress", "OPS-1", "done"))
        self.assertEqual((t["sprints"], t["sprint_count"]), ("Ops 3;Ops 4", "2"))
        self.assertEqual(t["links"], "Blocks:inward:OPS-2:done")
        self.assertEqual(t["description"], "Certs expire in March.")
        self.assertEqual(t["url"], "https://acme.atlassian.net/browse/OPS-7")
        self.assertEqual(t["last_comment_at"], "2026-03-02")

    def test_stale_signals(self):
        out = os.path.join(self.tmp, "signals.csv")
        run("stale-triage/scripts/stale_signals.py", self.backlog, "--prs", os.path.join(EX, "merged-prs.json"),
            "--today", TODAY, "--inactive", "Dana Lee;dlee", "--out", out)
        sig = {r["key"]: r["signals"] for r in read(out)}
        self.assertIn("merged_pr(closes", sig["PORT-17"])
        self.assertIn("zombie_wip", sig["PORT-17"])
        self.assertIn("merged_pr(closes", sig["acme/portal-web#105"])
        self.assertIn("blockers_resolved(PORT-22)", sig["PORT-21"])
        self.assertIn("parent_closed(PORT-3)", sig["PORT-14"])
        self.assertIn("carryover(4 sprints)", sig["PORT-20"])
        self.assertIn("past_due", sig["PORT-27"])
        self.assertIn("inactive_assignee", sig["PORT-18"])
        self.assertIn("thin", sig["PORT-19"])
        self.assertNotIn("PORT-10", sig)                              # healthy ticket stays quiet
        self.assertNotIn("PORT-22", sig)                              # closed tickets are not triaged

    def test_duplicates(self):
        out = os.path.join(self.tmp, "dups.csv")
        run("duplicate-detection/scripts/find_duplicates.py", self.backlog, "--out", out)
        pairs = {frozenset((r["a"], r["b"])): r for r in read(out)}
        for a, b in [("PORT-12", "PORT-13"), ("acme/portal-web#101", "acme/portal-web#102"), ("PORT-10", "acme/portal-web#103")]:
            self.assertIn(frozenset((a, b)), pairs, f"missed {a} ~ {b}")
        self.assertEqual(pairs[frozenset(("PORT-21", "PORT-22"))]["already_linked"], "yes")
        self.assertNotIn(frozenset(("PORT-1", "PORT-10")), pairs)      # parent/child skipped

    def test_alignment_digest(self):
        out = os.path.join(self.tmp, "flags.csv")
        p = run("alignment-check/scripts/alignment_digest.py", self.backlog, "--flags-out", out)
        flags = {(r["key"], r["flag"]) for r in read(out)}
        self.assertIn(("PORT-18", "high_no_parent"), flags)
        self.assertIn(("PORT-15", "parent_closed"), flags)
        self.assertIn("## PORT-3 — Legacy reporting dashboard [Done]", p.stdout)

    def test_apply_dry_run_changes_nothing(self):
        p = run("cleanup-apply/scripts/apply_actions.py", os.path.join(EX, "actions.example.csv"), "--backlog", self.backlog)
        self.assertIn("7 approved to run", p.stdout)
        self.assertIn("Nothing changed", p.stdout)

    def test_apply_rejects_bad_rows(self):
        bad = os.path.join(self.tmp, "bad.csv")
        with open(bad, "w") as f:
            f.write("key,action,target,resolution,comment,reason,source,confidence,approved\nPORT-11,close,,,,,,,yes\n")
        p = run("cleanup-apply/scripts/apply_actions.py", bad, check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("needs a comment", p.stderr)


class FakeJira(BaseHTTPRequestHandler):
    calls = []
    updated = {}

    def log_message(self, *a):
        pass

    def reply(self, code, body=None):
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakeJira.calls.append(("GET", self.path, None))
        if self.path.endswith("/transitions"):
            return self.reply(200, {"transitions": [{"id": "11", "name": "Start", "to": {"statusCategory": {"key": "indeterminate"}}},
                                                    {"id": "31", "name": "Close", "to": {"statusCategory": {"key": "done"}}}]})
        key = self.path.split("/issue/")[1].split("?")[0]
        return self.reply(200, {"fields": {"updated": FakeJira.updated.get(key, "2026-01-01") + "T10:00:00.000+0000",
                                           "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                                           "assignee": None, "labels": [], "parent": None}})

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else None

    def do_POST(self):
        body = self.body()
        FakeJira.calls.append(("POST", self.path, body))
        if self.path.endswith("/transitions") and "fields" in body and "PORT-14" in self.path:
            return self.reply(400, {"errors": {"resolution": "Field 'resolution' cannot be set."}})
        return self.reply(201 if self.path.endswith(("/comment", "issueLink")) else 204, {} if self.path.endswith("/comment") else None)

    def do_PUT(self):
        FakeJira.calls.append(("PUT", self.path, self.body()))
        return self.reply(204)


FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
if sys.argv[1:3] == ["issue", "view"]:
    print(json.dumps({"state": "OPEN", "updatedAt": os.environ.get("FAKE_GH_UPDATED", "2026-01-01") + "T00:00:00Z",
                      "assignees": [{"login": "dlee"}], "labels": [], "milestone": None}))
'''


class Execute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.backlog = os.path.join(self.tmp, "backlog.csv")
        run("backlog-ingest/scripts/normalize.py", os.path.join(EX, "jira-export.csv"), os.path.join(EX, "github-issues.json"), "--out", self.backlog)
        bin_dir = os.path.join(self.tmp, "bin")
        os.mkdir(bin_dir)
        with open(os.path.join(bin_dir, "gh"), "w") as f:
            f.write(FAKE_GH.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
        os.chmod(os.path.join(bin_dir, "gh"), 0o755)
        self.server = HTTPServer(("127.0.0.1", 0), FakeJira)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        FakeJira.calls, FakeJira.updated = [], {}
        self.gh_log = os.path.join(self.tmp, "gh.log")
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"], FAKE_GH_LOG=self.gh_log,
                        JIRA_URL=f"http://127.0.0.1:{self.server.server_port}", JIRA_EMAIL="pm@example.com", JIRA_API_TOKEN="x")
        self.env.pop("JIRA_PAT", None)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def apply(self, *extra, check=True):
        return run("cleanup-apply/scripts/apply_actions.py", os.path.join(EX, "actions.example.csv"), "--backlog", self.backlog,
                   "--audit", os.path.join(self.tmp, "audit.csv"), "--execute", *extra, env=self.env, check=check)

    def gh_calls(self):
        with open(self.gh_log) as f:
            return [json.loads(line) for line in f]

    def test_execute_all(self):
        p = self.apply()
        self.assertIn("ok 7", p.stdout)
        gh = self.gh_calls()
        self.assertIn(["issue", "close", "105", "-R", "acme/portal-web", "--reason", "completed", "--comment", "Fixed by #210 (merged 2026-08-05)."], gh)
        self.assertIn(["issue", "close", "102", "-R", "acme/portal-web", "--duplicate-of", "101"], gh)
        posts = [(path, body) for m, path, body in FakeJira.calls if m == "POST"]
        self.assertIn(("/rest/api/2/issueLink", {"type": {"name": "Duplicate"}, "inwardIssue": {"key": "PORT-13"}, "outwardIssue": {"key": "PORT-12"}}), posts)
        self.assertIn(("/rest/api/2/issue/PORT-17/transitions", {"transition": {"id": "31"}, "fields": {"resolution": {"name": "Done"}}}), posts)
        # PORT-14's workflow rejects the resolution field; the script retries without it.
        self.assertIn(("/rest/api/2/issue/PORT-14/transitions", {"transition": {"id": "31"}}), posts)
        audit = read(os.path.join(self.tmp, "audit.csv"))
        self.assertEqual({r["result"] for r in audit}, {"ok"})
        self.assertTrue(all(r["undo"] for r in audit if r["action"] in ("close", "close-duplicate")))

    def test_skips_tickets_changed_since_snapshot(self):
        FakeJira.updated["PORT-17"] = "2026-10-23"     # someone touched it after the export
        p = self.apply("--only", "PORT-17")
        self.assertIn("SKIPPED", p.stdout)
        self.assertFalse([c for c in FakeJira.calls if c[0] == "POST"])

    def test_limit_is_a_canary(self):
        self.apply("--limit", "1")
        audit = read(os.path.join(self.tmp, "audit.csv"))
        self.assertEqual(len([r for r in audit if r["action"] != "keep"]), 1)


if __name__ == "__main__":
    unittest.main()
