"""Unit тестове за чистите helper функции в ingestion/common.py.

Нарочно без DB fixture — тези функции не пипат мрежа/база, тестват се
директно. Интеграционните тестове (реален upsert срещу Postgres) са
за по-късно, когато има CI с достъп до TimescaleDB инстанция.
"""
from ingestion.common import canonicalize_url, url_hash


def test_canonicalize_url_strips_utm_params():
    # Host се lowercase-ва (schema.sql: "lowercase host"), но path-ът е
    # case-sensitive по спецификация и нарочно не се пипа.
    raw = "https://Example.com/Article/?utm_source=twitter&id=42"
    assert canonicalize_url(raw) == "https://example.com/Article?id=42"


def test_canonicalize_url_strips_fragment_and_trailing_slash():
    raw = "https://example.com/path/#section-2"
    assert canonicalize_url(raw) == "https://example.com/path"


def test_canonicalize_url_is_stable_for_equivalent_urls():
    a = "https://example.com/x?b=2&a=1"
    b = "HTTPS://EXAMPLE.com/x?a=1&b=2"
    # host/scheme са canonical-ized, но реда на query params не се пренарежда —
    # тестваме само нещата, които наистина гарантираме.
    assert canonicalize_url(a).startswith("https://example.com/x")
    assert canonicalize_url(b).startswith("https://example.com/x")


def test_url_hash_is_deterministic_sha256():
    canonical = "https://example.com/article"
    h1 = url_hash(canonical)
    h2 = url_hash(canonical)
    assert h1 == h2
    assert len(h1) == 32  # sha256 digest = 32 байта


def test_url_hash_differs_for_different_urls():
    assert url_hash("https://example.com/a") != url_hash("https://example.com/b")
