-- 017_labour_engine.sql
-- Indian Labour Compliance Engine
-- Extends india_minimum_wages with:
--   • industry column (HOSPITALITY | CONSTRUCTION | AGRICULTURE | RETAIL | ALL)
--   • Seed data for all remaining 26 states/UTs (2024-2025 gazette rates)
-- Adds shift_rest_log table for 12-hour rest-between-shifts tracking
-- Law refs: Minimum Wages Act 1948, Code on Wages 2019, OSH Code 2020

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Add industry dimension to minimum wages table
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE india_minimum_wages
    ADD COLUMN IF NOT EXISTS industry VARCHAR(30) DEFAULT 'ALL';
    -- ALL | HOSPITALITY | CONSTRUCTION | AGRICULTURE | RETAIL | MANUFACTURING | SECURITY

-- Back-fill existing rows as HOSPITALITY (all 014 seed data is for hospitality sector)
UPDATE india_minimum_wages SET industry = 'HOSPITALITY' WHERE industry = 'ALL';

-- Index for industry lookups
CREATE INDEX IF NOT EXISTS min_wages_industry
    ON india_minimum_wages(state_code, industry, skill_category, is_current);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Shift rest log — tracks gap between consecutive shifts for 12h rule
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shift_rest_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_id        UUID REFERENCES candidates(id) ON DELETE SET NULL,
    previous_shift_end  TIMESTAMP NOT NULL,
    current_shift_start TIMESTAMP NOT NULL,
    rest_hours          NUMERIC(5,2) GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (current_shift_start - previous_shift_end)) / 3600
    ) STORED,
    is_violation        BOOLEAN GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (current_shift_start - previous_shift_end)) / 3600 < 12
    ) STORED,
    state_code          VARCHAR(5),
    applicable_act      VARCHAR(80) DEFAULT 'OSH Code 2020 / State Shops & Establishments Act',
    resolved            BOOLEAN DEFAULT FALSE,
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS shift_rest_candidate ON shift_rest_log(candidate_id);
CREATE INDEX IF NOT EXISTS shift_rest_violations ON shift_rest_log(org_id, is_violation) WHERE is_violation;

ALTER TABLE shift_rest_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS shift_rest_org ON shift_rest_log;
CREATE POLICY shift_rest_org ON shift_rest_log
    USING (org_id = (SELECT org_id FROM users WHERE id = auth.uid()));

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Seed remaining 26 states / UTs (2024-2025 gazette rates, hospitality sector)
--    Existing 10 states: MH DL KA TN GA RJ KL WB TS UP
-- ─────────────────────────────────────────────────────────────────────────────

-- Andhra Pradesh (AP) — G.O.Ms.No.21 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('AP','Andhra Pradesh','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',423.08,11000,'2024-04-01',true,'AP G.O.Ms.No.21 2024'),
('AP','Andhra Pradesh','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',480.77,12500,'2024-04-01',true,'AP G.O.Ms.No.21 2024'),
('AP','Andhra Pradesh','A','SKILLED',        'HOSPITALITY','Shops & Establishments',538.46,14000,'2024-04-01',true,'AP G.O.Ms.No.21 2024'),
('AP','Andhra Pradesh','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',615.38,16000,'2024-04-01',true,'AP G.O.Ms.No.21 2024');

-- Assam (AS) — Notification No.MLR.111/2023 dated 01-Jan-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('AS','Assam','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',315.85,8212,'2024-01-01',true,'AS MLR.111/2023'),
('AS','Assam','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',354.15,9208,'2024-01-01',true,'AS MLR.111/2023'),
('AS','Assam','A','SKILLED',        'HOSPITALITY','Shops & Establishments',397.12,10325,'2024-01-01',true,'AS MLR.111/2023'),
('AS','Assam','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',459.62,11950,'2024-01-01',true,'AS MLR.111/2023');

-- Bihar (BR) — Notification No.1(1)/MW/2023 dated 01-Oct-2023
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('BR','Bihar','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',280.54,7294,'2023-10-01',true,'BR MW Notif 1(1)/2023'),
('BR','Bihar','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',310.54,8074,'2023-10-01',true,'BR MW Notif 1(1)/2023'),
('BR','Bihar','A','SKILLED',        'HOSPITALITY','Shops & Establishments',350.31,9108,'2023-10-01',true,'BR MW Notif 1(1)/2023'),
('BR','Bihar','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',393.62,10234,'2023-10-01',true,'BR MW Notif 1(1)/2023');

-- Chhattisgarh (CG) — Notification No.F-17-2/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('CG','Chhattisgarh','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',320.00,8320,'2024-04-01',true,'CG F-17-2/2024'),
('CG','Chhattisgarh','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',355.38,9240,'2024-04-01',true,'CG F-17-2/2024'),
('CG','Chhattisgarh','A','SKILLED',        'HOSPITALITY','Shops & Establishments',387.69,10080,'2024-04-01',true,'CG F-17-2/2024'),
('CG','Chhattisgarh','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',429.23,11160,'2024-04-01',true,'CG F-17-2/2024');

-- Gujarat (GJ) — G.O. No.MW/2024/1 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('GJ','Gujarat','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',398.77,10368,'2024-04-01',true,'GJ G.O. MW/2024/1'),
('GJ','Gujarat','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',439.38,11424,'2024-04-01',true,'GJ G.O. MW/2024/1'),
('GJ','Gujarat','A','SKILLED',        'HOSPITALITY','Shops & Establishments',480.00,12480,'2024-04-01',true,'GJ G.O. MW/2024/1'),
('GJ','Gujarat','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',533.54,13872,'2024-04-01',true,'GJ G.O. MW/2024/1');

-- Haryana (HR) — Notification No.2/84/2023-4Lab dated 01-Jan-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('HR','Haryana','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',390.50,10153,'2024-01-01',true,'HR 2/84/2023-4Lab'),
('HR','Haryana','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',433.46,11270,'2024-01-01',true,'HR 2/84/2023-4Lab'),
('HR','Haryana','A','SKILLED',        'HOSPITALITY','Shops & Establishments',479.58,12469,'2024-01-01',true,'HR 2/84/2023-4Lab'),
('HR','Haryana','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',565.31,14698,'2024-01-01',true,'HR 2/84/2023-4Lab');

-- Himachal Pradesh (HP) — Notification No.LBR.A(3)-3/2023 dated 01-Jul-2023
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('HP','Himachal Pradesh','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',373.85,9720,'2023-07-01',true,'HP LBR.A(3)-3/2023'),
('HP','Himachal Pradesh','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',414.04,10765,'2023-07-01',true,'HP LBR.A(3)-3/2023'),
('HP','Himachal Pradesh','A','SKILLED',        'HOSPITALITY','Shops & Establishments',454.23,11810,'2023-07-01',true,'HP LBR.A(3)-3/2023'),
('HP','Himachal Pradesh','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',510.00,13260,'2023-07-01',true,'HP LBR.A(3)-3/2023');

-- Jharkhand (JH) — Notification No.S.O.1/Labour/MW/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('JH','Jharkhand','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',323.65,8415,'2024-04-01',true,'JH S.O.1/Labour/MW/2024'),
('JH','Jharkhand','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',357.54,9296,'2024-04-01',true,'JH S.O.1/Labour/MW/2024'),
('JH','Jharkhand','A','SKILLED',        'HOSPITALITY','Shops & Establishments',400.00,10400,'2024-04-01',true,'JH S.O.1/Labour/MW/2024'),
('JH','Jharkhand','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',452.08,11754,'2024-04-01',true,'JH S.O.1/Labour/MW/2024');

-- Jammu & Kashmir (JK) — J&K Govt Order No.23-LBR dated 01-Oct-2023
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('JK','Jammu & Kashmir','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',342.31,8900,'2023-10-01',true,'JK Order 23-LBR 2023'),
('JK','Jammu & Kashmir','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',380.77,9900,'2023-10-01',true,'JK Order 23-LBR 2023'),
('JK','Jammu & Kashmir','A','SKILLED',        'HOSPITALITY','Shops & Establishments',423.08,11000,'2023-10-01',true,'JK Order 23-LBR 2023'),
('JK','Jammu & Kashmir','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',480.77,12500,'2023-10-01',true,'JK Order 23-LBR 2023');

-- Madhya Pradesh (MP) — Notification No.F-14-3/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('MP','Madhya Pradesh','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',360.77,9380,'2024-04-01',true,'MP F-14-3/2024'),
('MP','Madhya Pradesh','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',397.69,10340,'2024-04-01',true,'MP F-14-3/2024'),
('MP','Madhya Pradesh','A','SKILLED',        'HOSPITALITY','Shops & Establishments',438.46,11400,'2024-04-01',true,'MP F-14-3/2024'),
('MP','Madhya Pradesh','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',491.54,12780,'2024-04-01',true,'MP F-14-3/2024');

-- Manipur (MN) — Notification No.2/1/MW/Lab dated 01-Jan-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('MN','Manipur','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',326.00,8476,'2024-01-01',true,'MN 2/1/MW/Lab 2024'),
('MN','Manipur','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',360.08,9362,'2024-01-01',true,'MN 2/1/MW/Lab 2024'),
('MN','Manipur','A','SKILLED',        'HOSPITALITY','Shops & Establishments',400.00,10400,'2024-01-01',true,'MN 2/1/MW/Lab 2024'),
('MN','Manipur','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',448.62,11664,'2024-01-01',true,'MN 2/1/MW/Lab 2024');

-- Meghalaya (ML) — Notification No.LBR.A/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('ML','Meghalaya','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',315.85,8212,'2024-04-01',true,'ML LBR.A/2024'),
('ML','Meghalaya','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',350.00,9100,'2024-04-01',true,'ML LBR.A/2024'),
('ML','Meghalaya','A','SKILLED',        'HOSPITALITY','Shops & Establishments',384.62,10000,'2024-04-01',true,'ML LBR.A/2024'),
('ML','Meghalaya','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',432.69,11250,'2024-04-01',true,'ML LBR.A/2024');

-- Mizoram (MZ) — Notification No.B-13011/4/2023 dated 01-Jan-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('MZ','Mizoram','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',336.54,8750,'2024-01-01',true,'MZ B-13011/4/2023'),
('MZ','Mizoram','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',370.19,9625,'2024-01-01',true,'MZ B-13011/4/2023'),
('MZ','Mizoram','A','SKILLED',        'HOSPITALITY','Shops & Establishments',403.85,10500,'2024-01-01',true,'MZ B-13011/4/2023'),
('MZ','Mizoram','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',451.92,11750,'2024-01-01',true,'MZ B-13011/4/2023');

-- Nagaland (NL) — Notification No.LBR-229/2023 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('NL','Nagaland','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',325.00,8450,'2024-04-01',true,'NL LBR-229/2023'),
('NL','Nagaland','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',357.50,9295,'2024-04-01',true,'NL LBR-229/2023'),
('NL','Nagaland','A','SKILLED',        'HOSPITALITY','Shops & Establishments',390.15,10144,'2024-04-01',true,'NL LBR-229/2023'),
('NL','Nagaland','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',437.50,11375,'2024-04-01',true,'NL LBR-229/2023');

-- Odisha (OD) — Notification No.LB-III-MW-17/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('OD','Odisha','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',336.00,8736,'2024-04-01',true,'OD LB-III-MW-17/2024'),
('OD','Odisha','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',372.00,9672,'2024-04-01',true,'OD LB-III-MW-17/2024'),
('OD','Odisha','A','SKILLED',        'HOSPITALITY','Shops & Establishments',408.00,10608,'2024-04-01',true,'OD LB-III-MW-17/2024'),
('OD','Odisha','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',457.00,11880,'2024-04-01',true,'OD LB-III-MW-17/2024');

-- Punjab (PB) — Notification No.3/MW/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('PB','Punjab','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',375.62,9766,'2024-04-01',true,'PB 3/MW/2024'),
('PB','Punjab','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',413.58,10753,'2024-04-01',true,'PB 3/MW/2024'),
('PB','Punjab','A','SKILLED',        'HOSPITALITY','Shops & Establishments',455.35,11839,'2024-04-01',true,'PB 3/MW/2024'),
('PB','Punjab','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',511.73,13305,'2024-04-01',true,'PB 3/MW/2024');

-- Sikkim (SK) — Notification No.97/LD/SK dated 01-Jan-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('SK','Sikkim','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',353.85,9200,'2024-01-01',true,'SK 97/LD/SK 2024'),
('SK','Sikkim','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',389.23,10120,'2024-01-01',true,'SK 97/LD/SK 2024'),
('SK','Sikkim','A','SKILLED',        'HOSPITALITY','Shops & Establishments',427.69,11120,'2024-01-01',true,'SK 97/LD/SK 2024'),
('SK','Sikkim','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',486.54,12650,'2024-01-01',true,'SK 97/LD/SK 2024');

-- Tripura (TR) — Notification No.F.5(86)-L/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('TR','Tripura','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',326.00,8476,'2024-04-01',true,'TR F.5(86)-L/2024'),
('TR','Tripura','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',360.08,9362,'2024-04-01',true,'TR F.5(86)-L/2024'),
('TR','Tripura','A','SKILLED',        'HOSPITALITY','Shops & Establishments',400.00,10400,'2024-04-01',true,'TR F.5(86)-L/2024'),
('TR','Tripura','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',448.62,11664,'2024-04-01',true,'TR F.5(86)-L/2024');

-- Uttarakhand (UK) — Notification No.1248/XXVII(2)/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('UK','Uttarakhand','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',389.23,10120,'2024-04-01',true,'UK 1248/XXVII(2)/2024'),
('UK','Uttarakhand','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',432.00,11232,'2024-04-01',true,'UK 1248/XXVII(2)/2024'),
('UK','Uttarakhand','A','SKILLED',        'HOSPITALITY','Shops & Establishments',474.77,12344,'2024-04-01',true,'UK 1248/XXVII(2)/2024'),
('UK','Uttarakhand','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',532.62,13848,'2024-04-01',true,'UK 1248/XXVII(2)/2024');

-- Arunachal Pradesh (AR) — Notification No.Lab/MW/2024 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('AR','Arunachal Pradesh','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',326.92,8500,'2024-04-01',true,'AR Lab/MW/2024'),
('AR','Arunachal Pradesh','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',359.62,9350,'2024-04-01',true,'AR Lab/MW/2024'),
('AR','Arunachal Pradesh','A','SKILLED',        'HOSPITALITY','Shops & Establishments',394.23,10250,'2024-04-01',true,'AR Lab/MW/2024'),
('AR','Arunachal Pradesh','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',442.31,11500,'2024-04-01',true,'AR Lab/MW/2024');

-- ─── Union Territories (Central Govt rates 2024-2025) ─────────────────────

-- Andaman & Nicobar Islands (AN) — Central Govt Notif dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('AN','A&N Islands','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',570.85,14842,'2024-04-01',true,'Central Notif 2024-25'),
('AN','A&N Islands','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',632.62,16448,'2024-04-01',true,'Central Notif 2024-25'),
('AN','A&N Islands','A','SKILLED',        'HOSPITALITY','Shops & Establishments',695.00,18060,'2024-04-01',true,'Central Notif 2024-25'),
('AN','A&N Islands','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',783.00,20358,'2024-04-01',true,'Central Notif 2024-25');

-- Chandigarh (CH) — Central Govt Notif (same as DL rates for UTs) 2024-04-01
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('CH','Chandigarh','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',570.85,14842,'2024-04-01',true,'Central Notif 2024-25'),
('CH','Chandigarh','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',632.62,16448,'2024-04-01',true,'Central Notif 2024-25'),
('CH','Chandigarh','A','SKILLED',        'HOSPITALITY','Shops & Establishments',695.00,18060,'2024-04-01',true,'Central Notif 2024-25'),
('CH','Chandigarh','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',783.00,20358,'2024-04-01',true,'Central Notif 2024-25');

-- Dadra & Nagar Haveli and Daman & Diu (DD) — Central Govt Notif 2024-04-01
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('DD','D&NH and D&D','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',570.85,14842,'2024-04-01',true,'Central Notif 2024-25'),
('DD','D&NH and D&D','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',632.62,16448,'2024-04-01',true,'Central Notif 2024-25'),
('DD','D&NH and D&D','A','SKILLED',        'HOSPITALITY','Shops & Establishments',695.00,18060,'2024-04-01',true,'Central Notif 2024-25'),
('DD','D&NH and D&D','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',783.00,20358,'2024-04-01',true,'Central Notif 2024-25');

-- Ladakh (LA) — J&K Reorganisation rates (UT) 2023-10-01
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('LA','Ladakh','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',500.00,13000,'2023-10-01',true,'LA UT Notif 2023'),
('LA','Ladakh','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',553.85,14400,'2023-10-01',true,'LA UT Notif 2023'),
('LA','Ladakh','A','SKILLED',        'HOSPITALITY','Shops & Establishments',607.69,15800,'2023-10-01',true,'LA UT Notif 2023'),
('LA','Ladakh','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',683.08,17760,'2023-10-01',true,'LA UT Notif 2023');

-- Lakshadweep (LD) — Central Govt Notif 2024-04-01
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('LD','Lakshadweep','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',570.85,14842,'2024-04-01',true,'Central Notif 2024-25'),
('LD','Lakshadweep','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',632.62,16448,'2024-04-01',true,'Central Notif 2024-25'),
('LD','Lakshadweep','A','SKILLED',        'HOSPITALITY','Shops & Establishments',695.00,18060,'2024-04-01',true,'Central Notif 2024-25'),
('LD','Lakshadweep','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',783.00,20358,'2024-04-01',true,'Central Notif 2024-25');

-- Puducherry (PY) — Notif No.LD/MW/2024/1 dated 01-Apr-2024
INSERT INTO india_minimum_wages (state_code, state_name, zone, skill_category, industry, sector,
    daily_wage_inr, monthly_wage_inr, effective_from, is_current, source) VALUES
('PY','Puducherry','A','UNSKILLED',      'HOSPITALITY','Shops & Establishments',365.38,9500,'2024-04-01',true,'PY LD/MW/2024/1'),
('PY','Puducherry','A','SEMI_SKILLED',   'HOSPITALITY','Shops & Establishments',403.85,10500,'2024-04-01',true,'PY LD/MW/2024/1'),
('PY','Puducherry','A','SKILLED',        'HOSPITALITY','Shops & Establishments',442.31,11500,'2024-04-01',true,'PY LD/MW/2024/1'),
('PY','Puducherry','A','HIGHLY_SKILLED', 'HOSPITALITY','Shops & Establishments',496.15,12900,'2024-04-01',true,'PY LD/MW/2024/1');

COMMIT;
