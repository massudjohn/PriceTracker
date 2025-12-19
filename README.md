# PriceTracker

PriceTracker is a FastAPI prototype for watching product prices, scraping Amazon listings, and
alerting when prices cross alert thresholds or look suspiciously discounted.

## Features

- **Watchlist management** – create, update, and remove products plus alert thresholds via the
  `/api` endpoints or the minimal HTML dashboard served from `/`.
- **Amazon fetch pipeline** – fetches product pages with rotating user agents, parses current/list
  prices and availability, and stores snapshots for analysis.
- **Anomaly detection** – flags extreme discounts (>=40% drop vs. 30-day median) and improbable
  prices (near-zero, extreme outliers, or list-price mismatches).
- **Notifications** – email, generic webhook, or Slack webhook delivery for anomalies and threshold
  matches. SMTP settings can be supplied through user preferences or `SMTP_*` environment variables.
- **Background jobs** – RQ worker and scheduler enqueue recurring fetches for every tracked product
  when Redis is available.

## Getting started

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start Redis (required for background scheduling) and run the API server:

```bash
REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --reload --port 8000 --app-dir src
```

Visit `http://localhost:8000/docs` for interactive API documentation or open `http://localhost:8000`
for the simple dashboard to add products, alerts, and notification preferences.

3. Launch the RQ worker so queued and scheduled fetch jobs execute:

```bash
rq worker price-tracker --url ${REDIS_URL:-redis://localhost:6379/0}
```

4. (Optional) Trigger a one-off fetch for all tracked products from another shell:

```bash
python - <<'PY'
from app.background.tasks import fetch_product_page
fetch_product_page()
PY
```

## Project layout

- `src/app/main.py` – FastAPI app entrypoint and startup hook that wires routes and periodic fetch
  scheduling.
- `src/app/routes.py` – CRUD endpoints for products, alerts, preferences, and a watchlist view plus
  the lightweight HTML dashboard.
- `src/app/models.py` – Pydantic models for products, alerts, preferences, price records, and
  snapshots.
- `src/app/database.py` – In-memory repository backing the prototype API and price history helpers
  (including a 30-day median calculator).
- `src/app/clients/amazon.py` – HTTP client with retry/backoff and user-agent rotation for Amazon
  product pages.
- `src/app/services/pricing.py` – Price parsing, anomaly heuristics, and notification orchestration.
- `src/app/services/notifications.py` – Email/webhook dispatchers for anomalies and thresholds.
- `src/app/background/` – RQ queue configuration plus scheduled price-fetch tasks.

## Testing & linting

The repository currently contains runtime code only. A quick syntax check can be run with:

```bash
python -m compileall src
```

Ruff and Black are configured via `pyproject.toml` for linting/formatting if you have those tools
installed:

```bash
ruff check src
black src
```
