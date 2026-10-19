# Development Guide

How to run the project in dev mode, use the mock inventory API, manage migrations and read the logs. See [`README.md`](../README.md) for the Docker Compose quick start.

## Requirements

- Python 3.11
- Node.js 20+ and npm
- Docker Desktop (to run with Docker Compose)

## Mock inventory API

Unit stock is looked up **in real time over HTTP**, never ingested into Qdrant — availability changes constantly, so vectorising it would answer with stale numbers. During the build phase a mock API on [mockapi.io](https://mockapi.io) uses the same shape as the internal production API, so switching to the real API only means changing environment variables, not code.

**Step 1 — Create the resource on mockapi.io**

Create a project and add a resource named `units` with the fields below (mockapi adds its own `id`; `lookup_inventory` ignores unknown fields). Three fields are required for a record to be valid: `unit_code`, `project_id` and `status`. The more of the remaining fields are filled in, the more precise the advice:

| Field | Type | Example | Notes |
| :--- | :--- | :--- | :--- |
| `unit_code` | string | `OP3-A-0203` | Unit code |
| `project_id` | string | `ocean-park-3` | Matches the `project_id` passed to the lookup |
| `subdivision` | string | `The Zenpark` | Subdivision of the unit |
| `tower` | string | `R1.03` | Tower |
| `floor` | string | `12` | Floor; a string so values like `12A` survive |
| `unit_type` | string | `2PN` | `1PN`…`10PN`, `Penthouse`, `Studio`, `Shophouse`, `Duplex` |
| `area_m2` | number | `68.2` | Area in m² |
| `direction` | string | `Đông Nam` | Unit/balcony orientation, as the source names it |
| `view_type` | string or array | `["Hồ", "Cảnh quan nội khu"]` | One or more views; a string may be separated by `,`, `|` or `/` |
| `price` | number | `3600000000` | VND. The string `"3600000000"` is accepted too |
| `status` | string | `available` | `available` / `reserved` / `sold` |

The endpoint returns a JSON array:

```json
[
  { "unit_code": "R1.03-1205", "project_id": "ocean-park-1",
    "subdivision": "The Zenpark", "tower": "R1.03", "floor": "12",
    "unit_type": "2PN", "area_m2": 68.2, "direction": "Đông Nam",
    "view_type": ["Hồ", "Cảnh quan nội khu"],
    "price": 3600000000, "status": "available" }
]
```

**Step 2 — Point `.env` at the endpoint**

```bash
INVENTORY_API_URL=https://<project-id>.mockapi.io/units
INVENTORY_API_KEY=
```

> The variable must be named exactly `INVENTORY_API_URL`. `Settings` uses `extra="ignore"` (`backend/core/config.py`), so a misspelled name (e.g. `INVENTORY_MOCK_API`) raises **no error** — it is silently ignored and every lookup fails with "INVENTORY_API_URL is not configured".

Leave `INVENTORY_API_KEY` empty for mockapi.io. When it is set, it is sent as an `Authorization: Bearer <key>` header — intended for the internal production API.

**Step 3 — Check it**

```bash
python -c "from backend.services.chat.inventory_service import lookup_inventory; print(lookup_inventory('ocean-park-3', 'Còn căn 2PN nào trống không?'))"

# or the unit tests (no network needed; httpx is mocked)
pytest tests/test_services/test_inventory_service.py -v
```

**How it works** — `lookup_inventory(project_id, query)` in `backend/services/chat/inventory_service.py`:

- Sends `project_id` as a query parameter, with a short timeout inside the chat latency budget.
- Reads the unit type from the Sale's natural-language question ("còn căn **2PN** không") and filters on it; with no unit type mentioned, it returns the whole stock list.
- **No matching unit → returns `[]`**, which is a valid answer ("2PN is sold out").
- **API unreachable → raises `InventoryApiError`**, so the pipeline shows "stock cannot be looked up right now". The two cases are kept apart: merging them would report a system failure when the units are simply sold out.
- A record missing a required field is skipped instead of failing the whole lookup.

## Running by hand (dev mode, hot reload)

**Backend (FastAPI)**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
alembic upgrade head               # REQUIRED before the first run

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# or: make run
```

> With Docker Compose there is no need to run `alembic upgrade head` by hand — the container applies migrations on startup (`docker-entrypoint.sh`).

**Project images**

The floor-plan and perspective images on the catalogue pages are not stored in the database; the frontend loads them from the public image bucket (`PROJECT_IMAGES_BASE_URL`). The original images (~58 MB) are not in git. On startup the backend also mirrors them into MinIO (`backend/core/bootstrap_data.py`) from `PROJECT_IMAGES_BASE_URL`/`PROJECT_IMAGES_ARCHIVE_URL` in `.env`, using the list in `seed-data/project_images_manifest.json`. No manual script or local image folder is needed — only the right environment variables and network access on the first start.

**Frontend (React + Vite)**

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173
npm run build        # production build into frontend/dist
npm run preview      # preview the build
npm run lint         # oxlint
```

## Database migrations (Alembic)

The schema is managed by Alembic and **not** by `Base.metadata.create_all`: `create_all` only creates missing tables and never `ALTER`s an existing one, so a column added later silently goes missing until a query fails at runtime.

```bash
alembic upgrade head                              # bring the database to the latest revision
alembic revision --autogenerate -m "description"  # generate a migration after changing a model
alembic downgrade -1                              # step back one revision
alembic current                                   # which revision the database is at
alembic check                                     # do the models drift from the migrations?
```

After changing any file in `backend/models/` you **must** create a new revision — `tests/test_migrations.py` fails if you forget.

A database whose tables already exist (created earlier with `create_all`) is marked once instead of upgraded: `alembic stamp head`.

## Testing

The test suite has three tiers:

| Tier | Path | Needs | Checks |
| :--- | :--- | :--- | :--- |
| Unit / API | `tests/test_api/`, `tests/test_services/`, `tests/test_core/` | Nothing | Endpoints and services on in-memory SQLite |
| Migration | `tests/test_migrations.py` | Nothing | Migrations match the models, no drift |
| E2E | `tests/test_e2e/` | `docker compose up -d` | Sale/Admin journeys against real MySQL |

```bash
pytest tests/test_api tests/test_migrations.py   # fast, no Docker needed
docker compose up -d && pytest tests/test_e2e    # E2E against the real stack
```

E2E tests **skip** themselves when the backend is not running, so `pytest tests/` is always safe.

```bash
make test        # pytest with a 70% coverage floor
make lint        # ruff check backend/ tests/ eval/
make format      # ruff format backend/ tests/ eval/
make typecheck   # mypy backend/
make check       # lint + format + typecheck + test
make clean       # remove __pycache__, .pytest_cache, .ruff_cache
```

## Access after startup

| Component | URL | Credentials |
| :--- | :--- | :--- |
| Frontend | `http://localhost:5173` | `sale_test` / `pass1234` — `admin_test` / `pass1234` (development only) |
| Backend API | `http://localhost:8000` | — |
| Swagger UI | `http://localhost:8000/docs` | — |
| Health check | `http://localhost:8000/health` | — |
| Qdrant Dashboard | `http://localhost:6333/dashboard` | — |
| MinIO Console | `http://localhost:9001` | `minioadmin` / `minioadmin` |
| MySQL | `localhost:3306` | `salesmate` / `salesmate` (db: `salesmate_db`) |
| Redis (long-term memory) | `localhost:6379` | — (`redis-cli KEYS "memory:*"`) |

Outside production, the backend seeds two test accounts on every start (`SEED_USERS` in `backend/core/seed.py`), so anyone who clones the repo and runs `docker compose up` can log in straight away. Seeding is **idempotent**: an existing account is reset to the password/role/active state above. It **never** runs when `APP_ENV` is a production value — these passwords are public. Shared accounts added to `SEED_USERS` need an email domain that `EmailStr` accepts (avoid `.local`, `.test`), or `/auth/login` fails with a 500 while serialising the response.

`/auth/login` allows 10 attempts per client address every 5 minutes (`backend/core/rate_limit.py`); a few wrong passwords in a row during development can trip it, and a backend restart resets it.

## Logging & observability

The backend writes **structured JSON logs to stdout** (one line per record), so `docker logs`, Loki or CloudWatch can read them without a custom parser.

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `LOG_LEVEL` | `INFO` | Log threshold. `DEBUG` also shows `/health` and minor details. |
| `LOG_JSON` | *(automatic)* | Empty: JSON in production, readable text in development. Set `true`/`false` to force. |
| `LOG_QUERY_TEXT` | `true` | Record the start of each chat question in the audit log, with phone numbers and emails redacted. |

Every request gets a `request_id` (or reuses the `X-Request-ID` the client sent), returned in the response headers:

```bash
docker compose logs backend | grep <request_id> | jq .
docker compose logs backend | jq 'select(.event=="pipeline.crash")'
docker compose logs backend | jq 'select(.event=="sale.query" and .verifier_score < 0.7)'
```

Business audit events go to the `salesmate.audit` logger, pinned at INFO — setting `LOG_LEVEL=WARNING` to cut noise does not lose the audit trail: `auth.login.success/.failure`, `auth.logout`, `document.upload`, `document.ingest.success/.blocked/.failure`, `sale.query`, `hitl.confirm`.

**Never logged** (guarded by `tests/test_api/test_audit_events.py` and `tests/test_services/test_silent_failures_logged.py`): passwords/JWTs/API keys (`RedactingFilter` masks them), AI-generated answers (only scores are logged), HITL `confirmed_content` (only `content_len` + `edited`), input values that caused a 422, uploaded file contents. A 500 response only returns `{"detail": "Internal server error", "request_id": "..."}`.

## Data and mock API sources

| Item | Source |
| :--- | :--- |
| Sales policy PDFs | `market-files.vinhomes.vn` — Google search: `site:vinhomes.vn "chính sách bán hàng" filetype:pdf` |
| Floor plans & amenities images | `rever.vn`, `batdongsan.com.vn` or the project's official website |
| Inventory API | Mock API — `mockapi.io` (see "Mock inventory API" above) |
