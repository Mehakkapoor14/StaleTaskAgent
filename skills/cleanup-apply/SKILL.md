---
name: cleanup-apply
description: Safely apply human-approved backlog cleanup actions — close, close as duplicate, link, comment, re-parent, relabel, unassign, reassign — to Jira and/or GitHub Issues, with a dry run by default, a canary run, a changed-since-snapshot check, and an audit log with undo hints. Use whenever the user has approved (or wants to approve) cleanup actions from a backlog review, says "go ahead and close those", "apply the changes", "execute the cleanup", "merge those duplicates", or wants to undo or audit what a previous cleanup did.
---

# Cleanup Apply

This is the only skill that changes tickets, so it is deliberately conservative. A cleanup tool loses the team's trust the first time it closes a ticket that mattered, and it rarely gets that trust back. So: humans approve each row, the default run changes nothing, the first real run touches one ticket, anything modified since triage is skipped, and every change is logged with how to undo it.

## Workflow

1. **Check approvals.** Read `pm/backlog/actions.csv`. Only rows with `approved` = `yes` run. If the user approves in conversation ("approve all the high-confidence duplicates"), fill the column for exactly those rows, show the list, and get a "yes" before continuing. Never set `approved` on rows the user hasn't covered.

2. **Dry run** (no changes):
   ```bash
   python3 scripts/apply_actions.py pm/backlog/actions.csv --backlog pm/backlog/backlog.csv
   ```
   The script validates every approved row (known action, target present, closing comment present, platform identifiable) and prints the plan. Show the plan to the user.

3. **Check access.**
   - GitHub: `gh auth status` must show a token with `repo` scope for the target repos.
   - Jira: `JIRA_URL` plus `JIRA_EMAIL` + `JIRA_API_TOKEN` (Cloud) or `JIRA_PAT` (Data Center), set in the user's environment. Ask the user to export them in their shell (suggest `! export JIRA_API_TOKEN=...`); never write tokens into files or echo them.
   - *Atlassian MCP instead of a token:* skip the script for Jira rows and perform each approved action with the MCP tools, following `references/actions.md`. Do the same freshness check (re-read the ticket and skip it if it was updated after the snapshot), and append one row per action to `pm/backlog/audit-log.csv` in the same columns the script uses.

4. **Canary run:** one change, then have the user look at it in Jira/GitHub:
   ```bash
   python3 scripts/apply_actions.py pm/backlog/actions.csv --backlog pm/backlog/backlog.csv --execute --limit 1
   ```
   This catches workflow surprises: a closing transition with a different name (`--jira-close-transition "Resolve"`), a resolution field that isn't on the screen (the script retries without it and says so), link directions shown the wrong way round, or comment formatting. For a Jira duplicate, confirm the closed ticket shows "duplicates <canonical>".

5. **Full run:**
   ```bash
   python3 scripts/apply_actions.py pm/backlog/actions.csv --backlog pm/backlog/backlog.csv --execute
   ```
   Tickets updated after the snapshot are **skipped**, not overwritten: someone acted on them since triage, so they need a fresh look. Use `--allow-changed` only if the user confirms the changes were unrelated (e.g. a bulk label migration). Already-closed tickets are skipped for close actions. Use `--only KEY` (repeatable) to re-run specific rows.

6. **Report**: counts of ok/skipped/failed, every failure with its error, the skipped tickets and why, and the audit log path. Failures and skips go back to the user as a list, not buried in a summary.

## Undo

Each audit row records the ticket's previous state (`previous`, as JSON) and an `undo` hint, e.g. `gh issue reopen 102 -R acme/portal-web` or "transition PORT-14 back to 'To Do'". To undo a batch, read the audit log for the run's timestamps and reverse the rows in reverse order, after confirming with the user. Nothing is ever deleted, so every action can be reversed.

## Permissions and etiquette

- Comments post under the token owner's name and notify watchers. A run of 200 closes sends 200 notifications. For large batches, suggest telling the team beforehand.
- Closing someone else's ticket is a social act. Comments must say why and how to object (stale-triage and duplicate-detection write them that way; check rows written by hand).
- Respect API limits: the script runs sequentially, which suits batches of a few hundred. For more, split by `--only` lists or run in chunks.

## Output

- Changes in Jira/GitHub.
- `pm/backlog/audit-log.csv` — appended: `timestamp,key,action,target,result,detail,previous,undo`.

## Connects to

- **backlog-cleanup**, **stale-triage**, **duplicate-detection**, **alignment-check** — produce `actions.csv`.
- **backlog-ingest** — re-ingest after applying, so the next review starts from the cleaned state.
