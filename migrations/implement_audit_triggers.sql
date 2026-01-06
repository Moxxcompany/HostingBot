-- HostBay Telegram Bot - Phase 4: Audit Triggers Implementation
-- Comprehensive audit system for enterprise-grade change logging
-- Created: September 2025

-- =============================================================================
-- 1. CREATE AUDIT LOG TABLE
-- =============================================================================

-- Create comprehensive audit log table for tracking all changes to sensitive tables
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(255) NOT NULL,
    operation VARCHAR(10) NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE'
    record_id INTEGER NOT NULL, -- The primary key of the affected record
    old_values JSONB, -- Previous values (NULL for INSERT)
    new_values JSONB, -- New values (NULL for DELETE)
    changed_fields TEXT[], -- Array of field names that changed (for UPDATE)
    
    -- User context from RLS system
    user_id INTEGER, -- Current app user (from RLS context)
    role_name VARCHAR(100), -- Database role executing the operation
    is_admin BOOLEAN DEFAULT FALSE, -- Whether operation was performed in admin context
    
    -- Metadata
    transaction_id BIGINT, -- Transaction ID for grouping related changes
    session_id VARCHAR(255), -- Session identifier if available
    ip_address INET, -- IP address if available
    user_agent TEXT, -- User agent if available
    
    -- Timing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Integrity and security
    checksum VARCHAR(64), -- Hash of the audit record for integrity verification
    
    -- Soft deletion support
    is_soft_delete BOOLEAN DEFAULT FALSE, -- Track when this is a soft delete operation
    soft_delete_reason TEXT -- Reason for soft deletion
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_audit_log_table_name ON audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_record_id ON audit_log(record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_operation ON audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_transaction_id ON audit_log(transaction_id);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON audit_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_table ON audit_log(user_id, table_name);

-- =============================================================================
-- 2. CREATE AUDIT TRIGGER FUNCTION
-- =============================================================================

-- Universal audit trigger function that captures all changes
CREATE OR REPLACE FUNCTION audit_trigger_func()
RETURNS TRIGGER AS $$
DECLARE
    audit_record RECORD;
    old_data JSONB;
    new_data JSONB;
    changed_fields TEXT[];
    current_user_id INTEGER;
    current_role TEXT;
    is_admin_ctx BOOLEAN;
    record_primary_key INTEGER;
    audit_checksum VARCHAR(64);
    is_soft_delete_op BOOLEAN DEFAULT FALSE;
    soft_delete_reason_txt TEXT;
BEGIN
    -- Extract RLS context information
    BEGIN
        current_user_id := current_setting('app.user_id', true)::INTEGER;
    EXCEPTION
        WHEN OTHERS THEN
            current_user_id := NULL;
    END;
    
    BEGIN
        is_admin_ctx := current_setting('app.is_admin', true)::BOOLEAN;
    EXCEPTION
        WHEN OTHERS THEN
            is_admin_ctx := FALSE;
    END;
    
    current_role := current_user;
    
    -- Handle different operations
    IF TG_OP = 'DELETE' THEN
        old_data := to_jsonb(OLD);
        new_data := NULL;
        record_primary_key := OLD.id;
        
        -- Check if this is a soft delete
        IF OLD.deleted_at IS NOT NULL THEN
            is_soft_delete_op := TRUE;
            soft_delete_reason_txt := COALESCE(OLD.deleted_by, 'Unknown');
        END IF;
        
    ELSIF TG_OP = 'INSERT' THEN
        old_data := NULL;
        new_data := to_jsonb(NEW);
        record_primary_key := NEW.id;
        
    ELSIF TG_OP = 'UPDATE' THEN
        old_data := to_jsonb(OLD);
        new_data := to_jsonb(NEW);
        record_primary_key := NEW.id;
        
        -- Identify changed fields
        changed_fields := ARRAY(
            SELECT key 
            FROM jsonb_each(old_data) o 
            WHERE o.value IS DISTINCT FROM (new_data->o.key)
        );
        
        -- Special handling for soft deletes
        IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
            is_soft_delete_op := TRUE;
            soft_delete_reason_txt := COALESCE(NEW.deleted_by, 'Unknown');
        END IF;
        
    END IF;
    
    -- Generate integrity checksum
    audit_checksum := encode(
        digest(
            concat(
                TG_TABLE_NAME, ':', TG_OP, ':', record_primary_key::TEXT, ':', 
                COALESCE(old_data::TEXT, ''), ':', COALESCE(new_data::TEXT, ''),
                ':', EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::TEXT
            ),
            'sha256'
        ),
        'hex'
    );
    
    -- Insert audit record
    INSERT INTO audit_log (
        table_name,
        operation,
        record_id,
        old_values,
        new_values,
        changed_fields,
        user_id,
        role_name,
        is_admin,
        transaction_id,
        checksum,
        is_soft_delete,
        soft_delete_reason
    ) VALUES (
        TG_TABLE_NAME,
        TG_OP,
        record_primary_key,
        old_data,
        new_data,
        changed_fields,
        current_user_id,
        current_role,
        is_admin_ctx,
        txid_current(),
        audit_checksum,
        is_soft_delete_op,
        soft_delete_reason_txt
    );
    
    -- Return appropriate record
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
    
EXCEPTION
    WHEN OTHERS THEN
        -- Log the error but don't prevent the original operation
        RAISE WARNING 'Audit trigger failed for table % operation %: %', TG_TABLE_NAME, TG_OP, SQLERRM;
        
        -- Return appropriate record to allow operation to continue
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 3. CREATE AUDIT TRIGGERS ON FINANCIAL TABLES
-- =============================================================================

-- Users table (wallet_balance changes are critical)
DROP TRIGGER IF EXISTS trigger_audit_users ON users;
CREATE TRIGGER trigger_audit_users
    AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Wallet transactions (all financial movements)
DROP TRIGGER IF EXISTS trigger_audit_wallet_transactions ON wallet_transactions;
CREATE TRIGGER trigger_audit_wallet_transactions
    AFTER INSERT OR UPDATE OR DELETE ON wallet_transactions
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Payment intents (payment processing audit trail)
DROP TRIGGER IF EXISTS trigger_audit_payment_intents ON payment_intents;
CREATE TRIGGER trigger_audit_payment_intents
    AFTER INSERT OR UPDATE OR DELETE ON payment_intents
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- =============================================================================
-- 4. CREATE AUDIT TRIGGERS ON BUSINESS DATA TABLES
-- =============================================================================

-- Orders (core business transactions)
DROP TRIGGER IF EXISTS trigger_audit_orders ON orders;
CREATE TRIGGER trigger_audit_orders
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Domains (domain ownership and configuration)
DROP TRIGGER IF EXISTS trigger_audit_domains ON domains;
CREATE TRIGGER trigger_audit_domains
    AFTER INSERT OR UPDATE OR DELETE ON domains
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Hosting subscriptions (hosting service lifecycle)
DROP TRIGGER IF EXISTS trigger_audit_hosting_subscriptions ON hosting_subscriptions;
CREATE TRIGGER trigger_audit_hosting_subscriptions
    AFTER INSERT OR UPDATE OR DELETE ON hosting_subscriptions
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- =============================================================================
-- 5. CREATE AUDIT TRIGGERS ON SECURITY-SENSITIVE TABLES
-- =============================================================================

-- User profiles (WHOIS and registration data)
DROP TRIGGER IF EXISTS trigger_audit_user_profiles ON user_profiles;
CREATE TRIGGER trigger_audit_user_profiles
    AFTER INSERT OR UPDATE OR DELETE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Callback tokens (pagination and UI flow security)
DROP TRIGGER IF EXISTS trigger_audit_callback_tokens ON callback_tokens;
CREATE TRIGGER trigger_audit_callback_tokens
    AFTER INSERT OR UPDATE OR DELETE ON callback_tokens
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- =============================================================================
-- 6. CREATE AUDIT TRIGGERS ON ADDITIONAL CRITICAL TABLES
-- =============================================================================

-- Domain registration intents (registration workflow audit)
DROP TRIGGER IF EXISTS trigger_audit_domain_registration_intents ON domain_registration_intents;
CREATE TRIGGER trigger_audit_domain_registration_intents
    AFTER INSERT OR UPDATE OR DELETE ON domain_registration_intents
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Hosting provision intents (hosting workflow audit)
DROP TRIGGER IF EXISTS trigger_audit_hosting_provision_intents ON hosting_provision_intents;
CREATE TRIGGER trigger_audit_hosting_provision_intents
    AFTER INSERT OR UPDATE OR DELETE ON hosting_provision_intents
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Payment callbacks (payment webhook audit trail)
DROP TRIGGER IF EXISTS trigger_audit_payment_callbacks ON payment_callbacks;
CREATE TRIGGER trigger_audit_payment_callbacks
    AFTER INSERT OR UPDATE OR DELETE ON payment_callbacks
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Crypto deposits (cryptocurrency transaction audit)
DROP TRIGGER IF EXISTS trigger_audit_crypto_deposits ON crypto_deposits;
CREATE TRIGGER trigger_audit_crypto_deposits
    AFTER INSERT OR UPDATE OR DELETE ON crypto_deposits
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- Refunds (refund processing audit trail)
DROP TRIGGER IF EXISTS trigger_audit_refunds ON refunds;
CREATE TRIGGER trigger_audit_refunds
    AFTER INSERT OR UPDATE OR DELETE ON refunds
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- cPanel accounts (hosting credential management)
DROP TRIGGER IF EXISTS trigger_audit_cpanel_accounts ON cpanel_accounts;
CREATE TRIGGER trigger_audit_cpanel_accounts
    AFTER INSERT OR UPDATE OR DELETE ON cpanel_accounts
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- DNS zones (DNS management audit)
DROP TRIGGER IF EXISTS trigger_audit_dns_zones ON dns_zones;
CREATE TRIGGER trigger_audit_dns_zones
    AFTER INSERT OR UPDATE OR DELETE ON dns_zones
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

-- =============================================================================
-- 7. CREATE AUDIT HELPER FUNCTIONS
-- =============================================================================

-- Function to query audit trail for a specific record
CREATE OR REPLACE FUNCTION get_audit_trail(
    p_table_name VARCHAR(255),
    p_record_id INTEGER,
    p_limit INTEGER DEFAULT 50
)
RETURNS TABLE(
    id INTEGER,
    operation VARCHAR(10),
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],
    user_id INTEGER,
    role_name VARCHAR(100),
    is_admin BOOLEAN,
    created_at TIMESTAMP,
    is_soft_delete BOOLEAN,
    soft_delete_reason TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id,
        a.operation,
        a.old_values,
        a.new_values,
        a.changed_fields,
        a.user_id,
        a.role_name,
        a.is_admin,
        a.created_at,
        a.is_soft_delete,
        a.soft_delete_reason
    FROM audit_log a
    WHERE a.table_name = p_table_name 
    AND a.record_id = p_record_id
    ORDER BY a.created_at DESC, a.id DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get audit summary for a user
CREATE OR REPLACE FUNCTION get_user_audit_summary(
    p_user_id INTEGER,
    p_days_back INTEGER DEFAULT 30
)
RETURNS TABLE(
    table_name VARCHAR(255),
    operation VARCHAR(10),
    operation_count BIGINT,
    latest_operation TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.table_name,
        a.operation,
        COUNT(*) as operation_count,
        MAX(a.created_at) as latest_operation
    FROM audit_log a
    WHERE a.user_id = p_user_id
    AND a.created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days' % p_days_back
    GROUP BY a.table_name, a.operation
    ORDER BY latest_operation DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to verify audit log integrity
CREATE OR REPLACE FUNCTION verify_audit_integrity(
    p_audit_id INTEGER DEFAULT NULL
)
RETURNS TABLE(
    audit_id INTEGER,
    is_valid BOOLEAN,
    calculated_checksum VARCHAR(64),
    stored_checksum VARCHAR(64)
) AS $$
DECLARE
    audit_rec RECORD;
    calc_checksum VARCHAR(64);
BEGIN
    -- If specific audit ID provided, check only that one
    IF p_audit_id IS NOT NULL THEN
        SELECT * INTO audit_rec FROM audit_log WHERE id = p_audit_id;
        
        IF FOUND THEN
            calc_checksum := encode(
                digest(
                    concat(
                        audit_rec.table_name, ':', audit_rec.operation, ':', audit_rec.record_id::TEXT, ':', 
                        COALESCE(audit_rec.old_values::TEXT, ''), ':', COALESCE(audit_rec.new_values::TEXT, ''),
                        ':', EXTRACT(EPOCH FROM audit_rec.created_at)::TEXT
                    ),
                    'sha256'
                ),
                'hex'
            );
            
            RETURN QUERY SELECT 
                audit_rec.id::INTEGER,
                (calc_checksum = audit_rec.checksum)::BOOLEAN,
                calc_checksum,
                audit_rec.checksum;
        END IF;
        
    ELSE
        -- Check all audit records (use with caution on large datasets)
        FOR audit_rec IN SELECT * FROM audit_log ORDER BY id LIMIT 1000 LOOP
            calc_checksum := encode(
                digest(
                    concat(
                        audit_rec.table_name, ':', audit_rec.operation, ':', audit_rec.record_id::TEXT, ':', 
                        COALESCE(audit_rec.old_values::TEXT, ''), ':', COALESCE(audit_rec.new_values::TEXT, ''),
                        ':', EXTRACT(EPOCH FROM audit_rec.created_at)::TEXT
                    ),
                    'sha256'
                ),
                'hex'
            );
            
            RETURN QUERY SELECT 
                audit_rec.id::INTEGER,
                (calc_checksum = audit_rec.checksum)::BOOLEAN,
                calc_checksum,
                audit_rec.checksum;
        END LOOP;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 8. GRANT PERMISSIONS
-- =============================================================================

-- Grant permissions to service roles
GRANT SELECT ON audit_log TO bot_service, admin_service, maintenance_role;
GRANT INSERT ON audit_log TO bot_service, admin_service, maintenance_role;

-- Admin can manage audit logs
GRANT UPDATE, DELETE ON audit_log TO admin_service, maintenance_role;

-- Grant sequence usage
GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO bot_service, admin_service, maintenance_role;

-- Grant function execution permissions
GRANT EXECUTE ON FUNCTION audit_trigger_func() TO bot_service, admin_service, maintenance_role;
GRANT EXECUTE ON FUNCTION get_audit_trail(VARCHAR(255), INTEGER, INTEGER) TO bot_service, admin_service, maintenance_role;
GRANT EXECUTE ON FUNCTION get_user_audit_summary(INTEGER, INTEGER) TO bot_service, admin_service, maintenance_role;
GRANT EXECUTE ON FUNCTION verify_audit_integrity(INTEGER) TO admin_service, maintenance_role;

-- =============================================================================
-- 9. AUDIT LOG MAINTENANCE
-- =============================================================================

-- Function to clean old audit logs (retention policy)
CREATE OR REPLACE FUNCTION cleanup_old_audit_logs(
    p_retention_days INTEGER DEFAULT 365
)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audit_log 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '%s days' % p_retention_days;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RAISE NOTICE 'Deleted % old audit log records older than % days', deleted_count, p_retention_days;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant cleanup function to maintenance role only
GRANT EXECUTE ON FUNCTION cleanup_old_audit_logs(INTEGER) TO maintenance_role;

-- =============================================================================
-- COMPLETION NOTICE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=== AUDIT TRIGGERS IMPLEMENTATION COMPLETED ===';
    RAISE NOTICE 'Audit log table created with comprehensive tracking';
    RAISE NOTICE 'Universal audit trigger function created';
    RAISE NOTICE 'Audit triggers applied to % sensitive tables:', (
        SELECT count(*) 
        FROM information_schema.triggers 
        WHERE trigger_name LIKE 'trigger_audit_%'
    );
    RAISE NOTICE '';
    RAISE NOTICE 'Tables with audit triggers:';
    RAISE NOTICE '- Financial: users, wallet_transactions, payment_intents';
    RAISE NOTICE '- Business: orders, domains, hosting_subscriptions';
    RAISE NOTICE '- Security: user_profiles, callback_tokens';
    RAISE NOTICE '- Workflows: domain_registration_intents, hosting_provision_intents';
    RAISE NOTICE '- Payments: payment_callbacks, crypto_deposits, refunds';
    RAISE NOTICE '- Infrastructure: cpanel_accounts, dns_zones';
    RAISE NOTICE '';
    RAISE NOTICE 'Helper functions available:';
    RAISE NOTICE '- get_audit_trail(table_name, record_id, limit)';
    RAISE NOTICE '- get_user_audit_summary(user_id, days_back)';
    RAISE NOTICE '- verify_audit_integrity(audit_id)';
    RAISE NOTICE '- cleanup_old_audit_logs(retention_days)';
    RAISE NOTICE '';
    RAISE NOTICE 'Features enabled:';
    RAISE NOTICE '- RLS context tracking (user_id, role, admin status)';
    RAISE NOTICE '- Soft deletion detection and logging';
    RAISE NOTICE '- Integrity verification with checksums';
    RAISE NOTICE '- Changed field tracking for updates';
    RAISE NOTICE '- Transaction grouping support';
    RAISE NOTICE '- Performance-optimized indexing';
    RAISE NOTICE '';
END
$$;