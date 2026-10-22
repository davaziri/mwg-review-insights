"""What every export shares: branding, file names, and a plain-English line for the filters."""

import base64
import json
import re
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from app.analysis.aggregate import Filters
from app.analysis.prep import PLAYTIME_BAND_LABELS
from app.config import Settings

LANGUAGE_NAMES = {
    "english": "English",
    "schinese": "Chinese (Simplified)",
    "tchinese": "Chinese (Traditional)",
    "japanese": "Japanese",
    "koreana": "Korean",
    "russian": "Russian",
    "spanish": "Spanish (Spain)",
    "latam": "Spanish (Latin America)",
    "brazilian": "Portuguese (Brazil)",
    "portuguese": "Portuguese",
    "german": "German",
    "french": "French",
    "italian": "Italian",
    "polish": "Polish",
    "turkish": "Turkish",
    "ukrainian": "Ukrainian",
    "czech": "Czech",
    "dutch": "Dutch",
    "swedish": "Swedish",
    "danish": "Danish",
    "norwegian": "Norwegian",
    "finnish": "Finnish",
    "hungarian": "Hungarian",
    "thai": "Thai",
    "vietnamese": "Vietnamese",
    "indonesian": "Indonesian",
    "romanian": "Romanian",
    "greek": "Greek",
    "bulgarian": "Bulgarian",
    "arabic": "Arabic",
    "other": "Other language",
}


def language_name(code: str | None) -> str:
    return LANGUAGE_NAMES.get(code or "", code or "Unknown")


@dataclass(frozen=True)
class Brand:
    app_name: str
    company_name: str
    palette: dict
    logo_data_uri: str | None


@cache
def _load_brand(brand_file: str, logo_file: str) -> Brand:
    data = json.loads(Path(brand_file).read_text(encoding="utf-8"))
    logo = Path(logo_file)
    uri = f"data:image/svg+xml;base64,{base64.b64encode(logo.read_bytes()).decode()}" if logo.is_file() else None
    return Brand(data["appName"], data["companyName"], data["palette"]["light"], uri)


def load_brand(settings: Settings) -> Brand:
    """The same branding file the web app uses. Reports always use the light palette."""
    return _load_brand(settings.brand_file, settings.logo_file)


def export_name(title_name: str, report_type: str, ext: str, today: date) -> str:
    """MWG_<Title>_<ReportType>_<YYYY-MM-DD>.<ext>, with the title reduced to letters and digits."""
    clean = re.sub(r"[^0-9A-Za-z]+", "_", title_name).strip("_") or "Title"
    return f"MWG_{clean}_{report_type}_{today.isoformat()}.{ext}"


def describe_filters(f: Filters) -> list[str]:
    """The filters as short phrases, for report headers and the About sheet."""
    out = []
    if f.date_from or f.date_to:
        start = f.date_from.isoformat() if f.date_from else "the first review"
        end = f.date_to.isoformat() if f.date_to else "today"
        out.append(f"Reviews written from {start} to {end}")
    if f.voted_up is not None:
        out.append("Recommended reviews only" if f.voted_up else "Not recommended reviews only")
    if f.playtime_bands:
        out.append("Playtime: " + ", ".join(PLAYTIME_BAND_LABELS.get(b, b) for b in f.playtime_bands))
    if f.languages:
        out.append("Languages: " + ", ".join(language_name(code) for code in f.languages))
    if f.early_access is not None:
        out.append("Written during early access" if f.early_access else "Written after release")
    if f.steam_deck is not None:
        out.append("Played mostly on Steam Deck" if f.steam_deck else "Not played mostly on Steam Deck")
    if f.has_dev_response is not None:
        out.append("With a developer reply" if f.has_dev_response else "Without a developer reply")
    return out


def date_range_text(f: Filters, first: str | None, last: str | None) -> str:
    """The dates a report actually covers: the filter range, or the first and last review."""
    start = f.date_from.isoformat() if f.date_from else first
    end = f.date_to.isoformat() if f.date_to else last
    if not start and not end:
        return "No reviews"
    return f"{start} to {end}"


def yes_no(value: bool | None) -> str:
    return "Yes" if value else "No"
