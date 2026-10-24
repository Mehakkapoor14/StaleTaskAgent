# Action Reference

`actions.csv` columns: `key,action,target,resolution,comment,reason,source,confidence,approved`

- `key` — Jira key (`PORT-12`) or GitHub `owner/repo#123`.
- `comment` — posted on the ticket; required for `close`, `close-duplicate`, `comment`.
- `reason` — internal rationale for the reviewer; not posted.
- `source` — which pass proposed it (`stale-triage`, `duplicate-detection`, `alignment-check`, `manual`).
- `confidence` — `high` / `medium` / `low`.
- `approved` — `yes` runs; `no` or blank does not.

## What each action does

| Action | `target` | Jira (REST API v2) | GitHub (`gh`) |
|---|---|---|---|
| `keep` | — | nothing (audit row only) | nothing (audit row only) |
| `close` | — | comment, then the first transition into a Done-category status (or `--jira-close-transition NAME`) with resolution from `resolution` | `gh issue close --reason completed` if resolution is `done`/blank, else `not planned`, with the comment |
| `close-duplicate` | canonical key | `Duplicate` link (this *duplicates* target), comment, close with resolution Duplicate | comment, then `gh issue close --duplicate-of N` (falls back to a "Duplicate of #N" comment + close as not planned on older `gh`) |
| `link` | other key | `Relates` link, plus comment if given | comment "Related to <target>" (GitHub has no generic issue links) |
| `comment` | — | add comment | `gh issue comment` |
| `move` | epic key / milestone title | set `parent` (or `--jira-epic-field` on Data Center) | `gh issue edit --milestone` |
| `relabel` | `+add;-remove` | label add/remove update | `--add-label` / `--remove-label` |
| `unassign` | — | assignee → empty | remove current assignees |
| `reassign` | user | Cloud: accountId; Data Center: username | GitHub login |

### Resolutions

`resolution` accepts `done`, `wont-do`, `obsolete`, `cannot-reproduce`, `duplicate`, or an exact Jira resolution name (e.g. `Won't Fix`). Defaults map to Jira's standard names: Done, Won't Do, Cannot Reproduce, Duplicate. If a Jira workflow doesn't show the resolution field on its closing transition, the script closes without it and says so in the audit log; set the resolution in Jira manually if it matters for reporting.

### Cross-platform targets

When `close-duplicate` or `link` pairs a Jira ticket with a GitHub issue, neither system can link natively. The script adds "Duplicate of <target>" / "Related to <target>" to the comment. Put the target's full URL in `comment` so people can click through.

### Jira link direction

For `issueLink`, the script sends `inwardIssue` = the ticket being closed and `outwardIssue` = the canonical one, so the closed ticket reads "duplicates <canonical>" and the canonical reads "is duplicated by <closed>". Jira's API naming here is easy to get backwards, and some instances rename link types. That is one reason the canary run exists: check the first duplicate in the Jira UI before running the batch.

## Performing actions through Atlassian MCP

When Jira is reached through MCP tools rather than an API token, follow the same semantics:

1. Fetch the issue; if its `updated` date is later than the snapshot's, skip it and record `skipped`.
2. Post the comment first, then link, then transition. If the transition fails, the comment still explains the intent and nothing is half-hidden.
3. Append to `pm/backlog/audit-log.csv`: `timestamp,key,action,target,result,detail,previous,undo`, with `previous` holding the status/assignee/labels/parent before the change.
