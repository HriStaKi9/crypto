# Market Signal Engine

Виж [CLAUDE.md](CLAUDE.md) за пълния контекст на проекта, нерушимите
правила (point-in-time, immutable news, без ливъридж) и фиксирания
обхват на активите.

## Пускане локално

```bash
cp .env.example .env
# редактирай .env — задължително смени POSTGRES_PASSWORD;
# CRYPTOPANIC_API_KEY / FINNHUB_API_KEY са опционални (без тях
# съответните части просто се прескачат с warning)

docker compose up -d --build
```

Това вдига 4 контейнера:

| Контейнер | Порт | Какво прави |
|---|---|---|
| `mse_db` | 5432 | PostgreSQL 16 + TimescaleDB + pgvector, авто-прилага `db/schema.sql` + `db/seeds.sql` при първо стартиране |
| `mse_adminer` | 8081 | GUI за директно разглеждане на таблиците |
| `mse_api` | 8000 | **Ingestion monitoring dashboard** — `http://localhost:8000` |
| `mse_ingestion` | — | `ingestion/scheduler.py`, тегли от GDELT/RSS/CryptoPanic/Binance/yfinance на техния реален update ритъм |

Отвори **http://localhost:8000** — обновява се сам на 30 сек, показва:
overview метрики (общо новини/цени, колко sources са последно `ok`),
freshness по актив (кога е последният бар, оцветено зелено/жълто/
червено), пълен `ingest_runs` статус, последни цени и новини.

Adminer (http://localhost:8081) — System: PostgreSQL, Server: `db`,
credentials от `.env`.

## Спиране / чистене

```bash
docker compose down        # спира, пази данните (volume)
docker compose down -v     # спира И трие всички данни
```

## Локална разработка без Docker за api/ingestion

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-runtime.txt   # леко, само за api/ingestion
# или requirements.txt за пълния стек (Sentiment/backtest, Етап 2-3+)

export DATABASE_URL="postgresql+psycopg://mse:<парола>@localhost:5432/market_signal_engine"
uvicorn api.main:app --reload           # dashboard на localhost:8000
python -m ingestion.scheduler           # непрекъснат ingestion във foreground
```

Всеки ingestion модул може да се пусне и еднократно за дебъг:
`python -m ingestion.binance`, `python -m ingestion.equities --backfill`, и т.н.

## Тестове

```bash
pip install pytest
pytest tests/
```
