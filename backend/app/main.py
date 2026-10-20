from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import sync, titles
from app.config import REPO_ROOT, get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Midwest Games Review Insights", version="0.1.0")
    app.include_router(titles.router)
    app.include_router(sync.router)

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"ok": True}

    _mount_frontend(app, Path(get_settings().frontend_dist or REPO_ROOT / "frontend" / "dist"))
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app (production). In development Vite serves it instead."""
    if not (dist / "index.html").is_file():
        return
    dist = dist.resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
