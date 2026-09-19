"""Ingestion на цени за акции — yfinance (дневни) + Finnhub (интрадей).

Ядрото по CLAUDE.md е само NVDA и AAPL. yfinance дневните бар-ове
покриват backtest нуждите за Етап 3; Finnhub интрадей е опционален
(изисква FINNHUB_API_KEY) и не е част от подразбиращия се scheduler
цикъл в Етап 1 — извиква се изрично при нужда от по-фина гранулярност.
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
import yfinance as yf

from db.session import get_session
from ingestion.common import finish_run, get_asset_id, get_source_id, start_run, upsert_prices

logger = logging.getLogger(__name__)

YFINANCE_SOURCE = "yfinance"
FINNHUB_SOURCE = "finnhub"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
REQUEST_TIMEOUT_S = 15

# CLAUDE.md: акциите в обхвата са само ядрото — NVDA, AAPL.
EQUITY_SYMBOLS = ["NVDA", "AAPL"]


def _row_to_bar(index_ts, row) -> dict:
    ts = index_ts.to_pydatetime()
    ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    volume = float(row["Volume"]) if row["Volume"] == row["Volume"] else None  # NaN guard
    return {
        "ts": ts,
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
        "volume": volume,
        "quote_ccy": "USD",
    }


def sync_symbol_daily(symbol: str, period: str = "1mo") -> tuple[int, int]:
    with get_session() as session:
        asset_id = get_asset_id(session, symbol)
        source_id = get_source_id(session, YFINANCE_SOURCE)
        run_id = start_run(session, source_id)
        total_fetched = 0
        total_new = 0
        try:
            history = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
            bars = [_row_to_bar(idx, row) for idx, row in history.iterrows()]
            total_fetched = len(bars)
            total_new = upsert_prices(session, asset_id, source_id, "1d", bars)
        except Exception as exc:
            finish_run(session, run_id, total_fetched, total_new, status="failed", error_text=str(exc))
            raise
        else:
            finish_run(session, run_id, total_fetched, total_new, status="ok")
        return total_fetched, total_new


def sync_symbol_intraday(symbol: str, lookback_hours: int = 24) -> tuple[int, int]:
    """Finnhub интрадей (резолюция 60 мин). Изисква FINNHUB_API_KEY."""
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        logger.warning("FINNHUB_API_KEY не е зададен — пропускам интрадей за %s", symbol)
        return 0, 0

    now = datetime.now(timezone.utc)
    frm = now - timedelta(hours=lookback_hours)
    with get_session() as session:
        asset_id = get_asset_id(session, symbol)
        source_id = get_source_id(session, FINNHUB_SOURCE)
        run_id = start_run(session, source_id, window_from=frm, window_to=now)
        total_fetched = 0
        total_new = 0
        try:
            resp = requests.get(
                f"{FINNHUB_BASE_URL}/stock/candle",
                params={
                    "symbol": symbol,
                    "resolution": "60",
                    "from": int(frm.timestamp()),
                    "to": int(now.timestamp()),
                    "token": api_key,
                },
                timeout=REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            payload = resp.json()
            bars = []
            if payload.get("s") == "ok":
                for t, o, h, l, c, v in zip(
                    payload["t"], payload["o"], payload["h"], payload["l"], payload["c"], payload["v"]
                ):
                    bars.append(
                        {
                            "ts": datetime.fromtimestamp(t, tz=timezone.utc),
                            "open": float(o),
                            "high": float(h),
                            "low": float(l),
                            "close": float(c),
                            "volume": float(v),
                            "quote_ccy": "USD",
                        }
                    )
            total_fetched = len(bars)
            total_new = upsert_prices(session, asset_id, source_id, "1h", bars)
        except Exception as exc:
            finish_run(session, run_id, total_fetched, total_new, status="failed", error_text=str(exc))
            raise
        else:
            finish_run(session, run_id, total_fetched, total_new, status="ok")
        return total_fetched, total_new


def run_once(period: str = "1mo") -> None:
    for symbol in EQUITY_SYMBOLS:
        try:
            fetched, new = sync_symbol_daily(symbol, period=period)
            logger.info("yfinance %s: %d бара, %d нови", symbol, fetched, new)
        except Exception as exc:
            logger.error("yfinance се провали за %s: %s", symbol, exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingestion на цени за акции (NVDA, AAPL)")
    parser.add_argument("--backfill", action="store_true", help="Пълен исторически backfill (period=max) вместо инкрементален (1mo)")
    parser.add_argument("--intraday", action="store_true", help="Ползвай Finnhub интрадей вместо yfinance дневни")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.intraday:
        for sym in EQUITY_SYMBOLS:
            sync_symbol_intraday(sym)
    else:
        run_once(period="max" if args.backfill else "1mo")
