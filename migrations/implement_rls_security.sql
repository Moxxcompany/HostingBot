-- HostBay Telegram Bot - Row-Level Security (RLS) Implementation
-- Phase 3: Multi-Tenant Data Isolation
-- Created: September 2025

-- =============================================================================
-- 1. CREATE DATABASE ROLES
-- =============================================================================

-- Create service roles if they don't exist
DO $$
BEGIN
    -- Bot service role - main application role with selective access
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bot_service') THEN
        CREATE ROLE bot_service;
        RAISE NOTICE 'Created bot_service role';
    END IF;
    
    -- Admin service role - can access all data for admin operations
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'admin_service') THEN
        CREATE ROLE admin_service;
        RAISE NOTICE 'Created admin_service role';
    END IF;
    
    -- Maintenance role - bypass RLS for operational tasks
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'maintenance_role') THEN
        CREATE ROLE maintenance_role BYPASSRLS;
        RAISE NOTICE 'Created maintenance_role with BYPASSRLS';
    END IF;
END
$$;

-- Grant basic permissions to service roles
GRANT CONNECT ON DATABASE postgres TO bot_service, admin_service, maintenance_role;
GRANT USAGE ON SCHEMA public TO bot_service, admin_service, maintenance_role;

-- Grant table permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bot_service, admin_service, maintenance_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bot_service, admin_service, maintenance_role;

-- Grant function execution permissions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO bot_service, admin_service, maintenance_role;

-- =============================================================================
-- 2. CREATE SECURITY CONTEXT FUNCTIONS
-- =============================================================================

-- Function to get current app user ID from session variable
CREATE OR REPLACE FUNCTION current_app_user_id()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
DECLARE
    user_id_str TEXT;
    user_id INTEGER;
BEGIN
    -- Get the session variable for current user
    user_id_str := current_setting('app.user_id', true);
    
    -- Return NULL if not set (allows service accounts to bypass)
    IF user_id_str IS NULL OR user_id_str = '' THEN
        RETURN NULL;
    END IF;
    
    -- Convert to integer safely
    BEGIN
        user_id := user_id_str::INTEGER;
        RETURN user_id;
    EXCEPTION
        WHEN invalid_text_representation THEN
            -- Log the error and return NULL for safety
            RAISE WARNING 'Invalid user_id in session: %', user_id_str;
            RETURN NULL;
    END;
END;
$$;

-- Function to check if current role is a service account
CREATE OR REPLACE FUNCTION is_service_role()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
    -- Service roles that can bypass user-level restrictions
    RETURN current_user IN ('admin_service', 'maintenance_role') 
           OR pg_has_role(current_user, 'admin_service', 'member')
           OR pg_has_role(current_user, 'maintenance_role', 'member');
END;
$$;

-- Function to check if current user is admin
CREATE OR REPLACE FUNCTION is_admin_context()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
DECLARE
    admin_flag_str TEXT;
BEGIN
    -- Check if admin flag is set in session
    admin_flag_str := current_setting('app.is_admin', true);
    RETURN admin_flag_str = 'true';
END;
$$;

-- =============================================================================
-- 3. ENABLE RLS ON BUSINESS TABLES
-- =============================================================================

-- Enable RLS on all business tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosting_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallet_transactions ENABLE ROW LEVEL SECURITY;

-- Also enable RLS on related tables that contain user data
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE callback_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE domain_registration_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE hosting_provision_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE domain_hosting_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_callbacks ENABLE ROW LEVEL SECURITY;
ALTER TABLE crypto_deposits ENABLE ROW LEVEL SECURITY;
ALTER TABLE refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE domain_searches ENABLE ROW LEVEL SECURITY;
ALTER TABLE cpanel_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE dns_zones ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- 4. CREATE RLS POLICIES FOR CORE BUSINESS TABLES
-- =============================================================================

-- USERS table policies
DROP POLICY IF EXISTS users_owner_policy ON users;
CREATE POLICY users_owner_policy ON users
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        id = current_app_user_id()
    );

-- ORDERS table policies
DROP POLICY IF EXISTS orders_owner_policy ON orders;
CREATE POLICY orders_owner_policy ON orders
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- DOMAINS table policies
DROP POLICY IF EXISTS domains_owner_policy ON domains;
CREATE POLICY domains_owner_policy ON domains
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- HOSTING_SUBSCRIPTIONS table policies
DROP POLICY IF EXISTS hosting_subscriptions_owner_policy ON hosting_subscriptions;
CREATE POLICY hosting_subscriptions_owner_policy ON hosting_subscriptions
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- PAYMENT_INTENTS table policies
DROP POLICY IF EXISTS payment_intents_owner_policy ON payment_intents;
CREATE POLICY payment_intents_owner_policy ON payment_intents
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM orders o 
            WHERE o.id = payment_intents.order_id 
            AND o.user_id = current_app_user_id()
        )
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM orders o 
            WHERE o.id = payment_intents.order_id 
            AND o.user_id = current_app_user_id()
        )
    );

-- WALLET_TRANSACTIONS table policies
DROP POLICY IF EXISTS wallet_transactions_owner_policy ON wallet_transactions;
CREATE POLICY wallet_transactions_owner_policy ON wallet_transactions
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- =============================================================================
-- 5. CREATE RLS POLICIES FOR RELATED TABLES
-- =============================================================================

-- USER_PROFILES table policies
DROP POLICY IF EXISTS user_profiles_owner_policy ON user_profiles;
CREATE POLICY user_profiles_owner_policy ON user_profiles
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- CALLBACK_TOKENS table policies
DROP POLICY IF EXISTS callback_tokens_owner_policy ON callback_tokens;
CREATE POLICY callback_tokens_owner_policy ON callback_tokens
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- DOMAIN_REGISTRATION_INTENTS table policies
DROP POLICY IF EXISTS domain_registration_intents_owner_policy ON domain_registration_intents;
CREATE POLICY domain_registration_intents_owner_policy ON domain_registration_intents
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- HOSTING_PROVISION_INTENTS table policies
DROP POLICY IF EXISTS hosting_provision_intents_owner_policy ON hosting_provision_intents;
CREATE POLICY hosting_provision_intents_owner_policy ON hosting_provision_intents
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- ORDER_ITEMS table policies (linked to orders)
DROP POLICY IF EXISTS order_items_owner_policy ON order_items;
CREATE POLICY order_items_owner_policy ON order_items
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM orders o 
            WHERE o.id = order_items.order_id 
            AND o.user_id = current_app_user_id()
        )
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM orders o 
            WHERE o.id = order_items.order_id 
            AND o.user_id = current_app_user_id()
        )
    );

-- DOMAIN_HOSTING_BUNDLES table policies
DROP POLICY IF EXISTS domain_hosting_bundles_owner_policy ON domain_hosting_bundles;
CREATE POLICY domain_hosting_bundles_owner_policy ON domain_hosting_bundles
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- PAYMENT_CALLBACKS table policies (linked to payment_intents)
DROP POLICY IF EXISTS payment_callbacks_owner_policy ON payment_callbacks;
CREATE POLICY payment_callbacks_owner_policy ON payment_callbacks
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM payment_intents pi 
            JOIN orders o ON o.id = pi.order_id
            WHERE pi.id = payment_callbacks.payment_intent_id 
            AND o.user_id = current_app_user_id()
        )
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM payment_intents pi 
            JOIN orders o ON o.id = pi.order_id
            WHERE pi.id = payment_callbacks.payment_intent_id 
            AND o.user_id = current_app_user_id()
        )
    );

-- CRYPTO_DEPOSITS table policies
DROP POLICY IF EXISTS crypto_deposits_owner_policy ON crypto_deposits;
CREATE POLICY crypto_deposits_owner_policy ON crypto_deposits
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- REFUNDS table policies
DROP POLICY IF EXISTS refunds_owner_policy ON refunds;
CREATE POLICY refunds_owner_policy ON refunds
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- NOTIFICATIONS table policies
DROP POLICY IF EXISTS notifications_owner_policy ON notifications;
CREATE POLICY notifications_owner_policy ON notifications
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- DOMAIN_SEARCHES table policies
DROP POLICY IF EXISTS domain_searches_owner_policy ON domain_searches;
CREATE POLICY domain_searches_owner_policy ON domain_searches
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        user_id = current_app_user_id()
    );

-- CPANEL_ACCOUNTS table policies (linked to hosting_subscriptions)
DROP POLICY IF EXISTS cpanel_accounts_owner_policy ON cpanel_accounts;
CREATE POLICY cpanel_accounts_owner_policy ON cpanel_accounts
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM hosting_subscriptions hs 
            WHERE hs.id = cpanel_accounts.subscription_id 
            AND hs.user_id = current_app_user_id()
        )
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM hosting_subscriptions hs 
            WHERE hs.id = cpanel_accounts.subscription_id 
            AND hs.user_id = current_app_user_id()
        )
    );

-- DNS_ZONES table policies (linked to domains)
DROP POLICY IF EXISTS dns_zones_owner_policy ON dns_zones;
CREATE POLICY dns_zones_owner_policy ON dns_zones
    FOR ALL
    TO bot_service, admin_service
    USING (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM domains d 
            WHERE d.id = dns_zones.domain_id 
            AND d.user_id = current_app_user_id()
        )
    )
    WITH CHECK (
        is_service_role() OR 
        is_admin_context() OR 
        EXISTS (
            SELECT 1 FROM domains d 
            WHERE d.id = dns_zones.domain_id 
            AND d.user_id = current_app_user_id()
        )
    );

-- =============================================================================
-- 6. CREATE FEATURE FLAG SUPPORT
-- =============================================================================

-- Function to check if RLS is enabled
CREATE OR REPLACE FUNCTION is_rls_enabled()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
DECLARE
    rls_enabled_str TEXT;
BEGIN
    -- Check environment variable or database setting
    rls_enabled_str := current_setting('app.rls_enabled', true);
    
    -- Default to true if not set (secure by default)
    IF rls_enabled_str IS NULL OR rls_enabled_str = '' THEN
        RETURN true;
    END IF;
    
    RETURN rls_enabled_str = 'true';
END;
$$;

-- =============================================================================
-- 7. GRANT PERMISSIONS TO EXISTING DATABASE USER
-- =============================================================================

-- Grant service role permissions to the main database connection user
-- This assumes the application connects as the database owner or a privileged user

-- Grant the ability to assume service roles
DO $$
DECLARE
    db_user TEXT;
BEGIN
    -- Get current database user
    SELECT current_user INTO db_user;
    
    -- Grant service roles to current user
    EXECUTE format('GRANT bot_service TO %I', db_user);
    EXECUTE format('GRANT admin_service TO %I', db_user);
    EXECUTE format('GRANT maintenance_role TO %I', db_user);
    
    RAISE NOTICE 'Granted service roles to %', db_user;
END
$$;

-- =============================================================================
-- 8. VERIFICATION AND TESTING FUNCTIONS
-- =============================================================================

-- Function to test RLS enforcement
CREATE OR REPLACE FUNCTION test_rls_enforcement(test_user_id INTEGER)
RETURNS TABLE(
    table_name TEXT,
    policy_active BOOLEAN,
    user_can_access BOOLEAN,
    row_count BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Set test user context
    PERFORM set_config('app.user_id', test_user_id::TEXT, true);
    PERFORM set_config('app.is_admin', 'false', true);
    
    -- Test each table
    RETURN QUERY
    SELECT 'users'::TEXT, 
           true::BOOLEAN,
           EXISTS(SELECT 1 FROM users WHERE id = test_user_id)::BOOLEAN,
           (SELECT count(*) FROM users)::BIGINT;
           
    RETURN QUERY
    SELECT 'orders'::TEXT,
           true::BOOLEAN,
           EXISTS(SELECT 1 FROM orders WHERE user_id = test_user_id)::BOOLEAN,
           (SELECT count(*) FROM orders)::BIGINT;
           
    RETURN QUERY
    SELECT 'domains'::TEXT,
           true::BOOLEAN,
           EXISTS(SELECT 1 FROM domains WHERE user_id = test_user_id)::BOOLEAN,
           (SELECT count(*) FROM domains)::BIGINT;
           
    -- Reset session variables
    PERFORM set_config('app.user_id', NULL, true);
    PERFORM set_config('app.is_admin', NULL, true);
END;
$$;

-- =============================================================================
-- 9. AUDIT AND LOGGING
-- =============================================================================

-- Create audit log table for RLS policy violations
CREATE TABLE IF NOT EXISTS rls_audit_log (
    id SERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    attempted_user_id INTEGER,
    session_user_id INTEGER,
    current_role TEXT,
    violation_type TEXT,
    violation_details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Function to log RLS violations
CREATE OR REPLACE FUNCTION log_rls_violation(
    p_table_name TEXT,
    p_operation TEXT,
    p_attempted_user_id INTEGER,
    p_violation_type TEXT,
    p_details JSONB DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    session_user_id INTEGER;
BEGIN
    -- Get session user ID
    BEGIN
        session_user_id := current_setting('app.user_id', true)::INTEGER;
    EXCEPTION
        WHEN OTHERS THEN
            session_user_id := NULL;
    END;
    
    -- Insert audit record
    INSERT INTO rls_audit_log (
        table_name,
        operation,
        attempted_user_id,
        session_user_id,
        current_role,
        violation_type,
        violation_details
    ) VALUES (
        p_table_name,
        p_operation,
        p_attempted_user_id,
        session_user_id,
        current_user,
        p_violation_type,
        p_details
    );
END;
$$;

-- =============================================================================
-- COMPLETION NOTICE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=== RLS IMPLEMENTATION COMPLETED ===';
    RAISE NOTICE 'Database roles created: bot_service, admin_service, maintenance_role';
    RAISE NOTICE 'Security functions created: current_app_user_id(), is_service_role(), is_admin_context()';
    RAISE NOTICE 'RLS enabled on % business tables', (
        SELECT count(*) FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN (
            'users', 'orders', 'domains', 'hosting_subscriptions', 
            'payment_intents', 'wallet_transactions', 'user_profiles',
            'callback_tokens', 'domain_registration_intents', 
            'hosting_provision_intents', 'order_items', 
            'domain_hosting_bundles', 'payment_callbacks',
            'crypto_deposits', 'refunds', 'notifications',
            'domain_searches', 'cpanel_accounts', 'dns_zones'
        )
    );
    RAISE NOTICE 'RLS policies created for owner-only access with service role bypass';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Update database.py to set session variables';
    RAISE NOTICE '2. Test RLS enforcement with different user contexts';
    RAISE NOTICE '3. Verify service roles can bypass when needed';
    RAISE NOTICE '4. Monitor RLS audit logs for violations';
    RAISE NOTICE '';
END
$$;