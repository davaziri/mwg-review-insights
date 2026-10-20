import logging
from datetime import date, datetime, timedelta

from app.models import Title
from app.steam.client import SteamClient, SteamError
from app.timeutil import utcnow

log = logging.getLogger(__name__)

_DATE_FORMATS = ("%b %d, %Y", "%d %b, %Y", "%B %d, %Y", "%d %B, %Y", "%b %Y", "%B %Y")


def parse_release_date(text: str | None) -> date | None:
    """Steam shows dates like 'Jun 2, 2025' or '2 Jun, 2025', or free text like 'Coming soon'."""
    if not text:
        return None
    cleaned = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def apply_appdetails(title: Title, data: dict) -> None:
    title.appdetails_json = data
    title.appdetails_fetched_at = utcnow()
    if data.get("name"):
        title.name = data["name"]
    title.header_image_url = data.get("header_image") or title.header_image_url
    release = data.get("release_date") or {}
    title.release_date_text = release.get("date") or None
    title.release_date = parse_release_date(title.release_date_text)
    title.coming_soon = release.get("coming_soon")
    title.developers = data.get("developers") or []
    title.publishers = data.get("publishers") or []


def appdetails_stale(title: Title, max_age_hours: int) -> bool:
    if title.appdetails_fetched_at is None:
        return True
    return utcnow() - title.appdetails_fetched_at > timedelta(hours=max_age_hours)


def refresh_appdetails(title: Title, client: SteamClient) -> bool:
    """Fetch and cache store metadata. Returns False (and keeps old values) if Steam has none."""
    try:
        data = client.get_appdetails(title.steam_app_id)
    except SteamError as exc:
        log.warning("appdetails failed for %s: %s", title.steam_app_id, exc)
        return False
    if data is None:
        # No public store page yet. Record the attempt so we don't retry on every request.
        title.appdetails_fetched_at = utcnow()
        return False
    apply_appdetails(title, data)
    return True
