"""Общи helper-и за ingestion модулите.

Всеки source-специфичен модул (gdelt.py, binance.py, ...) е "тъп" —
само тегли данни от API и ги подава тук. Единствената логика, която
пипа общите таблици (sources, assets, asset_aliases, news_raw,
prices, ingest_runs), живее на едно място, за да не се разминава
поведението между източниците (напр. как се прави upsert, как се
логва run в ingest_runs).

Правилата от CLAUDE.md, които важат тук:
  - news_raw е immutable (insert-only, ON CONFLICT DO NOTHING).
  - prices не се мърджва между източници — source_id е част от PK.
  - available_at е generated колона в БД; никой Python код не я пипа.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref",
}


def canonicalize_url(raw_url: str) -> str:
    """Приблизителна канонична форма: lowercase host, без tracking params, без fragment."""
    parts = urlsplit(raw_url.strip())
    host = parts.netloc.lower()
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def url_hash(canonical_url: str) -> bytes:
    return hashlib.sha256(canonical_url.encode("utf-8")).digest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_source_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT source_id FROM sources WHERE name = :name"), {"name": name}
    ).first()
    if row is None:
        raise LookupError(f"Неизвестен source в sources: {name!r} — добави го в db/seeds.sql")
    return row.source_id


def get_asset_id(session: Session, symbol: str) -> int:
    row = session.execute(
        text("SELECT asset_id FROM assets WHERE symbol = :symbol"), {"symbol": symbol}
    ).first()
    if row is None:
        raise LookupError(f"Неизвестен asset в assets: {symbol!r}")
    return row.asset_id


def get_asset_aliases(
    session: Session,
    symbol: str,
    min_confidence: float = 0.6,
    match_types: tuple[str, ...] = ("exact",),
) -> list[str]:
    """Псевдоними на актив за построяване на search заявки (напр. GDELT).

    По подразбиране взима само 'exact' псевдоними — cashtag-ове
    ("$BTC") рядко се срещат буквално в mainstream новинарски текст и
    само внасят шум в full-text заявка.
    """
    stmt = text(
        """
        SELECT aa.alias
        FROM asset_aliases aa
        JOIN assets a ON a.asset_id = aa.asset_id
        WHERE a.symbol = :symbol
          AND aa.confidence >= :min_confidence
          AND aa.match_type IN :match_types
        ORDER BY aa.confidence DESC
        """
    ).bindparams(bindparam("match_types", expanding=True))
    rows = session.execute(
        stmt, {"symbol": symbol, "min_confidence": min_confidence, "match_types": list(match_types)}
    ).all()
    return [r.alias for r in rows]


def start_run(
    session: Session,
    source_id: int,
    window_from: Optional[datetime] = None,
    window_to: Optional[datetime] = None,
) -> int:
    row = session.execute(
        text(
            """
            INSERT INTO ingest_runs (source_id, window_from, window_to, status)
            VALUES (:source_id, :window_from, :window_to, 'running')
            RETURNING run_id
            """
        ),
        {"source_id": source_id, "window_from": window_from, "window_to": window_to},
    ).first()
    session.commit()
    return row.run_id


def finish_run(
    session: Session,
    run_id: int,
    rows_fetched: int,
    rows_new: int,
    status: str = "ok",
    error_text: Optional[str] = None,
) -> None:
    session.execute(
        text(
            """
            UPDATE ingest_runs
            SET finished_at = now(), rows_fetched = :rows_fetched,
                rows_new = :rows_new, status = :status, error_text = :error_text
            WHERE run_id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "rows_fetched": rows_fetched,
            "rows_new": rows_new,
            "status": status,
            "error_text": error_text,
        },
    )
    session.commit()


def upsert_news_raw(session: Session, source_id: int, articles: Iterable[dict]) -> int:
    """Insert-only в news_raw (immutable — CLAUDE.md, правило 3).

    Всеки article dict: source_uid, url, title, published_at (datetime,
    UTC), плюс опционално body/language/publisher/raw_payload (dict).
    Връща брой РЕАЛНО нови редове (ON CONFLICT DO NOTHING + RETURNING).
    """
    rows_new = 0
    for art in articles:
        canonical = canonicalize_url(art["url"]) if art.get("url") else None
        result = session.execute(
            text(
                """
                INSERT INTO news_raw (
                    source_id, source_uid, url, url_canonical, url_hash,
                    title, body, language, publisher, published_at, raw_payload
                ) VALUES (
                    :source_id, :source_uid, :url, :url_canonical, :url_hash,
                    :title, :body, :language, :publisher, :published_at, :raw_payload::jsonb
                )
                ON CONFLICT (source_id, source_uid) DO NOTHING
                RETURNING raw_id
                """
            ),
            {
                "source_id": source_id,
                "source_uid": art["source_uid"],
                "url": art.get("url"),
                "url_canonical": canonical,
                "url_hash": url_hash(canonical) if canonical else None,
                "title": art["title"],
                "body": art.get("body"),
                "language": art.get("language"),
                "publisher": art.get("publisher"),
                "published_at": art["published_at"],
                "raw_payload": json.dumps(art["raw_payload"], default=str) if art.get("raw_payload") is not None else None,
            },
        )
        if result.first() is not None:
            rows_new += 1
    session.commit()
    return rows_new


def upsert_prices(
    session: Session, asset_id: int, source_id: int, bar_interval: str, bars: Iterable[dict]
) -> int:
    """Insert-only в prices (source_id е част от PK — CLAUDE.md, правило 4).

    Всеки bar dict: ts (datetime UTC, отваряне на свещта), open/high/
    low/close (float), volume (float, optional), quote_ccy (default 'USD').
    """
    rows_new = 0
    for bar in bars:
        result = session.execute(
            text(
                """
                INSERT INTO prices (
                    asset_id, source_id, bar_interval, ts,
                    open, high, low, close, volume, quote_ccy
                ) VALUES (
                    :asset_id, :source_id, :bar_interval, :ts,
                    :open, :high, :low, :close, :volume, :quote_ccy
                )
                ON CONFLICT (asset_id, source_id, bar_interval, ts) DO NOTHING
                RETURNING ts
                """
            ),
            {
                "asset_id": asset_id,
                "source_id": source_id,
                "bar_interval": bar_interval,
                "ts": bar["ts"],
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar.get("volume"),
                "quote_ccy": bar.get("quote_ccy", "USD"),
            },
        )
        if result.first() is not None:
            rows_new += 1
    session.commit()
    return rows_new
