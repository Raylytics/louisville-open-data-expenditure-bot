# How Lou builds its charts

The chart under an answer is **never chosen or described by the LLM**. The
model writes SQL and prose; everything visual is decided by deterministic,
unit-tested code that reads the result frame and the SQL. This document
records the approach, the rules and where they came from, so the next person
does not have to rediscover it from the code (reviewed 2026-10-23).

## Why deterministic

Charts are a *load-bearing caveat surface*: the partial-year marker, the
total-row exclusion and the axis format all exist because a wrong chart was
served to a reader. Prompts do not hold such rules reliably (see
`eval/judge-2026-09-25.md`), and an LLM-chosen chart cannot be unit-tested
against regression. So the LLM's only influence on the visual is the *shape
of the result*: which columns it selects, what it names them, and how it
orders rows. The prompts nudge that shape; the code does the rest.

## The pipeline (one request)

```
SQL (LLM)  ->  DuckDB  ->  result_df
                              |
   order_for_display / move_totals_to_end          data_model.py
                              |
   infer_chart(result_df, sql)      type, label column, value column
                              |
   sort by label (line only) -> drop_total_rows -> chart_window (30 points)
                              |
   measure_kind (currency | count)   is_time_named -> label_kind
   chart_partial_markers (partial year + data-through date)
                              |
   SSE `chart` event                                app.py ~L1815
                              |
   Chart.js render, theme tokens, hatched partial period   static/index.html
```

Every step is a pure function in `data_model.py` with tests in
`tests/test_known_answers.py`; `app.py` only wires them and emits the event;
the frontend only draws what the event says.

## The rules, and the incident behind each

**Which columns** (`infer_chart`)
- Value (y): a numeric column that varies and is not a time id. Prefer the
  measure the SQL `ORDER BY` keyed on (`sql_order_measure`), else a float
  (dollar sum) over an integer count, else the last candidate. Window
  ordinals (`ROW_NUMBER`, `RANK`) are excluded unless they are the only
  measure (`sql_ordinal_columns`). *Origin:* a multi-measure salary ranking
  charted the average in max-pay order; a kept row number drew a staircase.
- Label (x): the most-varying string or time-named dimension; constants
  (a filtered `fiscal_year`) are skipped.

**Which type** (`infer_chart`, `is_share_of_whole`)
- `line`: time-named axis, one row per period, chronologically sortable
  (numbers, dates, or zero-padded ISO parts like `2021-01`). Month *names*
  fail the sort test and fall to bars.
- `pie`: only a **complete partition of a few positive parts**: no `LIMIT`
  anywhere in the SQL, no `HAVING`, no `WHERE` that names the label column
  (`sql_filters_label`: "compare Police, Fire and EMS" is three groups of
  eighty, not a whole; a filter on another column such as the fiscal year
  narrows the population, not the partition, and is fine), a categorical
  (non-time) axis, 3 to 6 rows after null labels and any grand-total row are
  set aside (the same rows `chart_window` drops, so what is counted is what
  is drawn; a ROLLUP total has a NULL label), every label distinct, every
  value finite and > 0. The SQL is required: without it completeness cannot
  be proven and the frame gets bars. Known limit: a WHERE on the label's
  *source* column behind an alias is not seen and errs toward a pie.
  *Origin (2026-10-23):* the old rule was "five rows or fewer", which drew a
  pie of "top 5 agencies" as if the other 80 did not exist, a two-slice pie
  for every two-year comparison, and tried to render negative slices for a
  net-credit payee. The label-filter, null-label and duplicate-label tests
  were added the same day after review (roborev 6660).
- `bar`: everything else. It is the safe default; a bar is correct for any
  ranking or comparison.
- `None` when nothing fits: fewer than 2 rows or more than `CHART_MAX_ROWS`
  (300). That ceiling must stay well above the 30-point render cap, or a
  61-row agency ranking produces no chart at all (it did).

**Orientation** (`label_kind`, frontend)
- The event carries `label_kind`: `time` when the label column is
  time-named, else `category`. Bar charts over categories are drawn
  **horizontal** so payee and agency names read in full (34 characters
  before truncation instead of 18 at a 45-degree tilt), and the box height
  grows with the row count (24px a bar, 300 to 640px). Time axes and lines
  stay vertical, read left to right. *Origin (2026-10-23):* review against
  the dataviz guidance this project uses; long-named categories are the
  textbook case for horizontal bars.

**Which rows**
- `drop_total_rows` / `total_row_mask`: a grand-total row equals the sum of
  every other bar and would double the axis. Matched by label shape
  (`TOTAL`, `TOTAL - ALL GRANT FUNDS`, `GRAND TOTAL`) or by a label
  containing "total" whose value equals the sum of the rest, so real payees
  such as TOTAL TOOL SUPPLY INC survive. The same detector moves totals to
  the end of the table and corrects the row count, so every surface agrees.
- `chart_window`: at most `CHART_MAX_POINTS` (30). Which end to keep is
  decided from the *data*, not the chart type: an ascending time axis keeps
  the tail (newest periods), a descending one the head, anything else the
  head. The title says which slice ("last 30 of 61", "top 30 of 102", or
  "30 of 102" when the values do not actually descend). Null labels are
  dropped first; a `NaT` bucket otherwise lands at the newest end of a time
  axis and reads as the current month.
- Line charts are re-sorted by the label so a "top 5 years by spend" result
  reads chronologically instead of zig-zagging in rank order.

**Axis format** (`measure_kind`)
- `currency` or `count`, from the column *name* first (count words like
  `count`, `num_`, `employees`; unambiguous money words like `spend`,
  `amount`, `salary`), then integer dtype means count, else currency. The
  money list deliberately omits `total`, `paid`, `fund`, which also appear in
  count aliases (`total_vendors`). The frontend prefixes `$` only for
  currency, so "1,500 employees" is not "$1.5K". The prompt now asks the
  model to name measures accordingly, because this is where the name lands.

**Partial periods** (`period_context`, `chart_partial_markers`)
- A year axis that includes the in-progress fiscal year gets
  `partial_labels` and `data_through`. The frontend keeps the point (it is
  real data) and marks it: hatched bar or dashed segment with a hollow
  warning-colored dot, a hatched band behind it on lines, "partial period"
  in the tooltip, and a side note naming the date the data runs through.
  Expenditures answer only for *fiscal* years; a calendar axis over them, or
  a bare `year` column, gets no marker rather than a wrong one. *Origin:*
  FY2026 held 8.5 months of payments and plotted as a collapse in spending.
- The same `period` object feeds the deterministic headline, so chart and
  headline cannot disagree about which year is complete.

## Where the prompts touch the chart

The model is told three things, all about the *shape* of the result
(`app.py`, the `sql_system` string; `analytics_agent.build_interpret_prompt`):

1. Always give a multi-row result an explicit `ORDER BY` (time ascending for
   trends, measure descending otherwise). Unordered rows render as an
   unsorted bar chart, and the chart layer refuses to reorder what the query
   ordered (`order_for_display` reorders only results with no ORDER BY at
   all, after seven attempts at something smarter each flipped a result).
2. Shape the result to chart cleanly: one label column plus the measure the
   question asks about, measures named for what they hold (`total_spend`,
   `payment_count`), one row per period with the period as a bare number or
   `YYYY-MM`.
3. In the interpretation: the chart and table stand beside the text, so
   summarize instead of transcribing and write about the figures, not the
   chart.

Prompt rules are stated positively (`tests/test_prompt_lint.py`: models copy
quoted failure text). Any change to these lines moves `CACHE_VERSION` and
orphans every warmed starter; re-warm on deploy (`LOU_WARM=1`).

## Rendering (frontend)

- Chart.js, self-hosted (`static/vendor/chart.umd.min.js`), rendered inside
  its own try/catch so a blocked library or a render throw never aborts the
  SSE loop and loses the answer that streams after the chart (test-enforced).
- Colors come from the theme tokens at build time (`--accent`, `--ink-2`,
  `--rule`, `--paper`, `--warn-mark`), so a theme switch rebuilds the chart
  in the new palette (`redrawCharts`). The warning color is reserved for
  partial periods; pie slices use a fixed six-hue order anchored on the
  accent, never cycled past six because the backend caps a pie at six.
- Single series, so no legend except on pies; recessive grid; the canvas
  carries an `aria-label` with the first twelve label/value pairs.
- No animation: the chart is built in one synchronous step when its box
  scrolls into view (`pendingCharts`), so a half-height animation never
  shows.

## Changing it

| You want to... | Change | Then |
|---|---|---|
| Alter chart-type selection | `infer_chart` / `is_share_of_whole` in `data_model.py` | add a case to `tests/test_known_answers.py` (chart inference section) |
| Change the look | `static/index.html`, the `event.type === 'chart'` block | keep `test_chart_rendering_is_isolated_from_the_stream_loop` and `test_named_categories_are_drawn_as_horizontal_bars` green |
| Add a field to the `chart` event | `app.py` chart_evt | bump `EVENT_SCHEMA_VERSION` (cached starters replay old frames otherwise) and pin it in `tests/test_ask_endpoint.py` |
| Change what the model is asked for | `sql_system` in `app.py`, `build_interpret_prompt` | state it positively; `python eval/run_eval.py --provider cerebras` before deploying; re-warm |
| Add an axis-format word | `CHART_COUNT_KEYWORDS` / `CHART_MONEY_KEYWORDS` | read the `measure_kind` docstring first: the money list must stay unambiguous |

Invariants worth keeping: `CHART_MAX_ROWS` > `CHART_MAX_POINTS`; `period` is
computed once per request and shared by chart and headline; no code path
re-sorts a result the SQL ordered (except the line chart, which sorts by its
own time axis); the frontend decides nothing from label strings that the
backend could have decided from the column.

## Review findings, 2026-10-23

What the review found and what changed, kept here as the record:

- **Pie was over-used.** Any 2 to 5 row result became a pie, including
  top-N subsets, two-way comparisons, time axes with few periods and
  frames with negative values. Replaced by the completeness gate above
  (`is_share_of_whole`, `sql_limits_result`); a top-5 is now bars.
- **Long category names were unreadable** on vertical bars (18-character
  truncation, 45-degree tilt). Categorical bars are now horizontal with a
  taller box; the backend's new `label_kind` field drives it.
- **The pie palette** was 14 hues cycled, with the warning color as the
  second slice. Now six fixed hues, warning color reserved.
- **The prompts said almost nothing about result shape.** The SQL prompt
  now asks for one label column plus the asked-about measure, named for
  what it holds, one row per period; the interpret prompt tells the model
  the chart is beside the text so it writes about figures, not the chart.
- **Nothing was documented.** This file; linked from `CLAUDE.md` and the
  README.
