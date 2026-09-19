-- =====================================================================
-- Seed данни: sources, assets, asset_aliases
-- Съответства на db/schema.sql. Изпълнява се СЛЕД схемата.
-- Фиксиран обхват — виж CLAUDE.md: ядро / втори кръг / негативен контрол.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. SOURCES
-- tier_latency_s: реално известно закъснение на тира, за да може
-- backtest-ът да го добави към published_at. NewsAPI/NewsData.io
-- умишлено не се ползват (виж CLAUDE.md) — няма ред за тях тук.
-- ---------------------------------------------------------------------
INSERT INTO sources (name, kind, tier_latency_s, trust_weight, active) VALUES
    ('gdelt',            'news',  900, 0.90, TRUE),  -- 15-мин ъпдейт цикъл
    ('cryptopanic',      'news',    0, 0.85, TRUE),
    ('rss_coindesk',     'news',    0, 0.90, TRUE),
    ('rss_theblock',     'news',    0, 0.90, TRUE),
    ('binance',          'price',   0, 1.00, TRUE),
    ('coingecko',        'price',   0, 0.90, TRUE),
    ('yfinance',         'price',   0, 1.00, TRUE),
    ('finnhub',          'price',   0, 0.90, TRUE)
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------
-- 2. ASSETS
-- Ядро: BTC, ETH, NVDA, AAPL. Втори кръг: SOL, LINK. Негативен
-- контрол (никога реални пари): DOGE, SHIB.
-- listed_since = начало на надежден ценови ред за актива; delisted_at
-- е NULL за всички — нищо в обхвата не е делистнато към момента.
-- ---------------------------------------------------------------------
INSERT INTO assets (symbol, class, display_name, is_negative_control, primary_price_source, listed_since, delisted_at) VALUES
    ('BTC',  'crypto_major', 'Bitcoin',   FALSE, (SELECT source_id FROM sources WHERE name = 'binance'),  '2010-07-18', NULL),
    ('ETH',  'crypto_major', 'Ethereum',  FALSE, (SELECT source_id FROM sources WHERE name = 'binance'),  '2015-08-07', NULL),
    ('SOL',  'altcoin',      'Solana',    FALSE, (SELECT source_id FROM sources WHERE name = 'binance'),  '2020-04-10', NULL),
    ('LINK', 'altcoin',      'Chainlink', FALSE, (SELECT source_id FROM sources WHERE name = 'binance'),  '2017-09-19', NULL),
    ('DOGE', 'memecoin',     'Dogecoin',  TRUE,  (SELECT source_id FROM sources WHERE name = 'binance'),  '2013-12-06', NULL),
    ('SHIB', 'memecoin',     'Shiba Inu', TRUE,  (SELECT source_id FROM sources WHERE name = 'binance'),  '2020-08-01', NULL),
    ('NVDA', 'equity',       'NVIDIA',    FALSE, (SELECT source_id FROM sources WHERE name = 'yfinance'), '1999-01-22', NULL),
    ('AAPL', 'equity',       'Apple',     FALSE, (SELECT source_id FROM sources WHERE name = 'yfinance'), '1980-12-12', NULL)
ON CONFLICT (symbol, class) DO NOTHING;

-- ---------------------------------------------------------------------
-- 3. ASSET_ALIASES
-- confidence < 1.00 за псевдоними, които са двусмислени извън
-- финансов контекст ("Link" е обикновена дума, "Apple" е и плод).
-- Cashtag-овете са еднозначни -> confidence 1.00.
-- ---------------------------------------------------------------------

-- BTC
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'BTC'), 'Bitcoin', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'BTC'), 'BTC',     'exact',   0.95),
    ((SELECT asset_id FROM assets WHERE symbol = 'BTC'), '$BTC',    'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

-- ETH
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'ETH'), 'Ethereum', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'ETH'), 'Ether',    'exact',   0.95),
    ((SELECT asset_id FROM assets WHERE symbol = 'ETH'), 'ETH',      'exact',   0.90),
    ((SELECT asset_id FROM assets WHERE symbol = 'ETH'), '$ETH',     'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

-- SOL
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'SOL'), 'Solana', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'SOL'), 'SOL',    'exact',   0.60),  -- "sol" = двусмислена дума в текст
    ((SELECT asset_id FROM assets WHERE symbol = 'SOL'), '$SOL',   'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

-- LINK
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'LINK'), 'Chainlink', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'LINK'), 'LINK',      'exact',   0.50),  -- обикновена дума, ниска тежест
    ((SELECT asset_id FROM assets WHERE symbol = 'LINK'), '$LINK',     'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

-- DOGE (негативен контрол)
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'DOGE'), 'Dogecoin', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'DOGE'), 'DOGE',     'exact',   0.90),
    ((SELECT asset_id FROM assets WHERE symbol = 'DOGE'), '$DOGE',    'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

-- SHIB (негативен контрол)
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'SHIB'), 'Shiba Inu', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'SHIB'), 'SHIB',      'exact',   0.90),
    ((SELECT asset_id FROM assets WHERE symbol = 'SHIB'), '$SHIB',     'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

-- NVDA
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'NVDA'), 'Nvidia', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'NVDA'), 'NVDA',   'exact',   0.95),
    ((SELECT asset_id FROM assets WHERE symbol = 'NVDA'), '$NVDA',  'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

-- AAPL
INSERT INTO asset_aliases (asset_id, alias, match_type, confidence) VALUES
    ((SELECT asset_id FROM assets WHERE symbol = 'AAPL'), 'Apple Inc', 'exact',   1.00),
    ((SELECT asset_id FROM assets WHERE symbol = 'AAPL'), 'Apple',     'exact',   0.55),  -- двусмислено (плод)
    ((SELECT asset_id FROM assets WHERE symbol = 'AAPL'), 'AAPL',      'exact',   0.95),
    ((SELECT asset_id FROM assets WHERE symbol = 'AAPL'), '$AAPL',     'cashtag', 1.00)
ON CONFLICT (asset_id, alias) DO NOTHING;

COMMIT;
