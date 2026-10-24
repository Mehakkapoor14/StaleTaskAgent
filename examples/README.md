# Example backlog

A synthetic "Customer Portal Relaunch" project used for demos and by `tests/test_scripts.py`. Names, tickets, and PRs are invented.

| File | What it is |
|---|---|
| `jira-export.csv` | 20 Jira tickets in Jira's CSV export format (repeated Labels/Sprint/Comment columns, numeric `Parent` ids, `dd/Mon/yy` dates) |
| `github-issues.json` | 8 issues from `acme/portal-web` in `gh issue list --json` format |
| `merged-prs.json` | 3 PRs in `gh pr list --json` format (2 merged) |
| `goals.md` | Objectives and out-of-scope list, standing in for `pm/charter.md` |
| `actions.example.csv` | A partially approved action list, showing the format cleanup-apply reads |

Snapshot date for reproducible runs: `--today 2026-10-24`. Inactive people: `Dana Lee` (Jira) / `dlee` (GitHub).

## Planted problems

| Problem | Tickets | Found by |
|---|---|---|
| Done but never closed (merged closing PR) | PORT-17, acme/portal-web#105 | stale-triage `merged_pr` |
| Zombie in progress | PORT-17, #108 | stale-triage `zombie_wip` |
| Unblocked but forgotten | PORT-21 (blocker PORT-22 is done) | stale-triage `blockers_resolved` |
| Chronic carry-over | PORT-20 (4 sprints) | stale-triage `carryover` |
| Inactive owner on high-stakes work | PORT-18 (pen-test finding), #108 | stale-triage `inactive_assignee` |
| Past a legal deadline, no epic | PORT-27 | stale-triage `past_due`, alignment-check `high_no_parent` |
| Thin, old, unowned | PORT-19, #107 | stale-triage `thin`, `unowned_old` |
| Duplicates, different wording | PORT-12 ~ PORT-13; #101 ~ #102 | duplicate-detection |
| Duplicates across Jira and GitHub | PORT-10 ~ PORT-11 ~ #103 | duplicate-detection (3-ticket cluster) |
| Under a closed epic / retired feature | PORT-14, PORT-15 (epic PORT-3) | alignment-check `parent_closed` + goals |
| Out of scope per goals | PORT-16 (mobile), #106 (IE11), PORT-14/15 (legacy dashboard) | alignment-check (judgment) |
| Healthy — should not be flagged | PORT-10, PORT-24 | — |
