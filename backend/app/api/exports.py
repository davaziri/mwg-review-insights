"""Downloads: CSV and Excel of coded reviews, and PDF reports. Each one uses the page filters."""

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters
from app.api.common import filters_dep, resolve_app, title_or_404
from app.config import get_settings
from app.db import get_session
from app.exports.common import export_name, load_brand
from app.exports.csv_export import coded_reviews_csv
from app.exports.html import footer_template
from app.exports.pdf import PdfError, render_pdf
from app.exports.portfolio_report import portfolio_report_html
from app.exports.report import title_report_html
from app.exports.tables import build_context
from app.exports.xlsx_export import workbook
from app.timeutil import utcnow

router = APIRouter(prefix="/api", tags=["exports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _download(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"},
    )


def _context(session: Session, title_id: int, f: Filters):
    title = title_or_404(session, title_id)
    app_id = resolve_app(title, f.app_id)
    return build_context(session, get_settings(), title, app_id, f)


def _name(ctx, report_type: str, ext: str) -> str:
    return export_name(ctx.subject, report_type, ext, utcnow().date())


@router.get("/titles/{title_id}/export.csv")
def export_csv(title_id: int, f: Filters = Depends(filters_dep), session: Session = Depends(get_session)):
    ctx = _context(session, title_id, f)
    return _download(coded_reviews_csv(session, ctx), "text/csv; charset=utf-8", _name(ctx, "CodedReviews", "csv"))


@router.get("/titles/{title_id}/export.xlsx")
def export_xlsx(title_id: int, f: Filters = Depends(filters_dep), session: Session = Depends(get_session)):
    ctx = _context(session, title_id, f)
    return _download(workbook(session, ctx, load_brand(get_settings())), XLSX, _name(ctx, "Data", "xlsx"))


@router.get("/titles/{title_id}/export.pdf")
def export_pdf(title_id: int, f: Filters = Depends(filters_dep), session: Session = Depends(get_session)):
    settings = get_settings()
    ctx = _context(session, title_id, f)
    brand = load_brand(settings)
    html = title_report_html(session, ctx, brand)
    try:
        pdf = render_pdf(html, settings, footer_template(brand, f"{ctx.subject} Steam review report"))
    except PdfError as exc:
        raise HTTPException(503, str(exc)) from exc
    return _download(pdf, "application/pdf", _name(ctx, "Report", "pdf"))


@router.get("/portfolio/export.pdf")
def export_portfolio_pdf(date_from: date | None = None, date_to: date | None = None, session: Session = Depends(get_session)):
    settings = get_settings()
    brand = load_brand(settings)
    html = portfolio_report_html(session, settings, brand, date_from, date_to)
    try:
        pdf = render_pdf(html, settings, footer_template(brand, "Portfolio report"))
    except PdfError as exc:
        raise HTTPException(503, str(exc)) from exc
    return _download(pdf, "application/pdf", export_name("Portfolio", "Report", "pdf", utcnow().date()))
