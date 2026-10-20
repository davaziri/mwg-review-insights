# Midwest Games Review Insights

Internal tool that pulls every Steam review for each Midwest Games title, finds the recurring themes players talk about, and lets the team explore the results and export reports.

- Plan: [docs/PLAN.md](docs/PLAN.md)
- Original brief: [docs/SPEC.md](docs/SPEC.md)

| Phase | Status |
|---|---|
| 1. Review ingestion | Done; verified against live Steam |
| 2. Analysis pipeline | Not started |
| 3. App UI | Not started |
| 4. Exports | Not started |
| 5. Access, scheduling, handoff | Not started |

## Run it locally

Needs Python 3.11+ and Node 20+.

```bash
cp .env.example .env     # optional: add a Steam publisher key
make dev
```

Open http://localhost:5173. `make dev` installs everything on first run, applies database migrations, adds the seed titles, and starts three processes: the API (port 8000), the background worker, and the web app. Ctrl+C stops all three.

The database is a single SQLite file at `data/mwg.db`.

Other commands:

| Command | What it does |
|---|---|
| `make test` | Backend tests and frontend type check |
| `make sync` | Sync every active title right now, without the worker |
| `make sync APP=3308200` | Sync one title right now |
| `make migrate` | Apply database migrations and add any missing seed titles |

## Run it with Docker

```bash
cp .env.example .env
make up          # docker compose up --build -d
```

Open http://localhost:8000. Two containers run from one image: `app` (API and web app) and `worker` (nightly sync and the "Sync now" queue). Data lives in `./data`. `make logs` follows the logs and `make down` stops everything.

## How syncing works

- Reviews come from Steam's `IUserReviewsService/GetAppReviews` Web API. Title name, header image, release date and developer come from the store's `appdetails` endpoint and are cached for 24 hours. No web pages are scraped.
- **Full sync**: walks every review newest first. Reviews Steam no longer returns are marked deleted (never removed from the database). This runs the first time a title syncs, then weekly.
- **Incremental sync**: walks reviews by most recent edit and stops once it reaches reviews already stored. This only fetches new and edited reviews. A review counts as edited when Steam's `timestamp_updated` changes; only edited reviews will be re-analyzed in Phase 2.
- Every sync saves Steam's review totals as that day's snapshot, so the Titles page shows "Steam reports N" whenever our count differs from Steam's.
- Without a publisher key, requests are spaced about 1 second apart. On HTTP 429 or a server error the client backs off exponentially (2s, 4s, 8s, up to 5 minutes, or whatever `Retry-After` says).
- Progress is saved after every page. If a sync fails or the worker is stopped, the next sync for that title picks up from the last page instead of starting over.
- The worker queues a sync for every non-archived title each night (default 3:00 America/Chicago, set by `SYNC_CRON` and `SYNC_TIMEZONE`). Unreleased titles show "No reviews yet" and start filling in on their own once reviews exist.
- A title with a demo app (GodsTV) syncs the demo separately. Demo reviews are never mixed into the main title's numbers.

## Adding a title

On the Titles page, click **Add title** and enter the Steam App ID (the number in the store URL). The name, image, release date and developer are filled in from Steam, and a first sync starts right away. Titles can also be edited, archived (hidden and no longer synced, history kept) or removed (deletes everything stored for it) from the ••• menu.

## Environment variables

See [.env.example](.env.example). The main ones:

| Variable | Default | Purpose |
|---|---|---|
| `STEAM_PUBLISHER_KEY` | empty | Optional Steamworks publisher key; allows faster syncing |
| `SYNC_CRON` | `0 3 * * *` | When the nightly sync runs |
| `SYNC_TIMEZONE` | `America/Chicago` | Timezone for `SYNC_CRON` |
| `FULL_SYNC_INTERVAL_DAYS` | `7` | Days between full crawls (deletion checks) |
| `DATABASE_URL` | `sqlite:///data/mwg.db` | Database location |
| `ANTHROPIC_API_KEY` | empty | Needed from Phase 2 |
| `MODEL_TAGGING`, `MODEL_ANALYSIS` | `claude-haiku-5-5`, `claude-sonnet-5-5` | Models used from Phase 2 |

## Tests

`make test` runs the backend tests (Steam client pagination, 429 backoff, cursor encoding and resume, incremental sync, edit and deletion detection, the API, and migrations) against a fake Steam server. No test calls Steam.

To capture real Steam responses as test fixtures (author Steam IDs are replaced with placeholders):

```bash
cd backend && .venv/bin/python -m app.cli record-fixtures --app-id 3308200 --pages 2
```
