# Experience capture: interaction records, ratings, review

Epic `louisville-open-data-2jj`. Every answer the site serves is kept as an
*experience* so the person who asked can rate it (five stars) and so old
answers can be reviewed, semi-automatically, to improve the bot. This page is
the contract; `interactions.py` is the code.

## What is recorded, and what is not

**Never recorded:** IP address, user agent, cookies, headers of any kind,
accounts, e-mail. The record's key set is closed and tested
(`tests/test_interactions.py::test_record_has_a_closed_key_set_and_nothing_identifying`);
adding a field is a deliberate change to that test.

**Recorded, per answer:**

| field | what |
|---|---|
| `answer_id` | minted by the server for every response, cached replay included; `<ms hex>-<32 random bits>`, so it is unguessable, sorts by time and locates its own item |
| `session_id` | a random token the browser mints into `sessionStorage` for one tab (`SESSION_ID` in `static/index.html`), so one sitting's questions read back in order. The server never sets it, validates only its shape, and stores `''` when it is missing or malformed |
| `question`, `history` | the question verbatim (it *is* the experience) and the last 6 turns the client sent, each capped at 1,000 chars |
| `events` | every SSE frame of the answer (`sql`, `results`, `step`, `chart`, `interpretation`, `note`, `error`, …) as decoded JSON, minus the uncached `answer` frame |
| `steps`, `total_ms` | the pipeline timeline pulled from the `step` frames: stage, status, ms, model, tier |
| `outcome` | `ok`, `error`, `incomplete` (no interpretation), `abandoned` (the client went away mid-stream) |
| `cache_hit`, `cache_key`, `cache_version` | whether this was a replay, and of which cached answer, so a rating aggregates against the answer it was given for and a re-warm invalidates cleanly |
| `dev_mode`, `trimmed`, `schema`, `ts`, `day`, `recorded_at` | housekeeping |

The record is written once, after the last frame, from the `finally` of the
stream wrapper in `app.ask`, so an abandoned or crashed stream is recorded as
such. The write is best-effort: a store failure is logged, counted on
`/api/health` (`interactions`), and never reaches the answer.

Oversized answers are trimmed under DynamoDB's 400 KB item limit, bulkiest
and least reviewable parts first: result rows, then `debug`/`log` chatter,
then the chart payload, then over-long prose. The SQL, the steps and the
interpretation always survive (`interactions.trim_events`).

## Where it lives

| deployment | store | set by |
|---|---|---|
| Lambda (production) | DynamoDB table `lou-interactions`: `pk = day#<UTC day>`, `sk = <ts_ms>#<answer_id>`, TTL `ttl` | `INTERACTIONS_TABLE` from the stack (`infra/cdk/lou_stack.py`); unset = recording off, with a warning |
| preview (`infra/preview.sh`) | the same table on DynamoDB Local | the script creates it |
| self-hosted / dev | append-only JSONL, one line per record and one per rating | `$STATS_DIR/interactions.jsonl`, or `INTERACTIONS_FILE` |

`RECORD_INTERACTIONS=0` turns recording off anywhere. **Records are kept for
good** (decision 2026-10-27, `louisville-open-data-2jj.5`): no `ttl`
attribute is written, so the table's TTL never touches them. Setting
`INTERACTION_TTL_DAYS=<n>` expires records (and rating stubs) after n days
instead. A rating whose answer has no record behind it (the record write
failed, or the id was guessed inside the 30-day rating window) lands as a
stub that always expires (`interactions.STUB_TTL_DAYS`, 30), so guessed ids
cannot pile up; a rating on a real record never adds a TTL to it. At ~8.5 KB
a record, a year of a few hundred questions a day is
under 1 GB, about $0.25/month of DynamoDB storage. The JSONL file has no
retention either. The table is `RETAIN` on stack deletion (records are not
rebuildable, unlike `lou-state`). The table sits inside the Lambda permissions
boundary's `lou-*` DynamoDB grant, which is why DynamoDB rather than S3: the
boundary grants the runtime no S3 write, and changing it is a human IAM step
(Phase 4).

One day's records are one `Query` (`query_day`), paged. A rating is an
`UpdateItem` upsert on the answer's item, so a rating that arrives after a
failed record write still lands as a stub carrying only the rating.

## The `answer` frame

Every `/api/ask` stream opens with
`{"type": "answer", "answer_id": "...", "cached": true|false}`. It is built
outside `send()` and so never cached: each replay of a cached answer gets a
fresh id, and `EVENT_SCHEMA_VERSION`, which guards the *shape of cached
frames*, is untouched. The frontend keeps it on the card (`card.answerId`)
for the rating widget. The short-circuit responses (empty question, rate
limited, bad body) carry no `answer` frame and are not recorded.

## Ratings

Five stars under every answer that carried an `answer` frame
(`renderRating` in `static/index.html`). The first click stores the stars at
once; reason chips (`wrong-number`, `wrong-period`, `not-answered`,
`chart-off`, `slow`, `confusing`, `great`) and a short note appear after it
and re-send the same rating, which the server upserts, so the latest verdict
wins. The payload is the `answer_id`, the tab's `session_id`, `stars`,
`reasons`, `comment`, and nothing else; it is posted to `POST /api/feedback`
with the SigV4 body hash CloudFront OAC requires.

The endpoint (`app.feedback`) validates through `interactions.clean_rating`
(stars 1-5, up to 8 reasons of 40 lower-case token chars, a 500-char
comment), refuses ids older than `RATING_MAX_AGE_DAYS` (30) or from the
future, caps the
body at 16 KB, and rate-limits in its own per-IP bucket (`fb:` prefix) so
rating never spends the question allowance. The IP feeds the limiter only.
A store failure or recording being off answers 503 with a plain message; the
widget shows it instead of a false "Thanks".

## Review (Phase 3)

A pull script reads days of records (admin endpoint or the read-only AWS
profile), an offline LLM judge grades each with the rubric from
`eval/judge-2026-09-25.md`, and a weekly report lists low-rated answers,
judge disagreements, p95 per stage and provider, vocabulary gaps for
`grounding.py`, and candidate golden cases to promote into
`eval/golden.yaml`.

## Visitor notice

`branding.privacy_note` (city pack, default from `/api/config`) renders under
the question box: *"Questions and ratings are stored to improve Lou. Please do
not type personal information."* Wording approved and retention decided
(keep for good) by the owner on 2026-10-27 (`louisville-open-data-2jj.5`).
