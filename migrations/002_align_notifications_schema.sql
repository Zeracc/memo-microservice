CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
    failed_at TIMESTAMPTZ NULL
);

ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS id UUID,
    ADD COLUMN IF NOT EXISTS external_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS recipient VARCHAR(32),
    ADD COLUMN IF NOT EXISTS message TEXT,
    ADD COLUMN IF NOT EXISTS type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS priority VARCHAR(32),
    ADD COLUMN IF NOT EXISTS status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS provider VARCHAR(32),
    ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS provider_response JSONB,
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB,
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER,
    ADD COLUMN IF NOT EXISTS last_job_id UUID,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS failed_at TIMESTAMPTZ;

UPDATE notifications
SET
    id = COALESCE(id, gen_random_uuid()),
    type = COALESCE(type, 'whatsapp'),
    priority = COALESCE(priority, 'normal'),
    status = COALESCE(status, 'pending'),
    provider = COALESCE(provider, 'uazapi'),
    attempt_count = COALESCE(attempt_count, 0),
    created_at = COALESCE(created_at, NOW()),
    updated_at = COALESCE(updated_at, NOW())
WHERE
    id IS NULL
    OR type IS NULL
    OR priority IS NULL
    OR status IS NULL
    OR provider IS NULL
    OR attempt_count IS NULL
    OR created_at IS NULL
    OR updated_at IS NULL;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM notifications
    WHERE recipient IS NULL OR message IS NULL
  ) THEN
    RAISE EXCEPTION
      'notifications contains NULL recipient/message rows; fix data before enforcing NOT NULL compatibility';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM notifications
    WHERE status NOT IN ('pending', 'processing', 'sent', 'failed', 'cancelled')
  ) THEN
    RAISE EXCEPTION
      'notifications contains invalid status values; fix data before applying schema alignment';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM notifications
    WHERE type NOT IN ('whatsapp')
  ) THEN
    RAISE EXCEPTION
      'notifications contains invalid type values; fix data before applying schema alignment';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM notifications
    WHERE priority NOT IN ('low', 'normal', 'high')
  ) THEN
    RAISE EXCEPTION
      'notifications contains invalid priority values; fix data before applying schema alignment';
  END IF;

  IF EXISTS (
    SELECT external_id
    FROM notifications
    WHERE external_id IS NOT NULL
    GROUP BY external_id
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION
      'notifications contains duplicate external_id values; fix duplicates before applying unique partial index';
  END IF;
END;
$$;

ALTER TABLE notifications
    ALTER COLUMN id SET DEFAULT gen_random_uuid(),
    ALTER COLUMN recipient TYPE VARCHAR(32),
    ALTER COLUMN recipient SET NOT NULL,
    ALTER COLUMN message TYPE TEXT,
    ALTER COLUMN message SET NOT NULL,
    ALTER COLUMN type TYPE VARCHAR(32),
    ALTER COLUMN type SET DEFAULT 'whatsapp',
    ALTER COLUMN type SET NOT NULL,
    ALTER COLUMN priority TYPE VARCHAR(32),
    ALTER COLUMN priority SET DEFAULT 'normal',
    ALTER COLUMN priority SET NOT NULL,
    ALTER COLUMN status TYPE VARCHAR(32),
    ALTER COLUMN status SET DEFAULT 'pending',
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN provider TYPE VARCHAR(32),
    ALTER COLUMN provider SET DEFAULT 'uazapi',
    ALTER COLUMN provider SET NOT NULL,
    ALTER COLUMN provider_response TYPE JSONB USING provider_response,
    ALTER COLUMN metadata TYPE JSONB USING metadata,
    ALTER COLUMN attempt_count SET DEFAULT 0,
    ALTER COLUMN attempt_count SET NOT NULL,
    ALTER COLUMN created_at SET DEFAULT NOW(),
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT NOW(),
    ALTER COLUMN updated_at SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'notifications_pkey'
      AND conrelid = 'notifications'::regclass
  ) THEN
    ALTER TABLE notifications
      ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_notifications_status'
      AND conrelid = 'notifications'::regclass
  ) THEN
    ALTER TABLE notifications
      ADD CONSTRAINT chk_notifications_status
      CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_notifications_type'
      AND conrelid = 'notifications'::regclass
  ) THEN
    ALTER TABLE notifications
      ADD CONSTRAINT chk_notifications_type
      CHECK (type IN ('whatsapp'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_notifications_priority'
      AND conrelid = 'notifications'::regclass
  ) THEN
    ALTER TABLE notifications
      ADD CONSTRAINT chk_notifications_priority
      CHECK (priority IN ('low', 'normal', 'high'));
  END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_external_id_not_null
    ON notifications (external_id)
    WHERE external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_notifications_status_created_at
    ON notifications (status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_notifications_recipient_created_at
    ON notifications (recipient, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_notifications_last_job_id
    ON notifications (last_job_id);

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON notifications;

CREATE TRIGGER trg_notifications_updated_at
BEFORE UPDATE ON notifications
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
