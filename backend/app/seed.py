from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Title

SEED_TITLES = [
    {"name": "Tombwater", "steam_app_id": 3308200, "status": "released"},
    {"name": "Duck Paradox", "steam_app_id": 2058150, "status": "released"},
    {"name": "Hive Jump 2: Survivors", "steam_app_id": 2545740, "status": "released"},
    {"name": "Dark Sky", "steam_app_id": 1454960, "status": "released"},
    {"name": "The Lullaby of Life", "steam_app_id": 2493180, "status": "released"},
    {
        "name": "GodsTV",
        "steam_app_id": 2626570,
        "status": "coming_soon",
        "demo_app_id": 3673170,
        "notes": "Early Access coming soon",
    },
    {"name": "The Legend of Baboo", "steam_app_id": 2928040, "status": "unreleased"},
    {"name": "Floor is...What!?", "steam_app_id": 1272140, "status": "unreleased"},
]


def seed_titles(session: Session) -> int:
    """Insert the seed titles that are not already present. Returns how many were added."""
    existing = set(session.scalars(select(Title.steam_app_id)))
    added = 0
    for row in SEED_TITLES:
        if row["steam_app_id"] in existing:
            continue
        session.add(Title(**row))
        added += 1
    session.commit()
    return added
