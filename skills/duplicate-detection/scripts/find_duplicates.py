#!/usr/bin/env python3
"""Find likely duplicate tickets in a normalized backlog CSV using TF-IDF cosine similarity.
Standard library only. This is the cheap, high-recall first pass; an agent then judges each
candidate pair by reading both tickets.

At least one ticket in each pair is open (an open ticket duplicating a closed one is still
worth catching: the work may already be done, or it is a regression). Parent/child pairs are
skipped, and pairs that are already linked are reported but marked.

Usage:
  find_duplicates.py backlog.csv --out duplicate-candidates.csv
  find_duplicates.py backlog.csv --threshold 0.25 --top 500 --out duplicate-candidates.csv
  find_duplicates.py backlog.csv --open-only --out duplicate-candidates.csv
"""
import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict

STOPWORDS = set("""
a about above after again all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has
have having he her here hers him his how i if in into is it its itself just let me more most my
no nor not now of off on once only or other our ours out over own same she should so some such
than that the their them then there these they this those through to too under until up very
was we were what when where which while who whom why will with would you your yours
issue ticket task story bug please need needs should able want wants get gets make use using
""".split())
TITLE_WEIGHT = 3


def stem(w):
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


def tokens(text):
    return [stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 1 and w not in STOPWORDS and not w.isdigit()]


def vectorize(tickets):
    docs = []
    for t in tickets:
        title = tokens(t["title"])
        body = tokens(t["description"][:1500])
        docs.append(Counter(title * TITLE_WEIGHT + body))
    df = Counter()
    for d in docs:
        df.update(d.keys())
    n = len(docs)
    vecs = []
    for d in docs:
        v = {term: (1 + math.log(c)) * math.log((1 + n) / (1 + df[term])) for term, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({k: x / norm for k, x in v.items()})
    return vecs, df


def jaccard(a, b):
    a, b = set(tokens(a)), set(tokens(b))
    return len(a & b) / len(a | b) if a and b else 0.0


def linked_keys(t):
    return {part.split(":")[2] for part in t["links"].split(";") if part.count(":") >= 2}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backlog", help="normalized backlog CSV")
    ap.add_argument("--out", required=True, help="candidate pairs CSV to write")
    ap.add_argument("--threshold", type=float, default=0.3, help="minimum cosine similarity (default 0.3)")
    ap.add_argument("--top", type=int, default=300, help="keep at most this many pairs (default 300)")
    ap.add_argument("--open-only", action="store_true", help="only compare open tickets with each other")
    ap.add_argument("--max-df", type=float, default=0.3, help="ignore terms in more than this share of tickets")
    args = ap.parse_args()

    with open(args.backlog, newline="", encoding="utf-8-sig") as f:
        tickets = list(csv.DictReader(f))
    if tickets and "status_category" not in tickets[0]:
        sys.exit(f"{args.backlog}: not a normalized backlog. Run backlog-ingest/scripts/normalize.py first.")
    if args.open_only:
        tickets = [t for t in tickets if t["status_category"] != "done"]
    if len(tickets) < 2:
        sys.exit("Need at least two tickets.")

    vecs, df = vectorize(tickets)
    cutoff = max(2, args.max_df * len(tickets))
    index = defaultdict(list)  # term -> [(doc, weight)]
    for i, v in enumerate(vecs):
        for term, w in v.items():
            if 1 < df[term] <= cutoff:
                index[term].append((i, w))

    scores = defaultdict(float)
    for postings in index.values():
        for x in range(len(postings)):
            i, wi = postings[x]
            for y in range(x + 1, len(postings)):
                j, wj = postings[y]
                scores[(i, j)] += wi * wj

    pairs = []
    for (i, j), s in scores.items():
        if s < args.threshold:
            continue
        a, b = tickets[i], tickets[j]
        if a["status_category"] == "done" and b["status_category"] == "done":
            continue
        if a["epic"] == b["key"] or b["epic"] == a["key"]:
            continue
        pairs.append((s, i, j))
    pairs.sort(reverse=True)
    pairs = pairs[: args.top]

    # Group pairs into clusters so 3-way duplicates are reviewed together.
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, i, j in pairs:
        parent[find(i)] = find(j)
    cluster_ids = {}

    rows = []
    for s, i, j in pairs:
        a, b = tickets[i], tickets[j]
        root = find(i)
        cluster_ids.setdefault(root, len(cluster_ids) + 1)
        linked = b["key"] in linked_keys(a) or a["key"] in linked_keys(b)
        # Suggested canonical: a closed ticket (work exists), else more discussion, else older.
        rank = lambda t: (t["status_category"] == "done", int(t["comment_count"] or 0), -int(t["created"].replace("-", "") or 0))
        canonical = a if rank(a) >= rank(b) else b
        rows.append({
            "cluster": cluster_ids[root], "score": f"{s:.2f}", "title_overlap": f"{jaccard(a['title'], b['title']):.2f}",
            "a": a["key"], "a_title": a["title"], "a_status": a["status"], "a_created": a["created"],
            "b": b["key"], "b_title": b["title"], "b_status": b["status"], "b_created": b["created"],
            "same_epic": "yes" if a["epic"] and a["epic"] == b["epic"] else "",
            "already_linked": "yes" if linked else "", "suggested_canonical": canonical["key"],
        })

    cols = ["cluster", "score", "title_overlap", "a", "a_title", "a_status", "a_created", "b", "b_title",
            "b_status", "b_created", "same_epic", "already_linked", "suggested_canonical"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    members = defaultdict(set)
    for _, i, j in pairs:
        members[find(i)].update((i, j))
    print(f"Compared {len(tickets)} tickets; {len(rows)} candidate pairs ≥ {args.threshold} in {len(members)} clusters")
    big = [m for m in members.values() if len(m) >= 3]
    if big:
        print(f"  {len(big)} clusters have 3+ tickets — review those as a group")
    for r in rows[:10]:
        print(f"  {r['score']}  {r['a']:<20} {r['a_title'][:38]:<38} ~ {r['b']:<20} {r['b_title'][:38]}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
