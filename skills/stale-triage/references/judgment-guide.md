# Stale Ticket Judgment Guide

Signals say *where to look*. This guide covers *how to decide*. When the evidence is mixed, choose the more reversible action: a comment instead of a close, a close instead of a delete (cleanup-apply never deletes).

## Reading the evidence

Check these in order. The first strong piece of evidence usually decides the class.

1. **Shipped work.** A merged PR that *closes/fixes/resolves* the ticket is strong evidence it's done. A PR that only *mentions* it ("part of PORT-10") is not: the ticket may cover more than that PR did. Check the ticket's acceptance criteria against the PR title/body.
2. **The last comments.** These often say outright what happened: "deployed Friday", "no longer needed after the redesign", "waiting on legal". Recent comments from customers, support, or stakeholders mean the ticket is alive.
3. **The parent.** A ticket under a closed epic is either leftover scope (obsolete), or valid work that lost its home (it needs a new parent, which is alignment-check's job).
4. **Links.** "Is blocked by X" where X is done means it's unblocked and someone should know. "Duplicates" / "is duplicated by" links point to where the work actually lives.
5. **People.** An inactive assignee means the ticket needs an owner. It does not mean the work is invalid.
6. **Time.** Time is the weakest signal. Use it only to rank candidates, never as the reason for closing.

## Traps that cause false positives

| Trap | What it looks like | What to do |
|---|---|---|
| Bulk edits | `updated` is recent but nobody has touched the content in months | Rely on `last_comment_at` and the content, not `updated` alone |
| Deliberate parking | Label like `icebox`, `someday`, `backlog-idea`; a "Parking lot" epic | `keep`, unless the team asked for parked items to be reviewed too |
| Long-lead items | Hardware, permits, procurement, legal, annual events | Judge against the expected lead time, not the sprint length |
| Recurring / reference tickets | "Quarterly access review", runbooks tracked as tickets | `keep`; suggest moving reference material to docs |
| Known-but-unprioritised bugs | Old, clear repro, nobody disputes it | Still valid. Don't close a real bug because nobody fixed it; at most relabel or lower priority |
| Hidden commitments | Customer name in the ticket, linked support case, contract or SLA reference | Never close silently; `comment` to the account owner |
| Regulated work | Security findings, audit items, legal/privacy, safety | Never close as stale; escalate with an owner and a date |

## Confidence

- **high**: direct evidence (merged closing PR, an explicit "no longer needed" comment from the owner, retired feature confirmed by a closed epic or charter).
- **medium**: strong circumstantial evidence (closed parent and no activity since; superseded by a newer ticket that clearly covers it).
- **low**: inference from signals alone. Low-confidence rows should almost always be `comment` actions, not closes.

## Writing the comment

The comment is posted on the ticket under the user's name and every watcher sees it. It should:

- State the specific reason, with a link or date: "PR #211 merged on 2026-08-20 upgraded the SDK to v5."
- Tell people how to object: "Reopen, or reply here, if anything is left."
- For questions, name a person and a date: "Sam: is this still needed? We'll close it on 2026-11-07 if there's no reply."
- Stay neutral. No blame ("nobody looked at this for a year"), no jargon about bots or scores.

Patterns:

- **Done:** "Closing as done: <evidence>. Reopen if <what would mean it isn't done>."
- **Obsolete:** "Closing: <what changed: feature retired / epic closed / decision>. If this is still needed for <new context>, please raise it there."
- **Needs owner:** "<Name>: this is still needed for <goal> but its assignee is no longer active. Can you take it or name an owner by <date>?"
- **Unclear:** "<Reporter>: can you add <what's missing: steps, expected result, who is affected> by <date>? Without it we'll close this as Won't Do; it can be reopened any time."
- **Unblocked:** "<Assignee>: the blocker <KEY> was resolved on <date>, so this can move forward. Still planned for <sprint/milestone>?"

## Systemic causes to look for

After judging the batch, look across it:

- Many zombie in-progress tickets under one person or team → overloaded, or work-in-progress limits not enforced.
- Many tickets owned by departed people → offboarding doesn't hand over tickets.
- Merged PRs not closing tickets → missing "Fixes KEY" convention or Jira–GitHub integration.
- Lots of thin tickets from one intake channel → that channel needs a ticket template.

Report these as recommendations. They are what stops the backlog from going stale again.
