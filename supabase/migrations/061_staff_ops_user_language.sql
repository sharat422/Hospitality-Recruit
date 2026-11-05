-- Per-person language preference for Staff Ops (PLAN.md decision 8).
--
-- Language belongs to the person, not the hotel: a Tamil-speaking steward
-- should get Tamil in a Bengaluru hotel. When this is NULL the app falls back
-- to the hotel's state default (properties.state), then to English.
BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(5);

DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_preferred_language_check
        CHECK (preferred_language IS NULL
               OR preferred_language IN ('en','hi','te','ta','kn'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON COLUMN users.preferred_language IS
    'Staff Ops UI language. NULL = derive from the hotel state, then English.';

COMMIT;
