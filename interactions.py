"""Interaction records: every answer the site serves, kept as an "experience"
so the person who asked can rate it and so old answers can be reviewed later
(epic louisville-open-data-2jj; the review tooling is Phase 3).

What a record is NOT. It carries no IP address, no user agent, no cookie, no
account, no header of any kind: nothing that identifies a person. The only
identifiers are
    answer_id   minted by the server per response (a cached replay gets a
                fresh one too), unguessable, and it encodes the minute it was
                minted so the record can be found again without an index;
    session_id  a random token the browser keeps in sessionStorage for one
                tab's lifetime, so one sitting's questions can be read in
                order. The server never sets it and never links two of them.
The question text is stored verbatim: it is the experience. The privacy note
under the input box asks visitors not to type personal information
(branding.privacy_note in the city pack).

Two backends, chosen the way state_store chooses: DynamoDB on Lambda (its own
table, `lou-interactions`, inside the permissions boundary's `lou-*` grant)
and a JSONL file on the self-hosted / dev path. Both are best-effort: a failed
write is logged and the answer is unaffected, the same stance as the cache.

Table layout (pk HASH, sk RANGE, TTL `ttl`):
    pk  day#<YYYY-MM-DD>        UTC day the answer_id was minted
    sk  <ts_ms>#<answer_id>     so one day's records read back in order
One item per answer. A rating is an UpdateItem on that item — an upsert, so a
rating that arrives after a failed record write still lands and the review
pass sees it.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import secrets
import threading
import time

log = logging.getLogger("interactions")

RECORD_SCHEMA = "1"
# DynamoDB items cap at 400 KB; leave room for the attributes beside `events`.
MAX_EVENTS_BYTES = 300_000
HISTORY_TURNS = 6
HISTORY_CHARS = 1000
COMMENT_CHARS = 500
MAX_REASONS = 8
REASON_CHARS = 40

_ANSWER_ID = re.compile(r"^[0-9a-f]{9,12}-[0-9a-f]{8}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


# ── identifiers ─────────────────────────────────────────────────────────────

def new_answer_id(now: float | None = None) -> str:
    """<ms since epoch, hex>-<32 random bits>: sortable, unguessable, and
    self-describing enough to locate its item (day + sk) with no index."""
    ms = int((time.time() if now is None else now) * 1000)
    return f"{ms:x}-{secrets.token_hex(4)}"


def parse_answer_id(answer_id) -> int | None:
    """The epoch milliseconds an id was minted at, or None if it is not one."""
    if not isinstance(answer_id, str) or not _ANSWER_ID.match(answer_id):
        return None
    return int(answer_id.split("-", 1)[0], 16)


def clean_session_id(value) -> str:
    """The client's token if it looks like one, else '' (never an error: a
    client without sessionStorage still gets its answer)."""
    return value if isinstance(value, str) and _SESSION_ID.match(value) else ""


def _day_of(ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def _keys(answer_id: str) -> tuple[str, str, int]:
    ts_ms = parse_answer_id(answer_id)
    if ts_ms is None:
        raise ValueError(f"not an answer id: {answer_id!r}")
    return f"day#{_day_of(ts_ms)}", f"{ts_ms}#{answer_id}", ts_ms


# ── records ─────────────────────────────────────────────────────────────────

def trim_history(history) -> list[dict]:
    """The last few turns the client sent, each capped — the record is about
    this answer, the earlier ones have records of their own."""
    out = []
    for turn in (history or [])[-HISTORY_TURNS:]:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", ""))[:16]
        content = str(turn.get("content", ""))[:HISTORY_CHARS]
        out.append({"role": role, "content": content})
    return out


def summarize_steps(events: list[dict]) -> tuple[list[dict], int]:
    """The pipeline timeline (one entry per `step` frame) and their total ms —
    the first thing a review pass sorts by."""
    steps = [{"id": e.get("id"), "status": e.get("status"), "ms": e.get("ms"),
              "model": e.get("model"), "tier": e.get("tier")}
             for e in events if e.get("type") == "step"]
    return steps, sum(int(s["ms"] or 0) for s in steps)


def outcome_of(events: list[dict], ended: str = "ok") -> str:
    """ok | error | incomplete | abandoned: how the stream ended. `ended` is
    what the generator saw (abandoned = the client went away)."""
    if ended != "ok":
        return ended
    if any(e.get("type") == "error" for e in events):
        return "error"
    if not any(e.get("type") == "interpretation" for e in events):
        return "incomplete"
    return "ok"


def trim_events(events: list[dict], limit: int = MAX_EVENTS_BYTES) -> tuple[list[dict], bool]:
    """Fit the frames under the item limit, dropping the bulkiest and least
    reviewable parts first; the SQL, steps and prose always survive."""
    def size(evs):
        return len(json.dumps(evs, ensure_ascii=False))
    if size(events) <= limit:
        return events, False
    evs = [dict(e) for e in events]
    for e in evs:                      # 1. result rows (the SQL can re-make them)
        if e.get("type") == "results":
            e.pop("rows", None)
            e.pop("content", None)
    if size(evs) > limit:              # 2. debug/log chatter
        evs = [e for e in evs if e.get("type") not in ("debug", "log")]
    if size(evs) > limit:              # 3. chart payload
        evs = [e for e in evs if e.get("type") != "chart"]
    if size(evs) > limit:              # 4. long prose, head only
        for e in evs:
            if isinstance(e.get("content"), str) and len(e["content"]) > 20_000:
                e["content"] = e["content"][:20_000]
    return evs, True


def build_record(*, answer_id: str, session_id: str, question: str, history, events: list[dict],
                 cache_hit: bool, cache_key: str, cache_version: str, outcome: str,
                 dev_mode: bool = False, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    ts_ms = parse_answer_id(answer_id)
    if ts_ms is None:
        raise ValueError(f"not an answer id: {answer_id!r}")
    kept, trimmed = trim_events(events)
    steps, total_ms = summarize_steps(events)
    return {
        "schema": RECORD_SCHEMA,
        "answer_id": answer_id,
        "session_id": session_id or "",
        "ts": ts_ms / 1000,
        "day": _day_of(ts_ms),
        "question": question,
        "history": trim_history(history),
        "cache_hit": bool(cache_hit),
        "cache_key": cache_key,
        "cache_version": cache_version,
        "outcome": outcome,
        "dev_mode": bool(dev_mode),
        "steps": steps,
        "total_ms": total_ms,
        "events": kept,
        "trimmed": trimmed,
        "recorded_at": now,
    }


def clean_rating(body: dict) -> dict | None:
    """The validated rating fields from a /api/feedback body, or None when the
    body is not a rating (bad stars, no id). Stars are 1-5 (the five-star
    widget); reasons are short tokens; the comment is capped."""
    if not isinstance(body, dict):
        return None
    answer_id = body.get("answer_id")
    if parse_answer_id(answer_id) is None:
        return None
    try:
        stars = int(body.get("stars"))
    except (TypeError, ValueError):
        return None
    if not 1 <= stars <= 5:
        return None
    reasons_in = body.get("reasons") or []
    if not isinstance(reasons_in, list):
        return None
    reasons = []
    for r in reasons_in[:MAX_REASONS]:
        if isinstance(r, str) and r.strip():
            reasons.append(re.sub(r"[^a-z0-9_-]", "", r.strip().lower())[:REASON_CHARS])
    comment = body.get("comment") or ""
    if not isinstance(comment, str):
        return None
    comment = comment.strip()[:COMMENT_CHARS]
    return {"answer_id": answer_id, "stars": stars,
            "reasons": [r for r in reasons if r], "comment": comment,
            "session_id": clean_session_id(body.get("session_id"))}


# ── backends ────────────────────────────────────────────────────────────────

class _Recorder:
    backend = "none"

    def __init__(self):
        self.errors = 0
        self.last_error: str | None = None
        self.writes = 0

    def _note(self, where: str, e: Exception) -> None:
        self.errors += 1
        self.last_error = f"{where}: {type(e).__name__}: {str(e)[:160]}"
        log.error("%s: interaction store unavailable (%s: %s); dropped", where, type(e).__name__, e)

    def status(self) -> dict:
        return {"backend": self.backend, "status": "ok" if not self.last_error else "degraded",
                "writes": self.writes, "errors": self.errors, "last_error": self.last_error}


class FileInteractions(_Recorder):
    """Append-only JSONL: one line per record, one per rating. The self-hosted
    container writes it to the state volume; dev runs to STATS_DIR."""
    backend = "file"

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self._lock = threading.Lock()

    def _append(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False)
        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def put(self, record: dict) -> bool:
        try:
            self._append({"kind": "interaction", **record})
            self.writes += 1
            return True
        except Exception as e:  # noqa: BLE001
            self._note("put", e)
            return False

    def rate(self, rating: dict, now: float | None = None) -> bool:
        try:
            self._append({"kind": "rating", "rated_at": time.time() if now is None else now, **rating})
            self.writes += 1
            return True
        except Exception as e:  # noqa: BLE001
            self._note("rate", e)
            return False

    def query_day(self, day: str) -> list[dict]:
        """That UTC day's records, each with its latest rating folded in."""
        records: dict[str, dict] = {}
        ratings: dict[str, dict] = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    kind = obj.pop("kind", "interaction")
                    if kind == "rating":
                        ratings[obj["answer_id"]] = obj
                    elif obj.get("day") == day:
                        records[obj["answer_id"]] = obj
        except FileNotFoundError:
            return []
        for aid, r in ratings.items():
            if aid in records:
                records[aid].update({k: r[k] for k in ("stars", "reasons", "comment", "rated_at") if k in r})
            elif parse_answer_id(aid) is not None and _day_of(parse_answer_id(aid)) == day:
                records[aid] = {"answer_id": aid, "day": day, **{k: r[k] for k in ("stars", "reasons", "comment", "rated_at") if k in r}}
        return sorted(records.values(), key=lambda r: r.get("ts", 0))


def _s(v) -> dict:
    return {"S": str(v)}


def _n(v) -> dict:
    return {"N": str(int(v)) if float(v).is_integer() else repr(float(v))}


def _bool(v) -> dict:
    return {"BOOL": bool(v)}


def ensure_table(client, name: str) -> None:
    """Create the table (pk HASH + sk RANGE, on-demand, TTL on `ttl`) if it
    does not exist. For tests and the preview; production has the stack."""
    if name not in client.list_tables().get("TableNames", []):
        client.create_table(
            TableName=name,
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"},
                       {"AttributeName": "sk", "KeyType": "RANGE"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=name)
    ttl = client.describe_time_to_live(TableName=name)["TimeToLiveDescription"]
    if ttl.get("TimeToLiveStatus") not in ("ENABLED", "ENABLING"):
        client.update_time_to_live(TableName=name,
                                   TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"})


class DynamoInteractions(_Recorder):
    backend = "dynamodb"

    def __init__(self, table: str, *, region: str | None = None, endpoint_url: str | None = None,
                 ttl_days: int = 180, client=None):
        super().__init__()
        if client is None:
            import boto3  # lazy: only the Lambda image carries boto3
            from botocore.config import Config
            client = boto3.client(
                "dynamodb", region_name=region, endpoint_url=endpoint_url,
                config=Config(connect_timeout=1, read_timeout=2, retries={"max_attempts": 2}),
            )
        self._c = client
        self.table = table
        self.ttl_s = ttl_days * 86400

    def put(self, record: dict) -> bool:
        try:
            pk, sk, ts_ms = _keys(record["answer_id"])
            item = {
                "pk": _s(pk), "sk": _s(sk),
                "answer_id": _s(record["answer_id"]),
                "session_id": _s(record.get("session_id", "")),
                "schema": _s(record.get("schema", RECORD_SCHEMA)),
                "ts": _n(record["ts"]), "day": _s(record["day"]),
                "question": _s(record["question"]),
                "history": _s(json.dumps(record.get("history", []), ensure_ascii=False)),
                "cache_hit": _bool(record["cache_hit"]),
                "cache_key": _s(record.get("cache_key", "")),
                "cache_version": _s(record.get("cache_version", "")),
                "outcome": _s(record["outcome"]),
                "dev_mode": _bool(record.get("dev_mode", False)),
                "steps": _s(json.dumps(record.get("steps", []))),
                "total_ms": _n(record.get("total_ms", 0)),
                "events": _s(json.dumps(record.get("events", []), ensure_ascii=False)),
                "trimmed": _bool(record.get("trimmed", False)),
                "recorded_at": _n(record.get("recorded_at", time.time())),
                "ttl": _n(ts_ms / 1000 + self.ttl_s),
            }
            self._c.put_item(TableName=self.table, Item=item)
            self.writes += 1
            return True
        except Exception as e:  # noqa: BLE001
            self._note("put", e)
            return False

    def rate(self, rating: dict, now: float | None = None) -> bool:
        """Upsert the rating onto the answer's item. A missing item (the record
        write failed, or the id is a guess) gets a stub carrying only the
        rating — never a reason to lose a visitor's verdict, and TTL'd like
        everything else."""
        now = time.time() if now is None else now
        try:
            pk, sk, ts_ms = _keys(rating["answer_id"])
            self._c.update_item(
                TableName=self.table, Key={"pk": _s(pk), "sk": _s(sk)},
                UpdateExpression=("SET stars = :stars, reasons = :reasons, #c = :comment, rated_at = :now, "
                                  "answer_id = :aid, #d = :day, #t = if_not_exists(#t, :ttl)"),
                ExpressionAttributeNames={"#c": "comment", "#d": "day", "#t": "ttl"},
                ExpressionAttributeValues={
                    ":stars": _n(rating["stars"]),
                    ":reasons": {"L": [_s(r) for r in rating.get("reasons", [])]},
                    ":comment": _s(rating.get("comment", "")),
                    ":now": _n(now), ":aid": _s(rating["answer_id"]),
                    ":day": _s(pk[len("day#"):]),
                    ":ttl": _n(ts_ms / 1000 + self.ttl_s),
                },
            )
            self.writes += 1
            return True
        except Exception as e:  # noqa: BLE001
            self._note("rate", e)
            return False

    def query_day(self, day: str) -> list[dict]:
        out = []
        kw = {"TableName": self.table, "KeyConditionExpression": "pk = :pk",
              "ExpressionAttributeValues": {":pk": _s(f"day#{day}")}}
        while True:
            r = self._c.query(**kw)
            out.extend(_decode(i) for i in r.get("Items", []))
            if "LastEvaluatedKey" not in r:
                return out
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def _decode(item: dict) -> dict:
    rec = {}
    for k, v in item.items():
        if k in ("pk", "sk"):
            continue
        if "S" in v:
            rec[k] = json.loads(v["S"]) if k in ("history", "steps", "events") else v["S"]
        elif "N" in v:
            f = float(v["N"])
            rec[k] = int(f) if f.is_integer() else f
        elif "BOOL" in v:
            rec[k] = v["BOOL"]
        elif "L" in v:
            rec[k] = [x.get("S", "") for x in v["L"]]
    return rec


def from_env():
    """A recorder for this deployment, or None when recording is off:
    RECORD_INTERACTIONS=0 anywhere; on the DynamoDB backend, no
    INTERACTIONS_TABLE (a stack from before the table existed keeps serving,
    loudly)."""
    if os.environ.get("RECORD_INTERACTIONS", "1").strip().lower() in ("0", "false", "no", "off"):
        log.info("Interaction recording is OFF (RECORD_INTERACTIONS)")
        return None
    ttl_days = int(os.environ.get("INTERACTION_TTL_DAYS", "180"))
    backend = os.environ.get("STATE_BACKEND", "local").strip().lower()
    if backend == "dynamodb":
        table = os.environ.get("INTERACTIONS_TABLE", "").strip()
        if not table:
            log.warning("STATE_BACKEND=dynamodb but INTERACTIONS_TABLE is unset: interaction recording is OFF")
            return None
        return DynamoInteractions(table, region=os.environ.get("AWS_REGION") or None,
                                  endpoint_url=os.environ.get("DYNAMODB_ENDPOINT_URL") or None,
                                  ttl_days=ttl_days)
    path = os.environ.get("INTERACTIONS_FILE", "").strip() or os.path.join(
        os.environ.get("STATS_DIR", os.environ.get("DATA_DIR", "data")), "interactions.jsonl")
    return FileInteractions(path)
