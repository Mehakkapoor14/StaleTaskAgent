---
name: backlog-cleanup
description: Run a full backlog health review and cleanup for Jira and/or GitHub Issues — ingest tickets, find stale, duplicate, and misaligned ones, reconcile the findings into one decision per ticket, and produce a review report and an approval-ready action list. Use whenever the user wants to clean up, groom, refine, triage, audit, prune, or "declutter" a backlog or issue tracker, prepare for backlog refinement or quarterly/PI planning, measure backlog health, set up a recurring cleanup, or says things like "our Jira is a mess" or "help me get the backlog under control".
---

# Backlog Cleanup

This is the end-to-end review: one snapshot, three lenses (stale, duplicate, misaligned), one decision per ticket, and a report a product owner can approve in a single sitting. The other skills each do one lens in depth; this one sequences them, resolves their disagreements, and frames the result for a human decision. Nothing is changed here. Approved actions go to **cleanup-apply**.

## Workflow

1. **Scope and context, in one batch of questions:**
   - Which Jira projects/JQL and/or GitHub repos?
   - Where are the goals (charter, OKRs, roadmap)? Check for `pm/charter.md` first.
   - Who has left or is inactive? Which labels/epics are deliberately parked?
   - Any tickets that must not be touched (customer escalations, audit evidence)?

   If the user wants results quickly, proceed with defaults and list your assumptions at the top of the report.

2. **Ingest** with **backlog-ingest** → `pm/backlog/backlog.csv` (plus merged PR files). Record the snapshot date.

3. **Run the three passes**, each appending rows to `pm/backlog/actions.csv`:
   1. **duplicate-detection** first: merging duplicates shrinks the set the other passes judge.
   2. **stale-triage** on what's left.
   3. **alignment-check** against the goals. If there are no goals, run only its structural checks and say so.

   For large backlogs (500+ open tickets), review the top-scored stale candidates, all duplicate clusters, and alignment epic by epic. Sample the long tail and report the sample size, rather than skimming everything shallowly.

4. **Reconcile to one decision per ticket.** Passes can disagree: stale-triage says "close as obsolete" while duplicate-detection says "close as duplicate of PORT-12". Keep one row per ticket (two only when the actions are compatible, like `unassign` plus `comment`). Precedence:
   1. **Duplicate** beats stale/obsolete: it tells readers where the work went.
   2. **Done** (merged PR) beats everything except duplicate.
   3. **Escalate/comment** beats close when any pass says the ticket is high-stakes.
   4. Otherwise keep the row with the stronger evidence, and fold the other pass's reason into it.

   Drop the rejected rows from `actions.csv`. Note conflicts you resolved in the report.

5. **Write the review report** from `templates/review.md` to `pm/backlog/review-YYYY-MM-DD.md`. Lead with the decision summary: how many actions, how many need approval, and the 3–5 findings that matter most (usually high-stakes work without owners, and systemic causes), not the bulk closes.

6. **Hand over for approval.** Tell the user how to approve: set `approved` to `yes` (or `no`) per row in `pm/backlog/actions.csv`, or tell you "approve all high-confidence closes" and you'll fill the column, showing them the list first. Then run **cleanup-apply**, starting with a one-ticket canary run.

7. **Record health metrics** in the report (see the template). They let the next review show the trend. If a previous `pm/backlog/review-*.md` exists, compare against it.

## Recurring cleanup

For a monthly or per-sprint cadence: the same workflow, but only flag tickets that are new candidates or whose situation changed since the last review (use the previous report's `keep` decisions, so a ticket deliberately kept isn't re-flagged without new evidence). If the user wants it automated, set it up as a scheduled agent that runs steps 2–5 and posts the report. Approval and apply stay manual.

## Output

- `pm/backlog/actions.csv` — reconciled, one decision per ticket, awaiting approval.
- `pm/backlog/review-YYYY-MM-DD.md` — the report.

## Connects to

- **backlog-ingest**, **duplicate-detection**, **stale-triage**, **alignment-check** — the passes.
- **cleanup-apply** — executes approved rows.
- **project-charter**, **status-report**, **raid-log** (ProjectManagementSkills) — goals in; health metrics and unowned high-stakes work out.
