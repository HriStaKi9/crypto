"""FastAPI ingestion monitoring dashboard — само за лична употреба.

НЕ е Stage 4 API (сигнали/backtest от CLAUDE.md) — това е observability
инструмент върху суровите ingestion таблици, за да се вижда дали
2-седмичният непрекъснат поток от Етап 1 наистина тече. Read-only,
без auth (мисли се за localhost/личен достъп, не за публично излагане).

Пуска се с: uvicorn api.main:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.queries import get_latest_prices, get_recent_news, get_source_status
from db.session import get_session

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Market Signal Engine — Ingestion Monitor")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/source-status")
def api_source_status() -> list[dict]:
    with get_session() as session:
        return get_source_status(session)


@app.get("/api/news/recent")
def api_recent_news(limit: int = 30) -> list[dict]:
    with get_session() as session:
        return get_recent_news(session, limit=limit)


@app.get("/api/prices/latest")
def api_latest_prices() -> list[dict]:
    with get_session() as session:
        return get_latest_prices(session)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    with get_session() as session:
        sources = get_source_status(session)
        news = get_recent_news(session, limit=30)
        prices = get_latest_prices(session)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"sources": sources, "news": news, "prices": prices},
    )
