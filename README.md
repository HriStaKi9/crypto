# Market Signal Engine

Виж [CLAUDE.md](CLAUDE.md) за пълния контекст на проекта, нерушимите
правила (point-in-time, immutable news, без ливъридж) и фиксирания
обхват на активите.

## Статус: Етап 1 (Ingestion + storage) — завършен код, тече валидация

Етап 1 по CLAUDE.md е "само събиране: без модел, без сигнали", с цел
2 седмици непрекъснат поток. Кодовата част е готова; самото 2-седмично
изпълнение тепърва тече (стартирано от датата, на която `docker
compose up` е пуснат за постоянно, не от датата на този commit).

### Какво прави

```
Източници (8 news + 4 price)          ingestion/*.py            PostgreSQL/TimescaleDB
─────────────────────────      ───────────────────────      ──────────────────────────
GDELT DOC 2.0 API          ──▶  gdelt.py                 ──▶
CryptoPanic API            ──▶  cryptopanic.py            ──▶  news_raw
CoinDesk/TheBlock RSS      ──▶  rss_feeds.py              ──▶  (immutable,
MarketWatch/Investing.com/                                     insert-only)
Yahoo Finance RSS          ──▶
                                                                    │
Binance klines REST        ──▶  binance.py                ──▶      │
yfinance (дневни)          ──▶  equities.py               ──▶  prices
Finnhub (интрадей, опц.)   ──▶                             ──▶  (hypertable)

Всеки run се логва в ingest_runs (started_at/status/rows_fetched/
rows_new/error_text) — пълен одит без нужда да четеш логове на ръка.
```

- **Point-in-time е гарантирано от БД, не от дисциплина.** `news_raw.available_at`
  е `GENERATED ALWAYS AS (GREATEST(published_at, ingested_at))` — никой
  Python код не решава кога една новина "става видима", СУБД-то го
  налага структурно (CLAUDE.md, правило 1).
- **Нищо не се трие/update-ва в `news_raw`.** Всеки upsert е `ON
  CONFLICT DO NOTHING` — суровите данни са append-only, дедупът е за
  Етап 2 (`nlp/dedup.py`, отделен слой `news_events`).
- **Цените не се мърджват между източници при запис.** `source_id` е
  част от PK на `prices`; изгледът `prices_resolved` решава коя цена
  печели при четене (primary source, после по `trust_weight`).
- **`ingestion/scheduler.py`** е единствената дълготрайна услуга —
  APScheduler orchestrator, всеки source на реалния си update ритъм
  (GDELT/RSS ~15 мин, CryptoPanic 10 мин, крипто цени на час, акции
  дневно). Първо изпълнение е веднага при старт, не след цял interval.
- **`api/main.py`** е read-only monitoring dashboard (не Stage 4
  сигнал API-то от CLAUDE.md) — `http://localhost:8000`, auto-refresh
  30 сек: overview метрики, freshness по актив, пълен `ingest_runs`
  статус, последни цени/новини. Виж таблицата с контейнери по-долу.

### Известни ограничения

- **Reuters няма работещ публичен RSS** (проверено на живо — 401/404
  на всеки известен път). Редът е в `sources` с `active=FALSE`, кодът
  не го тегли. Ако намериш работещ feed, виж коментара в
  `ingestion/rss_feeds.py`.
- **GDELT rate-limit-ва агресивно** при чести заявки от един IP — кодът
  го третира като нормален отказ (per-asset try/except, run-ът пак
  завършва `ok`), не е бъг, но означава непълно покритие в отделни цикли.
- Bulk backfill (`equities.py --backfill`, десетки хиляди редове) е
  бавен — insert ред-по-ред, не bulk. Без значение за нормалния
  инкрементален синхрон, само за еднократен пълен исторически import.

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
