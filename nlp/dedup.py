"""Дедуп слой: news_raw -> news_events.

Йерархия на матчинг: url_hash (exact) -> simhash (near-dup заглавия)
-> embedding (семантичен дубликат). Резултатът се пише в
`news_events` / `news_event_members`, `news_raw` остава недокоснат.
"""
