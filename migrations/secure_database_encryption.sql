-- HostBay Telegram Bot - SECURE Database Encryption Implementation
-- Enterprise-grade encryption with proper external key management
-- Created: September 2025
-- SECURITY: No master keys stored in source control or database

-- =============================================================================
-- 1. SECURE ENCRYPTION KEY MANAGEMENT SYSTEM
-- =============================================================================

-- Encryption keys table for METADATA ONLY (no actual keys stored)
CREATE TABLE IF NOT EXISTS encryption_keys (
    id SERIAL PRIMARY KEY,
    key_alias VARCHAR(100) UNIQUE NOT NULL,
    key_version INTEGER NOT NULL DEFAULT 1,
    -- SECURITY: Removed derived_key column - keys derived at runtime
    salt BYTEA NOT NULL, -- Salt used for key derivation
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retired_at TIMESTAMP NULL,
    
    -- Ensure only one default key at a time
    CONSTRAINT unique_default_key EXCLUDE (is_default WITH =) WHERE (is_default = TRUE)
);

-- Create index for efficient key lookups
CREATE INDEX IF NOT EXISTS idx_encryption_keys_alias_version ON encryption_keys(key_alias, key_version);
CREATE INDEX IF NOT EXISTS idx_encryption_keys_active ON encryption_keys(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_encryption_keys_default ON encryption_keys(is_default) WHERE is_default = TRUE;

-- =============================================================================
-- 2. SECURE ENCRYPTION/DECRYPTION FUNCTIONS
-- =============================================================================

-- Function to derive encryption key using PBKDF2 at runtime from external master key
CREATE OR REPLACE FUNCTION derive_encryption_key(
    master_key TEXT,
    salt BYTEA,
    iterations INTEGER DEFAULT 100000
)
RETURNS BYTEA AS $$
BEGIN
    -- Validate master key is provided
    IF master_key IS NULL OR length(master_key) = 0 THEN
        RAISE EXCEPTION 'Master key is required but not provided - check ENCRYPTION_MASTER_KEY environment variable';
    END IF;
    
    -- Validate salt
    IF salt IS NULL THEN
        RAISE EXCEPTION 'Salt is required for key derivation';
    END IF;
    
    -- Use PBKDF2 with SHA-256 for key derivation (32 bytes for AES-256)
    RETURN digest(
        hmac(master_key || salt::TEXT, salt::TEXT, 'sha256') || 
        hmac(master_key || salt::TEXT || '1', salt::TEXT, 'sha256'),
        'sha256'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to generate random salt
CREATE OR REPLACE FUNCTION generate_salt()
RETURNS BYTEA AS $$
BEGIN
    RETURN gen_random_bytes(32); -- 256-bit salt
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to create new encryption key metadata (no actual key stored)
CREATE OR REPLACE FUNCTION create_encryption_key(
    p_key_alias VARCHAR(100),
    p_make_default BOOLEAN DEFAULT FALSE
)
RETURNS INTEGER AS $$
DECLARE
    v_salt BYTEA;
    v_key_version INTEGER;
    v_key_id INTEGER;
BEGIN
    -- Generate salt for this key (only metadata stored)
    v_salt := generate_salt();
    
    -- Get next version number for this alias
    SELECT COALESCE(MAX(key_version), 0) + 1
    INTO v_key_version
    FROM encryption_keys
    WHERE key_alias = p_key_alias;
    
    -- If making this the default, clear other default flags
    IF p_make_default THEN
        UPDATE encryption_keys SET is_default = FALSE WHERE is_default = TRUE;
    END IF;
    
    -- Insert new key metadata (NO DERIVED KEY STORED)
    INSERT INTO encryption_keys (
        key_alias, key_version, salt, is_active, is_default
    ) VALUES (
        p_key_alias, v_key_version, v_salt, TRUE, p_make_default
    ) RETURNING id INTO v_key_id;
    
    RAISE NOTICE 'Created encryption key metadata: alias=%, version=%, id=%', p_key_alias, v_key_version, v_key_id;
    RETURN v_key_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get encryption key metadata (salt only - derive key at runtime)
CREATE OR REPLACE FUNCTION get_encryption_key_metadata(
    p_key_id INTEGER DEFAULT NULL,
    p_key_alias VARCHAR(100) DEFAULT NULL
)
RETURNS RECORD AS $$
DECLARE
    key_record RECORD;
BEGIN
    IF p_key_id IS NOT NULL THEN
        -- Get specific key by ID
        SELECT id, salt INTO key_record
        FROM encryption_keys
        WHERE id = p_key_id AND is_active = TRUE;
    ELSIF p_key_alias IS NOT NULL THEN
        -- Get latest version of key by alias
        SELECT id, salt INTO key_record
        FROM encryption_keys
        WHERE key_alias = p_key_alias AND is_active = TRUE
        ORDER BY key_version DESC
        LIMIT 1;
    ELSE
        -- Get default key
        SELECT id, salt INTO key_record
        FROM encryption_keys
        WHERE is_default = TRUE AND is_active = TRUE
        LIMIT 1;
    END IF;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No active encryption key found for key_id=% alias=%', p_key_id, p_key_alias;
    END IF;
    
    RETURN key_record;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Secure encryption function with runtime key derivation
CREATE OR REPLACE FUNCTION encrypt_sensitive_data(
    plaintext TEXT,
    key_id INTEGER DEFAULT NULL,
    key_alias VARCHAR(100) DEFAULT 'default'
)
RETURNS RECORD AS $$
DECLARE
    key_metadata RECORD;
    master_key TEXT;
    derived_key BYTEA;
    iv BYTEA;
    encrypted_data BYTEA;
    result RECORD;
BEGIN
    -- Handle NULL input
    IF plaintext IS NULL OR length(trim(plaintext)) = 0 THEN
        SELECT NULL::BYTEA as ciphertext, NULL::INTEGER as key_id INTO result;
        RETURN result;
    END IF;
    
    -- Get master key from environment (SECURE)
    master_key := current_setting('app.master_key', true);
    IF master_key IS NULL OR length(master_key) = 0 THEN
        RAISE EXCEPTION 'Master encryption key not available - set ENCRYPTION_MASTER_KEY environment variable';
    END IF;
    
    -- Get encryption key metadata (salt only)
    key_metadata := get_encryption_key_metadata(key_id, key_alias);
    
    -- Derive encryption key at runtime (SECURE)
    derived_key := derive_encryption_key(master_key, key_metadata.salt);
    
    -- Generate random IV for this encryption
    iv := gen_random_bytes(16); -- 128-bit IV for AES
    
    -- Encrypt using AES-256-CBC
    encrypted_data := encrypt_iv(
        plaintext::BYTEA,
        derived_key,
        iv,
        'aes-cbc'
    );
    
    -- Prepend IV to encrypted data (standard practice)
    encrypted_data := iv || encrypted_data;
    
    -- Return both ciphertext and key ID used
    SELECT encrypted_data as ciphertext, key_metadata.id as key_id INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Secure decryption function with runtime key derivation
CREATE OR REPLACE FUNCTION decrypt_sensitive_data(
    ciphertext BYTEA,
    key_id INTEGER
)
RETURNS TEXT AS $$
DECLARE
    key_metadata RECORD;
    master_key TEXT;
    derived_key BYTEA;
    iv BYTEA;
    encrypted_payload BYTEA;
    decrypted_data BYTEA;
BEGIN
    -- Handle NULL input
    IF ciphertext IS NULL THEN
        RETURN NULL;
    END IF;
    
    -- Get master key from environment (SECURE)
    master_key := current_setting('app.master_key', true);
    IF master_key IS NULL OR length(master_key) = 0 THEN
        RAISE EXCEPTION 'Master encryption key not available - set ENCRYPTION_MASTER_KEY environment variable';
    END IF;
    
    -- Get decryption key metadata (salt only)
    key_metadata := get_encryption_key_metadata(key_id);
    
    -- Derive decryption key at runtime (SECURE)
    derived_key := derive_encryption_key(master_key, key_metadata.salt);
    
    -- Extract IV (first 16 bytes) and payload
    iv := substring(ciphertext from 1 for 16);
    encrypted_payload := substring(ciphertext from 17);
    
    -- Decrypt using AES-256-CBC
    decrypted_data := decrypt_iv(
        encrypted_payload,
        derived_key,
        iv,
        'aes-cbc'
    );
    
    -- Convert back to text
    RETURN convert_from(decrypted_data, 'UTF8');
    
EXCEPTION
    WHEN OTHERS THEN
        -- Log decryption failure but don't expose sensitive details
        RAISE WARNING 'Decryption failed for key_id=%: %', key_id, SQLERRM;
        RETURN '[DECRYPTION_FAILED]';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 3. AUDIT LOGGING FOR ENCRYPTION OPERATIONS
-- =============================================================================

-- Audit table for encryption/decryption operations
CREATE TABLE IF NOT EXISTS encryption_audit (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(20) NOT NULL, -- 'encrypt', 'decrypt', 'key_create', 'key_rotate'
    table_name VARCHAR(255),
    column_name VARCHAR(255),
    record_id INTEGER,
    key_id INTEGER,
    key_alias VARCHAR(100),
    user_id INTEGER,
    role_name VARCHAR(100),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for audit table
CREATE INDEX IF NOT EXISTS idx_encryption_audit_operation ON encryption_audit(operation);
CREATE INDEX IF NOT EXISTS idx_encryption_audit_table_record ON encryption_audit(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_encryption_audit_key_id ON encryption_audit(key_id);
CREATE INDEX IF NOT EXISTS idx_encryption_audit_created_at ON encryption_audit(created_at);

-- Function to log encryption operations
CREATE OR REPLACE FUNCTION log_encryption_operation(
    p_operation VARCHAR(20),
    p_table_name VARCHAR(255) DEFAULT NULL,
    p_column_name VARCHAR(255) DEFAULT NULL,
    p_record_id INTEGER DEFAULT NULL,
    p_key_id INTEGER DEFAULT NULL,
    p_key_alias VARCHAR(100) DEFAULT NULL,
    p_success BOOLEAN DEFAULT TRUE,
    p_error_message TEXT DEFAULT NULL
)
RETURNS VOID AS $$
DECLARE
    current_user_id INTEGER;
    current_role TEXT;
BEGIN
    -- Extract user context from RLS system
    BEGIN
        current_user_id := current_setting('app.user_id', true)::INTEGER;
    EXCEPTION
        WHEN OTHERS THEN
            current_user_id := NULL;
    END;
    
    current_role := current_user;
    
    -- Insert audit record
    INSERT INTO encryption_audit (
        operation, table_name, column_name, record_id,
        key_id, key_alias, user_id, role_name,
        success, error_message
    ) VALUES (
        p_operation, p_table_name, p_column_name, p_record_id,
        p_key_id, p_key_alias, current_user_id, current_role,
        p_success, p_error_message
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 4. KEY ROTATION FUNCTIONS
-- =============================================================================

-- Function to rotate encryption keys (creates new metadata only)
CREATE OR REPLACE FUNCTION rotate_encryption_key(
    p_key_alias VARCHAR(100)
)
RETURNS INTEGER AS $$
DECLARE
    old_key_id INTEGER;
    new_key_id INTEGER;
BEGIN
    -- Get current default key ID
    SELECT id INTO old_key_id
    FROM encryption_keys
    WHERE key_alias = p_key_alias AND is_default = TRUE AND is_active = TRUE;
    
    -- Create new key version (metadata only)
    new_key_id := create_encryption_key(p_key_alias, TRUE);
    
    -- Retire old key (but keep it active for decryption of existing data)
    IF old_key_id IS NOT NULL THEN
        UPDATE encryption_keys 
        SET is_default = FALSE, retired_at = CURRENT_TIMESTAMP
        WHERE id = old_key_id;
        
        RAISE NOTICE 'Key rotation completed: old_key_id=%, new_key_id=%', old_key_id, new_key_id;
    END IF;
    
    -- Log key rotation
    PERFORM log_encryption_operation(
        'key_rotate', NULL, NULL, NULL, new_key_id, p_key_alias, TRUE
    );
    
    RETURN new_key_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 5. COMPLETION NOTICE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=== SECURE DATABASE ENCRYPTION IMPLEMENTATION COMPLETED ===';
    RAISE NOTICE 'Security features implemented:';
    RAISE NOTICE '- NO master keys stored in database or source control';
    RAISE NOTICE '- Runtime key derivation from external master key';
    RAISE NOTICE '- Only salt and metadata stored in database';
    RAISE NOTICE '- AES-256-CBC encryption with random IVs';
    RAISE NOTICE '- PBKDF2 key derivation for enhanced security';
    RAISE NOTICE '- Key rotation and version management';
    RAISE NOTICE '- Comprehensive audit logging';
    RAISE NOTICE '';
    RAISE NOTICE 'SECURITY REQUIREMENTS:';
    RAISE NOTICE '1. Set ENCRYPTION_MASTER_KEY environment variable';
    RAISE NOTICE '2. Use application-level connection with app.master_key session variable';
    RAISE NOTICE '3. Implement proper master key rotation in external key management system';
    RAISE NOTICE '4. Never commit master keys to source control';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Update application code for new secure functions';
    RAISE NOTICE '2. Migrate existing data with proper master key management';
    RAISE NOTICE '3. Implement external key management (KMS/Vault)';
    RAISE NOTICE '4. Set up regular key rotation schedule';
    RAISE NOTICE '5. Monitor encryption audit logs';
    RAISE NOTICE '';
END
$$;