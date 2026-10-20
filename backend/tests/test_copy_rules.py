"""House rule: no em dashes anywhere in UI copy, templates or app code."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCANNED = [
    (REPO / "frontend" / "src", {".ts", ".tsx", ".css"}),
    (REPO / "frontend" / "index.html", None),
    (REPO / "backend" / "app", {".py", ".html", ".md", ".j2"}),
]


def test_no_em_dashes_in_ui_or_app_code():
    offenders = []
    for root, suffixes in SCANNED:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.suffix in suffixes]
        for path in files:
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "—" in line:
                    offenders.append(f"{path.relative_to(REPO)}:{n}")
    assert offenders == [], f"Em dashes found: {offenders}"
