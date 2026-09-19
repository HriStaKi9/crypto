-- =====================================================================
-- Unified schema: multi-source market + news ingestion
-- PostgreSQL 15+ / TimescaleDB
-- Всички timestamp-и са TIMESTAMPTZ в UTC. Без изключения.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- fuzzy matching на заглавия
CREATE EXTENSION IF NOT EXISTS vector;       -- optional: embedding dedup

-- ---------------------------------------------------------------------
-- 1. РЕГИСТЪР НА АКТИВИ
-- ---------------------------------------------------------------------
CREATE TYPE asset_class AS ENUM (
    'crypto_major',   -- BTC, ETH
    'altcoin',        -- SOL, LINK
    'memecoin',       -- DOGE, SHIB — negative control
    'equity'          -- NVDA, AAPL
);

CREATE TABLE assets (
    asset_id            SERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    class               asset_class NOT NULL,
    display_name        TEXT NOT NULL,
    -- негативен контрол: влиза в анализа, но НЕ в реалното изпълнение
    is_negative_control BOOLEAN NOT NULL DEFAULT FALSE,
    -- кой източник е първичен за цена при конфликт между борси
    primary_price_source INT,
    listed_since        DATE,   -- за survivorship-bias корекция
    delisted_at         DATE,
    UNIQUE (symbol, class)
);

-- Псевдоними за entity linking в текста на новините.
-- Без тази таблица няма как да свържеш "Nvidia beats earnings" с NVDA.
CREATE TABLE asset_aliases (
    alias_id    SERIAL PRIMARY KEY,
    asset_id    INT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    match_type  TEXT NOT NULL CHECK (match_type IN ('exact','cashtag','regex')),
    -- по-ниска тежест за двусмислени псевдоними: "ETH", "Tesla" в нефинансов текст
    confidence  NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    UNIQUE (asset_id, alias)
);
CREATE INDEX idx_alias_trgm ON asset_aliases USING gin (alias gin_trgm_ops);

-- ---------------------------------------------------------------------
-- 2. РЕГИСТЪР НА ИЗТОЧНИЦИ
-- ---------------------------------------------------------------------
CREATE TABLE sources (
    source_id       SERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,      -- gdelt, cryptopanic, binance
    kind            TEXT NOT NULL CHECK (kind IN ('news','price')),
    -- ИЗВЕСТНО закъснение на тира в секунди (NewsAPI free = 86400!)
    -- Backtest-ът задължително добавя това към published_at.
    tier_latency_s  INT NOT NULL DEFAULT 0,
    trust_weight    NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    active          BOOLEAN NOT NULL DEFAULT TRUE
);

ALTER TABLE assets
    ADD CONSTRAINT fk_primary_price_source
    FOREIGN KEY (primary_price_source) REFERENCES sources(source_id);

-- ---------------------------------------------------------------------
-- 3. ЦЕНИ — конкатенация без загуба
-- Една и съща свещ от Binance и CoinGecko се пази ДВА пъти.
-- source_id е част от PK; изборът на "истинската" цена е при четене.
-- ---------------------------------------------------------------------
CREATE TABLE prices (
    asset_id     INT NOT NULL REFERENCES assets(asset_id),
    source_id    INT NOT NULL REFERENCES sources(source_id),
    bar_interval TEXT NOT NULL CHECK (bar_interval IN ('1m','5m','1h','1d')),
    ts           TIMESTAMPTZ NOT NULL,   -- ОТВАРЯНЕ на свещта, UTC
    open         NUMERIC(24,8) NOT NULL,
    high         NUMERIC(24,8) NOT NULL,
    low          NUMERIC(24,8) NOT NULL,
    close        NUMERIC(24,8) NOT NULL,
    volume       NUMERIC(28,8),
    quote_ccy    TEXT NOT NULL DEFAULT 'USD',
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, source_id, bar_interval, ts)
);
SELECT create_hypertable('prices','ts', if_not_exists => TRUE);

-- Изглед с разрешен конфликт: взима primary източника, fallback към
-- най-високия trust_weight ако primary мълчи за този бар.
CREATE VIEW prices_resolved AS
SELECT DISTINCT ON (p.asset_id, p.bar_interval, p.ts)
       p.asset_id, p.bar_interval, p.ts,
       p.open, p.high, p.low, p.close, p.volume, s.name AS source
FROM prices p
JOIN sources s ON s.source_id = p.source_id
JOIN assets  a ON a.asset_id  = p.asset_id
ORDER BY p.asset_id, p.bar_interval, p.ts,
         (p.source_id = a.primary_price_source) DESC,
         s.trust_weight DESC;

-- ---------------------------------------------------------------------
-- 4. НОВИНИ — суров слой, по един ред на източник-статия
-- Нищо не се слива тук. Immutable.
-- ---------------------------------------------------------------------
CREATE TABLE news_raw (
    raw_id        BIGSERIAL PRIMARY KEY,
    source_id     INT NOT NULL REFERENCES sources(source_id),
    source_uid    TEXT NOT NULL,            -- id-то на статията В източника
    url           TEXT,
    url_canonical TEXT,                     -- без utm_*, без fragment, lowercase host
    url_hash      BYTEA,                    -- sha256(url_canonical) — exact dedup
    title         TEXT NOT NULL,
    body          TEXT,
    language      TEXT,
    publisher     TEXT,                     -- reuters.com, coindesk.com

    -- ДВАТА timestamp-а. Това е най-важният ред в схемата.
    published_at  TIMESTAMPTZ NOT NULL,     -- твърди източникът
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- кога ТИ си го видял

    -- Моментът, от който сигналът има право да ползва новината.
    -- Backtest чете САМО това поле. Никога published_at.
    available_at  TIMESTAMPTZ GENERATED ALWAYS AS (
        GREATEST(published_at, ingested_at)
    ) STORED,

    title_simhash BIGINT,                   -- near-dup dedup
    raw_payload   JSONB,                    -- оригиналният отговор, за одит
    UNIQUE (source_id, source_uid)
);
CREATE INDEX idx_news_raw_available ON news_raw (available_at DESC);
CREATE INDEX idx_news_raw_urlhash   ON news_raw (url_hash);
CREATE INDEX idx_news_raw_title_trgm ON news_raw USING gin (title gin_trgm_ops);

-- ---------------------------------------------------------------------
-- 5. СЛЯТ СЛОЙ — една реална новина = едно събитие
-- Тук става конкатенацията между източниците.
-- ---------------------------------------------------------------------
CREATE TABLE news_events (
    event_id           BIGSERIAL PRIMARY KEY,
    canonical_title    TEXT NOT NULL,
    -- най-ранният момент, в който КОЙТО И ДА Е източник ти го е дал
    first_available_at TIMESTAMPTZ NOT NULL,
    cluster_size       INT NOT NULL DEFAULT 1,
    -- брой различни издатели = груба мярка за значимост на новината
    publisher_count    INT NOT NULL DEFAULT 1,
    dedup_method       TEXT,   -- url | simhash | embedding
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_available ON news_events (first_available_at DESC);

CREATE TABLE news_event_members (
    event_id  BIGINT NOT NULL REFERENCES news_events(event_id) ON DELETE CASCADE,
    raw_id    BIGINT NOT NULL REFERENCES news_raw(raw_id) ON DELETE CASCADE,
    is_anchor BOOLEAN NOT NULL DEFAULT FALSE,  -- първият/най-достоверният
    PRIMARY KEY (event_id, raw_id)
);
CREATE UNIQUE INDEX idx_member_raw ON news_event_members (raw_id);

-- ---------------------------------------------------------------------
-- 6. ВРЪЗКА СЪБИТИЕ -> АКТИВ
-- ---------------------------------------------------------------------
CREATE TABLE news_asset_link (
    event_id     BIGINT NOT NULL REFERENCES news_events(event_id) ON DELETE CASCADE,
    asset_id     INT NOT NULL REFERENCES assets(asset_id),
    relevance    NUMERIC(3,2) NOT NULL,   -- 0..1
    match_method TEXT NOT NULL,           -- alias | cashtag | ner | manual
    PRIMARY KEY (event_id, asset_id)
);

-- ---------------------------------------------------------------------
-- 7. SENTIMENT — версионирано, за да сравняваш модели
-- ---------------------------------------------------------------------
CREATE TABLE sentiment_scores (
    event_id      BIGINT NOT NULL REFERENCES news_events(event_id) ON DELETE CASCADE,
    model_name    TEXT NOT NULL,          -- finbert | cryptobert | vader
    model_version TEXT NOT NULL,
    score         NUMERIC(4,3) NOT NULL,  -- -1..+1
    label         TEXT,
    confidence    NUMERIC(4,3),
    scored_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, model_name, model_version)
);

-- ---------------------------------------------------------------------
-- 8. ODIT НА ЗАРЕЖДАНЕТО — без това не знаеш къде има дупки в данните
-- ---------------------------------------------------------------------
CREATE TABLE ingest_runs (
    run_id       BIGSERIAL PRIMARY KEY,
    source_id    INT NOT NULL REFERENCES sources(source_id),
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    window_from  TIMESTAMPTZ,
    window_to    TIMESTAMPTZ,
    rows_fetched INT DEFAULT 0,
    rows_new     INT DEFAULT 0,
    status       TEXT CHECK (status IN ('running','ok','partial','failed')),
    error_text   TEXT
);

-- ---------------------------------------------------------------------
-- 9. POINT-IN-TIME ИЗГЛЕД ЗА BACKTEST
-- Единственият изглед, който signal engine-ът има право да чете.
-- ---------------------------------------------------------------------
CREATE VIEW v_signal_features AS
SELECT
    l.asset_id,
    e.event_id,
    e.first_available_at AS available_at,
    e.publisher_count,
    l.relevance,
    s.model_name,
    s.score,
    s.score * l.relevance * LEAST(e.publisher_count, 5) / 5.0 AS weighted_score
FROM news_events e
JOIN news_asset_link  l ON l.event_id = e.event_id
JOIN sentiment_scores s ON s.event_id = e.event_id;
