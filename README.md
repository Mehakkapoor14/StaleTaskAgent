# StaleTaskAgent

AI agent skills that clean up **stale, duplicate, and misaligned** tickets in **Jira** and **GitHub Issues**. Deterministic scripts find the candidates, the agent judges each one by reading it the way an experienced triager would, a human approves, and every change is reversible and audited.

They use the Agent Skills `SKILL.md` format, so they work in Claude Code, Pi, and other agents that support it. They are a companion to [ProjectManagementSkills](https://github.com/Mehakkapoor14/ProjectManagementSkills) and share its `pm/` workspace.

**Why this exists, the impact it can have, and how to adopt it:** [docs/why-backlog-hygiene.md](docs/why-backlog-hygiene.md)

## Skills

| Skill | What it does |
|---|---|
| [backlog-ingest](skills/backlog-ingest/) | Pulls Jira (CSV export, REST, or MCP) and GitHub issues into one normalized snapshot |
| [stale-triage](skills/stale-triage/) | Finds abandoned, zombie, orphaned, and done-but-never-closed tickets (including via merged PRs) and recommends close / ask / reassign / keep |
| [duplicate-detection](skills/duplicate-detection/) | Finds duplicates worded differently and across Jira and GitHub, picks the ticket to keep, and carries details over |
| [alignment-check](skills/alignment-check/) | Traces tickets to the charter / OKRs; flags out-of-scope work, wrong or closed epics, and high-stakes work with no home |
| [backlog-cleanup](skills/backlog-cleanup/) | Runs the full review: one decision per ticket, a review report, and health metrics |
| [cleanup-apply](skills/cleanup-apply/) | Applies approved actions: dry run by default, one-ticket canary, skips tickets changed since triage, audit log with undo hints |

## How they work together

```
Jira / GitHub ──► backlog-ingest ──► pm/backlog/backlog.csv
                                          │
             ┌────────────────────────────┼────────────────────────────┐
     duplicate-detection             stale-triage               alignment-check (+ goals)
             └────────────────────────────┼────────────────────────────┘
                                          ▼
                       pm/backlog/actions.csv  ◄── backlog-cleanup reconciles + reports
                                          │
                                   human approval
                                          ▼
                       cleanup-apply ──► Jira / GitHub + pm/backlog/audit-log.csv
```

```
pm/backlog/
├── raw/                     untouched exports (evidence)
├── backlog.csv              backlog-ingest
├── signals.csv              stale-triage
├── duplicate-candidates.csv duplicate-detection
├── alignment-digest.md      alignment-check
├── actions.csv              proposed actions — set approved=yes to run
├── review-YYYY-MM-DD.md     backlog-cleanup report
└── audit-log.csv            cleanup-apply
```

Nothing changes in Jira or GitHub until a person approves specific rows in `actions.csv` and `cleanup-apply` runs with `--execute`.

## Installation

**Claude Code** — copy (or symlink) the skill folders into a skills directory:

```bash
# for all your projects
cp -r skills/* ~/.claude/skills/
# or for a single project
mkdir -p .claude/skills && cp -r /path/to/StaleTaskAgent/skills/* .claude/skills/
```

**Pi and other Agent Skills–compatible agents** — copy the folders under `skills/` into the agent's skills directory.

**Requirements:** Python 3.9+ (scripts use the standard library only). GitHub: the `gh` CLI, authenticated. Jira: a CSV export, an API token (`JIRA_URL` + `JIRA_EMAIL` + `JIRA_API_TOKEN`, or `JIRA_PAT` on Data Center), or Atlassian MCP tools.

Then ask your agent things like:

- "Run a backlog cleanup review for Jira project PORT and acme/portal-web. Goals are in pm/charter.md."
- "Which open issues are already fixed by merged PRs?"
- "Find duplicates in this Jira export."
- "Apply the approved actions — canary first."

## Try it on the example backlog

`examples/` holds a synthetic project with planted problems ([what's planted](examples/README.md)):

```bash
mkdir -p pm/backlog
python3 skills/backlog-ingest/scripts/normalize.py examples/jira-export.csv examples/github-issues.json \
  --jira-url https://acme.atlassian.net --out pm/backlog/backlog.csv
python3 skills/stale-triage/scripts/stale_signals.py pm/backlog/backlog.csv --prs examples/merged-prs.json \
  --today 2026-10-24 --inactive "Dana Lee;dlee" --out pm/backlog/signals.csv
python3 skills/duplicate-detection/scripts/find_duplicates.py pm/backlog/backlog.csv --out pm/backlog/duplicate-candidates.csv
python3 skills/alignment-check/scripts/alignment_digest.py pm/backlog/backlog.csv
python3 skills/cleanup-apply/scripts/apply_actions.py examples/actions.example.csv --backlog pm/backlog/backlog.csv
```

## Tests

```bash
python3 -m unittest discover tests
```

The tests run every script against the example backlog, and run `apply_actions.py --execute` against a fake `gh` and a fake Jira server, so no real tickets are touched.

## Skill layout

```
skills/<skill-name>/
├── SKILL.md       frontmatter (name, description) + instructions
├── templates/     output templates
├── references/    detail loaded only when needed
└── scripts/       deterministic helpers
```
