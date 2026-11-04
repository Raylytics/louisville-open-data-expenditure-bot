"""review/pull_interactions.py: pulls days of interaction records for review
(louisville-open-data-2jj.3). Runs against the JSONL store and moto."""

import json
import os
import sys

import boto3
from moto import mock_aws

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import interactions as ix  # noqa: E402
from review import pull_interactions as pi  # noqa: E402

DAY0 = 1_700_000_000.0  # 2023-11-14 22:13 UTC
DAY = ix._day_of(int(DAY0 * 1000))
NEXT = ix._day_of(int((DAY0 + 86400) * 1000))


def _events(ms=1200, tier="claude"):
    return [
        {"type": "step", "id": "grounding", "status": "ok", "ms": 4, "model": None, "tier": None},
        {"type": "step", "id": "generate_sql", "status": "ok", "ms": ms, "model": "m", "tier": tier},
        {"type": "results", "content": "x", "row_count": 1, "rows": [[1]]},
        {"type": "interpretation", "content": "prose"},
        {"type": "done"},
    ]


def _rec(now, session="abcdefgh12345678", **kw):
    base = dict(
        answer_id=ix.new_answer_id(now=now),
        session_id=session,
        question="q",
        history=[],
        events=_events(),
        cache_hit=False,
        cache_key="k",
        cache_version="v",
        outcome="ok",
        now=now,
    )
    base.update(kw)
    return ix.build_record(**base)


def _seed(store):
    visitor = _rec(DAY0)
    warm = _rec(DAY0 + 10, session="")  # a deploy-warmed starter
    dev = _rec(DAY0 + 20, dev_mode=True, events=_events(ms=3000, tier="openrouter"))
    slow = _rec(DAY0 + 30, events=_events(ms=9000), outcome="error")
    tomorrow = _rec(DAY0 + 86400, cache_hit=True)
    for r in (visitor, warm, dev, slow, tomorrow):
        assert store.put(r)
    assert store.rate(
        {
            "answer_id": visitor["answer_id"],
            "session_id": "abcdefgh12345678",
            "stars": 2,
            "reasons": ["wrong-number"],
            "comment": "",
        },
        now=DAY0 + 60,
    )
    return visitor, warm, dev, slow, tomorrow


def test_days_ending_is_oldest_first_and_inclusive():
    assert pi.days_ending("2026-11-02", 3) == ["2026-10-31", "2026-11-01", "2026-11-02"]
    assert len(pi.days_ending(None, 1)) == 1


def test_pull_filters_warm_starters_and_folds_ratings(tmp_path):
    store = ix.FileInteractions(str(tmp_path / "interactions.jsonl"))
    visitor, warm, dev, slow, tomorrow = _seed(store)

    by_day = pi.pull(store, [DAY, NEXT])
    ids = [r["answer_id"] for r in by_day[DAY]]
    assert ids == [visitor["answer_id"], dev["answer_id"], slow["answer_id"]], "warm starter dropped, oldest first"
    assert by_day[DAY][0]["stars"] == 2 and by_day[DAY][0]["reasons"] == ["wrong-number"]
    assert [r["answer_id"] for r in by_day[NEXT]] == [tomorrow["answer_id"]]

    assert len(pi.pull(store, [DAY], include_warm=True)[DAY]) == 4
    assert [r["answer_id"] for r in pi.pull(store, [DAY], include_dev=False)[DAY]] == [
        visitor["answer_id"],
        slow["answer_id"],
    ]


def test_rating_only_stubs_are_kept_not_mistaken_for_warm_starters(tmp_path):
    # roborev 6880: a stub (record write failed, visitor rated anyway) has no
    # session_id, like a warmed starter; the review exists to surface it.
    store = ix.FileInteractions(str(tmp_path / "interactions.jsonl"))
    _seed(store)
    orphan = ix.new_answer_id(now=DAY0 + 40)
    assert store.rate(
        {
            "answer_id": orphan,
            "session_id": "abcdefgh12345678",
            "stars": 1,
            "reasons": ["not-answered"],
            "comment": "nothing came back",
        },
        now=DAY0 + 90,
    )
    recs = pi.pull(store, [DAY])[DAY]
    stub = next(r for r in recs if r["answer_id"] == orphan)
    assert stub["stars"] == 1 and "question" not in stub and not pi.is_warm(stub)
    assert pi.summarize(recs)["low_rated"] == 2 and pi.summarize(recs)["rated"] == 2
    assert pi.is_warm({"question": "q", "session_id": "", "cache_hit": False})
    assert not pi.is_warm({"question": "q", "session_id": "", "stars": 4})


def test_summary_counts_outcomes_ratings_and_latency(tmp_path):
    store = ix.FileInteractions(str(tmp_path / "interactions.jsonl"))
    _seed(store)
    recs = [r for d in pi.pull(store, [DAY, NEXT]).values() for r in d]
    s = pi.summarize(recs)
    assert s["answers"] == 4 and s["outcomes"] == {"ok": 3, "error": 1}
    assert s["rated"] == 1 and s["stars"] == {2: 1} and s["low_rated"] == 1
    assert s["cache_hits"] == 1 and s["sessions"] == 1
    assert s["total_ms"]["p95"] == 9004 and s["total_ms"]["p50"] in (1204, 3004)
    assert s["stage_p95_ms"]["generate_sql"] == 9000 and s["stage_p95_ms"]["grounding"] == 4
    assert s["tier_calls"] == {"claude": 3, "openrouter": 1}
    assert pi.summarize([]) == {
        "answers": 0,
        "outcomes": {},
        "rated": 0,
        "stars": {},
        "low_rated": 0,
        "cache_hits": 0,
        "sessions": 0,
        "total_ms": {"p50": None, "p95": None},
        "stage_p95_ms": {},
        "tier_calls": {},
        "tier_p95_ms": {},
    }


def test_write_days_one_file_per_nonempty_day(tmp_path):
    store = ix.FileInteractions(str(tmp_path / "interactions.jsonl"))
    _seed(store)
    out = tmp_path / "out"
    written = pi.write_days(pi.pull(store, [DAY, NEXT, "1999-01-01"]), out)
    assert sorted(p.name for p in written) == [f"{DAY}.jsonl", f"{NEXT}.jsonl"]
    lines = (out / f"{DAY}.jsonl").read_text().splitlines()
    assert len(lines) == 3 and json.loads(lines[0])["question"] == "q"
    assert not (out / "1999-01-01.jsonl").exists()


def test_cli_against_dynamodb(tmp_path, capsys):
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        ix.ensure_table(client, "lou-interactions")
        _seed(ix.DynamoInteractions("lou-interactions", client=client))
        rc = pi.main(["--days", "2", "--end", NEXT, "--out", str(tmp_path / "out"), "--exclude-dev"])
    assert rc == 0
    text = capsys.readouterr().out
    assert f"{DAY}: 2 records" in text and f"{NEXT}: 1 records" in text
    assert '"answers": 3' in text and "2 file(s)" in text
    recs = [json.loads(l) for l in (tmp_path / "out" / f"{DAY}.jsonl").read_text().splitlines()]
    assert recs[0]["stars"] == 2 and isinstance(recs[0]["steps"], list), "ratings folded, JSON fields decoded"
    assert not any(k in r for r in recs for k in ("ip", "user_agent", "headers"))


def test_pulled_records_are_gitignored():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert "review/data/" in open(os.path.join(root, ".gitignore")).read()
