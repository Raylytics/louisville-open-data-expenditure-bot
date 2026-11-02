"""Pull interaction records for review (louisville-open-data-2jj.3, step 1).

Reads whole UTC days of records from the store the app wrote them to and
leaves one JSONL file per day under a local directory, with a summary of
what came back. The judge and the weekly report (steps 2-3) read those
files, so a review pass pays the DynamoDB read once.

    # production: the read-only side of the lou profile (MFA in a real
    # terminal first: aws sts get-caller-identity --profile lou). Tier 1.
    AWS_PROFILE=lou python review/pull_interactions.py --days 7
    # a local run's records
    python review/pull_interactions.py --local .stats/interactions.jsonl --days 3

Starter answers warmed by a deploy are recorded too (cache_hit False, no
session_id); they say nothing about visitors and are dropped unless
--include-warm. Records carry no IP, user agent or identity (interactions.py),
so the pulled files hold nothing a visitor did not type.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import interactions  # noqa: E402

DEFAULT_TABLE = "lou-interactions"
DEFAULT_OUT = Path(__file__).resolve().parent / "data"


def days_ending(end: str | None, n: int) -> list[str]:
    """`n` UTC days ending on `end` (YYYY-MM-DD; default today), oldest first."""
    last = datetime.strptime(end, "%Y-%m-%d").date() if end else datetime.now(timezone.utc).date()
    return [(last - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def is_warm(rec: dict) -> bool:
    """A starter answer recorded by warm_cache.py rather than a visitor: a real
    answer record (it has the question) with no session_id and no rating. A
    rating-only stub — the record write failed, the visitor rated anyway — has
    no session_id either and is exactly what a review must keep."""
    return "question" in rec and not rec.get("session_id") and rec.get("stars") is None


def pull(store, days: list[str], *, include_warm: bool = False, include_dev: bool = True) -> dict[str, list[dict]]:
    """Each day's records (latest rating folded in), filtered, oldest first."""
    out = {}
    for day in days:
        recs = store.query_day(day)
        if not include_warm:
            recs = [r for r in recs if not is_warm(r)]
        if not include_dev:
            recs = [r for r in recs if not r.get("dev_mode")]
        out[day] = sorted(recs, key=lambda r: r.get("ts", 0))
    return out


def percentile(values: list, p: float):
    if not values:
        return None
    xs = sorted(values)
    k = max(0, min(len(xs) - 1, round((len(xs) - 1) * p)))
    return xs[k]


def summarize(recs: list[dict]) -> dict:
    """What a reviewer wants to know before opening the files: how many
    answers, how they ended, how many were rated and how, cache hits, and
    the latency p50/p95 overall and per stage and provider tier."""
    outcomes, stars, stages, tiers = {}, {}, {}, {}
    totals = []
    for r in recs:
        outcomes[r.get("outcome", "?")] = outcomes.get(r.get("outcome", "?"), 0) + 1
        if r.get("stars") is not None:
            stars[int(r["stars"])] = stars.get(int(r["stars"]), 0) + 1
        if r.get("total_ms") is not None:
            totals.append(r["total_ms"])
        for s in r.get("steps") or []:
            if s.get("ms") is None:
                continue
            stages.setdefault(s.get("id"), []).append(s["ms"])
            if s.get("tier"):
                tiers.setdefault(s["tier"], []).append(s["ms"])
    return {
        "answers": len(recs),
        "outcomes": outcomes,
        "rated": sum(stars.values()),
        "stars": {k: stars[k] for k in sorted(stars)},
        "low_rated": sum(1 for r in recs if r.get("stars") is not None and int(r["stars"]) <= 2),
        "cache_hits": sum(1 for r in recs if r.get("cache_hit")),
        "sessions": len({r.get("session_id") for r in recs if r.get("session_id")}),
        "total_ms": {"p50": percentile(totals, 0.5), "p95": percentile(totals, 0.95)},
        "stage_p95_ms": {k: percentile(v, 0.95) for k, v in stages.items()},
        "tier_calls": {k: len(v) for k, v in tiers.items()},
        "tier_p95_ms": {k: percentile(v, 0.95) for k, v in tiers.items()},
    }


def write_days(by_day: dict[str, list[dict]], out_dir: Path) -> list[Path]:
    """One `<day>.jsonl` per day (an empty day leaves no file); the directory
    is gitignored — records are review material, never repository content."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for day, recs in by_day.items():
        if not recs:
            continue
        path = out_dir / f"{day}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        written.append(path)
    return written


def open_store(args):
    if args.local:
        return interactions.FileInteractions(args.local)
    return interactions.DynamoInteractions(args.table, region=args.region, endpoint_url=args.endpoint_url or None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=7, help="how many UTC days to pull (default 7)")
    ap.add_argument("--end", help="last day, YYYY-MM-DD UTC (default today)")
    ap.add_argument("--table", default=os.environ.get("INTERACTIONS_TABLE", DEFAULT_TABLE))
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    ap.add_argument(
        "--endpoint-url",
        default=os.environ.get("DYNAMODB_ENDPOINT_URL", ""),
        help="DynamoDB Local (the preview's state backend)",
    )
    ap.add_argument("--local", help="read a local run's interactions.jsonl instead of DynamoDB")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output directory (default {DEFAULT_OUT})")
    ap.add_argument("--include-warm", action="store_true", help="keep the deploy-warmed starter answers")
    ap.add_argument("--exclude-dev", action="store_true", help="drop ?dev=1 answers")
    args = ap.parse_args(argv)

    days = days_ending(args.end, args.days)
    by_day = pull(open_store(args), days, include_warm=args.include_warm, include_dev=not args.exclude_dev)
    written = write_days(by_day, args.out)
    for day in days:
        print(f"{day}: {len(by_day[day])} records")
    everything = [r for recs in by_day.values() for r in recs]
    print(json.dumps(summarize(everything), indent=2, default=str))
    print(f"{len(written)} file(s) under {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
