CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id VARCHAR(255) NULL,
    recipient VARCHAR(32) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(32) NOT NULL DEFAULT 'whatsapp',
    priority VARCHAR(32) NOT NULL DEFAULT 'normal',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    provider VARCHAR(32) NOT NULL DEFAULT 'uazapi',
    provider_message_id VARCHAR(255) NULL,
    provider_response JSONB NULL,
    error_message TEXT NULL,
    metadata JSONB NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_job_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,

    CONSTRAINT chk_notifications_status
        CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')),

    CONSTRAINT chk_notifications_type
        CHECK (type IN ('whatsapp')),

    CONSTRAINT chk_notifications_priority
        CHECK (priority IN ('low', 'normal', 'high'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_external_id_not_null
    ON notifications (external_id)
    WHERE external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_notifications_status_created_at
    ON notifications (status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_notifications_recipient_created_at
    ON notifications (recipient, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_notifications_last_job_id
    ON notifications (last_job_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON notifications;

CREATE TRIGGER trg_notifications_updated_at
BEFORE UPDATE ON notifications
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
