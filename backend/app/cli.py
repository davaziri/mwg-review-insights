"""Command line entry points.

    python -m app.cli init-db                 apply migrations and add seed titles
    python -m app.cli worker                  run the background worker (queue + nightly sync)
    python -m app.cli sync --all              sync every active title now, without the worker
    python -m app.cli sync --app-id 3308200 --mode full
    python -m app.cli record-fixtures --app-id 3308200 --pages 2
"""

import argparse
import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]


def init_db(database_url: str | None = None) -> None:
    from app.db import SessionLocal
    from app.seed import seed_titles

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    if database_url is None:
        with SessionLocal() as session:
            added = seed_titles(session)
        if added:
            print(f"Added {added} seed title(s).")


def sync_now(app_id: int | None, all_titles: bool, mode: str | None) -> None:
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import Title
    from app.steam.client import SteamClient
    from app.steam.sync import enqueue_sync
    from app.worker.runner import enqueue_all_active, process_queue

    settings = get_settings()
    with SessionLocal() as session:
        if all_titles:
            enqueue_all_active(session, settings, trigger="manual")
        else:
            title = session.scalar(select(Title).where(Title.steam_app_id == app_id))
            if title is None:
                raise SystemExit(f"No title with Steam app ID {app_id}")
            enqueue_sync(session, settings, title, trigger="manual", requested_by="cli", mode=mode)
    with SteamClient.from_settings(settings) as client:
        process_queue(SessionLocal, settings, client)


def record_fixtures(app_id: int, pages: int, sort_filter: int, out_dir: Path) -> None:
    """Save real GetAppReviews responses as test fixtures. Author Steam IDs are replaced with
    stable placeholders so no personal identifiers land in the repo."""
    from app.config import get_settings
    from app.steam.client import FIRST_CURSOR, SteamClient, parse_reviews_response

    settings = get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)
    ids: dict[str, str] = {}
    cursor = FIRST_CURSOR
    with SteamClient.from_settings(settings) as client:
        for n in range(1, pages + 1):
            body = client.get_reviews_raw(app_id, cursor, sort_filter=sort_filter)
            page = parse_reviews_response(body)
            for review in page.reviews:
                author = review.get("author") or {}
                if "steamid" in author:
                    author["steamid"] = ids.setdefault(str(author["steamid"]), f"7656119800000{len(ids):04d}")
            path = out_dir / f"reviews_{app_id}_filter{sort_filter}_page{n}.json"
            path.write_text(json.dumps({"request_cursor": cursor, "body": body}, indent=2, ensure_ascii=False))
            print(f"Wrote {path}")
            if not page.reviews:
                break
            cursor = page.cursor


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="apply migrations and add seed titles")
    sub.add_parser("worker", help="run the background worker")

    p_sync = sub.add_parser("sync", help="sync now, without the worker")
    target = p_sync.add_mutually_exclusive_group(required=True)
    target.add_argument("--app-id", type=int)
    target.add_argument("--all", action="store_true")
    p_sync.add_argument("--mode", choices=["full", "incremental"])

    p_rec = sub.add_parser("record-fixtures", help="save real Steam responses for tests")
    p_rec.add_argument("--app-id", type=int, required=True)
    p_rec.add_argument("--pages", type=int, default=2)
    p_rec.add_argument("--filter", type=int, default=1, dest="sort_filter")
    p_rec.add_argument("--out", type=Path, default=BACKEND_DIR / "tests" / "fixtures" / "steam" / "recorded")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "init-db":
        init_db()
    elif args.command == "worker":
        from app.worker.runner import main as worker_main

        worker_main()
    elif args.command == "sync":
        sync_now(args.app_id, args.all, args.mode)
    elif args.command == "record-fixtures":
        record_fixtures(args.app_id, args.pages, args.sort_filter, args.out)


if __name__ == "__main__":
    main()
