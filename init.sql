-- ============================================================
-- INIT SQL: Setup PostgreSQL + TimescaleDB untuk Ping Exporter
-- ============================================================
-- Jalanin ini sebagai superuser (postgres):
--   psql -U postgres -f init.sql
-- ============================================================

-- 1. Buat database (kalau belum ada)
SELECT 'CREATE DATABASE ping_metrics'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ping_metrics')\gexec

-- 2. Install TimescaleDB extension di database
\c ping_metrics;
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 3. Buat user khusus (ganti password sesuai .env)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pinguser') THEN
        CREATE USER pinguser WITH PASSWORD 'pingpassword123';
    END IF;
END
$$;

-- 4. Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ping_metrics TO pinguser;

-- 5. Tabel utama untuk ping metrics
CREATE TABLE IF NOT EXISTS ping_metrics (
    time TIMESTAMPTZ NOT NULL,
    target INET NOT NULL,
    worker TEXT NOT NULL,
    status TEXT NOT NULL,           -- 'up' atau 'down'
    rtt_ms DOUBLE PRECISION,        -- NULL kalau down
    packet_loss_percent DOUBLE PRECISION DEFAULT 0,
    sequence_num INTEGER
);

-- 6. Convert ke hypertable (partition by time)
SELECT create_hypertable('ping_metrics', 'time', if_not_exists => TRUE);

-- 7. Index untuk query cepat
CREATE INDEX IF NOT EXISTS idx_ping_target_time ON ping_metrics (target, time DESC);
CREATE INDEX IF NOT EXISTS idx_ping_worker_time ON ping_metrics (worker, time DESC);
CREATE INDEX IF NOT EXISTS idx_ping_status_time ON ping_metrics (status, time DESC);

-- 8. Grant table privileges
GRANT ALL ON ping_metrics TO pinguser;

-- ============================================================
-- VIEWS UNTUK REPORTING
-- ============================================================

-- View: Latest status per target (real-time monitoring)
CREATE OR REPLACE VIEW v_ping_latest AS
SELECT DISTINCT ON (target)
    target,
    worker,
    status,
    rtt_ms,
    packet_loss_percent,
    time AS last_seen
FROM ping_metrics
ORDER BY target, time DESC;

GRANT ALL ON v_ping_latest TO pinguser;

-- View: Uptime percentage per target (last 24h)
CREATE OR REPLACE VIEW v_ping_uptime_24h AS
SELECT 
    target,
    worker,
    COUNT(*) FILTER (WHERE status = 'up')::float / NULLIF(COUNT(*), 0)::float * 100 AS uptime_percent,
    AVG(rtt_ms) AS avg_rtt_ms,
    MIN(rtt_ms) AS min_rtt_ms,
    MAX(rtt_ms) AS max_rtt_ms,
    COUNT(*) AS total_pings,
    COUNT(*) FILTER (WHERE status = 'down') AS failed_pings
FROM ping_metrics
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY target, worker;

GRANT ALL ON v_ping_uptime_24h TO pinguser;

-- View: Worker performance summary
CREATE OR REPLACE VIEW v_worker_stats AS
SELECT 
    worker,
    COUNT(*) AS total_pings,
    COUNT(*) FILTER (WHERE status = 'down') AS down_count,
    AVG(rtt_ms) AS avg_rtt,
    MIN(time) AS first_ping,
    MAX(time) AS last_ping
FROM ping_metrics
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY worker;

GRANT ALL ON v_worker_stats TO pinguser;

-- ============================================================
-- RETENTION POLICY (Opsional - auto hapus data lama)
-- ============================================================
-- Hapus data lebih dari 30 hari
SELECT add_retention_policy('ping_metrics', INTERVAL '30 days', if_not_exists => TRUE);
