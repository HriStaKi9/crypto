"""CryptoPanic + RSS ingestion — крипто новини, втори новинарски слой.

CryptoPanic изисква auth_token (безплатен план) — ако CRYPTOPANIC_API_KEY
не е зададен, тази част се прескача с warning вместо да чупи целия run.
RSS (CoinDesk, The Block) не изискват auth и винаги се опитват — те са
отделни `sources` редове (rss_coindesk, rss_theblock), затова всеки се
логва като собствен ingest_run.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

from db.session import get_session
from ingestion.common import finish_run, get_source_id, start_run, upsert_news_raw

logger = logging.getLogger(__name__)

CRYPTOPANIC_BASE_URL = os.environ.get("CRYPTOPANIC_BASE_URL", "https://cryptopanic.com/api/v1")
REQUEST_TIMEOUT_S = 20

RSS_FEEDS = {
    "rss_coindesk": os.environ.get("RSS_COINDESK_URL", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    "rss_theblock": os.environ.get("RSS_THEBLOCK_URL", "https://www.theblock.co/rss.xml"),
}


def _fetch_cryptopanic() -> list[dict]:
    api_key = os.environ.get("CRYPTOPANIC_API_KEY")
    if not api_key:
        logger.warning("CRYPTOPANIC_API_KEY не е зададен — пропускам CryptoPanic")
        return []
    resp = requests.get(
        f"{CRYPTOPANIC_BASE_URL}/posts/",
        params={"auth_token": api_key, "public": "true"},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    rows = []
    for item in results:
        published = item.get("published_at")
        if not published or not item.get("id") or not item.get("title"):
            continue
        rows.append(
            {
                "source_uid": str(item["id"]),
                "url": item.get("url"),
                "title": item["title"],
                "publisher": (item.get("source") or {}).get("title"),
                "published_at": datetime.fromisoformat(published.replace("Z", "+00:00")),
                "raw_payload": item,
            }
        )
    return rows


def _fetch_rss(feed_url: str) -> list[dict]:
    # requests (не feedparser-овия вграден urllib fetcher) — консистентен
    # timeout/headers с останалите модули и няма проблем с CA certs на
    # системи, където urllib не намира валиден trust store.
    resp = requests.get(feed_url, timeout=REQUEST_TIMEOUT_S, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    rows = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = entry.get("title")
        published = entry.get("published") or entry.get("updated")
        if not link or not title or not published:
            continue
        try:
            published_at = parsedate_to_datetime(published)
        except (TypeError, ValueError):
            continue
        published_at = (
            published_at.replace(tzinfo=timezone.utc)
            if published_at.tzinfo is None
            else published_at.astimezone(timezone.utc)
        )
        rows.append(
            {
                "source_uid": hashlib.sha256(link.encode("utf-8")).hexdigest(),
                "url": link,
                "title": title,
                "publisher": parsed.feed.get("title"),
                "published_at": published_at,
                "raw_payload": {"summary": entry.get("summary")},
            }
        )
    return rows


def _run_source(source_name: str, fetch_fn) -> None:
    with get_session() as session:
        source_id = get_source_id(session, source_name)
        run_id = start_run(session, source_id)
        try:
            rows = fetch_fn()
            fetched = len(rows)
            new = upsert_news_raw(session, source_id, rows)
        except Exception as exc:
            finish_run(session, run_id, 0, 0, status="failed", error_text=str(exc))
            raise
        else:
            finish_run(session, run_id, fetched, new, status="ok")
            logger.info("%s: %d статии, %d нови", source_name, fetched, new)


def run_once() -> None:
    _run_source("cryptopanic", _fetch_cryptopanic)
    for source_name, feed_url in RSS_FEEDS.items():
        _run_source(source_name, lambda u=feed_url: _fetch_rss(u))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_once()
