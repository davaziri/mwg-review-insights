"""Print report HTML to a US Letter PDF with Chromium (through Playwright)."""

from urllib.parse import urlparse

from app.config import Settings

# The report pages are self-contained except for Steam's header images. Every other request is
# refused, so nothing in a report can reach the network.
IMAGE_HOSTS = (".steamstatic.com", ".akamaihd.net")
MARGINS = {"top": "0.55in", "bottom": "0.7in", "left": "0.6in", "right": "0.6in"}


class PdfError(Exception):
    pass


def _allow(route) -> None:
    request = route.request
    host = urlparse(request.url).hostname or ""
    if request.resource_type == "image" and host.endswith(IMAGE_HOSTS):
        route.continue_()
    else:
        route.abort()


def render_pdf(html: str, settings: Settings, footer: str) -> bytes:
    from playwright.sync_api import Error, sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=settings.chromium_path or None)
            try:
                page = browser.new_page()
                page.route("**/*", _allow)
                page.set_content(html, wait_until="load", timeout=30_000)
                return page.pdf(
                    format="Letter",
                    print_background=True,
                    display_header_footer=True,
                    header_template="<span></span>",
                    footer_template=footer,
                    margin=MARGINS,
                )
            finally:
                browser.close()
    except Error as exc:
        raise PdfError(f"Could not make the PDF: {exc.message.splitlines()[0]}") from exc
