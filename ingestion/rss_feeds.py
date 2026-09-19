"""Генерично RSS ingestion за всички статични (не-API) новинарски
feed-ове — крипто-специфични (CoinDesk, The Block) и общи пазарни
(MarketWatch, Investing.com, Yahoo Finance per-тикер). Reuters е в
`sources` (active=FALSE) но не се тегли — виж FLAT_FEEDS по-долу.

Всеки feed е просто (source_name в `sources`, url) двойка — не се
различават по код, само по конфигурация тук. CryptoPanic е отделно в
cryptopanic.py, защото изисква auth_token.

feedparser-ов вграден urllib има проблем с CA certs на тази машина —
теглим съдържанието през requests (сертификати от certifi) и подаваме
байтовете на feedparser.parse().

Всеки feed се третира изолирано (own try/except) — счупен/недостъпен
feed не бива да спре останалите за този цикъл.
"""
from __future__ import annotations

import calendar
import hashlib
import logging
import os
from datetime import datetime, timezone

import feedparser
import requests

from ingestion.common import run_source

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 20
USER_AGENT = "Mozilla/5.0 (compatible; MarketSignalEngine/0.1)"

# Статични, общи feed-ове — по един ред в sources.
# NB: 'reuters' е в sources (active=FALSE) но нарочно НЕ е тук —
# reuters.com връща 401 на всеки публичен RSS път (провери на живо
# 2026-09-19), reutersagency.com feed-а е 404. Reuters спря публичните
# RSS-и преди години; ако намериш работещ URL, добави го тук и смени
# active на TRUE в db/seeds.sql.
FLAT_FEEDS = {
    "rss_coindesk": os.environ.get("RSS_COINDESK_URL", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    "rss_theblock": os.environ.get("RSS_THEBLOCK_URL", "https://www.theblock.co/rss.xml"),
    "marketwatch": os.environ.get("RSS_MARKETWATCH_URL", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    "investing_com": os.environ.get("RSS_INVESTING_URL", "https://www.investing.com/rss/news_25.rss"),
}

# Yahoo Finance е per-тикер, не един flat feed — един source
# ('yahoo_finance'), много URL-и, обединени в един ingest_run.
YAHOO_TICKERS = ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "DOGE-USD", "SHIB-USD", "NVDA", "AAPL"]


def fetch_rss(feed_url: str) -> list[dict]:
    resp = requests.get(feed_url, timeout=REQUEST_TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    rows = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = entry.get("title")
        # feedparser нормализира РАЗЛИЧНИ date формати (RFC822 при
        # CoinDesk/MarketWatch/Yahoo, "YYYY-MM-DD HH:MM:SS" при
        # Investing.com) в published_parsed — UTC struct_time. Ръчен
        # parse на суровия низ (email.utils.parsedate_to_datetime)
        # тихо чупи на нестандартни формати и губи цели източници.
        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if not link or not title or not struct:
            continue
        published_at = datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)
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


def _fetch_yahoo_all() -> list[dict]:
    rows: list[dict] = []
    for ticker in YAHOO_TICKERS:
        url = f"https://finance.yahoo.com/rss/headline?s={ticker}"
        try:
            rows.extend(fetch_rss(url))
        except requests.RequestException as exc:
            logger.warning("Yahoo Finance RSS се провали за %s: %s", ticker, exc)
    return rows


def run_once() -> None:
    for source_name, feed_url in FLAT_FEEDS.items():
        try:
            run_source(source_name, lambda u=feed_url: fetch_rss(u))
        except Exception as exc:
            logger.error("%s: run се провали: %s", source_name, exc)
    try:
        run_source("yahoo_finance", _fetch_yahoo_all)
    except Exception as exc:
        logger.error("yahoo_finance: run се провали: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_once()
