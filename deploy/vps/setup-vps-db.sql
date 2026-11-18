-- ============================================================================
-- MayorClips — Base de Datos Aislada en PostgreSQL 16 (VPS 166.0.112.247)
-- Totalmente separada de jjpaper_db para proteger el ERP MixNet y JJ Paper.
-- ============================================================================

CREATE DATABASE mayorclips_db;

\c mayorclips_db;

-- Tabla de Cuentas Conectadas (Instagram, Facebook, TikTok, YouTube)
CREATE TABLE IF NOT EXISTS social_accounts (
    id VARCHAR(64) PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,
    account_name VARCHAR(128) NOT NULL,
    account_id VARCHAR(128) NOT NULL,
    access_token_enc TEXT NOT NULL,
    refresh_token_enc TEXT,
    expires_at TIMESTAMPTZ,
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de Publicaciones Programadas
CREATE TABLE IF NOT EXISTS posts (
    id VARCHAR(64) PRIMARY KEY,
    media_id VARCHAR(64) NOT NULL,
    media_type VARCHAR(32) DEFAULT 'clip',
    caption_base TEXT NOT NULL,
    platforms_json JSONB DEFAULT '[]'::jsonb,
    scheduled_for TIMESTAMPTZ,
    status VARCHAR(32) DEFAULT 'draft',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de Estado por Red Social
CREATE TABLE IF NOT EXISTS post_targets (
    id VARCHAR(64) PRIMARY KEY,
    post_id VARCHAR(64) REFERENCES posts(id) ON DELETE CASCADE,
    platform VARCHAR(32) NOT NULL,
    remote_post_id VARCHAR(128),
    status VARCHAR(32) DEFAULT 'pending',
    error_message TEXT,
    direct_url TEXT,
    published_at TIMESTAMPTZ
);

-- Tabla de Métricas y Estadísticas Históricas (Snapshots cada 3h)
CREATE TABLE IF NOT EXISTS post_metrics (
    id VARCHAR(64) PRIMARY KEY,
    post_target_id VARCHAR(64) REFERENCES post_targets(id) ON DELETE CASCADE,
    platform VARCHAR(32) NOT NULL,
    views BIGINT DEFAULT 0,
    likes BIGINT DEFAULT 0,
    comments BIGINT DEFAULT 0,
    shares BIGINT DEFAULT 0,
    watch_time_sec NUMERIC DEFAULT 0.0,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_post_metrics_target ON post_metrics(post_target_id);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
