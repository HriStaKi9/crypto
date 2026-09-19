"""Read-only SQL заявки за ingestion monitoring dashboard-а.

Само SELECT-и — този модул никога не пише в базата. Ползва
`prices_resolved` изгледа (не суровата `prices` таблица), за да
показва разрешената между-източниците цена, а не всеки ред поотделно.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_source_status(session: Session) -> list[dict]:
    """Последният ingest_runs ред за всеки source (или нищо, ако никога не е пускан)."""
    rows = session.execute(
        text(
            """
            SELECT s.name, s.kind, s.active,
                   r.started_at, r.finished_at, r.status, r.rows_fetched, r.rows_new, r.error_text
            FROM sources s
            LEFT JOIN LATERAL (
                SELECT * FROM ingest_runs ir
                WHERE ir.source_id = s.source_id
                ORDER BY ir.started_at DESC
                LIMIT 1
            ) r ON true
            ORDER BY s.name
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def get_recent_news(session: Session, limit: int = 30) -> list[dict]:
    rows = session.execute(
        text(
            """
            SELECT nr.title, nr.url, nr.publisher, nr.published_at, nr.available_at,
                   s.name AS source
            FROM news_raw nr
            JOIN sources s ON s.source_id = nr.source_id
            ORDER BY nr.available_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_latest_prices(session: Session) -> list[dict]:
    """Последният бар за всяка комбинация (asset, bar_interval), резолвнат между източници."""
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (pr.asset_id, pr.bar_interval)
                   a.symbol, a.display_name, pr.bar_interval, pr.ts, pr.close, pr.source
            FROM prices_resolved pr
            JOIN assets a ON a.asset_id = pr.asset_id
            ORDER BY pr.asset_id, pr.bar_interval, pr.ts DESC
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def get_overview_metrics(session: Session) -> dict:
    """Обобщени числа за целия ingestion поток — първото нещо, което показва
    дали 2-седмичният непрекъснат collection от CLAUDE.md Етап 1 наистина тече.
    """
    row = session.execute(
        text(
            """
            SELECT
                (SELECT count(*) FROM news_raw) AS total_news,
                (SELECT count(*) FROM news_raw WHERE available_at > now() - interval '24 hours') AS news_last_24h,
                (SELECT count(*) FROM prices) AS total_price_bars,
                (SELECT count(*) FROM sources WHERE active) AS active_sources,
                (
                    SELECT count(*)
                    FROM sources s
                    WHERE EXISTS (
                        SELECT 1 FROM ingest_runs ir
                        WHERE ir.source_id = s.source_id
                        ORDER BY ir.started_at DESC
                        LIMIT 1
                    )
                ) AS sources_ever_run,
                (
                    SELECT count(*) FROM (
                        SELECT DISTINCT ON (ir.source_id) ir.status
                        FROM ingest_runs ir
                        ORDER BY ir.source_id, ir.started_at DESC
                    ) latest
                    WHERE latest.status = 'ok'
                ) AS sources_last_run_ok,
                (
                    SELECT count(*) FROM (
                        SELECT DISTINCT ON (ir.source_id) ir.status
                        FROM ingest_runs ir
                        ORDER BY ir.source_id, ir.started_at DESC
                    ) latest
                    WHERE latest.status IN ('failed', 'running')
                ) AS sources_last_run_bad
            """
        )
    ).mappings().first()
    return dict(row) if row else {}


def get_asset_freshness(session: Session) -> list[dict]:
    """Колко назад е последният ценови бар за всеки актив — вижда се веднага
    ако някой asset е спрял да получава данни, без да четеш ingest_runs ред по ред.
    """
    rows = session.execute(
        text(
            """
            SELECT a.symbol, a.class, p.bar_interval,
                   MAX(p.ts) AS latest_ts,
                   EXTRACT(EPOCH FROM (now() - MAX(p.ts))) / 3600.0 AS staleness_hours
            FROM assets a
            LEFT JOIN prices p ON p.asset_id = a.asset_id
            GROUP BY a.symbol, a.class, p.bar_interval
            ORDER BY a.symbol, p.bar_interval
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]
