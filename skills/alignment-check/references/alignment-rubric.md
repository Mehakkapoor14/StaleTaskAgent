# Alignment Rubric

## Mapping a ticket to an objective

A ticket **serves** an objective when finishing it moves a measurable success criterion of that objective, or removes something that blocks it. Ask: "If we finished only this ticket, which objective's number would change?"

| Strength | Test | Example (objective: "billing support tickets down 40%") |
|---|---|---|
| **Direct** | It is part of a deliverable the objective names | "Users can download invoices as PDF" |
| **Enabling** | The direct work can't ship or stay healthy without it | "Upgrade payment SDK before v4 is deprecated" |
| **Indirect** | Plausibly helps, but the link takes more than one step | "Refactor billing service" (only if it unblocks direct work; say which) |
| **None** | No credible link | "Dark mode for the portal" |

Record the strongest link and the objective number. "Indirect" tickets with High priority deserve a question: why is work this far from the goal urgent?

Some work keeps the lights on without serving any one objective: on-call fixes, security patches, legal obligations, dependency upgrades. Treat it as aligned under an implicit "operate safely and legally" objective, even if the charter forgot to say so. Note that the charter should say so.

## Out of scope

Match a ticket to an out-of-scope item only on clear meaning, not shared words: "Fix colour contrast on the legacy dashboard" is out of scope if the legacy dashboard is retired. "Colour contrast on the new invoice page" is not.

When a ticket is out of scope:
- If the reporter is a customer, or the ticket has recent demand, `comment` before closing: the scope decision may need revisiting, and the reporter deserves to know.
- If it's internal leftover work for a retired area, `close` with `wont-do` and cite the decision.

## Epic and parent placement

- **Wrong epic:** the ticket's content belongs to a different open epic. Propose `move` with that epic's key.
- **Closed epic:** the epic is done but this child isn't. It's either leftover scope (close) or valid follow-on work (move to the epic that now owns that area, or flag that no epic exists).
- **No epic:** fine for small bugs in some teams; a problem for anything High priority or larger than a few days, because it won't appear in roadmap or capacity views.
- **Epic serves nothing:** report at epic level and propose the decision once (close the epic and its children, or update the charter).

## Priority sanity

Flag (don't change) when:
- A High/Highest ticket serves no objective, or only indirectly.
- A ticket that directly serves a deadline-bound objective is Low or unprioritised.
- Most tickets in the backlog are High, which means priority carries no information. Recommend a reset rather than listing every ticket.

## Labels and components

Propose `relabel` only when the label is clearly wrong or missing and the team uses labels for routing or reporting (check whether most tickets have them). Use the team's existing label vocabulary; don't invent new labels without saying so.

## Traceability summary format

```
| Objective | Open | In progress | Gaps |
|---|---|---|---|
| 1. Self-service billing GA (30 Nov) | 7 | 2 | Tax breakdown (PORT-21) unblocked but not scheduled |
| 2. Enterprise SSO (31 Dec) | 3 | 0 | Duplicate Safari bug split across PORT-12/PORT-13 |
| 3. Close pen-test findings before SOC 2 | 1 | 0 | PORT-18 has no epic and an inactive owner |
| — No objective | 6 (24%) | | 3 are out of scope per charter |
```
