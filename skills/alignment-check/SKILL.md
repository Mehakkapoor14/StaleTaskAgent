---
name: alignment-check
description: Check whether a Jira or GitHub Issues backlog actually serves the project's goals — flag tickets that are out of scope, under the wrong or a closed epic, unparented, mis-prioritized against objectives, or mislabeled — and propose re-parenting, re-prioritizing, relabeling, or closing. Use whenever the user asks if the backlog matches the roadmap, OKRs, charter, strategy, or quarterly goals; mentions scope creep, misaligned or orphan tickets, "why are we working on this?", backlog-to-roadmap traceability, or preparing for quarterly/PI planning — even if they only share goals and a ticket export.
---

# Alignment Check

A backlog drifts away from its goals one reasonable-looking ticket at a time. Work for a retired feature lingers, a pet project gets a High priority, a critical security finding sits with no epic and so never shows up in planning. Stale and duplicate tickets are clutter; misaligned tickets are worse, because the team spends real effort on work that doesn't count toward the goals while the work that does count gets crowded out. Your job is to trace every open ticket back to a goal, and to say plainly when it can't be traced.

## Workflow

1. **Get the goals.** Use, in order of preference:
   - `pm/charter.md` (from the **project-charter** skill): objectives, success criteria, scope in/out.
   - A goals/OKR/roadmap document the user provides, saved to `pm/backlog/goals.md`.
   - The open epics themselves, if nothing else exists. Say so in the report, because then you can only check structure, not strategy.

   Extract a numbered list of **objectives** and an explicit **out-of-scope** list. If the out-of-scope list is empty, propose likely entries from what the goals imply and confirm them with the user. Out-of-scope items are where most of the findings come from.

2. **Get a compact view of the backlog:**
   ```bash
   python3 scripts/alignment_digest.py pm/backlog/backlog.csv --flags-out pm/backlog/alignment-flags.csv > pm/backlog/alignment-digest.md
   ```
   The digest groups open tickets by epic/milestone with one line each and adds structural flags: `no_parent`, `parent_closed`, `parent_missing`, `high_no_parent`, `no_labels`. For big backlogs, review one epic at a time with `--epic KEY` (or `--epic none` for unparented tickets).

3. **Check alignment at two levels**, using `references/alignment-rubric.md` (read it first):
   - **Epic level.** Does each open epic map to an objective? An epic that maps to nothing, or to an out-of-scope item, makes all its children misaligned at once. Report this once at the epic level instead of N times.
   - **Ticket level.** For each ticket: which objective does it serve (cite the number), or none? Is it in the right epic? Does its priority match the importance of its objective? Do its labels/components match its content?

4. **Classify and propose actions:**

   | Finding | Proposed action |
   |---|---|
   | Out of scope (matches an out-of-scope item) | `close` (`wont-do`) with the charter reference, or `comment` to the reporter if they may know something the charter doesn't |
   | Serves an objective but under the wrong/closed/no epic | `move` → the right epic (Jira parent) or milestone (GitHub) |
   | Serves no objective but isn't out of scope (nice-to-have) | `relabel` (e.g. `+icebox`) or `comment` asking the product owner. Don't close valuable ideas just because they're unplanned |
   | Priority doesn't match its objective | Flag in the report. Priority changes are a product owner's call, so propose them rather than write them as actions |
   | High-importance work with no home (e.g. security finding, legal deadline, no epic) | Escalate: `comment` to the owner and flag as a planning gap. These are the most valuable findings |
   | Wrong labels/components | `relabel` with `+add;-remove` |

5. **Write the proposed actions** to `pm/backlog/actions.csv` (append; create with header if missing):
   `key,action,target,resolution,comment,reason,source,confidence,approved`
   with `source=alignment-check`; `reason` names the objective or out-of-scope item ("Out of scope: native mobile apps (charter §Scope)").

6. **Report traceability.** Give, per objective: the number of open tickets serving it, how many are in progress, and whether anything critical to it is missing or unparented. Then give the share of open tickets that trace to no objective. An objective with zero tickets is a finding in its own right: either the plan is missing work or the objective is quietly being dropped.

## Guardrails

- Goals documents go out of date. If many tickets contradict a goal in the same way (e.g. 20 mobile tickets created last month), the charter may be what's stale. Raise it with the user instead of proposing 20 closures.
- Don't infer strategy from priority fields; they are often unmaintained.
- Recommend only; **cleanup-apply** executes approved rows.

## Output

- `pm/backlog/alignment-digest.md`, `pm/backlog/alignment-flags.csv` — script output.
- Rows appended to `pm/backlog/actions.csv`.
- Traceability summary in chat, or in the review report when run by **backlog-cleanup**.

## Connects to

- **project-charter** (ProjectManagementSkills) — the source of objectives and scope.
- **stale-triage** — tickets under closed epics show up in both passes; agree one action per ticket.
- **status-report** (ProjectManagementSkills) — "share of backlog aligned to objectives" is a useful health measure for steering updates.
