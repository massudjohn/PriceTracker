# PriceTracker

A FastAPI-based prototype for managing a product watchlist and scheduling periodic price checks.

## Getting started

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the API server:

```bash
uvicorn app.main:app --reload --port 8000 --app-dir src
```

Visit `http://localhost:8000/docs` for interactive documentation.

3. (Optional) Start the worker that will process queued fetch jobs:

```bash
rq worker price-tracker --url redis://localhost:6379/0
```

A Redis server is required for the queue and scheduler; update the `REDIS_URL` environment
variable if needed.

## Project layout

- `src/app/main.py` – FastAPI app entrypoint and startup hooks.
- `src/app/routes.py` – CRUD endpoints for products and alerts, including a watchlist view.
- `src/app/models.py` – Pydantic data models for products, price records, and alerts.
- `src/app/database.py` – In-memory repository backing the prototype API.
- `src/app/background/` – RQ queue configuration and task stubs for periodic fetching.

## Linting

Ruff and Black are configured via `pyproject.toml`. Run Ruff locally with:

```bash
ruff check src
```
