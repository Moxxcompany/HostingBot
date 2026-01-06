-- System Maintenance Mode Table
-- Singleton pattern ensures only one maintenance record exists at any time

CREATE TABLE IF NOT EXISTS system_maintenance (
    id SERIAL PRIMARY KEY,
    is_active BOOLEAN DEFAULT FALSE,
    started_at TIMESTAMP WITH TIME ZONE,
    ends_at TIMESTAMP WITH TIME ZONE,
    duration_minutes INTEGER,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Ensure only one maintenance record (enforce singleton pattern)
CREATE UNIQUE INDEX IF NOT EXISTS system_maintenance_singleton ON system_maintenance ((1));

-- Insert initial record
INSERT INTO system_maintenance (is_active, created_by) 
VALUES (FALSE, NULL)
ON CONFLICT DO NOTHING;

-- Add comment for documentation
COMMENT ON TABLE system_maintenance IS 'System maintenance mode configuration with singleton pattern';
COMMENT ON COLUMN system_maintenance.is_active IS 'Whether maintenance mode is currently active';
COMMENT ON COLUMN system_maintenance.started_at IS 'When maintenance mode was activated';
COMMENT ON COLUMN system_maintenance.ends_at IS 'When maintenance mode is scheduled to end';
COMMENT ON COLUMN system_maintenance.duration_minutes IS 'Duration of maintenance in minutes';
COMMENT ON COLUMN system_maintenance.created_by IS 'Admin user ID who enabled maintenance';
