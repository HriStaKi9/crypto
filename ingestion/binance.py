"""Binance public REST ingestion — крипто цени (OHLCV).

Без auth. Пише в `prices` с `source_id` за 'binance'. Не мърджва
редове от други източници — конфликтът се разрешава при четене през
`prices_resolved`.
"""
