# Midwest Games Review Insights

An internal web app that pulls every Steam review for each Midwest Games title, finds the themes players talk about and how they feel about each, and lets the team explore the results and export reports.

- Plan and decisions: [docs/PLAN.md](docs/PLAN.md)
- Original brief: [docs/SPEC.md](docs/SPEC.md)

| Phase | Status |
|---|---|
| 1. Review ingestion | Done; verified against live Steam |
| 2. Analysis pipeline | Done; verified on Duck Paradox (spot check: 20 of 20 right) and Tombwater |
| 3. App UI | Done |
| 4. Exports | Done |
| 5. Access, scheduling, handoff | Done; Google sign-in, Slack and email to be checked on first setup |

**Contents:** [Run it on your computer](#run-it-on-your-computer) · [Run it with Docker](#run-it-with-docker) · [Using the app](#using-the-app) · [Adding a title](#adding-a-title) · [Editing a codebook](#editing-a-codebook) · [How syncing works](#how-syncing-works) · [How analysis works](#how-analysis-works) · [Nightly analysis and alerts](#nightly-analysis-and-alerts) · [Exports](#exports) · [Sign-in and roles](#sign-in-and-roles) · [Cost expectations](#cost-expectations) · [Deploy on a small cloud server](#deploy-on-a-small-cloud-server) · [Settings](#settings) · [Branding](#branding) · [Tests](#tests)

## Run it on your computer

Needs Python 3.11+ and Node 20+.

```bash
cp .env.example .env     # then add ANTHROPIC_API_KEY to run analyses
make dev
```

Open http://localhost:5173. `make dev` installs everything on first run (including the Chromium used for PDF reports), applies database migrations, adds the seed titles, and starts three processes: the API (port 8000), the background worker, and the web app. Ctrl+C stops all three.

Sign-in is off for `make dev` (you are an admin, and the header says "Sign-in off"), so it works without any Google setup. The database is a single SQLite file at `data/mwg.db`.

| Command | What it does |
|---|---|
| `make test` | Backend tests and frontend type check |
| `make sync` | Sync every active title right now, without the worker |
| `make sync APP=3308200` | Sync one title right now |
| `make migrate` | Apply database migrations and add any missing seed titles |

## Run it with Docker

```bash
cp .env.example .env     # fill in the sign-in settings first (see Sign-in and roles)
make up                  # docker compose up --build -d
```

Open http://localhost:8000. Two containers run from one image: `app` (API, web app and PDF reports) and `worker` (nightly sync, nightly analysis, alerts and the "Sync now" queue). Data lives in `./data`. `make logs` follows the logs and `make down` stops everything. Docker always uses Google sign-in unless `.env` says `AUTH_MODE=local`, so a server is never open by accident.

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

## Adding a title

Admins: open **Manage titles** and click **Add title**. Enter the Steam App ID, the number in the store page address (`store.steampowered.com/app/3308200/...` is 3308200). If the game has a separate demo on Steam, enter the demo's App ID too; its reviews are kept apart from the main game's. The name, header image, release date and developer are filled in from Steam, and the first sync starts right away. A title that isn't out yet shows "No reviews yet" and fills in on its own once reviews appear.

From the ••• menu on each row you can edit a title, archive it (hidden and no longer synced, history kept) or remove it (deletes everything stored for it).

To find a new title's themes, open it, go to **Themes setup** and follow the next section.

## Editing a codebook

A codebook is a title's list of themes. Each theme has a name, a one-sentence definition, notes on what counts and what doesn't, and example reviews. Admins manage it under **Themes setup**:

1. **Find themes** has the analysis model read a sample of up to 400 of the title's reviews and propose 8 to 15 themes. It shows the cost first (about $0.10 to $0.20). The proposal is saved as a draft version.
2. **Edit themes** opens the editor: rename a theme or change its definition and notes, **merge** two or more themes into one, **split** one into two, **add** a theme, or **delete** one. Save as a new version; versions never change once saved, so you can always see what a theme meant when a report was made.
3. **Approve** the version you want used. Only the approved version counts in charts, reports and exports.
4. **Analyze reviews** tags every review against the approved version (the cost is shown first). Approving a new version means every review is tagged again under it, because the themes changed.
5. **Spot check** shows 20 random tagged reviews with the quotes highlighted, to check the tags by eye. The **Analysis quality** page shows how often a second model agreed, and how many quotes were dropped.

If more than 10% of reviews raise points no theme covers, the codebook is flagged on Themes setup: read the "other" notes on the quality page and consider adding or widening a theme.

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

Open a title and go to its **Themes setup** tab (admins only for the buttons).

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

## Nightly analysis and alerts

**Nightly analysis** is switched on per title by an admin, under **Themes setup**, where the expected monthly cost is shown next to the switch. After the nightly sync (at `ANALYSIS_CRON`, default 5:00), the worker estimates a run for each such title's new and edited reviews:

- At or under `NIGHTLY_ANALYSIS_MAX_USD` (default $0.50 per title per night) it starts on its own.
- Above that it waits, an alert is sent, and an admin can start it from Themes setup.
- The quality check runs only when there are at least 20 new reviews (a smaller sample says little), and the executive summary is rewritten at most every `SUMMARY_REFRESH_DAYS` days (default 7).

**Alerts** go to a Slack channel (an incoming webhook) and/or email (any SMTP server), when those are set up, and are always listed under **Run log > Alerts**. The worker checks every few minutes for:

- a sync or analysis that failed,
- a nightly analysis waiting for an admin,
- a title whose share of recommended reviews fell by more than 5 points over 7 days (titles with at least 20 reviews, at most one alert per title per week).

**Run log > Alerts > Send a test alert** checks the Slack and email settings.

To set up Slack: create an app at api.slack.com/apps, turn on Incoming Webhooks, add one for the channel, and put its address in `SLACK_WEBHOOK_URL`. For email, fill in the `SMTP_*` settings from your email provider and list the recipients in `ALERT_EMAILS`.

## Exports

Every export uses the filters set on the page it comes from, and is named `MWG_<Title>_<ReportType>_<YYYY-MM-DD>`, for example `MWG_Duck_Paradox_Report_2026-10-20.pdf`.

- **Export** (top right of a title's page):
  - **PDF report**: cover, headline numbers, reviews per month, overall impression, executive summary, theme table with sentiment bars, the 3 most praised and 3 most criticized themes with up to 3 verbatim quotes each (each linked to the review on Steam), and a note on how the report was made (dates, filters, review counts, models, codebook version, quality check). US Letter, with page numbers.
  - **Excel workbook**: About (filters, counts, models), Theme summary, Coded reviews (one row per review, a column per theme with its sentiment), and Monthly trends. Plain values only, no formulas, so it opens cleanly in Google Sheets.
  - **CSV of coded reviews**: the same rows as the workbook's Coded reviews sheet.
- **Portfolio PDF** (on the Portfolio page): a summary page across all titles, then one page per title with reviews. Pick a date range next to the button.
- **Copy as image** on every chart puts a PNG of the chart, with its title and legend, on the clipboard. Browsers that don't allow that save it as a file instead.

Reviews are written by the public, so a review that starts with `=` (which a spreadsheet could run as a formula) is always stored as text: in the workbook as a text cell, and in the CSV with a leading apostrophe. Quotes in PDF reports are checked against the review text again when the report is made, and any that don't match are left out.

PDFs are printed by Chromium through Playwright. `make dev` and the Docker image install it; to use a Chromium that's already on the machine instead, set `CHROMIUM_PATH`.

## Sign-in and roles

People sign in with a Google account on the company's domain. There are two roles:

- **Viewer**: browse everything and download every export.
- **Admin**: also add and edit titles, sync, find themes, edit and approve codebooks, run analyses, match themes in Compare, switch on nightly analysis, and manage people.

Everyone starts as a viewer, except the addresses in `ADMIN_EMAILS`. If `ADMIN_EMAILS` is empty, the first person to sign in becomes an admin. Admins change roles, and can turn someone's access off, on the **People** page.

To set up Google sign-in (once, by someone with access to the company's Google Workspace):

1. Go to console.cloud.google.com, create a project (for example "Review Insights"), and open **APIs & Services**.
2. **OAuth consent screen**: choose **Internal** (only people in your Workspace can use it), fill in the app name and a support email.
3. **Credentials > Create credentials > OAuth client ID**: type **Web application**. Under **Authorized redirect URIs** add `https://<your address>/api/auth/callback` (for example `https://insights.midwestgames.com/api/auth/callback`).
4. Copy the client ID and secret into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, set `ALLOWED_DOMAINS` (for example `midwestgames.com`), `ADMIN_EMAILS` and `PUBLIC_URL`, and restart the app.

Only accounts whose email is on an allowed domain, and which are company accounts (not personal Gmail accounts using a company address), can sign in. Sessions last 14 days (`SESSION_DAYS`). The session cookie is signed with `SESSION_SECRET`; if that's empty, a random one is created once and kept in the data folder.

`AUTH_MODE=local` turns sign-in off and makes everyone an admin. Use it only on your own computer.

## Cost expectations

The only running costs are Anthropic API usage and wherever you host the app. Steam's API is free, and exports, charts, search and alerts cost nothing. Every analysis shows its cost before it runs, and every run's actual cost is logged (Run log > Analyses, and the Analysis quality page).

Measured on real titles (October 2026):

| Work | Duck Paradox (331 reviews) | Tombwater (306 reviews) |
|---|---|---|
| Find themes (once per title, again only if you ask) | $0.09 to $0.12 | $0.15 |
| Analyze every review: tagging, quality check and summary | $0.10 to $0.12 | $0.13 |
| Match themes across titles in Compare (once per pair of codebooks) | $0.01 for both titles | |

What that means going forward:

- **A new title** costs roughly $0.25 to $0.30 per 300 reviews to set up (find themes plus the first analysis). Tagging itself scales at about $0.08 per 1,000 reviews; the quality check and summary add about $0.10 per run.
- **Nightly analysis** costs about $0.15 to $0.25 per title per month at current review volumes, mostly the weekly summary. The Themes setup page shows the forecast for each title. Nothing runs nightly unless an admin switches it on, and each night is capped by `NIGHTLY_ANALYSIS_MAX_USD`.
- **Hosting** on a small cloud server is typically $5 to $15 a month (provider's price).

Prices per model are built in and can be changed with `MODEL_PRICES` if Anthropic's prices change.

## Deploy on a small cloud server

This runs the app on one small Linux server with HTTPS. Any provider works (DigitalOcean, Linode, AWS Lightsail, Google Cloud, Azure).

1. **Create the server**: Ubuntu 24.04 LTS, 1 to 2 CPUs, 2 GB of memory, 25 GB of disk. Allow incoming ports 22 (SSH), 80 and 443 only.
2. **Point a name at it**: create a DNS record such as `insights.midwestgames.com` pointing to the server's IP address.
3. **Install Docker** (on the server):
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
4. **Get the app and configure it**:
   ```bash
   sudo git clone https://github.com/davaziri/mwg-review-insights.git /opt/mwg
   sudo chown -R $USER /opt/mwg && cd /opt/mwg
   cp .env.example .env && chmod 600 .env && nano .env
   ```
   Set at least `ANTHROPIC_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_DOMAINS`, `ADMIN_EMAILS` and `PUBLIC_URL=https://insights.midwestgames.com`. Leave `AUTH_MODE` unset. Set up Google sign-in as described above, with the redirect address on this name.
5. **Start it**: `sudo docker compose up -d --build` (the first build takes several minutes). The database is created and migrated on start. The app listens on port 8000 on the server only.
6. **Add HTTPS** with Caddy, a free web server that gets and renews certificates by itself:
   ```bash
   sudo apt update && sudo apt install -y caddy
   echo 'insights.midwestgames.com {
       reverse_proxy localhost:8000
   }' | sudo tee /etc/caddy/Caddyfile
   sudo systemctl reload caddy
   ```
   Open https://insights.midwestgames.com and sign in.
7. **Back up the database** every night (it's one file). For example, run `sudo apt install -y sqlite3 && mkdir -p /opt/mwg/backups`, then add this line in `sudo crontab -e`:
   ```
   30 4 * * * sqlite3 /opt/mwg/data/mwg.db ".backup /opt/mwg/backups/mwg-$(date +\%u).db"
   ```
   That keeps a week of daily copies. Copy them off the server now and then (or use your provider's disk snapshots).
8. **Update** to a new version: `cd /opt/mwg && git pull && sudo docker compose up -d --build`. Migrations run on start and keep all data.

## Settings

All settings go in `.env` (see [.env.example](.env.example)). Never commit `.env`; it holds the secrets.

| Setting | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` (or `MWG_ANTHROPIC_API_KEY`) | empty | Needed for analysis |
| `MODEL_TAGGING`, `MODEL_ANALYSIS` | `claude-haiku-5-5`, `claude-sonnet-5-5` | Tagging model, and the model for themes, quality checks and summaries |
| `TAGGING_EFFORT`, `ANALYSIS_EFFORT` | `low`, `high` | How much each model reasons before answering |
| `MODEL_PRICES` | built in | Override or add per-model prices (JSON) |
| `DIRECT_MAX_REVIEWS` | `100` | Runs with at least this many reviews use the Batches API (half price) |
| `AUTH_MODE` | `google` (`local` with `make dev`) | `local` turns sign-in off: your own computer only |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | empty | From Google Cloud (see Sign-in and roles) |
| `ALLOWED_DOMAINS` | empty | Email domains that may sign in, comma-separated |
| `ADMIN_EMAILS` | empty | Always admins, comma-separated |
| `PUBLIC_URL` | empty | The address people open, e.g. `https://insights.midwestgames.com` |
| `SESSION_SECRET` | made for you | Signs the sign-in cookie |
| `SESSION_DAYS` | `14` | How long a sign-in lasts |
| `STEAM_PUBLISHER_KEY` | empty | Optional Steamworks publisher key; allows faster syncing |
| `SYNC_CRON`, `SYNC_TIMEZONE` | `0 3 * * *`, `America/Chicago` | When the nightly sync runs |
| `FULL_SYNC_INTERVAL_DAYS` | `7` | Days between full crawls (deletion checks) |
| `ANALYSIS_CRON` | `0 5 * * *` | When nightly analysis runs (same timezone) |
| `NIGHTLY_ANALYSIS_MAX_USD` | `0.50` | Per title per night; above this a run waits for an admin |
| `SUMMARY_REFRESH_DAYS` | `7` | Nightly runs rewrite the summary at most this often |
| `SLACK_WEBHOOK_URL` | empty | Slack incoming webhook for alerts |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | empty, `587` | Email server for alerts (port 465 uses SSL; others use STARTTLS) |
| `ALERT_EMAILS` | empty | Who gets alert emails, comma-separated |
| `ALERT_DROP_POINTS`, `ALERT_DROP_DAYS`, `ALERT_MIN_REVIEWS` | `5`, `7`, `20` | The % recommended drop alert |
| `CHROMIUM_PATH` | empty | Use an already-installed Chromium for PDFs |
| `DATABASE_URL` | `sqlite:///data/mwg.db` | Database location (SQLite now; the schema also works on Postgres) |

## Branding

Everything brand-specific lives in one file, [frontend/src/theme/brand.json](frontend/src/theme/brand.json): the app name, the logo path (the logo itself is `frontend/public/brand/logo.svg`), and every color for light and dark mode. The web app and the PDF reports both read it. The colors there are placeholders until Midwest Games supplies its own. [brand.ts](frontend/src/theme/brand.ts) next to it explains what each color is for. The chart colors were checked for color-blind readers with a palette validator; if you change them, keep positive, mixed and negative clearly apart from each other in both modes.

## Tests

`make test` runs the backend tests and the frontend type check. Nothing in the tests calls Steam or Anthropic: Steam is replaced by a fake server and by real Steam responses recorded earlier, and the models by a stand-in that answers like them.

They cover, among other things: the Steam client (paging, 429 backoff, cursor encoding and resume), incremental sync with edit and deletion detection, quote validation, aggregation math, the analysis pipeline, search, exports (including PDF rendering when Chromium is available), sign-in and roles, nightly analysis, alerts, and migrations (including that upgrading a database keeps every row). One end-to-end test runs a full sync on recorded Steam responses.

GitHub Actions runs the same tests on every push (`.github/workflows/ci.yml`).

To capture new real Steam responses as test fixtures (author Steam IDs are replaced with placeholders):

```bash
cd backend && .venv/bin/python -m app.cli record-fixtures --app-id 3308200 --pages 2
```
