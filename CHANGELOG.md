# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases follow Semantic Versioning.

## [Unreleased]

### Added

- Chat input guardrails (`backend/ai/guardrails.py`): Unicode normalisation, invisible-character stripping, a
  `CHAT_MAX_QUERY_CHARS` length cap, and a deterministic prompt-injection refusal at `preflight`.
- Output guard that withholds any answer reproducing the system instructions.
- `CHAT_LATENCY_BUDGET_SECONDS` (default 5 s): the Verifier retry runs only when it still fits the budget.
- "Luxe" frontend theme: ivory/ink neutrals with a single champagne-gold accent, Cormorant Garamond headlines,
  refined buttons, cards, chat bubbles, focus rings and reduced-motion support (`frontend/src/styles/luxe.css`).
- Admin navigation grouped into "Kinh doanh", "Tri thức" and "Chất lượng AI" dropdowns so the bar stays on one row;
  catalogue, zone and news pages share one serif heading voice; the marketing footer no longer shows inside the admin console.
- Dependency-aware readiness probes for MySQL, Qdrant, and Redis at `/health/ready`, plus a process-only liveness
  probe at `/health/live`.
- Prometheus metrics at `/metrics`, including HTTP request, latency, in-progress, dependency state, and dependency
  probe latency series.
- Measurable 30-day availability, latency, and error-rate objectives in `SLO.md`.
- Contributor community standards in `CODE_OF_CONDUCT.md`.

### Changed

- Live-path Gemini calls use the minimum thinking budget and per-call timeouts; query embeddings retry once with a
  capped delay; the Gemini client has a request timeout.
- Lead scoring's LLM pass now overlaps the customer's answer instead of preceding it.
- Route handlers without `await` are now sync, so FastAPI runs them in its threadpool instead of blocking the event
  loop with the synchronous pipeline.
- User questions and chat history are wrapped in escaped `<user_question>` / `<conversation_history>` tags in the
  generation prompt, and the Verifier prompt tags its inputs the same way.
- Project rows are loaded once per request and Qdrant collection existence is cached for 60 s.
- Default `COHERE_RERANK_TIMEOUT_SECONDS` lowered from 2.5 to 1.5; Redis socket timeouts lowered from 2 s to
  0.5 s and the inventory API timeout from 5 s to 2.5 s, so no single fallback can spend the whole chat budget.
- The BM25 sparse model is warmed on a background thread at startup when hybrid search is enabled.
- `/health` is now a backward-compatible readiness endpoint and returns HTTP 503 when a required dependency fails.
- Docker Compose, the image healthcheck, and Render now use `/health/ready`.
- Ruff now enforces Bugbear, Bandit, Simplify, and return-style rules in addition to the existing rule groups.

### Fixed

- Bound fact-extraction state explicitly instead of capturing a loop variable in an ingestion closure (`B023`).
