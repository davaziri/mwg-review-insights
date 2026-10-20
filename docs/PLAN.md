# Midwest Games Review Insights: approved plan

This is the plan approved before building started. The full original brief is in [SPEC.md](SPEC.md).
Work happens in five phases. Each phase ends with a summary, run instructions, and a pause for approval.

## Phases

1. Review ingestion (Steam client, sync, snapshots, nightly job, Titles page with "Sync now")
2. Analysis pipeline (theme discovery, codebook review, tagging, quality checks, aggregation, summaries, cost guardrails)
3. App UI (portfolio, title view, drill-down, filters, search, compare, analysis quality)
4. Exports (PDF title and portfolio reports, XLSX, CSV, chart PNG)
5. Access, scheduling, alerts, README, tests

## Folder structure

```
mwg-review-insights/
├── Makefile                    # make dev | test | migrate | build
├── docker-compose.yml          # app + worker, shared ./data volume
├── .env.example
├── README.md
├── docker/app.Dockerfile       # Python + Playwright Chromium + built frontend
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py             # FastAPI; also serves the built frontend in prod
│   │   ├── config.py           # settings: MODEL_TAGGING, MODEL_ANALYSIS, prices, keys
│   │   ├── db.py
│   │   ├── models/             # SQLAlchemy models
│   │   ├── api/                # titles, reviews, themes, codebooks, runs, quality, compare, exports, auth
│   │   ├── steam/              # client.py, appdetails.py, sync.py
│   │   ├── analysis/           # prep, sampling, discovery, tagging, tag_schema, quotes, qa, aggregate, summary, cost, text_rules, prompts/
│   │   ├── exports/            # pdf.py, xlsx.py, csv.py, templates/
│   │   ├── auth/               # Google sign-in, domain check, roles
│   │   ├── notify/             # Slack webhook, SMTP
│   │   └── worker/             # nightly scheduler and job runner
│   └── tests/
│       ├── fixtures/steam/     # recorded Steam responses
│       └── test_*.py
├── frontend/src/
│   ├── theme/brand.ts          # logo and colors: the one branding file
│   ├── api/  pages/  components/
│   └── lib/chartPng.ts
└── data/                       # SQLite file and export cache (gitignored)
```

## Database schema

JSON columns use SQLAlchemy's generic JSON type so a move to Postgres needs no rewrites. SQLite runs in WAL mode so the app and worker can share the file. All timestamps are UTC.

```
titles
  id · steam_app_id UNIQUE · demo_app_id NULL · name
  status (released | early_access | coming_soon | unreleased) · notes · archived_at NULL
  header_image_url · release_date NULL · release_date_text · developers JSON · publishers JSON
  appdetails_json JSON · appdetails_fetched_at · created_at · updated_at

reviews  (never hard-deleted)
  id · title_id · app_id (main app or demo app) · recommendation_id UNIQUE · language · review_text
  timestamp_created · timestamp_updated · voted_up · votes_up · votes_funny
  weighted_vote_score (decimal) · comment_count · steam_purchase · received_for_free
  written_during_early_access · primarily_steam_deck · refunded
  developer_response NULL · timestamp_dev_responded NULL
  author_steamid · author_num_games_owned · author_num_reviews · author_playtime_forever
  author_playtime_at_review · author_playtime_last_two_weeks · author_last_played
  raw_json JSON (the full object as Steam sent it)
  content_status (ok | no_content) · playtime_band (lt2h | 2to10h | 10to50h | 50h_plus)
  first_seen_at · last_seen_at · deleted_at NULL
reviews_fts  (SQLite FTS5 on review_text, added in Phase 3)

review_snapshots  (daily query_summary)
  id · title_id · app_id · snapshot_date · total_reviews · total_positive · total_negative
  review_score · review_score_desc · UNIQUE (title_id, app_id, snapshot_date)

sync_runs
  id · title_id · app_id · mode (incremental | full) · trigger · status · cursor (resume point)
  pages_fetched · new_count · updated_count · deleted_count · started_at · finished_at · error

codebooks       id · title_id · version · status · parent_id · created_by · needs_review_reason · created_at · approved_at
themes          id · codebook_id · key · name · definition · include_notes · exclude_notes · example_review_ids · derived_from · sort_order
analysis_runs   id · title_id · codebook_id · kind · trigger · status · models · counts · estimated and actual tokens and cost · batch_ids · timings · error
review_tags     id · review_id · codebook_id · analysis_run_id · review_timestamp_updated · model · gist_en · other_flag · other_note · is_current · tagged_at
theme_mentions  id · review_tag_id · theme_id · sentiment · quote_start · quote_end
qa_results      id · analysis_run_id · review_id · theme_id · primary_present · primary_sentiment · qa_present · qa_sentiment
summaries       id · title_id · analysis_run_id · codebook_id · model · content JSON · created_at
users           id · email · name · role · created_at · last_login_at
alerts_sent     id · title_id · kind · dedupe_key · payload · sent_at
```

Tables are added in the phase that needs them. Quotes are stored as character offsets into the review text, so a displayed quote is always the reviewer's exact text.

## Tagging JSON schema

Enforced with structured outputs (`output_config.format`). `theme_id` is an enum built from the approved codebook version. Up to 20 reviews per request; the instructions and codebook form a cached system prompt.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["reviews"],
  "properties": {
    "reviews": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["review_id", "mentions", "overall", "other_flag", "other_note", "gist_en"],
        "properties": {
          "review_id": { "type": "string" },
          "mentions": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["theme_id", "sentiment", "quote"],
              "properties": {
                "theme_id":  { "type": "string", "enum": ["<theme keys from codebook vN>"] },
                "sentiment": { "type": "string", "enum": ["positive", "negative", "mixed"] },
                "quote":     { "type": "string" }
              }
            }
          },
          "overall": {
            "type": "object",
            "additionalProperties": false,
            "required": ["sentiment", "quote"],
            "properties": {
              "sentiment": { "type": "string", "enum": ["positive", "negative", "mixed", "none"] },
              "quote":     { "type": "string" }
            }
          },
          "other_flag": { "type": "boolean" },
          "other_note": { "type": "string" },
          "gist_en":    { "type": "string" }
        }
      }
    }
  }
}
```

## Models and cost

- `MODEL_TAGGING=claude-haiku-5-5`, `MODEL_ANALYSIS=claude-sonnet-5-5`
- Rough first full run for Tombwater (about 300 reviews): about $0.40. Tagging scales at about $0.08 per 1,000 reviews.
- The app shows an exact estimate (token counting on the real requests) before every run and requires confirmation.

## Decisions

1. First full download uses `filter=1` (Recent). Nightly incremental sync sorts by last update and stops at the previous high point, so edits are caught. A weekly full fetch marks missing reviews as deleted.
2. "Unchanged" means same review text and same codebook version. A new codebook version re-tags everything.
3. A quote that fails the verbatim check is dropped; the theme and sentiment tag is kept and the drop is counted on the quality page.
4. Tagging runs Haiku 5.5 at low effort, configurable.
5. Small manual runs (under about 100 reviews) call the API directly; nightly and bulk runs use the Batches API.
6. Theme discovery needs at least about 30 reviews with real text.
7. GodsTV's demo app is synced separately and never mixed into the main title's numbers.
8. Verbatim quotes keep their em dashes. Everything the app generates has none.
9. Added after the first spot check: every review also gets an overall impression of the game as a whole, with its own verbatim quote. General praise ("very nice", "amazing game") goes there instead of being forced into a theme, and it is counted apart from the themes. Tags carry a tag version (now 2), so tags made before this were redone on the next run.

## Approved extra dependencies

- Backend: uvicorn, httpx, pydantic-settings, Jinja2, Authlib, itsdangerous, APScheduler, pytest, respx
- Frontend: react-router, @tanstack/react-query

## Steam API notes (gathered while building)

- `IUserReviewsService/GetAppReviews/v1` must be called with `input_json`; plain query parameters fall back to defaults (English only, Helpful sort).
- Enum parameters are numbers. String values such as `filter=recent` silently fall back to Helpful.
- `languages` takes Steam API language names (`["all"]`, `"turkish"`), not Web API codes (`tr`).
- Cursors must be URL-encoded; a raw `+` returns an empty response.
- The response is wrapped in `{"response": {...}}`. An unknown app returns `{"response": {}}`.
- `weighted_vote_score` can arrive as a string or a number.
- Steam can cache answers to keyless callers for several minutes.
- The old `store.steampowered.com/appreviews` endpoint is disabled on 22 October 2026.

Confirmed against live Steam on 2026-10-20:

- `filter=2` is the Updated sort (newest `timestamp_updated` first); `filter=1` is Recent.
- Responses carry `cursor`, `query_summary`, `reviews` and `total_matching` inside `response`.
- Review and author field names match the old endpoint, except authors no longer include `num_games_owned`.
- Stored counts matched Steam's `total_reviews` exactly for every title (Tombwater 305, Duck Paradox 331,
  Hive Jump 2 114, Dark Sky 71, The Lullaby of Life 45, GodsTV demo 126, others 0).
- A second sync ran incrementally: one request, nothing new or edited.

Phase 2 notes (decided while building):

- Analysis runs and summaries are per Steam app, so GodsTV's demo (126 reviews) can be analyzed on its own; codebooks stay per title.
- The QA re-tag uses 5% of the reviews tagged in a run, with a minimum of 20 (5% of a 300-review title would be 15).
- Steam review markup ([b], [h1], [list]) is removed into a `display_text` field; quotes are matched and highlighted against it.
- Sonnet 5.5 direct calls opt into Anthropic's server-side refusal fallback; Haiku 5.5 has none, so a declined or missing review gets one more try on its own and otherwise stays pending for the next run.

Phase 2 live results on Duck Paradox (331 reviews, 284 with text, 47 with almost none):

- Theme discovery proposed 15 themes on the second try, after the discovery prompt was tightened (the first try gave 5). Codebook v2 was approved as proposed.
- First analysis run: $0.10. Spot check of 20 random reviews: 15 right, 5 off, all 5 general praise ("very nice", "amazing game") with no positive tag.
- Second run after adding the overall impression: $0.12 (tagging $0.02, QA $0.04, summary $0.05). All 5 disagreements now carry a positive overall impression quoting the words the reviewer used. QA on a new random 20: theme agreement 96%, kappa 0.73, sentiment agreement 64%, overall impression agreement 90%. 628 of 633 quotes verified.
- Total spent on Duck Paradox, both discovery attempts and both runs: $0.43.
