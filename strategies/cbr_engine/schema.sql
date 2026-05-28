-- ============================================================================
-- AEGIS CBR Engine - PostgreSQL Schema
-- ============================================================================

-- Fingerprints: Her zaman noktasında 50+ feature
CREATE TABLE fingerprints (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,

    -- Price Structure (5)
    current_price FLOAT8,
    distance_from_ath FLOAT8,
    distance_from_200ma FLOAT8,
    atr_14 FLOAT8,
    volatility_regime VARCHAR(20), -- LOW, MID, HIGH

    -- Technical Indicators (7)
    rsi_14 FLOAT8,
    macd_histogram FLOAT8,
    stoch_rsi FLOAT8,
    obv_trend FLOAT8,
    volume_profile INT,
    liquidity_sweep FLOAT8,
    structure_score FLOAT8,

    -- Macro Correlation (4)
    dxy_14d_corr FLOAT8,
    gold_14d_corr FLOAT8,
    brent_14d_corr FLOAT8,
    vix_level FLOAT8,

    -- Sentiment/Fear (2)
    fear_greed_index FLOAT8,
    us_10y_yield FLOAT8,

    -- On-Chain (3)
    exchange_netflow_7d FLOAT8,
    funding_rate_avg FLOAT8,
    open_interest_change FLOAT8,

    -- Temporal (4)
    day_of_week INT,
    hour_of_day INT,
    days_from_halving INT,
    macro_event_window BOOLEAN,

    -- Meta Classification (3)
    market_type VARCHAR(20), -- DIP, PEAK, BREAKOUT, REJECTION
    regime_label VARCHAR(20), -- BULL, BEAR, SIDEWAYS
    quality_score FLOAT8, -- 0.0-1.0

    UNIQUE(symbol, timestamp)
);

-- Forward Returns: Backtest sırasında hesaplanacak (look-ahead bias yok)
CREATE TABLE forward_returns (
    id BIGSERIAL PRIMARY KEY,
    fingerprint_id BIGINT NOT NULL REFERENCES fingerprints(id),
    return_1h FLOAT8,
    return_4h FLOAT8,
    return_24h FLOAT8,
    return_7d FLOAT8,
    max_drawdown_24h FLOAT8,
    UNIQUE(fingerprint_id)
);

-- Case Base: Benzer işlemler ve sonuçları
CREATE TABLE cases (
    id BIGSERIAL PRIMARY KEY,
    fingerprint_id BIGINT NOT NULL REFERENCES fingerprints(id),
    trade_id VARCHAR(50),
    entry_price FLOAT8,
    action VARCHAR(10), -- LONG, SHORT
    reason TEXT,
    result_1h FLOAT8,
    result_24h FLOAT8,
    win BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector Embeddings: Benzerlik araması için
CREATE TABLE embeddings (
    id BIGSERIAL PRIMARY KEY,
    fingerprint_id BIGINT NOT NULL REFERENCES fingerprints(id) UNIQUE,
    embedding FLOAT8[] NOT NULL,
    regime_label VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Optimization Weights: Haftalık güncellenen ağırlıklar
CREATE TABLE optimization_weights (
    id BIGSERIAL PRIMARY KEY,
    week_of DATE,
    price_weight FLOAT8,
    technical_weight FLOAT8,
    macro_weight FLOAT8,
    onchain_weight FLOAT8,
    temporal_weight FLOAT8,
    performance_metric FLOAT8,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_fingerprints_symbol_ts ON fingerprints(symbol, timestamp DESC);
CREATE INDEX idx_fingerprints_regime ON fingerprints(regime_label);
CREATE INDEX idx_fingerprints_market_type ON fingerprints(market_type);
CREATE INDEX idx_cases_fingerprint ON cases(fingerprint_id);
CREATE INDEX idx_cases_result ON cases(result_24h);
CREATE INDEX idx_embeddings_regime ON embeddings(regime_label);
