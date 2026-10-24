---
name: duplicate-detection
description: Find duplicate and overlapping tickets in Jira and/or GitHub Issues — including duplicates worded differently and duplicates across the two tools — decide which ticket to keep, and propose a merge plan that preserves useful detail. Use whenever the user mentions duplicate tickets, duplicate issues, the same bug reported twice, overlapping stories, dedupe, merging tickets, consolidating a backlog, "haven't we already got a ticket for this?", or wants to check a new request against the existing backlog — even if they just paste a ticket and ask whether it already exists.
---

# Duplicate Detection

Duplicates cost more than clutter. Two people fix the same bug, priority gets split across two tickets so neither looks important, and reporters never learn the fix already shipped. Keyword search misses most duplicates because people describe the same problem differently ("SSO broken in Safari" vs. "Okta redirect loop on Mac"). The approach here: a cheap similarity pass finds candidate pairs with high recall, then you judge each pair by reading it, the way an experienced triager would.

## Workflow

1. **Load the snapshot** `pm/backlog/backlog.csv` (run **backlog-ingest** first if missing). Include recently closed tickets: an open ticket that duplicates a closed one means either the work is done or it has regressed.

2. **Generate candidates:**
   ```bash
   python3 scripts/find_duplicates.py pm/backlog/backlog.csv --out pm/backlog/duplicate-candidates.csv
   ```
   TF-IDF cosine similarity over title (weighted ×3) and description. Default `--threshold 0.3` favours recall. Raise it to 0.4 for very large backlogs; lower it to 0.2 if the user knows duplicates exist that weren't found. Pairs are grouped into `cluster`s, parent/child pairs are skipped, and pairs that are already linked are marked `already_linked`.

   **Checking one new ticket against the backlog** (e.g. the user pastes a request): skip the script. Search the snapshot for the key concepts and synonyms yourself, then judge the closest 5–10.

3. **Judge each pair or cluster.** Read both tickets in full (title, description, last comments). Classify:

   | Verdict | Meaning | Action |
   |---|---|---|
   | **Duplicate** | Same problem or same deliverable; doing one fully completes the other | `close-duplicate` the non-canonical ticket(s) → canonical |
   | **Overlapping** | Substantial shared scope but each has something the other lacks | Keep both, or merge: move the unique scope into the canonical as a comment, then close; or `link` and narrow one |
   | **Related** | Same area, different work (e.g. a bug and the feature that caused it) | `link` |
   | **Distinct** | Similar words, different meaning | No action. Don't write a row |

   Similarity scores only rank the pairs. A 0.6 pair can be distinct ("Export invoices to PDF" vs. "Export invoices to CSV") and a 0.3 pair can be an exact duplicate. Decide on meaning.

4. **Pick the canonical ticket** per cluster (one per cluster, not per pair). Prefer, in order:
   1. The one where the work is happening (in progress, assigned, active comments).
   2. The one with the best information (repro steps, acceptance criteria, customer links).
   3. The older one (it has more watchers and history).
   4. The one in the system the team actually works in, for Jira-vs-GitHub pairs.

   The script's `suggested_canonical` is a starting point only.

5. **Preserve information.** Before proposing a close, check whether the duplicate holds something the canonical lacks: extra repro steps, an affected customer, a different environment, a deadline. If so, write that into the closing `comment` ("Adds: also happens on Safari 16; reported by Globex"), so nothing is lost when the duplicate is closed. The canonical keeps the history; watchers of the duplicate get pointed to it.

6. **Write the proposed actions** to `pm/backlog/actions.csv` (append; create with header if missing):
   `key,action,target,resolution,comment,reason,source,confidence,approved`
   with `source=duplicate-detection` and `target` = canonical key. `approved` stays blank for the human.

7. **Report**: candidate pairs reviewed, verdict counts, clusters with 3+ tickets (often a sign the intake process makes people re-file), and any cross-tool duplicates (a sign Jira and GitHub are both being used as the front door).

## Cross-tool duplicates

When a Jira ticket and a GitHub issue are duplicates, there is no native link between the two systems. cleanup-apply posts a "Duplicate of <key/url>" comment on the closed one and closes it. Make the comment include the canonical ticket's URL so readers can follow it.

## Output

- `pm/backlog/duplicate-candidates.csv` — script output.
- Rows appended to `pm/backlog/actions.csv`.
- Summary in chat, or in the review report when run by **backlog-cleanup**.

## Connects to

- **backlog-ingest** — produces the snapshot.
- **stale-triage** — "superseded by a newer ticket" is a duplicate decision; one action per ticket.
- **cleanup-apply** — executes approved merges (Jira: Duplicate link + close; GitHub: close as duplicate).
