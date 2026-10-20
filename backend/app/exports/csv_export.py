"""CSV of coded reviews, one row per review."""

import csv
import io
from datetime import date

from sqlalchemy.orm import Session

from app.exports.tables import ExportContext, coded_reviews

# A cell starting with one of these can run as a formula when the file is opened in a spreadsheet.
# Reviews are written by the public, so such cells get a leading apostrophe, which spreadsheets
# show as plain text.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value: str) -> str:
    return "'" + value if value.startswith(FORMULA_START) else value


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return safe_text(value)
    return str(value)


def coded_reviews_csv(session: Session, ctx: ExportContext) -> bytes:
    header, rows = coded_reviews(session, ctx)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    # The byte order mark tells Excel the file is UTF-8, so non-English reviews show correctly.
    return ("﻿" + buf.getvalue()).encode("utf-8")
