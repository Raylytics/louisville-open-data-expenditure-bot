"""interactions.py: the record of every answer (epic louisville-open-data-2jj).

Pinned here:
  - ids: an answer_id is unguessable, sortable and locates its own item
    (day + sk) with no index; a session_id is accepted only in the shape the
    browser mints, never anything that could carry an identity;
  - the record carries NO IP, user agent, header or identity — the key set is
    closed and tested, so a field cannot slip in unnoticed;
  - oversized answers are trimmed under the DynamoDB item limit, dropping
    rows and chatter before SQL, steps or prose;
  - both backends (JSONL, DynamoDB via moto) write records, upsert ratings
    onto them, read a day back in order, and degrade (log + False) instead of
    raising when the store fails;
  - from_env(): off switch, dynamodb without a table = off, local = file.
"""
import json
import os
import time

import boto3
import pytest
from moto import mock_aws

import interactions as ix

TABLE = "lou-interactions-test"

# The whole key set of a record. A new field is a deliberate decision, and
# never one of these.
RECORD_KEYS = {"schema", "answer_id", "session_id", "ts", "day", "question", "history",
               "cache_hit", "cache_key", "cache_version", "outcome", "dev_mode", "steps",
               "total_ms", "events", "trimmed", "recorded_at"}
FORBIDDEN_KEYS = {"ip", "client_ip", "remote_addr", "user_agent", "ua", "headers", "cookie",
                  "email", "user", "account"}


def _events(n_rows=3):
    return [
        {"type": "step", "id": "grounding", "status": "ok", "ms": 4, "model": None, "tier": None},
        {"type": "sql", "content": "SELECT 1"},
        {"type": "step", "id": "generate_sql", "status": "ok", "ms": 1200, "model": "m", "tier": "claude"},
        {"type": "results", "content": "x", "row_count": n_rows, "rows": [[i] for i in range(n_rows)]},
        {"type": "debug", "content": "chatter"},
        {"type": "interpretation", "content": "prose"},
        {"type": "done"},
    ]


def _record(aid=None, **kw):
    aid = aid or ix.new_answer_id()
    base = dict(answer_id=aid, session_id="abcdefgh12345678", question="how much?",
                history=[], events=_events(), cache_hit=False, cache_key="v:how much?",
                cache_version="v", outcome="ok")
    base.update(kw)
    return ix.build_record(**base)


# ── identifiers ─────────────────────────────────────────────────────────────

def test_answer_ids_are_unique_sortable_and_self_locating():
    a = ix.new_answer_id(now=1_700_000_000.0)
    b = ix.new_answer_id(now=1_700_000_001.0)
    assert a != b and a < b
    assert ix.parse_answer_id(a) == 1_700_000_000_000
    pk, sk, ts = ix._keys(a)
    assert pk == "day#2023-11-14" and sk.startswith("1700000000000#") and ts == 1_700_000_000_000


@pytest.mark.parametrize("bad", [None, "", "abc", "zz-12345678", "1" * 40, 123, "18b7c6c8c00-xyz"])
def test_malformed_answer_ids_are_rejected(bad):
    assert ix.parse_answer_id(bad) is None


@pytest.mark.parametrize("value,expected", [
    ("abcdefgh12345678", "abcdefgh12345678"),
    ("A-Z_09" * 3, "A-Z_09" * 3),
    ("short", ""), ("", ""), (None, ""), (42, ""),
    ("has space in it 12345", ""), ("x" * 65, ""),
    ("evan@example.com-xx", ""),          # never anything shaped like an identity
])
def test_session_ids_are_accepted_only_in_the_browsers_shape(value, expected):
    assert ix.clean_session_id(value) == expected


# ── the record ──────────────────────────────────────────────────────────────

def test_record_has_a_closed_key_set_and_nothing_identifying():
    rec = _record()
    assert set(rec) == RECORD_KEYS
    assert not (set(rec) & FORBIDDEN_KEYS)
    assert rec["day"] == ix._day_of(ix.parse_answer_id(rec["answer_id"]))
    assert rec["steps"] == [{"id": "grounding", "status": "ok", "ms": 4, "model": None, "tier": None},
                            {"id": "generate_sql", "status": "ok", "ms": 1200, "model": "m", "tier": "claude"}]
    assert rec["total_ms"] == 1204
    assert rec["trimmed"] is False and rec["events"] == _events()


def test_history_is_trimmed_to_the_last_turns_and_capped():
    hist = ["junk"] + [{"role": "user", "content": "x" * 5000}] * 10
    rec = _record(history=hist)
    assert len(rec["history"]) == ix.HISTORY_TURNS
    assert all(len(t["content"]) == ix.HISTORY_CHARS for t in rec["history"])


def test_outcome_reads_the_stream():
    assert ix.outcome_of(_events()) == "ok"
    assert ix.outcome_of(_events() + [{"type": "error", "content": "boom"}]) == "error"
    assert ix.outcome_of([{"type": "sql", "content": "x"}]) == "incomplete"
    assert ix.outcome_of(_events(), ended="abandoned") == "abandoned"


def test_oversized_answers_are_trimmed_under_the_item_limit_rows_first():
    big = _events(n_rows=1)
    big[3]["rows"] = [["x" * 1000] for _ in range(400)]   # ~400 KB of rows
    kept, trimmed = ix.trim_events(big)
    assert trimmed is True
    results = next(e for e in kept if e["type"] == "results")
    assert "rows" not in results and "content" not in results
    assert results["row_count"] == 1
    # The reviewable parts survive untouched.
    assert [e["type"] for e in kept] == [e["type"] for e in big]
    assert next(e for e in kept if e["type"] == "sql")["content"] == "SELECT 1"
    assert len(json.dumps(kept)) <= ix.MAX_EVENTS_BYTES
    # The originals were not mutated.
    assert len(big[3]["rows"]) == 400


def test_trim_drops_chatter_then_chart_when_rows_are_not_enough():
    evs = _events(n_rows=0) + [{"type": "chart", "labels": ["l" * 100] * 2000, "values": [1] * 2000}]
    evs.append({"type": "debug", "content": "d" * 200_000})
    kept, trimmed = ix.trim_events(evs, limit=50_000)
    assert trimmed
    types = [e["type"] for e in kept]
    assert "debug" not in types and "log" not in types and "chart" not in types
    assert "sql" in types and "interpretation" in types and "step" in types


# ── rating bodies ───────────────────────────────────────────────────────────

def test_clean_rating_accepts_a_five_star_body_and_normalises_it():
    aid = ix.new_answer_id()
    r = ix.clean_rating({"answer_id": aid, "stars": "4", "reasons": ["Wrong Number", "slow!", 7, ""],
                         "comment": "  nice  " + "x" * 1000, "session_id": "abcdefgh12345678"})
    assert r["answer_id"] == aid and r["stars"] == 4
    assert r["reasons"] == ["wrongnumber", "slow"]
    assert len(r["comment"]) == ix.COMMENT_CHARS and r["comment"].startswith("nice")
    assert r["session_id"] == "abcdefgh12345678"


@pytest.mark.parametrize("body", [
    None, [], {}, {"stars": 5}, {"answer_id": "nope", "stars": 5},
    {"answer_id": ix.new_answer_id(), "stars": 0}, {"answer_id": ix.new_answer_id(), "stars": 6},
    {"answer_id": ix.new_answer_id(), "stars": "five"}, {"answer_id": ix.new_answer_id(), "stars": 3, "reasons": "x"},
    {"answer_id": ix.new_answer_id(), "stars": 3, "comment": ["x"]},
])
def test_clean_rating_rejects_anything_else(body):
    assert ix.clean_rating(body) is None


# ── file backend ────────────────────────────────────────────────────────────

def test_file_backend_writes_reads_and_folds_ratings(tmp_path):
    store = ix.FileInteractions(str(tmp_path / "sub" / "ix.jsonl"))   # dir is created
    a = _record(ix.new_answer_id(now=1_700_000_000.0))
    b = _record(ix.new_answer_id(now=1_700_000_001.0), outcome="error")
    other_day = _record(ix.new_answer_id(now=1_700_100_000.0))
    assert store.put(a) and store.put(b) and store.put(other_day)
    assert store.rate({"answer_id": a["answer_id"], "stars": 2, "reasons": ["slow"], "comment": "meh"}, now=5.0)
    day = store.query_day("2023-11-14")
    assert [r["answer_id"] for r in day] == [a["answer_id"], b["answer_id"]]
    assert day[0]["stars"] == 2 and day[0]["reasons"] == ["slow"] and day[0]["comment"] == "meh" and day[0]["rated_at"] == 5.0
    assert "stars" not in day[1]
    assert [r["answer_id"] for r in store.query_day("2023-11-16")] == [other_day["answer_id"]]
    assert store.status()["writes"] == 4 and store.status()["status"] == "ok"


def test_file_backend_rating_without_a_record_still_shows_up(tmp_path):
    store = ix.FileInteractions(str(tmp_path / "ix.jsonl"))
    aid = ix.new_answer_id(now=1_700_000_000.0)
    assert store.rate({"answer_id": aid, "stars": 5, "reasons": [], "comment": ""})
    day = store.query_day("2023-11-14")
    assert len(day) == 1 and day[0]["answer_id"] == aid and day[0]["stars"] == 5


def test_file_backend_degrades_instead_of_raising(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    store = ix.FileInteractions(str(blocked / "ix.jsonl"))
    assert store.put(_record()) is False
    assert store.status()["status"] == "degraded" and store.status()["errors"] == 1
    # A file that does not exist yet reads as empty, not as an error.
    assert ix.FileInteractions(str(tmp_path / "none.jsonl")).query_day("2023-11-14") == []


# ── DynamoDB backend ────────────────────────────────────────────────────────

@pytest.fixture
def dynamo():
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        ix.ensure_table(client, TABLE)
        ix.ensure_table(client, TABLE)   # idempotent
        yield client


def test_dynamo_backend_round_trips_a_record_with_ttl(dynamo):
    store = ix.DynamoInteractions(TABLE, client=dynamo, ttl_days=10)
    rec = _record(ix.new_answer_id(now=1_700_000_000.0), history=[{"role": "user", "content": "hi"}])
    assert store.put(rec)
    item = dynamo.get_item(TableName=TABLE, Key={"pk": {"S": "day#2023-11-14"},
                                                  "sk": {"S": f"1700000000000#{rec['answer_id']}"}})["Item"]
    assert int(item["ttl"]["N"]) == 1_700_000_000 + 10 * 86400
    assert set(item) - {"pk", "sk", "ttl"} == RECORD_KEYS
    back = store.query_day("2023-11-14")
    assert len(back) == 1
    b = back[0]
    for k in RECORD_KEYS:
        assert b[k] == rec[k], k
    assert b["history"] == [{"role": "user", "content": "hi"}]
    assert b["events"] == _events()


def test_dynamo_backend_keeps_records_for_good_by_default(dynamo):
    """2jj.5 (2026-10-27): no retention. With ttl_days unset nothing carries a
    `ttl` attribute, so the table's TTL never expires a record or a rating."""
    store = ix.DynamoInteractions(TABLE, client=dynamo)
    assert store.ttl_s == 0
    rec = _record(ix.new_answer_id(now=1_700_000_000.0))
    assert store.put(rec)
    stub = ix.new_answer_id(now=1_700_000_001.0)
    assert store.rate({"answer_id": stub, "stars": 2, "reasons": [], "comment": ""}, now=1_700_000_002.0)
    assert store.rate({"answer_id": rec["answer_id"], "stars": 4, "reasons": [], "comment": ""},
                      now=1_700_000_003.0)
    items = dynamo.scan(TableName=TABLE)["Items"]
    assert len(items) == 2 and not any("ttl" in it for it in items)
    assert sorted(r["stars"] for r in store.query_day("2023-11-14")) == [2, 4]


def test_dynamo_backend_reads_a_day_in_order_and_pages(dynamo, monkeypatch):
    store = ix.DynamoInteractions(TABLE, client=dynamo)
    ids = [ix.new_answer_id(now=1_700_000_000.0 + i) for i in (3, 1, 2)]
    for aid in ids:
        assert store.put(_record(aid))
    assert store.put(_record(ix.new_answer_id(now=1_700_100_000.0)))   # the next day
    # Force pagination through the Query loop.
    real = dynamo.query
    def paged(**kw):
        return real(**kw, Limit=2) if "Limit" not in kw else real(**kw)
    monkeypatch.setattr(dynamo, "query", paged)
    day = store.query_day("2023-11-14")
    assert [r["answer_id"] for r in day] == sorted(ids)


def test_dynamo_backend_upserts_a_rating_onto_the_record(dynamo):
    store = ix.DynamoInteractions(TABLE, client=dynamo, ttl_days=3)
    rec = _record(ix.new_answer_id(now=1_700_000_000.0))
    assert store.put(rec)
    assert store.rate({"answer_id": rec["answer_id"], "stars": 3, "reasons": ["slow", "wrongperiod"],
                       "comment": "hm"}, now=1_700_000_100.0)
    assert store.rate({"answer_id": rec["answer_id"], "stars": 5, "reasons": [], "comment": ""},
                      now=1_700_000_200.0)                       # the latest rating wins
    [b] = store.query_day("2023-11-14")
    assert b["stars"] == 5 and b["reasons"] == [] and b["comment"] == "" and b["rated_at"] == 1_700_000_200
    assert b["question"] == "how much?" and b["events"] == _events()   # the record is intact
    assert b["ttl"] == 1_700_000_000 + 3 * 86400                       # the record's TTL kept


def test_dynamo_backend_rating_before_a_record_lands_as_a_stub(dynamo):
    store = ix.DynamoInteractions(TABLE, client=dynamo, ttl_days=3)
    aid = ix.new_answer_id(now=1_700_000_000.0)
    assert store.rate({"answer_id": aid, "stars": 1, "reasons": ["didnotanswer"], "comment": "x"})
    [b] = store.query_day("2023-11-14")
    assert b["answer_id"] == aid and b["stars"] == 1 and b["day"] == "2023-11-14"
    assert b["ttl"] == 1_700_000_000 + 3 * 86400
    assert "question" not in b


def test_dynamo_backend_degrades_when_the_table_is_gone(dynamo):
    store = ix.DynamoInteractions("lou-no-such-table", client=dynamo)
    assert store.put(_record()) is False
    assert store.rate({"answer_id": ix.new_answer_id(), "stars": 4, "reasons": [], "comment": ""}) is False
    s = store.status()
    assert s["status"] == "degraded" and s["errors"] == 2 and "ResourceNotFound" in s["last_error"]


# ── from_env ────────────────────────────────────────────────────────────────

def test_from_env_off_switch(monkeypatch):
    monkeypatch.setenv("RECORD_INTERACTIONS", "0")
    assert ix.from_env() is None


def test_from_env_dynamodb_without_a_table_is_off(monkeypatch):
    monkeypatch.setenv("STATE_BACKEND", "dynamodb")
    monkeypatch.delenv("INTERACTIONS_TABLE", raising=False)
    monkeypatch.delenv("RECORD_INTERACTIONS", raising=False)
    assert ix.from_env() is None


def test_from_env_dynamodb_with_a_table(monkeypatch):
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("STATE_BACKEND", "dynamodb")
    monkeypatch.setenv("INTERACTIONS_TABLE", "lou-interactions")
    monkeypatch.setenv("INTERACTION_TTL_DAYS", "7")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    with mock_aws():
        store = ix.from_env()
    assert isinstance(store, ix.DynamoInteractions)
    assert store.table == "lou-interactions" and store.ttl_s == 7 * 86400


def test_from_env_dynamodb_keeps_for_good_unless_told(monkeypatch):
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("STATE_BACKEND", "dynamodb")
    monkeypatch.setenv("INTERACTIONS_TABLE", "lou-interactions")
    monkeypatch.delenv("INTERACTION_TTL_DAYS", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    with mock_aws():
        store = ix.from_env()
    assert store.ttl_s == 0


def test_from_env_local_is_a_file_under_stats_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("STATE_BACKEND", raising=False)
    monkeypatch.delenv("INTERACTIONS_FILE", raising=False)
    monkeypatch.setenv("STATS_DIR", str(tmp_path))
    store = ix.from_env()
    assert isinstance(store, ix.FileInteractions)
    assert store.path == str(tmp_path / "interactions.jsonl")
    monkeypatch.setenv("INTERACTIONS_FILE", str(tmp_path / "elsewhere.jsonl"))
    assert ix.from_env().path == str(tmp_path / "elsewhere.jsonl")
