-- HostBay REST API Tables
-- Created: 2025-10-31
-- Purpose: API key authentication, rate limiting, and usage tracking

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(128) UNIQUE NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    permissions JSONB DEFAULT '{
        "domains": {"read": true, "write": true},
        "dns": {"read": true, "write": true},
        "nameservers": {"read": true, "write": true},
        "hosting": {"read": true, "write": true},
        "wallet": {"read": true, "write": false},
        "orders": {"read": true, "write": false}
    }'::jsonb,
    rate_limit_per_hour INTEGER DEFAULT 1000,
    rate_limit_per_day INTEGER DEFAULT 10000,
    last_used_at TIMESTAMP,
    ip_whitelist JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    revoked_at TIMESTAMP,
    revoked_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active, expires_at);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);

-- API Usage Logs table
CREATE TABLE IF NOT EXISTS api_usage_logs (
    id SERIAL PRIMARY KEY,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE CASCADE,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    response_time_ms INTEGER,
    request_ip VARCHAR(45),
    user_agent TEXT,
    error_message TEXT,
    request_body_size INTEGER,
    response_body_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_usage_key_time ON api_usage_logs(api_key_id, created_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_endpoint ON api_usage_logs(endpoint, created_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_status ON api_usage_logs(status_code, created_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_created ON api_usage_logs(created_at);

-- Comments for documentation
COMMENT ON TABLE api_keys IS 'API authentication keys with permissions and rate limits';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256 hash of the API key (never store plain text)';
COMMENT ON COLUMN api_keys.key_prefix IS 'First 16 chars of key for display (e.g., hbay_live_Ak7m)';
COMMENT ON COLUMN api_keys.permissions IS 'JSON object defining read/write permissions per resource';
COMMENT ON COLUMN api_keys.ip_whitelist IS 'Array of allowed IP addresses/CIDR ranges (empty = allow all)';

COMMENT ON TABLE api_usage_logs IS 'API request logs for usage tracking and analytics';
COMMENT ON COLUMN api_usage_logs.response_time_ms IS 'Request processing time in milliseconds';
