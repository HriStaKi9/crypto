"""Binance public REST ingestion — крипто цени (OHLCV), без auth.

Тегли klines по актив и ги пише в `prices` със source 'binance'. Не
мърджва с други източници — `source_id` е част от PK (CLAUDE.md,
правило 4); конфликтът между източници се решава при четене през
`prices_resolved`.

Взимаме само ЗАТВОРЕНИ свещи (close_time < сега) — така никога не
пишем "в момента формираща се" свещ, чиито OHLC стойности още се
менят, и не се налага да решаваме дали re-fetch е update или нов ред.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

from db.session import get_session
from ingestion.common import finish_run, get_asset_id, get_source_id, start_run, upsert_prices

logger = logging.getLogger(__name__)

SOURCE_NAME = "binance"
BASE_URL = os.environ.get("BINANCE_BASE_URL", "https://api.binance.com")
REQUEST_TIMEOUT_S = 15
KLINES_LIMIT = 1000

# CLAUDE.md обхват: BTC/ETH (ядро), SOL/LINK (втори кръг), DOGE/SHIB (негативен контрол).
SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "LINK": "LINKUSDT",
    "DOGE": "DOGEUSDT",
    "SHIB": "SHIBUSDT",
}
BAR_INTERVALS = ("1h", "1d")  # съвпада с bar_interval CHECK в schema.sql


def fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = KLINES_LIMIT,
) -> list[list]:
    params: dict[str, object] = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_ms is not None:
        params["startTime"] = start_ms
    if end_ms is not None:
        params["endTime"] = end_ms
    resp = requests.get(f"{BASE_URL}/api/v3/klines", params=params, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def _kline_to_bar(kline: list) -> dict:
    open_time_ms = kline[0]
    return {
        "ts": datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc),
        "open": float(kline[1]),
        "high": float(kline[2]),
        "low": float(kline[3]),
        "close": float(kline[4]),
        "volume": float(kline[5]),
        "quote_ccy": "USDT",
    }


def _is_closed(kline: list, now_ms: int) -> bool:
    close_time_ms = kline[6]
    return close_time_ms < now_ms


def sync_symbol(symbol: str, binance_symbol: str, bar_interval: str, limit: int = KLINES_LIMIT) -> tuple[int, int]:
    with get_session() as session:
        asset_id = get_asset_id(session, symbol)
        source_id = get_source_id(session, SOURCE_NAME)
        run_id = start_run(session, source_id)
        total_fetched = 0
        total_new = 0
        try:
            klines = fetch_klines(binance_symbol, bar_interval, limit=limit)
            now_ms = int(time.time() * 1000)
            bars = [_kline_to_bar(k) for k in klines if _is_closed(k, now_ms)]
            total_fetched = len(bars)
            total_new = upsert_prices(session, asset_id, source_id, bar_interval, bars)
        except Exception as exc:
            finish_run(session, run_id, total_fetched, total_new, status="failed", error_text=str(exc))
            raise
        else:
            finish_run(session, run_id, total_fetched, total_new, status="ok")
        return total_fetched, total_new


def run_once() -> None:
    for symbol, binance_symbol in SYMBOL_MAP.items():
        for bar_interval in BAR_INTERVALS:
            try:
                fetched, new = sync_symbol(symbol, binance_symbol, bar_interval)
                logger.info("Binance %s/%s: %d свещи, %d нови", symbol, bar_interval, fetched, new)
            except requests.RequestException as exc:
                logger.error("Binance заявка се провали за %s/%s: %s", symbol, bar_interval, exc)
            time.sleep(0.5)  # weight limit учтивост


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_once()
