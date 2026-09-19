"""CryptoPanic ingestion — крипто новини, API слой.

Изисква auth_token (безплатен план) — ако CRYPTOPANIC_API_KEY не е
зададен, run-ът се прескача с warning вместо да чупи целия scheduler
цикъл. Статичните RSS feed-ове (CoinDesk, The Block, Reuters,
MarketWatch, Investing.com, Yahoo Finance) са в rss_feeds.py — не се
различават от CryptoPanic по код, само по това, че нямат API/auth.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import requests

from ingestion.common import run_source

logger = logging.getLogger(__name__)

CRYPTOPANIC_BASE_URL = os.environ.get("CRYPTOPANIC_BASE_URL", "https://cryptopanic.com/api/v1")
REQUEST_TIMEOUT_S = 20


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


def run_once() -> None:
    run_source("cryptopanic", _fetch_cryptopanic)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_once()
