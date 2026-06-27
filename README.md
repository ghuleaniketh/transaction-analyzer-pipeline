# alemeno-transaction-pipeline

A FastAPI-based transaction processing pipeline that ingests CSV files, runs cleaning
and anomaly detection, enriches missing categories using an LLM (Google Gemini),
produces a narrative summary and a risk level, and persists results to Postgres for
retrieval via an HTTP API.

This repository contains the API, background worker, pipeline steps, and DB models
used to process batches of financial transactions.

## Key features

- CSV upload endpoint that creates an asynchronous processing job.
- Background processing using Redis + RQ workers.
- Data cleaning (date normalization, amount parsing, duplicate removal).
- Anomaly detection (statistical outliers per account and currency mismatches).
- LLM-backed category classification and narrative summary generation (Google Gemini).
- Persistent storage of `Job`, `Transaction`, and `JobSummary` in Postgres (SQLAlchemy).
- Alembic migrations included.

## Project structure

- [app/main.py](app/main.py) — FastAPI application entrypoint.
- [app/api/routes/jobs.py](app/api/routes/jobs.py) — upload, list, status, and results endpoints.
- [app/schemas/job.py](app/schemas/job.py) — Pydantic request/response models.
- [app/models/](app/models/) — SQLAlchemy models (`Job`, `Transaction`, `JobSummary`).
- [app/pipeline/](app/pipeline/) — parser, cleaner, anomaly detection, LLM client, runner.
- [app/workers/tasks.py](app/workers/tasks.py) — RQ worker task `process_job`.
- [app/database.py](app/database.py) — DB engine and session factory.
- [app/redis_conn.py](app/redis_conn.py) — Redis connection and RQ queue.
- `alembic/` — DB migrations.
- `requirements.txt` — Python dependencies.
- `docker-compose.yml` and `Dockerfile` — container/orchestration artifacts.

## Prerequisites

- Python 3.10+ (project uses modern typing features).
- Postgres database.
- Redis server for RQ.
- Google Gemini API key (optional for LLM features; pipeline has fallbacks).

## Environment variables

Create a `.env` file at the project root (or export these variables into your shell):

- `DATABASE_URL` — SQLAlchemy-compatible Postgres URL (e.g. `postgresql://user:pass@host/db`).
- `REDIS_URL` — Redis connection URL (e.g. `redis://localhost:6379/0`).
- `GEMINI_API_KEY` — (Optional) API key for Google GenAI / Gemini.
- `GEMINI_MODEL` — (Optional) Gemini model name. Default is `gemini-2.5-flash-lite`.

The settings are read by [app/config.py](app/config.py) using pydantic-settings.

## Local development setup

1. Clone the repository and change into the project directory.

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Populate `.env` with the required environment variables (see above).

5. Prepare the database (run migrations):

```bash
alembic upgrade head
```

6. Start the API server (development):

```bash
uvicorn app.main:app --reload
```

7. Start an RQ worker in a separate terminal so background jobs are processed:

```bash
rq worker default --url "$REDIS_URL"
```

Note: ensure `REDIS_URL` and `DATABASE_URL` are available in the shell or `.env`.

## Running with Docker / docker-compose

This repository includes a `Dockerfile` and `docker-compose.yml` to run the full
stack (API, Postgres, Redis, and an RQ worker) locally with a single command. The
`api` service applies Alembic migrations automatically on startup, so the database
schema is always current before the server accepts requests. The `docker-compose.yml`
defines the following services:

- `postgres` — Postgres 16, exposes port `5432`, named volume `postgres_data`.
- `redis` — Redis 7, exposes port `6379`.
- `api` — The FastAPI application. The container runs `alembic upgrade head`
	and then `uvicorn app.main:app` (port `8000` exposed). Mounted app and alembic
	folders allow live code changes during development.
- `worker` — An RQ worker process that runs `rq worker` and processes job tasks.

Typical commands:

```bash
# Build and run the whole stack in foreground (useful for debugging)
docker compose up --build

# Run in detached mode
docker compose up -d --build

# View logs for the API
docker compose logs -f api

# Apply DB migrations (if not already run by the api service)
docker compose run --rm api alembic upgrade head

# Run a one-off RQ worker (if needed)
docker compose run --rm worker rq worker --url redis://redis:6379

# Stop and remove containers, networks and volumes
docker compose down -v
```

Notes and tips:

- The `api` and `worker` services both use `env_file: .env` and set `DATABASE_URL`
	and `REDIS_URL` to point at the Docker-managed Postgres and Redis services.
- By default the compose file maps host ports `5432`, `6379` and `8000` so you can
	connect from your host machine.
- If you add a new top-level folder that the app needs at runtime (the way `alembic/`
	was added), remember to add it to the relevant service's volumes too, or it will
	go stale inside the container until the next rebuild.
- If you plan to run the stack on CI or a dev machine that already has Postgres
	or Redis running, change the ports or adjust the `DATABASE_URL`/`REDIS_URL` in
	`.env` to avoid conflicts.

See the actual compose file for full details: `docker-compose.yml` at project root.

## API usage

Base URL: `http://localhost:8000` (uvicorn default)

### 1. Upload a CSV and create a job

```bash
curl -F "file=@tests/fixtures/transactions.csv" http://localhost:8000/jobs/upload
```

Response — `201`-style payload with the new job's id and initial status:

```json
{
  "job_id": "89433c1b-5413-47d4-a7c5-f94923e6b878",
  "status": "pending"
}
```

### 2. List jobs

```bash
curl http://localhost:8000/jobs/
```

Optionally filter by status:

```bash
curl "http://localhost:8000/jobs/?status=completed"
```

Real example response (two completed jobs, newest first):

```json
[
  {
    "job_id": "89433c1b-5413-47d4-a7c5-f94923e6b878",
    "status": "completed",
    "filename": "transactions.csv",
    "created_at": "2026-06-25T13:19:01.495485Z"
  },
  {
    "job_id": "402a5850-cbf4-49d3-b2e1-c1f7b0e24179",
    "status": "completed",
    "filename": "transactions.csv",
    "created_at": "2026-06-25T08:18:42.212538Z"
  }
]
```

An unrecognized `status` value (e.g. `?status=bogus`) returns an empty list rather
than an error — this keeps the endpoint simple and avoids maintaining a hardcoded
list of valid status strings in two places. There's no pagination on this endpoint
yet; see [Known limitations](#known-limitations--production-notes) below.

### 3. Poll job status

```bash
curl http://localhost:8000/jobs/<job_id>/status
```

```json
{
  "job_id": "89433c1b-5413-47d4-a7c5-f94923e6b878",
  "status": "completed",
  "filename": "transactions.csv",
  "row_count_raw": 95,
  "row_count_clean": 85,
  "created_at": "2026-06-25T13:19:01.495485Z",
  "completed_at": "2026-06-25T13:19:25.118203Z",
  "error_message": null,
  "summary": {
    "row_count_raw": 95,
    "row_count_clean": 85
  }
}
```

### 4. Fetch job results

Only available once `status == "completed"`. If the job exists but isn't finished
yet, this returns `409 Conflict` with the current status in the error detail —
the client is expected to keep polling `/status` until it's done.

```bash
curl http://localhost:8000/jobs/<job_id>/results
```

```json
{
  "job_id": "89433c1b-5413-47d4-a7c5-f94923e6b878",
  "status": "completed",
  "transactions": [
    {
      "id": "1c2d3e4f-...",
      "txn_id": "GENERATED-A1B2C3D4",
      "date": "2026-05-12",
      "merchant": "Swiggy",
      "amount": 4250.00,
      "currency": "USD",
      "status": "success",
      "category": "Food & Dining",
      "account_id": "ACC-1042",
      "notes": null,
      "is_anomaly": true,
      "anomaly_reason": "currency_mismatch",
      "llm_category": "Food & Dining",
      "llm_failed": false
    }
  ],
  "anomalies": [
    {
      "id": "1c2d3e4f-...",
      "anomaly_reason": "currency_mismatch"
    }
  ],
  "category_breakdown": [
    { "category": "Food & Dining", "total_amount": 18420.50, "count": 22 },
    { "category": "Travel", "total_amount": 12100.00, "count": 9 }
  ],
  "summary": {
    "total_spend_inr": 412300.75,
    "total_spend_usd": 540.00,
    "top_merchants": ["Swiggy", "IRCTC", "Zomato"],
    "anomaly_count": 15,
    "narrative": "Spending is concentrated in food delivery and travel, with a small cluster of currency-mismatch anomalies on domestic-only merchants...",
    "risk_level": "medium"
  }
}
```

`category_breakdown` is sorted by `total_amount` descending — highest-spend
categories first. `transactions` and `anomalies` use the same object shape; entries
in `anomalies` are simply the subset of `transactions` where `is_anomaly` is `true`.
Money amounts come from `Numeric(12,2)`/`Numeric(14,2)` Postgres columns rounded to
two decimal places.

## Pipeline details

The pipeline runs in this exact order — several steps depend on a previous step
having already run (see [Known gotchas](#known-gotchas) below):

1. **Parse** ([app/pipeline/parser.py](app/pipeline/parser.py)) — CSV → list of dicts via `csv.DictReader`.
2. **Deduplicate** ([app/pipeline/cleaning.py](app/pipeline/cleaning.py)) — removes exact duplicate rows, deliberately ignoring the `notes` field (some rows are flagged `"Duplicate?"` in `notes` as a red herring, but aren't actual duplicates).
3. **Fill missing transaction IDs** — generates a `GENERATED-XXXXXXXX` id for any row with a blank `txn_id`. Must run after dedup (so synthetic ids don't get deduped against each other) and before LLM classification (which needs a stable identifier).
4. **Clean fields** — normalizes dates (`DD-MM-YYYY`, `YYYY/MM/DD`, `YYYY-MM-DD` → ISO), strips currency symbols, normalizes status and currency strings. Category is intentionally left alone at this stage.
5. **Detect anomalies** ([app/pipeline/anomaly.py](app/pipeline/anomaly.py)) — flags statistical outliers (>3x the median amount for that account) and currency mismatches (USD charges to domestic-only merchants such as Swiggy, Ola, IRCTC, MakeMyTrip, Zomato, BookMyShow).
6. **LLM classification** ([app/pipeline/llm_client.py](app/pipeline/llm_client.py)) — a single batched Gemini call classifies any row still missing a category. Uses row index rather than `txn_id` for mapping responses back, since some `txn_id`s are blank at this point. Wrapped in try/except — on failure, affected rows get `llm_failed=True` and fall back to `Uncategorised`.
7. **Fill remaining categories** — any row still uncategorized after the LLM step (including ones where the LLM call failed outright) defaults to `Uncategorised`. This step must run after LLM classification, not before, or the LLM never gets called on those rows.
8. **Generate summary** — real totals and top-merchant lists are computed in Python (not by the LLM, which is unreliable at precise arithmetic); a separate Gemini call generates only the narrative text and risk level. Also wrapped in try/except, falling back to a minimal summary dict on failure.

All Gemini calls go through [app/pipeline/retry.py](app/pipeline/retry.py), which retries with exponential backoff (1s/2s/4s) and re-raises after exhausting retries. This isn't defensive boilerplate — Gemini's free tier has thrown real `503 UNAVAILABLE` errors during testing, and the retry logic is what keeps those from failing the whole job.

[app/pipeline/pipeline_runner.py](app/pipeline/pipeline_runner.py) orchestrates all of the above in order and returns a result dict. Verified end-to-end against the real fixture: 95 → 85 rows after dedup, 15 anomalies detected (5 statistical + 10 currency), 0 LLM failures, all categories filled.

## Failure modes & safeguards

- LLM failures do not fail the entire job: affected transactions are marked
  `llm_failed=True` and fall back to `Uncategorised`, and summary generation
  falls back to a minimal safe structure if the narrative call fails.
- Worker-level failures set job `status` to `failed` and record an `error_message`.
- Uploads are validated for `.csv` extension and UTF-8 content; empty files are rejected.
- `google-generativeai` is fully deprecated and returns 404s — this project only uses
  the `google-genai` SDK (`from google import genai`).

## Testing & fixtures

- A real fixture is available at `tests/fixtures/transactions.csv` (95 rows, 9 columns,
  including red-herring `"Duplicate?"` notes and legitimate `"SUSPICIOUS"` flags) and
  is used for all manual and pipeline testing referenced in this README.
- Unit tests for the pure pipeline functions (`cleaning.py`, `anomaly.py`) live in
  `tests/`.

## Known gotchas

These are real issues hit during development — noted here so they aren't repeated:

- Fish shell doesn't support bash heredocs (`<< 'EOF'`). Use `echo "..." > file` or
  edit files directly.
- A function that mutates a list in place must still end with `return rows` — silent
  `None` returns happened twice from missing this.
- Docker volume mounts must match the Dockerfile's actual `WORKDIR` (`/app`). Any new
  top-level folder needs to be added to `docker-compose.yml` volumes or it goes stale
  inside the container until rebuild.
- LLM classification must run before defaulting unfilled rows to `Uncategorised`, not
  after — otherwise the LLM is never actually called on them.
- Gemini's free tier occasionally returns `503 UNAVAILABLE` under load. This is
  expected, not a bug — `retry_with_backoff` handles it.

## Known limitations & production notes

- No authentication or authorization — add this before exposing the API publicly.
- No file size limit on CSV uploads, and the whole file is read into memory rather
  than streamed; large uploads should switch to streaming parsing.
- Neither `/jobs` nor `/jobs/{job_id}/results` paginates. For `/jobs`, this is fine at
  demo scale but would need `limit`/`offset` (or cursor-based pagination) once the
  jobs table grows large. For `/results`, an individual job with a very large number
  of transactions would return an unbounded JSON array — pagination or streaming
  would be needed there too.
- LLM output is trusted somewhat loosely; hardening would mean strictly validating
  the shape of Gemini's response before persisting it.
- No retry/dead-letter handling at the RQ level if a worker process crashes mid-job —
  only Gemini API calls have retry logic, not job execution itself.

## Where to look in code

- API entry: [app/main.py](app/main.py).
- Jobs API: [app/api/routes/jobs.py](app/api/routes/jobs.py).
- Schemas: [app/schemas/job.py](app/schemas/job.py).
- Worker: [app/workers/tasks.py](app/workers/tasks.py).
- Pipeline: [app/pipeline/](app/pipeline/).
- Models: [app/models/](app/models/).