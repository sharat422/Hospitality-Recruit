-- =============================================================================
-- 025_smart_recruitment.sql
-- Smart Recruitment module for Indian hotel hiring.
--
-- New / extended:
--   jobs              — property, department, role template, Hindi+English JD,
--                       salary range, source tracking, apply URL, QR URL
--   candidates        — interview/offer/hire timestamps, rejection fields,
--                       offer salary, QR-apply flag
--   role_templates    — 10 seeded hospitality roles with Hindi+English JDs
--   mobile_otp_sessions — 6-digit OTP for WhatsApp/Naukri/Apna mobile apply
--   job_qr_scans      — per-scan audit for QR-code apply links
-- =============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Extend jobs
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE jobs
    -- Property & team context
    ADD COLUMN IF NOT EXISTS property_name      VARCHAR(200),
    ADD COLUMN IF NOT EXISTS department         VARCHAR(100),
    ADD COLUMN IF NOT EXISTS role_template      VARCHAR(100),
    -- REFERENCES role_templates(role_key) — not FK because templates may change
    ADD COLUMN IF NOT EXISTS location_city      VARCHAR(100),
    ADD COLUMN IF NOT EXISTS location_state     VARCHAR(100),

    -- Bilingual JDs (Req 2)
    ADD COLUMN IF NOT EXISTS jd_english         TEXT,
    ADD COLUMN IF NOT EXISTS jd_hindi           TEXT,

    -- Compensation
    ADD COLUMN IF NOT EXISTS salary_min_inr     INTEGER,
    ADD COLUMN IF NOT EXISTS salary_max_inr     INTEGER,
    ADD COLUMN IF NOT EXISTS experience_min_years SMALLINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS experience_max_years SMALLINT,

    -- Operational
    ADD COLUMN IF NOT EXISTS openings_count     SMALLINT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS is_urgent          BOOLEAN  NOT NULL DEFAULT FALSE,

    -- Apply links (Req 6)
    ADD COLUMN IF NOT EXISTS apply_url          TEXT,
    ADD COLUMN IF NOT EXISTS qr_url             TEXT,

    -- Source stats aggregated per job (Req 3)
    -- Keys: naukri|apna|workindia|shine|indeed_india|whatsapp|referral|walk_in|qr_code|other
    ADD COLUMN IF NOT EXISTS source_stats       JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS jobs_property ON jobs(org_id, property_name)
    WHERE property_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS jobs_department ON jobs(org_id, department)
    WHERE department IS NOT NULL;
CREATE INDEX IF NOT EXISTS jobs_urgent ON jobs(org_id, is_urgent)
    WHERE is_urgent = TRUE AND status = 'open';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Extend candidates
-- ─────────────────────────────────────────────────────────────────────────────

-- Source detail (who referred / which portal job ID) (Req 3)
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS source_detail      VARCHAR(200);

-- Pipeline timestamps for the 5-stage funnel (Req 7)
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS interview_at       TIMESTAMP,
    ADD COLUMN IF NOT EXISTS offered_at         TIMESTAMP,
    ADD COLUMN IF NOT EXISTS hired_at           TIMESTAMP;

-- Rejection tracking
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS rejection_reason   VARCHAR(200),
    ADD COLUMN IF NOT EXISTS rejection_stage    VARCHAR(50);
    -- stage where rejected: screened | interview | offer

-- Interview & offer details
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS interview_notes    TEXT,
    ADD COLUMN IF NOT EXISTS offer_salary_inr   INTEGER,

    -- True when candidate applied via QR code (Req 6)
    ADD COLUMN IF NOT EXISTS applied_via_qr     BOOLEAN NOT NULL DEFAULT FALSE,

    -- Job this candidate applied for (may be NULL for old records)
    ADD COLUMN IF NOT EXISTS applied_job_id     UUID REFERENCES jobs(id) ON DELETE SET NULL;

-- Allowed pipeline_stage values (documentation — enforced at app layer):
--   applied | screened | interview | offer | hired | rejected

CREATE INDEX IF NOT EXISTS cand_pipeline ON candidates(org_id, pipeline_stage);
CREATE INDEX IF NOT EXISTS cand_job      ON candidates(applied_job_id)
    WHERE applied_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cand_source   ON candidates(org_id, source);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. role_templates — seeded with 10 common Indian hospitality roles
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS role_templates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_key            VARCHAR(100) NOT NULL UNIQUE,
    display_name        VARCHAR(200) NOT NULL,
    display_name_hindi  VARCHAR(200),
    category            VARCHAR(50)  NOT NULL,
    -- F&B | Kitchen | Housekeeping | FrontOffice | Security | General
    department          VARCHAR(100),
    jd_english          TEXT NOT NULL,
    jd_hindi            TEXT NOT NULL,
    required_skills     JSONB DEFAULT '[]',
    preferred_certs     JSONB DEFAULT '[]',
    min_experience_years SMALLINT DEFAULT 0,
    salary_min_inr      INTEGER,
    salary_max_inr      INTEGER,
    created_at          TIMESTAMP DEFAULT NOW()
);

INSERT INTO role_templates
    (role_key, display_name, display_name_hindi, category, department,
     jd_english, jd_hindi, required_skills, preferred_certs,
     min_experience_years, salary_min_inr, salary_max_inr)
VALUES

-- F&B Service
('waiter',
 'Waiter / Server', 'वेटर / सर्वर', 'F&B', 'Food & Beverage',
 'We are looking for a courteous and energetic Waiter to join our F&B team. You will take orders, serve food and beverages, and ensure every guest receives warm, professional hospitality. Experience in a hotel or restaurant is preferred but we welcome freshers with good communication skills.',
 'हम अपनी F&B टीम में एक विनम्र और ऊर्जावान वेटर की तलाश कर रहे हैं। आप ऑर्डर लेंगे, खाना और पेय परोसेंगे, और सुनिश्चित करेंगे कि प्रत्येक अतिथि को गर्मजोशी भरी, पेशेवर आतिथ्य सेवा मिले। होटल या रेस्तरां में अनुभव पसंद किया जाएगा, लेकिन अच्छी संचार कौशल वाले फ्रेशर्स का स्वागत है।',
 '["Guest service", "Menu knowledge", "Table setting", "POS system", "Upselling"]',
 '["FSSAI Basic Food Hygiene", "FOSTAC"]',
 0, 12000, 22000),

('captain_waiter',
 'Captain Waiter', 'कैप्टेन वेटर', 'F&B', 'Food & Beverage',
 'We are seeking an experienced Captain Waiter to lead a table section and guide junior service staff. You will train team members, handle guest escalations, manage mise en place, and ensure SOP compliance. Minimum 2 years of hotel F&B experience required.',
 'हम एक अनुभवी कैप्टेन वेटर की तलाश कर रहे हैं जो एक टेबल सेक्शन का नेतृत्व करें और जूनियर सर्विस स्टाफ का मार्गदर्शन करें। आप टीम के सदस्यों को प्रशिक्षित करेंगे, अतिथि की शिकायतें संभालेंगे, और SOP अनुपालन सुनिश्चित करेंगे। न्यूनतम 2 वर्ष का होटल F&B अनुभव आवश्यक है।',
 '["Team leadership", "Guest escalation", "Menu expertise", "Training", "POS systems"]',
 '["FSSAI", "Food Safety Supervisor Certificate"]',
 2, 18000, 30000),

('banquet_waiter',
 'Banquet Waiter', 'बैंक्वेट वेटर', 'F&B', 'Banquet',
 'Join our Banquet team as a Banquet Waiter and help deliver exceptional event experiences. You will set up banquet halls, serve during events, coordinate with the kitchen, and maintain cleanliness throughout. Experience in large-scale banquet service preferred.',
 'हमारी बैंक्वेट टीम में बैंक्वेट वेटर के रूप में जुड़ें और असाधारण इवेंट अनुभव प्रदान करने में मदद करें। आप बैंक्वेट हॉल सेट करेंगे, इवेंट के दौरान सर्व करेंगे, और किचन के साथ समन्वय करेंगे। बड़े बैंक्वेट सर्विस में अनुभव पसंद किया जाएगा।',
 '["Banquet setup", "High-volume service", "Event coordination", "Team work"]',
 '["FSSAI Basic Food Hygiene", "FOSTAC"]',
 0, 12000, 20000),

-- Kitchen
('kitchen_helper',
 'Kitchen Helper', 'किचन हेल्पर', 'Kitchen', 'Kitchen',
 'We need a Kitchen Helper to support our culinary team with cleaning, prep work, and basic cooking assistance. This is an excellent entry-level role for anyone looking to start a career in the hospitality kitchen. No prior experience required — we will train you.',
 'हमें अपनी पाक टीम को सफाई, प्रेप वर्क और बुनियादी खाना पकाने की सहायता में समर्थन देने के लिए किचन हेल्पर की आवश्यकता है। यह आतिथ्य किचन में करियर शुरू करने के इच्छुक किसी के लिए एक उत्कृष्ट एंट्री-लेवल भूमिका है। कोई पूर्व अनुभव आवश्यक नहीं — हम आपको प्रशिक्षित करेंगे।',
 '["Kitchen hygiene", "Basic knife skills", "Food storage", "Station prep"]',
 '["FSSAI Basic Food Hygiene"]',
 0, 10000, 16000),

('commis_chef',
 'Commis Chef', 'कमी शेफ', 'Kitchen', 'Kitchen',
 'We are looking for a Commis Chef with culinary training or 1 year of kitchen experience. You will prepare ingredients, cook assigned dishes under CDP supervision, maintain kitchen hygiene, and follow HACCP standards. Hotel culinary certification is an advantage.',
 'हम पाक प्रशिक्षण या 1 वर्ष के किचन अनुभव के साथ एक कमी शेफ की तलाश कर रहे हैं। आप सामग्री तैयार करेंगे, CDP पर्यवेक्षण में निर्धारित व्यंजन पकाएंगे, किचन स्वच्छता बनाए रखेंगे। होटल पाक प्रमाणन एक लाभ है।',
 '["Culinary techniques", "HACCP", "Station management", "Recipe adherence"]',
 '["FSSAI", "FOSTAC", "Culinary Diploma (preferred)"]',
 1, 14000, 22000),

('sous_chef',
 'Sous Chef', 'सू शेफ', 'Kitchen', 'Kitchen',
 'Experienced Sous Chef required to support the Head Chef in managing kitchen operations, menu development, staff training, and food cost control. Must have 5+ years of hotel or restaurant kitchen experience at 4/5-star level.',
 'हेड शेफ को किचन संचालन, मेनू विकास, स्टाफ प्रशिक्षण और फूड कॉस्ट नियंत्रण में सहयोग करने के लिए अनुभवी सू शेफ की आवश्यकता है। 4/5-स्टार स्तर के होटल या रेस्तरां किचन में 5+ वर्ष का अनुभव होना चाहिए।',
 '["Kitchen management", "Menu development", "Cost control", "Staff training", "HACCP"]',
 '["FSSAI License", "Culinary Arts Certificate", "Food Safety Management"]',
 5, 35000, 65000),

-- Housekeeping
('room_attendant',
 'Room Attendant', 'रूम अटेंडेंट', 'Housekeeping', 'Housekeeping',
 'We are hiring Room Attendants to maintain our guest rooms and public areas to the highest cleanliness standards. You will clean rooms, replenish amenities, handle lost and found, and report maintenance issues. Prior hotel housekeeping experience preferred.',
 'हम अपने अतिथि कमरों और सार्वजनिक क्षेत्रों को उच्चतम स्वच्छता मानकों पर बनाए रखने के लिए रूम अटेंडेंट भर्ती कर रहे हैं। आप कमरे साफ करेंगे, सुविधाएं भरेंगे और रखरखाव की समस्याओं की रिपोर्ट करेंगे। होटल हाउसकीपिंग अनुभव पसंद किया जाएगा।',
 '["Cleaning standards", "Chemical handling", "Linen management", "Guest privacy"]',
 '["Housekeeping Certificate", "Chemical Handling Safety"]',
 0, 11000, 18000),

('housekeeping_supervisor',
 'Housekeeping Supervisor', 'हाउसकीपिंग सुपरवाइजर', 'Housekeeping', 'Housekeeping',
 'Experienced Housekeeping Supervisor required to manage a team of room attendants, conduct quality inspections, manage linen inventory, and handle guest requests. Must have 3+ years of hotel housekeeping experience with at least 1 year in a supervisory role.',
 'रूम अटेंडेंट की टीम का प्रबंधन करने, गुणवत्ता निरीक्षण करने, लिनन इन्वेंटरी प्रबंधित करने के लिए अनुभवी हाउसकीपिंग सुपरवाइजर की आवश्यकता है। 3+ वर्ष का होटल हाउसकीपिंग अनुभव और कम से कम 1 वर्ष पर्यवेक्षी भूमिका में होना चाहिए।',
 '["Team management", "Quality inspection", "Inventory control", "Guest relations"]',
 '["Housekeeping Management Certificate", "First Aid"]',
 3, 20000, 35000),

-- Front Office
('receptionist',
 'Receptionist / Front Desk Agent', 'रिसेप्शनिस्ट', 'FrontOffice', 'Front Office',
 'Join our Front Office team as a Receptionist and be the face of our hotel. You will manage check-in/check-out, handle guest queries, coordinate with housekeeping, and use our PMS (Opera/IDS). Excellent communication in Hindi and English required.',
 'हमारी फ्रंट ऑफिस टीम में रिसेप्शनिस्ट के रूप में जुड़ें और हमारे होटल का चेहरा बनें। आप चेक-इन/चेक-आउट प्रबंधित करेंगे, अतिथि प्रश्नों को संभालेंगे, और हमारे PMS (Opera/IDS) का उपयोग करेंगे। हिंदी और अंग्रेजी में उत्कृष्ट संचार आवश्यक है।',
 '["PMS software", "Check-in/check-out", "Guest relations", "Billing", "Upselling"]',
 '["Hospitality Front Office Certificate", "Fire Safety"]',
 0, 15000, 25000),

-- Security
('security_guard',
 'Security Guard', 'सुरक्षा गार्ड', 'Security', 'Security',
 'We are looking for vigilant Security Guards to maintain safety and security at our property. You will monitor access, patrol premises, manage CCTV, respond to emergencies, and maintain incident logs. PSARA license required.',
 'हम अपनी संपत्ति पर सुरक्षा बनाए रखने के लिए सतर्क सुरक्षा गार्डों की तलाश कर रहे हैं। आप पहुंच की निगरानी करेंगे, परिसर में गश्त करेंगे, CCTV प्रबंधित करेंगे और आपातकाल का जवाब देंगे। PSARA लाइसेंस आवश्यक है।',
 '["Access control", "Emergency response", "CCTV monitoring", "Incident reporting"]',
 '["PSARA License", "First Aid Certificate", "Fire Safety"]',
 1, 12000, 20000)

ON CONFLICT (role_key) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. mobile_otp_sessions — 60-second apply form with OTP login (Req 4)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mobile_otp_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone      VARCHAR(20)  NOT NULL,
    otp        VARCHAR(6)   NOT NULL,
    job_id     UUID         REFERENCES jobs(id)          ON DELETE CASCADE,
    org_id     UUID         REFERENCES organizations(id) ON DELETE CASCADE,
    attempts   SMALLINT     NOT NULL DEFAULT 0,
    verified   BOOLEAN      NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMP    NOT NULL,              -- 10 minutes from creation
    created_at TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS otp_phone_job ON mobile_otp_sessions(phone, job_id, verified);
-- Expire old sessions regularly (app-layer cleanup or pg_cron)


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. job_qr_scans — track every QR code scan (Req 6)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_qr_scans (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     UUID        NOT NULL REFERENCES jobs(id)          ON DELETE CASCADE,
    org_id     UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source     VARCHAR(50) NOT NULL DEFAULT 'qr_code',
    -- qr_code | noticeboard_qr | payslip_qr | poster_qr
    ip_address VARCHAR(45),
    user_agent TEXT,
    scanned_at TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS qr_job_date ON job_qr_scans(job_id, scanned_at DESC);

COMMIT;
