# Market Signal Engine — университетски проект

## Какво е това
Web-based **decision-support** система: претегля новинарски поток срещу ценови
данни и генерира сигнал (buy / hold / sell) с увереност и обяснение.

НЕ е финансов съветник и не се позиционира като такъв — нито в кода, нито в UI,
нито в текста на работата. Изходът е сигнал + confidence + причините зад него.

## Обхват (фиксиран — не се разширява без причина)

| Група | Активи | Реални пари |
|---|---|---|
| Ядро | BTC, ETH, NVDA, AAPL | да, ако изобщо |
| Втори кръг | SOL, LINK | не |
| Негативен контрол | DOGE, SHIB | **никога** |

Мемекойните са в проекта, за да се **покаже**, че предсказателната сила пада до
нивото на случайността при тях. Това е резултат, не провал.

## Нерушими правила

1. **Point-in-time.** Signal engine чете САМО `available_at`, никога
   `published_at`. `available_at` е генерирана колона в базата, за да е
   невъзможно да се заобиколи. Всяко нарушение = look-ahead bias = проектът
   пада на защитата.
2. **Всички timestamp-и са TIMESTAMPTZ в UTC.** Без локални зони никъде.
3. **Суровите данни са immutable.** `news_raw` не се UPDATE-ва и не се трие.
   Дедупът е отделен слой (`news_events`), за да може да се преизчислява.
4. **Цените не се сливат при запис.** `source_id` е част от PK. Конфликтът се
   решава при четене чрез `prices_resolved`.
5. **Survivorship bias.** `listed_since` / `delisted_at` се попълват съвестно,
   особено за мемекойните. Иначе backtest-ът тихо лъже.
6. **Няма ливъридж, няма фючърси.** Никъде, при никакви обстоятелства.

## Източници на данни

| Слой | Източник | Бележка |
|---|---|---|
| Новини (гръбнак) | GDELT 2.0 | без auth, безплатен, архив от 2015, 15-мин ъпдейт |
| Крипто новини | CryptoPanic, RSS (CoinDesk, The Block) | |
| Цени крипто | Binance public REST, CoinGecko | |
| Цени акции | yfinance (дневни), Finnhub (интрадей) | |
| Sentiment | FinBERT / CryptoBERT, локално | не харчи API кредити |

**Избягвай:** NewsAPI free (100 заявки/ден, 24ч закъснение, само 1 месец назад)
и NewsData.io free (12ч закъснение, 200 кредита/ден). Неизползваеми и за
backtest, и за реално време.

Ако все пак се ползва източник със закъснение — `sources.tier_latency_s` трябва
да се попълни и backtest-ът го добавя към `published_at`.

## Етапи

- [ ] **1. Ingestion + storage.** Само събиране. Цел: 2 седмици непрекъснат
      поток. Без модел, без сигнали.
- [ ] **2. Sentiment pipeline.** FinBERT върху заглавия → `sentiment_scores`.
- [ ] **3. Signal engine + backtest** срещу buy-and-hold baseline.
- [ ] **4. FastAPI + frontend.**
- [ ] **5. Forward test** (paper, заключен commit + timestamp).
- [ ] **6.** Евентуално реално изпълнение — само ядро, само като execution test.

## Валидация — как се доказва, че работи

Реалните пари НЕ доказват нищо. При 10–30 сделки случайността обяснява всичко;
за да отличиш 55% win rate от 50% трябват стотици сделки.

Доказателството е:
- **Backtest** срещу buy-and-hold, strict point-in-time.
- **Forward test**: моделът се заключва с git commit + timestamp, после всеки
  сигнал се записва в реално време без пипане на логиката. Това е чист
  out-of-sample резултат и е по-силно от реални пари.
- **Метрики**: Sharpe ratio, max drawdown, hit rate, profit factor.
  Не „спечелих X лева“.

Ако се ползват реални пари, те се описват като **execution test** — проверка на
spread, slippage, такси и изпълнимост — не като валидация на предсказателна сила.
Фиксиран размер на позицията за всички сделки, иначе сигналите не са сравними.
Логва се: timestamp, сигнал, цена на изпълнение, такси, slippage.

## Стек

- Python 3.11+, FastAPI, SQLAlchemy, APScheduler
- PostgreSQL 15+ с TimescaleDB
- HuggingFace transformers (FinBERT / CryptoBERT)
- vectorbt или backtrader за backtest
- Frontend: React / Next.js

## Структура

```
.
├── CLAUDE.md
├── db/
│   ├── schema.sql
│   └── seeds/           # assets, sources, asset_aliases
├── ingestion/
│   ├── gdelt.py
│   ├── cryptopanic.py
│   ├── binance.py
│   └── equities.py
├── nlp/
│   ├── dedup.py         # url_hash → simhash → embedding
│   ├── entity_link.py   # alias matching → news_asset_link
│   └── sentiment.py
├── signals/
│   ├── technical.py     # RSI, MACD, MA crossover, volume
│   └── engine.py        # композитен сигнал -2..+2
├── backtest/
├── api/
├── web/
└── tests/
```

## Стил на работа

Директно и конкретно. Итеративно уточняване вместо дълги обяснения.
Български или английски според контекста.
