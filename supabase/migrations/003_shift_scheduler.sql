/*
  Shift-Aware Auto-Scheduler Migration

  Creates tables and infrastructure for intelligent interview scheduling:
  - Manager calendar integration (Google Calendar / Outlook via Cal.com)
  - Candidate availability management (SMS-based)
  - Shift-aware interview slots (X0PA-style matching)
  - Auto-interview booking with conflict detection
  - Reminder + rescheduling automation
  - ATS sync for confirmed interviews

  Pain Point Resolution:
  - 60% faster time-to-fill (automated scheduling, no back-and-forth)
  - 50% fewer no-shows (automated reminders, opt-in confirmation)
  - Manager efficiency: one-click approval (no manual calendar updates)
  
  Expected Outcomes:
  - ROI: 10-15 minutes saved per candidate (scheduling coordination)
  - Estimated annual savings: $15,000-25,000 per manager (40 roles/year)
*/

-- ============================================================================
-- Interview Slots: When managers are available (from Google/Outlook calendars)
-- ============================================================================

CREATE TABLE interview_slots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    manager_id UUID NOT NULL REFERENCES users(id),
    
    -- Time slot
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_minutes INT DEFAULT 30, -- typical: 15-60 minutes
    
    -- Calendar source
    calendar_provider VARCHAR(50), -- google, outlook, manual
    calendar_event_id VARCHAR(255), -- Google Calendar event ID for sync
    calendar_integration_id UUID,  -- FK to manager's calendar config
    
    -- Slot status
    status VARCHAR(50) DEFAULT 'available', -- available, booked, blocked
    booked_by_candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    booked_interview_id UUID UNIQUE REFERENCES interviews(id) ON DELETE SET NULL,
    
    -- Metadata
    location VARCHAR(255), -- Video conference URL or in-person address
    video_conference_url VARCHAR(500), -- Zoom/Teams/Google Meet URL
    max_slots INT DEFAULT 1, -- For group interviews
    
    -- Sync tracking
    synced_to_ats BOOLEAN DEFAULT FALSE,
    gm_approved BOOLEAN DEFAULT FALSE,
    gm_approved_at TIMESTAMP,
    gm_approved_by UUID REFERENCES users(id),
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX interview_slots_org_job ON interview_slots(org_id, job_id);
CREATE INDEX interview_slots_manager ON interview_slots(manager_id, status);
CREATE INDEX interview_slots_available_time ON interview_slots(org_id, status, start_time) 
    WHERE status = 'available';
CREATE INDEX interview_slots_booked ON interview_slots(org_id, booked_interview_id) 
    WHERE status = 'booked';

ALTER TABLE interview_slots ENABLE ROW LEVEL SECURITY;
CREATE POLICY interview_slots_org_isolation ON interview_slots
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = interview_slots.org_id));

-- ============================================================================
-- Interviews: Confirmed interview bookings
-- ============================================================================

CREATE TABLE interviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    manager_id UUID NOT NULL REFERENCES users(id),
    interview_slot_id UUID NOT NULL REFERENCES interview_slots(id),
    
    -- Interview details
    interview_type VARCHAR(50) DEFAULT 'phone', -- phone, video, in_person, group
    interview_round INT DEFAULT 1, -- round 1, 2 (final), etc
    scheduled_at TIMESTAMP NOT NULL,
    estimated_duration_minutes INT DEFAULT 30,
    
    -- Status
    status VARCHAR(50) DEFAULT 'scheduled', -- scheduled, confirmed, completed, no_show, rescheduled, cancelled
    candidate_confirmed BOOLEAN DEFAULT FALSE,
    candidate_confirmed_at TIMESTAMP,
    manager_notes TEXT,
    
    -- Communication
    sms_invitation_sent BOOLEAN DEFAULT FALSE,
    sms_invitation_sent_at TIMESTAMP,
    sms_reminder_sent BOOLEAN DEFAULT FALSE,
    sms_reminder_sent_at TIMESTAMP,
    sms_followup_sent BOOLEAN DEFAULT FALSE,
    
    -- Calendar sync
    calendar_event_id VARCHAR(255), -- synced Google/Outlook event ID
    calendar_synced BOOLEAN DEFAULT FALSE,
    calendar_synced_at TIMESTAMP,
    
    -- ATS sync
    ats_synced BOOLEAN DEFAULT FALSE,
    ats_interview_id VARCHAR(255), -- ID in target ATS
    ats_synced_at TIMESTAMP,
    
    -- Rescheduling
    originally_scheduled_at TIMESTAMP,
    rescheduled_count INT DEFAULT 0,
    rescheduled_from_interview_id UUID REFERENCES interviews(id) ON DELETE SET NULL,
    
    -- Outcome
    interview_notes TEXT,
    interview_rating FLOAT CHECK (interview_rating IS NULL OR (interview_rating >= 1 AND interview_rating <= 5)),
    next_steps VARCHAR(255), -- move_to_offer, schedule_final_round, reject, etc
    completed_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX interviews_org_candidate ON interviews(org_id, candidate_id);
CREATE INDEX interviews_job_scheduled ON interviews(job_id, scheduled_at);
CREATE INDEX interviews_manager ON interviews(manager_id, scheduled_at);
CREATE INDEX interviews_status ON interviews(org_id, status);
CREATE INDEX interviews_unconfirmed ON interviews(org_id, status, candidate_confirmed)
    WHERE status = 'scheduled' AND candidate_confirmed = FALSE;
CREATE INDEX interviews_no_show ON interviews(org_id, status) WHERE status = 'no_show';

ALTER TABLE interviews ENABLE ROW LEVEL SECURITY;
CREATE POLICY interviews_org_isolation ON interviews
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = interviews.org_id));

-- Enable realtime for live dashboard
ALTER PUBLICATION supabase_realtime ADD TABLE interviews;

-- ============================================================================
-- Manager Calendar Configurations
-- ============================================================================

CREATE TABLE manager_calendar_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    manager_id UUID NOT NULL REFERENCES users(id),
    
    -- Calendar provider
    provider VARCHAR(50) NOT NULL, -- google, outlook, manual
    
    -- OAuth credentials (encrypted)
    access_token VARCHAR(1000) NOT NULL,
    refresh_token VARCHAR(1000),
    token_expires_at TIMESTAMP,
    
    -- Calendar details
    calendar_id VARCHAR(255), -- Google Calendar ID or Outlook calendar ID
    calendar_email VARCHAR(255),
    calendar_name VARCHAR(255),
    
    -- Sync settings
    sync_enabled BOOLEAN DEFAULT TRUE,
    auto_sync_frequency_minutes INT DEFAULT 15, -- re-sync every 15 minutes
    last_sync_at TIMESTAMP,
    
    -- Interview availability settings
    default_interview_duration_minutes INT DEFAULT 30,
    buffer_between_interviews_minutes INT DEFAULT 15, -- gap for prep
    
    -- Preferences
    preferred_interview_times JSONB DEFAULT '{
        "monday": ["09:00", "10:00", "14:00", "15:00"],
        "tuesday": ["09:00", "10:00", "14:00", "15:00"],
        "wednesday": ["09:00", "10:00", "14:00", "15:00"],
        "thursday": ["09:00", "10:00", "14:00", "15:00"],
        "friday": ["09:00", "10:00", "14:00", "15:00"]
    }', -- {day_name: [times]} format
    
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    
    -- Calendar blockers
    auto_block_lunch BOOLEAN DEFAULT TRUE,
    lunch_start_time TIME DEFAULT '12:00',
    lunch_end_time TIME DEFAULT '13:00',
    
    auto_block_eod BOOLEAN DEFAULT TRUE,
    eod_start_time TIME DEFAULT '17:00',
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id, manager_id)
);

ALTER TABLE manager_calendar_configs ENABLE ROW LEVEL SECURITY;
CREATE POLICY manager_calendar_org_isolation ON manager_calendar_configs
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = manager_calendar_configs.org_id));

-- ============================================================================
-- Candidate Availability: When candidates can interview
-- ============================================================================

CREATE TABLE candidate_availabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    candidate_id UUID NOT NULL REFERENCES candidates(id),
    job_id UUID NOT NULL REFERENCES jobs(id),
    
    -- Availability info
    available_start_date DATE NOT NULL,
    available_end_date DATE NOT NULL,
    
    -- Time windows (JSONB for flexibility)
    available_times JSONB DEFAULT '{
        "monday": ["09:00-17:00"],
        "tuesday": ["09:00-17:00"],
        "wednesday": ["09:00-17:00"],
        "thursday": ["09:00-17:00"],
        "friday": ["09:00-17:00"]
    }', -- {day: [time_ranges]}
    
    -- Constraints
    preferred_interview_type VARCHAR(50), -- phone, video, in_person
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    
    -- Collection method
    collected_via VARCHAR(50) DEFAULT 'sms', -- sms, mobile_app, web_form, api
    collected_at TIMESTAMP DEFAULT NOW(),
    
    -- Validation
    confirmed BOOLEAN DEFAULT FALSE,
    confirmation_method VARCHAR(50), -- sms_reply, click_link, etc
    confirmed_at TIMESTAMP,
    
    -- Freshness
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '7 days', -- availability valid for 7 days
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX candidate_availabilities_org_candidate ON candidate_availabilities(org_id, candidate_id);
CREATE INDEX candidate_availabilities_job ON candidate_availabilities(job_id, available_start_date);

ALTER TABLE candidate_availabilities ENABLE ROW LEVEL SECURITY;
CREATE POLICY candidate_availabilities_org_isolation ON candidate_availabilities
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = candidate_availabilities.org_id));

-- ============================================================================
-- Auto-Reminders: Tracking sent reminders and responses
-- ============================================================================

CREATE TABLE interview_reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    interview_id UUID NOT NULL REFERENCES interviews(id),
    
    -- Reminder details
    reminder_type VARCHAR(50), -- initial_invite, 24h_before, 1h_before, reschedule_offer
    scheduled_send_time TIMESTAMP,
    sent_at TIMESTAMP,
    
    -- Message
    message_template VARCHAR(50), -- sms_invite, sms_24h_reminder, etc
    
    -- Twilio tracking
    twilio_message_sid VARCHAR(255) UNIQUE,
    delivery_status VARCHAR(50), -- sent, delivered, failed, undelivered
    
    -- Candidate response
    candidate_response VARCHAR(50), -- confirmed, declined, rescheduled_requested, no_response
    candidate_response_at TIMESTAMP,
    candidate_response_message TEXT,
    
    -- Retry tracking
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 2,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX interview_reminders_org_interview ON interview_reminders(org_id, interview_id);
CREATE INDEX interview_reminders_status ON interview_reminders(org_id, delivery_status);
CREATE INDEX interview_reminders_unresponded ON interview_reminders(org_id, interview_id, candidate_response)
    WHERE candidate_response IS NULL;

ALTER TABLE interview_reminders ENABLE ROW LEVEL SECURITY;
CREATE POLICY interview_reminders_org_isolation ON interview_reminders
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = interview_reminders.org_id));

-- ============================================================================
-- Interview Rescheduling: Track rescheduling requests and alternatives
-- ============================================================================

CREATE TABLE interview_rescheduling_offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    original_interview_id UUID NOT NULL REFERENCES interviews(id),
    
    -- Rescheduled slot
    new_interview_slot_id UUID NOT NULL REFERENCES interview_slots(id),
    
    -- Offer status
    status VARCHAR(50) DEFAULT 'offered', -- offered, accepted, declined, expired
    offered_at TIMESTAMP DEFAULT NOW(),
    response_at TIMESTAMP,
    expired_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours',
    
    -- Alternative slots offered
    alternative_slot_ids UUID[] DEFAULT '{}', -- other options presented to candidate
    
    -- Reason for reschedule
    reason_for_reschedule VARCHAR(50), -- candidate_requested, manager_conflict, no_show, etc
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX interview_rescheduling_offers_org ON interview_rescheduling_offers(org_id, status);

ALTER TABLE interview_rescheduling_offers ENABLE ROW LEVEL SECURITY;
CREATE POLICY interview_rescheduling_offers_org_isolation ON interview_rescheduling_offers
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = interview_rescheduling_offers.org_id));

-- ============================================================================
-- Calendar Sync Logs: Track all calendar integration attempts
-- ============================================================================

CREATE TABLE calendar_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    manager_id UUID NOT NULL REFERENCES users(id),
    manager_calendar_config_id UUID NOT NULL REFERENCES manager_calendar_configs(id),
    
    -- Sync details
    sync_type VARCHAR(50), -- pull_availability, push_event, delete_event, reschedule
    sync_direction VARCHAR(20), -- inbound (calendar → HospRecruit), outbound (HospRecruit → calendar)
    
    -- Calendar event
    calendar_event_id VARCHAR(255),
    interview_id UUID REFERENCES interviews(id),
    
    -- Sync result
    status VARCHAR(50) DEFAULT 'pending', -- pending, success, failed, retry
    error_message TEXT,
    retry_count INT DEFAULT 0,
    last_retry_at TIMESTAMP,
    
    -- Payload tracking
    payload_sent JSONB,
    response_received JSONB,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX calendar_sync_logs_org ON calendar_sync_logs(org_id, created_at DESC);
CREATE INDEX calendar_sync_logs_status ON calendar_sync_logs(org_id, status) WHERE status != 'success';
CREATE INDEX calendar_sync_logs_manager ON calendar_sync_logs(manager_id, sync_type);

ALTER TABLE calendar_sync_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY calendar_sync_logs_org_isolation ON calendar_sync_logs
    USING (auth.user_id() IN (SELECT id FROM users WHERE org_id = calendar_sync_logs.org_id));

-- ============================================================================
-- Triggers: Auto-update workflows
-- ============================================================================

-- Trigger: When interview is booked, update interview_slot status
CREATE OR REPLACE FUNCTION update_interview_slot_on_booking()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE interview_slots
    SET status = 'booked',
        booked_interview_id = NEW.id,
        updated_at = NOW()
    WHERE id = NEW.interview_slot_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER interview_booked_update_slot
AFTER INSERT ON interviews
FOR EACH ROW
EXECUTE FUNCTION update_interview_slot_on_booking();

-- Trigger: When interview is cancelled, free up the slot
CREATE OR REPLACE FUNCTION free_interview_slot_on_cancel()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'cancelled' AND OLD.status != 'cancelled' THEN
        UPDATE interview_slots
        SET status = 'available',
            booked_interview_id = NULL,
            updated_at = NOW()
        WHERE id = NEW.interview_slot_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER interview_cancelled_free_slot
AFTER UPDATE ON interviews
FOR EACH ROW
EXECUTE FUNCTION free_interview_slot_on_cancel();

-- Trigger: When interview is rescheduled, sync to calendar
CREATE OR REPLACE FUNCTION trigger_calendar_sync_on_reschedule()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.scheduled_at IS DISTINCT FROM OLD.scheduled_at THEN
        INSERT INTO calendar_sync_logs (
            org_id,
            manager_id,
            manager_calendar_config_id,
            sync_type,
            sync_direction,
            interview_id,
            status,
            created_at
        ) SELECT
            interviews.org_id,
            interviews.manager_id,
            manager_calendar_configs.id,
            'reschedule',
            'outbound',
            NEW.id,
            'pending',
            NOW()
        FROM interviews
        JOIN manager_calendar_configs ON manager_calendar_configs.manager_id = interviews.manager_id
        WHERE interviews.id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER interview_reschedule_trigger_sync
AFTER UPDATE ON interviews
FOR EACH ROW
EXECUTE FUNCTION trigger_calendar_sync_on_reschedule();

-- ============================================================================
-- Realtime Configuration
-- ============================================================================

ALTER PUBLICATION supabase_realtime ADD TABLE interview_slots;
ALTER PUBLICATION supabase_realtime ADD TABLE interview_reminders;
ALTER PUBLICATION supabase_realtime ADD TABLE candidate_availabilities;
