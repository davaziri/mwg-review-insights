# Midwest Games Review Insights

Internal tool that pulls every Steam review for each Midwest Games title, finds the recurring themes players talk about, and lets the team explore the results and export reports.

- Plan: [docs/PLAN.md](docs/PLAN.md)
- Original brief: [docs/SPEC.md](docs/SPEC.md)

| Phase | Status |
|---|---|
| 1. Review ingestion | Done; verified against live Steam |
| 2. Analysis pipeline | Done; verified on Duck Paradox (spot check: 20 of 20 right) |
| 3. App UI | Built; waiting for review |
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

## How analysis works

Open a title from the Titles page (**Themes**).

1. **Find themes.** The analysis model (`MODEL_ANALYSIS`) reads a stratified sample of up to 400 reviews (positive and negative, playtime bands, early access and full release, languages) and proposes 8 to 15 themes, each with a definition, include and exclude notes, and two example reviews. This is saved as a draft codebook.
2. **Review the codebook.** Rename, merge, split, add or delete themes with **Edit themes**. Saving creates a new version; versions never change once saved. **Approve** the version you want used.
3. **Analyze reviews.** The tagging model (`MODEL_TAGGING`) reads every review that has text and no tag for its current version under the approved codebook, 20 reviews per request. For each review it returns the themes mentioned, sentiment per theme, a short quote per theme, the reviewer's **overall impression** of the game (positive, mixed, negative, or none) with its own quote, an "other" flag for points no theme covers, and an English gist for non-English reviews. General praise or criticism ("great game", "waste of money") goes into the overall impression, not into a theme, and is counted separately so theme numbers stay about specific topics. Then the analysis model re-tags a random 5% (at least 20 reviews) as a quality check, and writes an executive summary citing review IDs.

Every run starts as a **cost estimate** (input tokens counted by Anthropic's token counter, output estimated) and only runs after you confirm it. Actual tokens and cost are logged per run on the **Analysis quality** page. Runs with 100 or more reviews go through the Batches API at half price; smaller ones call the API directly.

Rules the pipeline enforces in code:

- **Quotes are verbatim.** Each quote must be found in the review's own text (exact match, or one that differs only in whitespace or letter case). The app stores the position and always shows the review's own text there. Quotes that fail are dropped and counted on the quality page.
- **Unchanged reviews are never re-tagged.** A review is re-tagged only when Steam's `timestamp_updated` changes, when a new codebook version is approved, or when the app starts recording something new per review (the tag version, currently 2, changes in an update).
- **No em dashes** in anything generated (theme text, gists, notes, summaries). Reviewers' own quotes are left as written.
- If more than 10% of analyzed reviews raise points no theme covers, the codebook is flagged for review.
- Reviews with almost no text ("good", "10/10", emoji) are stored as "no content" and counted, but not sent to the model.

The **Spot check** on a title's page shows 20 random tagged reviews with their quotes highlighted, to check the tags by eye. The overall impression quote is shown in bold with an outline.

## Using the app

- **Portfolio** (the home page): a card per title with its header image, review count, % recommended, Steam's rating, reviews per week for the last 12 weeks, the last 30 days against the 30 before, the most praised and most criticized themes, and when it last synced. Unreleased titles show "No reviews yet". "Most praised" is the theme with the most positive mentions after taking away its negative ones (and the reverse for "most criticized"), so a theme that splits players doesn't top either list.
- **A title's page** has three tabs, with one row of filters above the first two: dates, vote, playtime, language, early access or after release, Steam Deck, and developer reply. The filters live in the page address, so a filtered view can be bookmarked or sent to someone.
  - **Overview**: headline numbers, reviews per month (recommended above the line, not recommended below), the executive summary, the overall impression split, and the theme table. The theme table sorts by share, sentiment or net, shows each theme's trend over the selected dates, and each theme opens its own page: definition, what counts and what doesn't, mentions per month by sentiment, and its reviews (all, or only positive, mixed or negative), with the quotes highlighted.
  - **Reviews**: every review, searchable. Search matches parts of words in any language (Chinese and Japanese included); put a phrase in quotes to match it exactly. Sort by newest, oldest, most helpful or most playtime, or narrow to one overall impression.
  - **Themes setup**: find themes, edit and approve the codebook, run analysis, and spot-check 20 random reviews (Phase 2).
- **Compare**: pick 2 to 4 titles to see % recommended, Steam's rating, reviews per month and % recommended by quarter side by side. Each title keeps its color while it stays picked.
  - Each title's themes come from its own reviews, so the same topic can have a different name in each game. **Match similar themes** has the analysis model group the themes that are about the same thing (it reads the theme names and definitions, not the reviews). Like every model call it shows the cost first (about $0.02 for two titles) and runs only when confirmed. The result is saved and reused until one of the titles approves a new codebook. Matching needs at least two titles with analyzed reviews.
- **Every chart** has a "Show numbers" switch that shows the same data as a table, and hovering a chart shows the exact values.
- **Light and dark mode**: the switch in the top right follows the computer's setting until someone picks light or dark.

## Branding

Everything visual that is brand-specific lives in one file, [frontend/src/theme/brand.ts](frontend/src/theme/brand.ts): the app name, the logo path (the logo itself is `frontend/public/brand/logo.svg`), and every color for light and dark mode. The colors there are placeholders until Midwest Games supplies its own. The chart colors were checked for color-blind readers with a palette validator; if you change them, keep positive, mixed and negative clearly apart from each other in both modes.

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
| `ANTHROPIC_API_KEY` (or `MWG_ANTHROPIC_API_KEY`) | empty | Needed for analysis. In Claude Code cloud sessions use `MWG_ANTHROPIC_API_KEY` |
| `MODEL_TAGGING`, `MODEL_ANALYSIS` | `claude-haiku-5-5`, `claude-sonnet-5-5` | Tagging model and analysis model |
| `TAGGING_EFFORT`, `ANALYSIS_EFFORT` | `low`, `high` | How much each model reasons before answering |
| `DIRECT_MAX_REVIEWS` | `100` | Runs with at least this many reviews use the Batches API |
| `MODEL_PRICES` | built in | Override or add per-model prices (JSON) |

## Tests

`make test` runs the backend tests (Steam client pagination, 429 backoff, cursor encoding and resume, incremental sync, edit and deletion detection, the API, and migrations) against a fake Steam server. No test calls Steam.

To capture real Steam responses as test fixtures (author Steam IDs are replaced with placeholders):

```bash
cd backend && .venv/bin/python -m app.cli record-fixtures --app-id 3308200 --pages 2
```
