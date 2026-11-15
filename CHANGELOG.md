# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-15

### Added
- Customer verification (order ID plus email or phone) with server-side session state;
  after verification, order tools take no order ID, so the model cannot be steered to
  another customer's order.
- Lockout after 3 failed verification attempts, with automatic escalation to a human.
- `policy.py`: store policy as plain code (30-day refund window, cancel only while
  processing, refunds above $200 need a human). The LLM only explains the result, and the
  policy is checked again at execution time.
- Confirmation gate enforced in code: cancel and refund tools refuse to run until the
  customer has sent a new message after the policy check.
- Idempotent actions: refunds are unique per order at the database level; cancelling twice
  reports `already_cancelled`.
- `escalate_to_human`, and a full audit log (`actions` table) of every tool call.
- Cases saved for every conversation, with outcome, action and order taken from database
  facts. The LLM writes only `issue_type` and a summary, and a fallback summary is stored if
  its output is unusable.
- MCP server over stdio exposing read tools, policy and escalation (not write tools).
- FastAPI service: `POST /chat`, `POST /chat/stream` (SSE), `POST /sessions/{id}/close`,
  `GET /health`, with `X-API-Key` authentication.
- Telegram front-end that talks only to the API, with a typing indicator and a 600 s timeout
  for slow local models.
- Dockerfile and a compose profile for the app; GitHub Actions CI (ruff and pytest).
- 24 automated tests that need neither an LLM nor an API key.
- Eval harness: 9 scenarios (functional and red-team), repeated runs, subprocess timeout,
  token counts, invented-promise detection, and separate SAFETY and QUALITY failures.
- Local development with Ollama through the Anthropic-compatible endpoint
  (`ANTHROPIC_BASE_URL`), with no code changes.

### Changed
- Database schema extended with `sessions`, `refunds`, `escalations` and `actions`. Existing
  development databases must be recreated (`docker compose down -v`).
- SQL files moved into the package (`src/support_bot/sql/`) so installed copies can find them.
- The dev Postgres is published on host port 5433.
- Requires Python 3.11 or newer.
- `Agent.send()` is a generator of events, so the CLI, API and Telegram share one loop.
- New `MAX_TOKENS` setting, because reasoning models spend output tokens on thinking.

### Fixed
- A model reply with no text no longer leaves the customer in silence or stores an empty
  assistant message; a fallback message is sent instead.

## [0.2.0] - pre-release

### Added
- PostgreSQL for real order data: `customers`, `orders`, `order_items`, `cases`, `messages`,
  seeded with demo scenarios using relative dates.
- Policy limits also expressed as database `CHECK` constraints (second line of defence).
- Dev Postgres through `docker compose`.

### Changed
- All SQL confined to `db.py`; Postgres types converted at the database boundary.
- `fake_data.py` removed.

## [0.1.0] - pre-release

### Added
- Tool-use loop with `lookup_order` and `check_return_eligibility` on mock data.
- Structured JSON case summary.
- `src/` package layout with downward-only imports, moved from a single `bot.py`.