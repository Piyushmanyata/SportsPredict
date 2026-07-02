# SportsPredict MCP API reference (verified against the live API docs)

Persisted here so future sessions don't have to re-derive field names from
the HTML docs export. Re-verify only if a call errors unexpectedly (same
policy as section 4.3 of the spec for event/lobby IDs).

## Read endpoints

**`list_matches`** (`event_id`, `lobby_id` both optional) fields:
`id, name, event_id, opening_time, closing_time, open_market_count`.
No `status` or `teams` field -- `name` is a single combined string
(e.g. `"Mexico vs South Africa"`). `opening_time`/`closing_time` are
ISO-8601 UTC, e.g. `"2026-06-11T19:00:00Z"`.

**`list_markets`** (`lobby_id`, `match_id` optional, `match_id` strongly
recommended -- unfiltered is ~720 markets) fields: `id, question,
event_type, status, match {id, name, opening_time, closing_time},
lobby_id`. No `market_id` key -- the market's own id field is just `id`.

**`list_predictions`** (`lobby_id` optional) fields: `type, id, market_id,
lobby_id, question, probability, brier_score, market_status,
created_date`. **`probability` here is a 0-1 decimal** (e.g. `0.75`), not
1-99. `brier_score` is `null` until settled.

**`list_results`** (`lobby_id` optional) fields: `type, id, market_id,
lobby_id, question, probability_submitted` (0-1 decimal), `brier_score`
(populated), `market_status` (`"settled"`), `created_date`.

## Write endpoints

`submit_prediction` / `submit_predictions_batch` (<=50 items) /
`update_prediction`: **probability is an integer 1-99 inclusive** (0 and
100 rejected). Body: `market_id`, `lobby_id`, `probability` (+ optional
`api_key_id` for the 2-bot OAuth case). Batch response: `{total,
succeeded, failed, results: [{market_id, success, trade{...}} |
{market_id, success: false, error}]}` -- failures never roll back
successes.

Note the read/write asymmetry: reads return 0-1 decimals, writes take
1-99 integers. Always `x = round(p * 100)` clamped to `[1, 99]` when
submitting, and `p = x / 100.0` when comparing a read-back value to an
internal probability.

## Other endpoints

- `list_events` (`limit`, default 25 / max 100)
- `list_lobbies` (`event_id` optional)
- `join_lobby` (lobby id in path)

## Errors and rate limits

60 req/min per IP, shared across REST + MCP. `400` malformed/empty batch
(also: batch of 0 or >50 items) · `401` auth · `403` not a lobby member
· `404` bad UUID · `409` already predicted (submit) / already a member
(join) · `422` bounds (1-99 int) or bad UUID · `429` back off 30-60s ·
`500` exponential backoff retry.

## Structural notes

No pagination cursor on any list endpoint besides `limit` on
`list_events`. `list_markets` nests the parent `match` object inline.
Transport is stateless Streamable HTTP/JSON-RPC -- re-sync every
session, never assume the server remembers IDs or prior values. No
`current_price` field and no webhooks -- results must be polled via
`list_results`.
