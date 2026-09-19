"""GDELT 2.0 DOC API ingestion — гръбнак на новинарския поток.

Безплатен, без auth, архив от 2015, обновява се на ~15 мин. Пише в
`news_raw` (immutable). НЕ прави дедуп и НЕ решава кой asset е свързан
с коя новина — това е job на nlp/entity_link.py по-късно. `available_at`
е generated колона в БД, тук изобщо не се пипа.

За всеки актив от фиксирания обхват (CLAUDE.md) строи search заявка от
`asset_aliases` (само 'exact' псевдоними с confidence >= 0.7 — cashtag-
овете не са полезни за full-text search в mainstream новини).

GDELT DOC API няма собствен article id → source_uid = sha256(url).
`published_at` тук е GDELT `seendate` (кога GDELT е индексирал
статията, не непременно точното editorial publish време) —
най-близкото безплатно приближение. Евентуално системно изоставане се
компенсира чрез `sources.tier_latency_s`, ако бъде установено, а не
чрез промяна на тази стойност.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone

import requests

from db.session import get_session
from ingestion.common import finish_run, get_asset_aliases, get_source_id, start_run, upsert_news_raw

logger = logging.getLogger(__name__)

SOURCE_NAME = "gdelt"
ASSET_SYMBOLS = ["BTC", "ETH", "NVDA", "AAPL", "SOL", "LINK", "DOGE", "SHIB"]
BASE_URL = os.environ.get("GDELT_BASE_URL", "https://api.gdeltproject.org/api/v2")
MAX_RECORDS = 250
REQUEST_TIMEOUT_S = 30
THROTTLE_S = 5  # учтивост към безплатния API между заявки на отделни активи

_SEENDATE_FMT = "%Y%m%dT%H%M%SZ"


def _build_query(aliases: list[str]) -> str:
    terms = " OR ".join(f'"{a}"' if " " in a else a for a in aliases)
    return f"({terms}) sourcelang:english"


def _parse_seendate(raw: str) -> datetime:
    return datetime.strptime(raw, _SEENDATE_FMT).replace(tzinfo=timezone.utc)


def fetch_articles(query: str) -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/doc/doc",
        params={
            "query": query,
            "mode": "artlist",
            "maxrecords": MAX_RECORDS,
            "format": "json",
            "sort": "datedesc",
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("articles", [])


def _to_news_raw_row(article: dict) -> dict | None:
    url = article.get("url")
    seendate = article.get("seendate")
    title = article.get("title")
    if not url or not seendate or not title:
        return None
    return {
        "source_uid": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "url": url,
        "title": title,
        "language": article.get("language"),
        "publisher": article.get("domain"),
        "published_at": _parse_seendate(seendate),
        "raw_payload": article,
    }


def run_once() -> None:
    with get_session() as session:
        source_id = get_source_id(session, SOURCE_NAME)
        run_id = start_run(session, source_id)
        total_fetched = 0
        total_new = 0
        try:
            for symbol in ASSET_SYMBOLS:
                aliases = get_asset_aliases(session, symbol, min_confidence=0.7, match_types=("exact",))
                if not aliases:
                    logger.warning("Няма aliases с достатъчна confidence за %s — пропускам", symbol)
                    continue
                query = _build_query(aliases)
                try:
                    articles = fetch_articles(query)
                except requests.RequestException as exc:
                    logger.error("GDELT заявка се провали за %s: %s", symbol, exc)
                    time.sleep(THROTTLE_S)
                    continue
                rows = [row for a in articles if (row := _to_news_raw_row(a)) is not None]
                new = upsert_news_raw(session, source_id, rows)
                total_fetched += len(rows)
                total_new += new
                logger.info("GDELT %s: %d статии, %d нови", symbol, len(rows), new)
                time.sleep(THROTTLE_S)
        except Exception as exc:
            finish_run(session, run_id, total_fetched, total_new, status="failed", error_text=str(exc))
            raise
        else:
            finish_run(session, run_id, total_fetched, total_new, status="ok")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_once()
