# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases follow Semantic Versioning.

## [Unreleased]

### Added

- `/auth/login` is throttled per client address (10 attempts per 5 minutes) in its own bucket, separate from the
  anonymous chat budget.
- Frontend CI job: oxlint, type-check and production build run on every push and pull request.
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

- `backend/services/` is grouped by capability: `chat/`, `documents/` and `leads/`; billing and news stay top-level.
- Small modules folded into the module that owns them: the price/commitment risk check now lives in
  `backend/ai/guardrails.py`, conflict severity in `document_conflict_service`, document coverage and classifier
  project resolution in `project_scope_service`, and the category helpers in `backend/models/document.py`.
- Schemas consolidated by area: `chat.py` (sessions, messages, HITL, feedback), `document.py` (documents,
  relations, conflict flags) and `customer.py` (customer chat, summaries, live inbox).
- Staff-only frontend routes (admin console, live inbox, news workspace) load on demand; the initial JS download
  drops from 659.6 kB to 456.0 kB (gzip 169.5 kB to 125.2 kB).
- About 2,750 lines of CSS that no component references were removed; the CSS bundle drops from 296.9 kB to
  246.2 kB.
- The project-image CDN URL is one constant (`frontend/src/config.ts`) instead of 225 copies.
- Log messages, docstrings, script output and developer guides are in English.
- PyMuPDF is capped below 2.0, whose table extraction changes identifier spacing in price tables.
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

### Removed

- The CLI-only metadata audit (`metadata_audit_service`, `scripts/audit_document_metadata.py`).
- Unused settings `APP_PORT`, `APP_HOST`, `LLM_API_KEY`, `LLM_MODEL` and the unused `VITE_WS_URL` build argument.
- Duplicate and unreferenced images in `frontend/public/`.

### Fixed

- Test accounts with public passwords are no longer created or reset when `APP_ENV` is a production value.
- On Render, anonymous visitors are no longer counted as the load balancer's single address by the rate limiter
  (`TRUSTED_PROXY_COUNT=1`).
- A document blocked as a duplicate during reclassification records `block_reason`, so the Admin list labels it as
  a duplicate.
- Project alias matching keeps the letter "đ" instead of dropping it.
- Bound fact-extraction state explicitly instead of capturing a loop variable in an ingestion closure (`B023`).
