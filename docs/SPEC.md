# Build: Midwest Games Review Insights (internal tool)

You are building an internal web app for Midwest Games, a video game publisher. The app pulls every Steam review for each Midwest Games title, uses Claude to find the recurring themes players talk about and how they feel about each one, and lets the team explore the results and export clean reports. The goal is to stop relying on third-party review-analysis services.

Work in phases. At the end of each phase, stop, summarize what you built, show me how to run it, and wait for my go-ahead before starting the next phase. Ask me before adding any paid service or dependency not listed here.

## Ground rules

- **Clean-room build.** Do not copy, imitate, or reference the code, theme lists, theme definitions, wording, or visual design of any existing commercial review-analysis product. Themes must be derived from each game's own reviews by the pipeline described below.
- **Official data sources only.** Use Steam's documented Web API. No scraping of store or community HTML.
- **Every quote shown in the app or a report must be verbatim** from a real review and must link back to it. Validate this in code (substring check against the stored review text) and drop any quote that fails.
- **No em dashes** in any generated text: UI copy, theme names, summaries, or exported reports.
- Keep secrets in `.env` (provide `.env.example`). Never commit keys.

## Titles to track (seed data)

Store these in a `titles` table and make the list editable in the app (add, remove, archive), so new signings can be added without code changes.

| Title | Steam App ID | Status |
|---|---|---|
| Tombwater | 3308200 | Released |
| Duck Paradox | 2058150 | Released |
| Hive Jump 2: Survivors | 2545740 | Released |
| Dark Sky | 1454960 | Released |
| The Lullaby of Life | 2493180 | Released |
| GodsTV | 2626570 | Early Access coming soon (demo app: 3673170) |
| The Legend of Baboo | 2928040 | Unreleased |
| Floor is...What!? | 1272140 | Unreleased |

Unreleased titles should appear in the portfolio view as "No reviews yet" and start syncing automatically once reviews exist. Pull each title's name, header image, release date, and developer from Steam's `appdetails` store endpoint and cache them.

## Tech stack

- Backend: Python 3.11+, FastAPI, SQLite via SQLAlchemy (with Alembic migrations), so it can move to Postgres later without rewrites.
- Frontend: React + TypeScript (Vite), Tailwind, Recharts.
- LLM: the Anthropic Python SDK. Put model names in config (`MODEL_TAGGING`, `MODEL_ANALYSIS`). Check the current Anthropic docs for model IDs; use a fast, cheap model (Haiku class) for per-review tagging and a stronger model (Sonnet class) for theme discovery and written summaries. Use the Message Batches API for bulk tagging and prompt caching for the shared codebook/system prompt.
- Exports: PDF via HTML templates rendered with Playwright (Chromium), XLSX via openpyxl, CSV.
- Packaging: Docker Compose (app + scheduled worker). Include a `make dev` or equivalent one-command local start.

## Phase 1: Review ingestion

Use `GET https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/` with parameters passed as `input_json`. The older `store.steampowered.com/appreviews` endpoint is deprecated, so don't use it. Key details:

- Page through all reviews with `filter` = 1 (Recent) and the returned `cursor` (URL-encode it), `num_per_page` = 100, `languages` = ["all"], `purchase_type` = 1 (All), `review_type` = 0 (All). Stop when a page comes back empty.
- Support an optional `STEAM_PUBLISHER_KEY` (a Steamworks publisher Web API key) for a higher rate limit. Without it, throttle to about 1 request per second, back off exponentially on HTTP 429, and resume from the last cursor if a run is interrupted.
- Store every field Steam returns: `recommendationid`, `language`, `review`, `timestamp_created`, `timestamp_updated`, `voted_up`, `votes_up`, `votes_funny`, `weighted_vote_score`, `comment_count`, `steam_purchase`, `received_for_free`, `written_during_early_access`, `developer_response`, `timestamp_dev_responded`, `primarily_steam_deck`, `refunded`, and author fields (`steamid`, `num_reviews`, `playtime_forever`, `playtime_at_review`, `playtime_last_two_weeks`, `last_played`). Playtime is in minutes. Store the first page's `query_summary` (total positive, total negative, score description) as a daily snapshot per title.
- Incremental sync: upsert by `recommendationid`, and re-analyze a review only if `timestamp_updated` changed. Mark reviews that disappear (deleted) instead of hard-deleting them.
- A nightly scheduled sync for all active titles, plus a "Sync now" button per title in the UI.

**Done when:** syncing Duck Paradox and Tombwater stores counts that match the Steam store's totals (allowing for Steam's off-topic filtering), and a second sync only fetches new or edited reviews.

## Phase 2: Analysis pipeline

Build it as a separate, re-runnable job per title.

1. **Prep.** Skip empty or near-empty reviews (store them as "no content" so counts stay honest). Keep the original language. For non-English reviews, have the tagging model read the original and write an English summary; never machine-translate quotes shown as verbatim.
2. **Theme discovery (per title).** Take a stratified sample (mix of positive/negative, playtime bands, early access vs full release, languages; up to about 400 reviews). Ask the analysis model to propose a codebook of 8 to 15 themes specific to this game. Each theme gets a short plain-English name, a one-sentence definition, inclusion and exclusion notes, and 2 example review IDs. Save the codebook with a version number.
3. **Human review of the codebook.** In the UI, let a user rename, merge, split, add, or delete themes before tagging runs. Editing creates a new codebook version.
4. **Tagging (every review).** For each review, the tagging model returns structured JSON (use tool use / JSON schema, not free text): which themes it mentions (multi-label), sentiment per theme (positive, negative, mixed), a short verbatim quote per theme, an "other" flag for important points no theme covers, and an English gist for non-English reviews. Batch reviews (for example 20 per request) and send them through the Batches API.
5. **Quality checks.** Validate every quote with the substring check. Re-tag a random 5% with the analysis model and report agreement per theme on an "Analysis quality" page. If "other" exceeds 10% of reviews, flag the codebook for review.
6. **Aggregation.** Per title and per theme, compute: share of reviews mentioning it, positive/negative/mixed split, net sentiment, change over time (monthly), and splits by playtime band (under 2h, 2 to 10h, 10 to 50h, 50h+), early access vs full release, language, Steam Deck, and refunded. Also compute developer response rate and median response time.
7. **Written summary.** The analysis model writes a short executive summary per title (top 3 strengths, top 3 problems, what changed in the last 30 days), citing review IDs it relied on. Re-generate after each analysis run.
8. **Cost guardrails.** Before any run, show the estimated token count and dollar cost and require confirmation in the UI. Log actual cost per run. Never re-tag unchanged reviews.

**Done when:** the full pipeline runs end to end on Duck Paradox, and I can open 20 random tagged reviews and agree with the tags.

## Phase 3: App UI

Clean, internal-tool look with Midwest Games branding (logo and colors configurable in one theme file). Light and dark mode.

- **Portfolio view:** a card or row per title with header image, total reviews, % positive, 30-day trend, top praised theme, top criticized theme, last synced time.
- **Title view:**
  - Header stats (total reviews, % positive, Steam score label, review volume over time).
  - Theme table: each theme's share of reviews, sentiment split bar, and trend sparkline, sortable.
  - Theme drill-down: definition, sentiment over time, and a paginated list of matching reviews with highlighted quotes, playtime, date, language, and a link to the review on Steam.
  - Filters that apply to everything on the page: date range, positive/negative, playtime band, language, early access vs release, Steam Deck, and "has developer response".
  - Search across review text.
- **Compare view:** pick 2 to 4 titles and compare % positive, review volume, and shared or similar themes side by side.
- **Analysis quality page** (Phase 2, step 5).

## Phase 4: Exports

Exports respect whatever filters are active. Each export file is named `MWG_<Title>_<ReportType>_<YYYY-MM-DD>`.

- **PDF report (one title):** cover page, executive summary, headline stats, theme table with sentiment bars, top 3 positive and negative themes with 2 to 3 verbatim quotes each, trend chart, methodology note (date range, review count, model names, codebook version). US Letter, Midwest branding, page numbers.
- **PDF portfolio report:** one page per title plus a summary page across all titles.
- **XLSX** (must open cleanly in Google Sheets): tabs for theme summary, coded reviews (one row per review with theme columns), and monthly trends. No formulas that Google Sheets can't evaluate.
- **CSV** of coded reviews.
- **Copy chart as PNG** on every chart.

## Phase 5: Access, scheduling, and handoff

- Login limited to Midwest Games accounts (Google sign-in restricted to the company domain, configurable) with a simple admin vs viewer role. Viewers can browse and export; admins can sync, edit codebooks, and run analyses.
- Nightly sync + analysis of new reviews for all active titles, with a run log page and an email or Slack webhook (optional, configurable) when a run fails or a title's % positive drops more than 5 points in 7 days.
- README covering setup, environment variables, how to add a new title, how to edit a codebook, cost expectations, and how to deploy on a small cloud VM.
- Tests: unit tests for the Steam client (pagination, 429 backoff, cursor resume), quote validation, and aggregation math; one end-to-end test with recorded Steam responses (no live calls in CI).

## Before you start

Reply with: your proposed folder structure, the database schema, the tagging JSON schema, and a rough per-title cost estimate for tagging Tombwater's current review count. Then wait for my approval.
