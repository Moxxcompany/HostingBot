-- =============================================================================
-- WEBHOOK HEALTH MONITORING SCHEMA
-- =============================================================================
-- 
-- This schema implements comprehensive webhook health monitoring for payment
-- system reliability. It tracks webhook delivery success/failure rates,
-- detects missing confirmations, and provides metrics for provider health.
--
-- Created: September 2025
-- Purpose: Webhook health monitoring and alert system
--

-- =============================================================================
-- 1. WEBHOOK DELIVERY TRACKING
-- =============================================================================

-- Track all webhook delivery attempts and their outcomes
CREATE TABLE webhook_delivery_logs (
    id SERIAL PRIMARY KEY,
    payment_intent_id INTEGER REFERENCES payment_intents(id),
    provider VARCHAR(50) NOT NULL, -- 'dynopay', 'blockbee'
    webhook_type VARCHAR(50) NOT NULL, -- 'payment_status', 'confirmation', 'callback'
    
    -- Request details
    request_id VARCHAR(255), -- Provider's webhook/callback ID
    expected_at TIMESTAMP, -- When webhook was expected based on payment timeline
    received_at TIMESTAMP, -- When webhook was actually received
    
    -- Processing details
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    processing_duration_ms INTEGER,
    
    -- Outcome tracking
    delivery_status VARCHAR(50) NOT NULL, -- 'received', 'failed', 'timeout', 'invalid', 'duplicate'
    processing_status VARCHAR(50) NOT NULL, -- 'success', 'failed', 'partial', 'skipped'
    http_status_code INTEGER,
    
    -- Error and retry tracking
    error_type VARCHAR(100), -- 'security_failed', 'parsing_error', 'business_logic_error'
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP,
    
    -- Security and validation
    security_validation_passed BOOLEAN DEFAULT FALSE,
    signature_valid BOOLEAN,
    timestamp_valid BOOLEAN,
    rate_limit_exceeded BOOLEAN DEFAULT FALSE,
    
    -- Payload information
    payload_size_bytes INTEGER,
    payload_hash VARCHAR(64), -- SHA-256 hash for deduplication
    raw_payload JSONB, -- Store full payload for debugging
    
    -- Business impact
    payment_confirmed BOOLEAN DEFAULT FALSE,
    wallet_credited BOOLEAN DEFAULT FALSE,
    user_notified BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 2. PROVIDER HEALTH METRICS
-- =============================================================================

-- Aggregate health metrics per provider with time-based buckets
CREATE TABLE webhook_provider_health (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    metric_window_start TIMESTAMP NOT NULL,
    metric_window_end TIMESTAMP NOT NULL,
    window_duration_minutes INTEGER NOT NULL, -- 5, 15, 60, 1440 (day)
    
    -- Delivery metrics
    total_expected_webhooks INTEGER DEFAULT 0,
    total_received_webhooks INTEGER DEFAULT 0,
    total_successful_webhooks INTEGER DEFAULT 0,
    total_failed_webhooks INTEGER DEFAULT 0,
    total_duplicate_webhooks INTEGER DEFAULT 0,
    
    -- Performance metrics
    avg_delivery_delay_seconds DECIMAL(10,3), -- Average delay from expected to received
    avg_processing_time_ms DECIMAL(10,3),
    min_processing_time_ms INTEGER,
    max_processing_time_ms INTEGER,
    p95_processing_time_ms INTEGER, -- 95th percentile
    
    -- Success rates (calculated fields)
    delivery_success_rate DECIMAL(5,4), -- 0.0000 to 1.0000 (percentage as decimal)
    processing_success_rate DECIMAL(5,4),
    security_pass_rate DECIMAL(5,4),
    
    -- Error tracking
    security_failures INTEGER DEFAULT 0,
    parsing_errors INTEGER DEFAULT 0,
    business_logic_errors INTEGER DEFAULT 0,
    timeout_errors INTEGER DEFAULT 0,
    rate_limit_hits INTEGER DEFAULT 0,
    
    -- Calculated health score (0-100)
    health_score DECIMAL(5,2),
    health_status VARCHAR(20), -- 'healthy', 'degraded', 'critical', 'down'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(provider, metric_window_start, window_duration_minutes)
);

-- =============================================================================
-- 3. MISSING CONFIRMATION DETECTION
-- =============================================================================

-- Track payment intents that may be missing webhook confirmations
CREATE TABLE missing_confirmation_alerts (
    id SERIAL PRIMARY KEY,
    payment_intent_id INTEGER REFERENCES payment_intents(id),
    provider VARCHAR(50) NOT NULL,
    
    -- Detection details
    detection_type VARCHAR(50) NOT NULL, -- 'timeout', 'pattern_anomaly', 'manual_check'
    detected_at TIMESTAMP NOT NULL,
    expected_confirmation_by TIMESTAMP,
    time_overdue_minutes INTEGER,
    
    -- Payment details snapshot
    payment_status VARCHAR(50),
    payment_amount DECIMAL(12,2),
    payment_currency VARCHAR(10),
    crypto_currency VARCHAR(10),
    payment_address VARCHAR(255),
    order_id VARCHAR(255),
    
    -- Detection context
    last_webhook_received_at TIMESTAMP,
    total_webhooks_received INTEGER DEFAULT 0,
    payment_created_at TIMESTAMP,
    payment_expires_at TIMESTAMP,
    
    -- Recovery tracking
    recovery_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'recovered', 'failed', 'manual'
    recovery_attempted_at TIMESTAMP,
    recovery_method VARCHAR(50), -- 'api_poll', 'manual_check', 'provider_query'
    recovery_result TEXT,
    
    -- Alert management
    alert_sent BOOLEAN DEFAULT FALSE,
    alert_sent_at TIMESTAMP,
    alert_level VARCHAR(20), -- 'warning', 'error', 'critical'
    escalation_level INTEGER DEFAULT 0,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP,
    
    -- Resolution tracking
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 4. WEBHOOK HEALTH EVENTS
-- =============================================================================

-- Log significant health events for alerting and analysis
CREATE TABLE webhook_health_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL, -- 'threshold_breach', 'provider_down', 'recovery', 'anomaly'
    severity VARCHAR(20) NOT NULL, -- 'info', 'warning', 'error', 'critical'
    provider VARCHAR(50),
    
    -- Event details
    event_title VARCHAR(255) NOT NULL,
    event_description TEXT,
    event_context JSONB, -- Structured data about the event
    
    -- Metrics snapshot
    current_health_score DECIMAL(5,2),
    current_success_rate DECIMAL(5,4),
    affected_payments_count INTEGER DEFAULT 0,
    
    -- Threshold information
    threshold_type VARCHAR(50), -- 'success_rate', 'response_time', 'missing_confirmations'
    threshold_value DECIMAL(10,4),
    actual_value DECIMAL(10,4),
    
    -- Alert management
    alert_sent BOOLEAN DEFAULT FALSE,
    alert_sent_at TIMESTAMP,
    alert_fingerprint VARCHAR(32), -- For deduplication
    
    -- Resolution tracking
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    auto_resolved BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 5. WEBHOOK MONITORING CONFIGURATION
-- =============================================================================

-- Configuration table for monitoring thresholds and settings
CREATE TABLE webhook_monitoring_config (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    
    -- Threshold settings
    min_success_rate_threshold DECIMAL(5,4) DEFAULT 0.9500, -- 95%
    max_avg_processing_time_ms INTEGER DEFAULT 5000, -- 5 seconds
    max_delivery_delay_seconds INTEGER DEFAULT 300, -- 5 minutes
    missing_confirmation_timeout_minutes INTEGER DEFAULT 30,
    
    -- Alert settings
    alert_on_threshold_breach BOOLEAN DEFAULT TRUE,
    alert_cooldown_minutes INTEGER DEFAULT 60, -- Don't spam alerts
    escalation_thresholds INTEGER[] DEFAULT ARRAY[3, 10, 25], -- Failed webhooks for escalation
    
    -- Monitoring settings
    monitoring_enabled BOOLEAN DEFAULT TRUE,
    health_check_interval_minutes INTEGER DEFAULT 5,
    metric_aggregation_intervals INTEGER[] DEFAULT ARRAY[5, 15, 60, 1440], -- minutes
    
    -- Recovery settings
    auto_recovery_enabled BOOLEAN DEFAULT TRUE,
    max_recovery_attempts INTEGER DEFAULT 3,
    recovery_backoff_minutes INTEGER[] DEFAULT ARRAY[5, 15, 30],
    
    -- Data retention
    delivery_log_retention_days INTEGER DEFAULT 30,
    health_metrics_retention_days INTEGER DEFAULT 90,
    missing_alerts_retention_days INTEGER DEFAULT 180,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(provider)
);

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

-- Webhook delivery logs indexes
CREATE INDEX idx_webhook_delivery_logs_provider ON webhook_delivery_logs(provider);
CREATE INDEX idx_webhook_delivery_logs_payment ON webhook_delivery_logs(payment_intent_id);
CREATE INDEX idx_webhook_delivery_logs_received ON webhook_delivery_logs(received_at);
CREATE INDEX idx_webhook_delivery_logs_status ON webhook_delivery_logs(delivery_status, processing_status);
CREATE INDEX idx_webhook_delivery_logs_hash ON webhook_delivery_logs(payload_hash);

-- Provider health indexes
CREATE INDEX idx_webhook_provider_health_provider ON webhook_provider_health(provider);
CREATE INDEX idx_webhook_provider_health_window ON webhook_provider_health(metric_window_start, metric_window_end);
CREATE INDEX idx_webhook_provider_health_score ON webhook_provider_health(health_score);

-- Missing confirmation alerts indexes
CREATE INDEX idx_missing_confirmation_payment ON missing_confirmation_alerts(payment_intent_id);
CREATE INDEX idx_missing_confirmation_provider ON missing_confirmation_alerts(provider);
CREATE INDEX idx_missing_confirmation_detected ON missing_confirmation_alerts(detected_at);
CREATE INDEX idx_missing_confirmation_status ON missing_confirmation_alerts(recovery_status, resolved);
CREATE INDEX idx_missing_confirmation_alerts ON missing_confirmation_alerts(alert_sent, acknowledged);

-- Health events indexes
CREATE INDEX idx_webhook_health_events_type ON webhook_health_events(event_type, severity);
CREATE INDEX idx_webhook_health_events_provider ON webhook_health_events(provider);
CREATE INDEX idx_webhook_health_events_created ON webhook_health_events(created_at);
CREATE INDEX idx_webhook_health_events_fingerprint ON webhook_health_events(alert_fingerprint);

-- Monitoring config indexes
CREATE INDEX idx_webhook_monitoring_config_provider ON webhook_monitoring_config(provider);

-- =============================================================================
-- TRIGGERS FOR AUTOMATED UPDATES
-- =============================================================================

-- Update timestamp trigger for relevant tables
CREATE TRIGGER update_webhook_delivery_logs_updated_at 
    BEFORE UPDATE ON webhook_delivery_logs 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_missing_confirmation_alerts_updated_at 
    BEFORE UPDATE ON missing_confirmation_alerts 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_webhook_monitoring_config_updated_at 
    BEFORE UPDATE ON webhook_monitoring_config 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- INITIAL CONFIGURATION DATA
-- =============================================================================

-- Insert default monitoring configuration for known providers
INSERT INTO webhook_monitoring_config (provider, min_success_rate_threshold, max_avg_processing_time_ms, missing_confirmation_timeout_minutes) VALUES
('dynopay', 0.9500, 5000, 30),
('blockbee', 0.9500, 5000, 30);

-- =============================================================================
-- USEFUL VIEWS FOR MONITORING
-- =============================================================================

-- Real-time provider health view
CREATE VIEW current_provider_health AS
SELECT 
    provider,
    health_score,
    health_status,
    delivery_success_rate,
    processing_success_rate,
    avg_delivery_delay_seconds,
    avg_processing_time_ms,
    total_received_webhooks,
    total_failed_webhooks,
    metric_window_end as last_updated
FROM webhook_provider_health wph1
WHERE wph1.metric_window_start = (
    SELECT MAX(wph2.metric_window_start)
    FROM webhook_provider_health wph2
    WHERE wph2.provider = wph1.provider
    AND wph2.window_duration_minutes = 15  -- Use 15-minute windows for current health
);

-- Active missing confirmations view
CREATE VIEW active_missing_confirmations AS
SELECT 
    mca.*,
    pi.status as current_payment_status,
    pi.amount,
    pi.currency,
    pi.created_at as payment_created,
    EXTRACT(EPOCH FROM (NOW() - mca.detected_at))/60 as minutes_missing
FROM missing_confirmation_alerts mca
JOIN payment_intents pi ON mca.payment_intent_id = pi.id
WHERE mca.resolved = FALSE
AND mca.recovery_status IN ('pending', 'failed')
ORDER BY mca.detected_at ASC;

-- Recent webhook health events view
CREATE VIEW recent_health_events AS
SELECT 
    event_type,
    severity,
    provider,
    event_title,
    current_health_score,
    current_success_rate,
    created_at,
    resolved,
    alert_sent
FROM webhook_health_events
WHERE created_at >= NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;

-- =============================================================================
-- COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE webhook_delivery_logs IS 'Tracks individual webhook delivery attempts and their processing outcomes';
COMMENT ON TABLE webhook_provider_health IS 'Aggregated health metrics per provider with time-based windows';
COMMENT ON TABLE missing_confirmation_alerts IS 'Tracks payment intents that may be missing webhook confirmations';
COMMENT ON TABLE webhook_health_events IS 'Log of significant health events for alerting and analysis';
COMMENT ON TABLE webhook_monitoring_config IS 'Configuration for monitoring thresholds and alert settings';

COMMENT ON VIEW current_provider_health IS 'Real-time health status for all providers based on latest metrics';
COMMENT ON VIEW active_missing_confirmations IS 'Currently unresolved missing confirmation alerts with payment details';
COMMENT ON VIEW recent_health_events IS 'Webhook health events from the last 24 hours';