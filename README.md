# alemeno-transaction-pipeline

A FastAPI-based transaction processing pipeline that ingests CSV files, runs cleaning
and anomaly-detection, enriches missing categories using an LLM (Google Gemini),
produces a narrative summary and a risk level, and persists results to Postgres for
retrieval via an HTTP API.

This repository contains the API, background worker, pipeline steps, and DB models
used to process batches of financial transactions.

## Key Features

- CSV upload endpoint that creates an asynchronous processing job.
- Background processing using Redis + RQ workers.
- Data cleaning (date normalization, amount parsing, duplicate removal).
- Anomaly detection (statistical outliers per account and currency mismatches).
- LLM-backed category classification and narrative summary generation (Google Gemini).
- Persistent storage of `Job`, `Transaction`, and `JobSummary` in Postgres (SQLAlchemy).
- Alembic migrations included.

## Project Structure

- [app/main.py](app/main.py) — FastAPI application entrypoint.
- [app/api/routes/jobs.py](app/api/routes/jobs.py) — upload and job result endpoints.
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
stack (API, Postgres, Redis, and an RQ worker) locally. The `docker-compose.yml`
in this project defines the following services:

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
- The `api` service runs `alembic upgrade head` at container start; you can also
	run migrations manually with the command above.
- If you plan to run the stack on CI or a dev machine that already has Postgres
	or Redis running, change the ports or adjust the `DATABASE_URL`/`REDIS_URL` in
	`.env` to avoid conflicts.

See the actual compose file for full details: `docker-compose.yml` at project root.

## API Usage

Base URL: `http://localhost:8000` (uvicorn default)

1) Upload CSV and create job

```bash
curl -F "file=@tests/fixtures/transactions.csv" http://localhost:8000/jobs/upload
```

Response: JSON with `job_id` (UUID) and initial `status` ("pending").

2) Poll job status

```bash
curl http://localhost:8000/jobs/<job_id>/status
```

3) Fetch job results (only when status == "completed")

```bash
curl http://localhost:8000/jobs/<job_id>/results
```

The `/results` payload includes:
- `transactions`: array of cleaned/enriched transaction objects.
- `anomalies`: transactions flagged as anomalies.
- `category_breakdown`: total and count per category.
- `summary`: top merchants, totals, narrative, and `risk_level`.

See the implementation in [app/api/routes/jobs.py](app/api/routes/jobs.py) for full field details.

## Pipeline details (short)

- Parsing: `app/pipeline/parser.py` uses `csv.DictReader`.
- Cleaning: `app/pipeline/cleaning.py` normalizes dates, amounts, status, currency,
	removes duplicates, and generates synthetic txn ids when missing.
- Anomalies: `app/pipeline/anomaly.py` flags statistical outliers (>3x median per account)
	and USD charges to domestic-only merchants.
- LLM: `app/pipeline/llm_client.py` communicates with Google Gemini for batch classification
	and a single summary generation call. Calls are retried via `app/pipeline/retry.py`.
- Runner: `app/pipeline/pipeline_runner.py` composes steps and returns a result dict.

## Failure modes & safeguards

- LLM failures do not fail the entire job: categories fall back to `Uncategorised`,
	and summary generation falls back to a minimal safe structure.
- Worker-level failures set job `status` to `failed` and record an `error_message`.
- Uploads are validated for `.csv` extension and UTF-8 content.

## Testing & fixtures

- A sample fixture is available at `tests/fixtures/transactions.csv` for manual testing.
- Recommended: write unit tests for individual pipeline functions (date parsing,
	amount parsing, anomaly detection, LLM response shaping).

## Security & production notes

- Add authentication/authorization before exposing publicly.
- Consider file size limits and streaming parsing for very large CSV uploads.
- Harden LLM output parsing and validate responses strictly before trusting them.
- Add pagination for `/results` if jobs can hold many transactions.

## Potential Improvements

- Add end-to-end tests and CI workflow.
- Add metrics and observability (Prometheus, logs, Sentry).
- Add RBAC and request quotas.
- Support incremental/streaming ingestion for large datasets.

## Where to look in code

- API entry: [app/main.py](app/main.py).
- Jobs API: [app/api/routes/jobs.py](app/api/routes/jobs.py).
- Worker: [app/workers/tasks.py](app/workers/tasks.py).
- Pipeline: [app/pipeline/](app/pipeline/).
- Models: [app/models/](app/models/).

---

If you'd like, I can also:
- add a short `CONTRIBUTING.md` with run/test commands,
- create a `run-dev.sh` helper to start the server and worker
- or generate a one-file example showing a curl-based upload and poll flow.


