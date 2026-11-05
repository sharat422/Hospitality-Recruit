-- Staff Ops demo hotel. Step 4 of 4 (docs/staff-ops/DB_DESIGN.md).
--
-- SKIP THIS FILE IN PRODUCTION. It inserts fictional data.
--
-- Fixed UUIDs throughout so the file is re-runnable and so other seeds and
-- tests can reference these rows. Every insert is ON CONFLICT DO NOTHING.
--
-- Hyderabad/Telangana is chosen deliberately: it exercises the language
-- default, which should resolve to Telugu for this hotel.
--
-- Demo staff accounts need rows in auth.users, whose schema belongs to
-- Supabase and varies by version. That part is wrapped in an exception
-- handler: if it cannot run, the migration still completes and the hotel,
-- departments, designations, settings and casual pool are all usable.
BEGIN;

-- Preflight. The seed touches tables from all three preceding migrations, so
-- it names which one is missing rather than failing on the first insert.
DO $$
DECLARE missing TEXT[] := '{}';
BEGIN
    IF to_regclass('public.staff_ops_employee_profiles') IS NULL
       OR to_regclass('public.staff_ops_designations') IS NULL THEN
        missing := missing || '062_staff_ops_core.sql';
    END IF;
    IF to_regclass('public.staff_ops_casual_workers') IS NULL
       OR to_regclass('public.staff_ops_agency_monthly_compliance') IS NULL THEN
        missing := missing || '063_staff_ops_operations.sql';
    END IF;
    IF to_regclass('public.staff_ops_settings') IS NULL THEN
        missing := missing || '064_staff_ops_governance.sql';
    END IF;

    IF array_length(missing, 1) > 0 THEN
        RAISE EXCEPTION
          E'The demo seed cannot run yet.\n'
          'Apply first, in order: %\n'
          'Run supabase/migrations/CHECK_APPLIED.sql to see what is in place.',
          array_to_string(missing, ' then ');
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Organisation and hotel
-- ---------------------------------------------------------------------------
INSERT INTO organizations (id, name, industry)
VALUES ('d0000000-0000-4000-a000-000000000001', 'Sarovar Demo Hotels', 'hospitality')
ON CONFLICT (id) DO NOTHING;

INSERT INTO properties (
    id, org_id, name, type, code, location, city, state, country, postal_code,
    timezone, room_count, employee_capacity, star_rating, brand_color,
    contact_email, contact_phone, staff_ops_enabled
) VALUES (
    'd0000000-0000-4000-a000-000000000010',
    'd0000000-0000-4000-a000-000000000001',
    'Grand Sarovar Residency', 'HOTEL', 'GSR-HYD',
    'Banjara Hills, Hyderabad', 'Hyderabad', 'Telangana', 'India', '500034',
    'Asia/Kolkata', 120, 150, 4.5, '#7C3AED',
    'ops@demo-sarovar.example', '+914023456789', TRUE
) ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Departments
-- ---------------------------------------------------------------------------
INSERT INTO property_departments (id, org_id, property_id, code, name, budgeted_headcount)
VALUES
 ('d0000000-0000-4000-a000-000000000101','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','FRONT_OFFICE','Front Office',12),
 ('d0000000-0000-4000-a000-000000000102','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','HOUSEKEEPING','Housekeeping',28),
 ('d0000000-0000-4000-a000-000000000103','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','KITCHEN','Kitchen',22),
 ('d0000000-0000-4000-a000-000000000104','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','FB_SERVICE','F&B Service',20),
 ('d0000000-0000-4000-a000-000000000105','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','ENGINEERING','Engineering',8),
 ('d0000000-0000-4000-a000-000000000106','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','SECURITY','Security',10)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Shift templates
-- ---------------------------------------------------------------------------
-- Night crosses midnight; per PLAN decision it books to its START date.
INSERT INTO shift_templates (id, org_id, property_id, name, shift_type, start_time, end_time, break_minutes, color)
VALUES
 ('d0000000-0000-4000-a000-000000000201','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Morning','MORNING','07:00','15:00',30,'#2563EB'),
 ('d0000000-0000-4000-a000-000000000202','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Evening','EVENING','15:00','23:00',30,'#D97706'),
 ('d0000000-0000-4000-a000-000000000203','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Night','NIGHT','23:00','07:00',30,'#4338CA'),
 ('d0000000-0000-4000-a000-000000000204','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','General','GENERAL','09:00','18:00',60,'#059669')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Designations
-- ---------------------------------------------------------------------------
INSERT INTO staff_ops_designations (id, org_id, property_id, department_id, code, name, grade, display_order)
VALUES
 ('d0000000-0000-4000-a000-000000000301','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000101','FO_MANAGER','Front Office Manager','M2',10),
 ('d0000000-0000-4000-a000-000000000302','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000101','FO_AGENT','Front Office Agent','E2',20),
 ('d0000000-0000-4000-a000-000000000303','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000102','HK_SUPERVISOR','Housekeeping Supervisor','S1',30),
 ('d0000000-0000-4000-a000-000000000304','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000102','HK_ATTENDANT','Room Attendant','E1',40),
 ('d0000000-0000-4000-a000-000000000305','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000103','EXEC_CHEF','Executive Chef','M2',50),
 ('d0000000-0000-4000-a000-000000000306','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000103','COMMIS','Commis Chef','E1',60),
 ('d0000000-0000-4000-a000-000000000307','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000104','STEWARD','Steward','E1',70),
 ('d0000000-0000-4000-a000-000000000308','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000106','SECURITY_GUARD','Security Guard','E1',80)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Settings — every labour-law value, none hard-coded
-- ---------------------------------------------------------------------------
INSERT INTO staff_ops_settings (id, org_id, property_id, key, value, value_type, description, state_code, valid_from)
VALUES
 ('d0000000-0000-4000-a000-000000000401','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','ot_multiplier','2'::jsonb,'NUMBER','Overtime pay multiplier (Factories Act s.59)','TG','2026-04-01'),
 ('d0000000-0000-4000-a000-000000000402','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','max_ot_hours_per_day','2'::jsonb,'NUMBER','Maximum overtime hours in a day','TG','2026-04-01'),
 ('d0000000-0000-4000-a000-000000000403','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','daily_standard_hours','8'::jsonb,'NUMBER','Standard working hours before OT begins','TG','2026-04-01'),
 ('d0000000-0000-4000-a000-000000000404','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','casual_payment_mode','"SEPARATE_DAILY"'::jsonb,'STRING','How casual workers are paid','TG','2026-04-01'),
 ('d0000000-0000-4000-a000-000000000405','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','casual_rate_basis','"PER_SHIFT"'::jsonb,'STRING','Basis for casual worker rates','TG','2026-04-01'),
 ('d0000000-0000-4000-a000-000000000406','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','casual_leave_accrual','"NONE"'::jsonb,'STRING','Whether casuals accrue leave','TG','2026-04-01'),
 ('d0000000-0000-4000-a000-000000000407','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','comp_off_expiry_days','30'::jsonb,'NUMBER','Days before an earned comp-off lapses','TG','2026-04-01'),
 ('d0000000-0000-4000-a000-000000000408','d0000000-0000-4000-a000-000000000001',NULL,'epf_employer_contrib_pct','12'::jsonb,'NUMBER','EPF employer contribution (org-wide default)',NULL,'2026-04-01')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Attendance codes — copy the hospitality defaults for this hotel
-- ---------------------------------------------------------------------------
INSERT INTO attendance_codes (org_id, property_id, code, label_en, label_hi, lop_factor, counts_as_worked, consumes_leave_type, requires_approval, rules, display_order)
VALUES
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','P','Present','उपस्थित',0,TRUE,NULL,FALSE,'{}'::jsonb,10),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','WO','Weekly Off','साप्ताहिक अवकाश',0,FALSE,NULL,FALSE,'{}'::jsonb,20),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','H','Holiday','सार्वजनिक अवकाश',0,FALSE,NULL,FALSE,'{}'::jsonb,30),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','CL','Casual Leave','आकस्मिक अवकाश',0,FALSE,'CASUAL',TRUE,'{}'::jsonb,40),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','SL','Sick Leave','बीमारी अवकाश',0,FALSE,'SICK',TRUE,'{}'::jsonb,50),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','EL','Earned Leave','अर्जित अवकाश',0,FALSE,'EARNED',TRUE,'{}'::jsonb,60),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','CO','Comp Off','क्षतिपूर्ति अवकाश',0,FALSE,'COMP_OFF',TRUE,'{"earn_basis":"PER_OT_DAY","expiry_days":30}'::jsonb,70),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','HD','Half Day','आधा दिन',0.5,TRUE,NULL,FALSE,'{}'::jsonb,80),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','OD','On Duty (elsewhere)','ड्यूटी पर (बाहर)',0,TRUE,NULL,TRUE,'{}'::jsonb,90),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','LWP','Leave Without Pay','अवैतनिक अवकाश',1,FALSE,NULL,TRUE,'{}'::jsonb,100),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','A','Absent','अनुपस्थित',1,FALSE,NULL,FALSE,'{}'::jsonb,110)
ON CONFLICT (property_id, code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Agency and its compliance history
-- ---------------------------------------------------------------------------
INSERT INTO staff_ops_agencies (id, org_id, property_id, name, gstin, pan, contact_name, contact_phone,
                                contract_start, contract_end, clra_licence_number, clra_licence_expiry)
VALUES ('d0000000-0000-4000-a000-000000000501','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010',
        'Deccan Facility Services','36AABCD1234E1Z5','AABCD1234E','Ravi Kumar','+919812345670',
        '2026-04-01','2027-03-31','TG/CLRA/2026/00482','2027-03-31')
ON CONFLICT (id) DO NOTHING;

INSERT INTO staff_ops_agency_monthly_compliance
    (org_id, property_id, agency_id, period_year, period_month, doc_type, workers_covered, amount_inr, due_date, status)
VALUES
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000501',2026,8,'PF_CHALLAN',14,21400.00,'2026-09-15','VERIFIED'),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000501',2026,8,'ESI_CHALLAN',14,5800.00,'2026-09-15','VERIFIED'),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000501',2026,9,'PF_CHALLAN',14,21400.00,'2026-10-15','SUBMITTED'),
 ('d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','d0000000-0000-4000-a000-000000000501',2026,10,'PF_CHALLAN',NULL,NULL,'2026-11-15','PENDING')
ON CONFLICT (agency_id, period_year, period_month, doc_type) DO NOTHING;

-- VERIFIED rows need a verifier; the constraint is satisfied by backfilling
-- from whichever demo manager exists, so this runs after the users block.

-- ---------------------------------------------------------------------------
-- Casual pool — needs no login, so it seeds unconditionally
-- ---------------------------------------------------------------------------
INSERT INTO staff_ops_casual_workers
    (id, org_id, property_id, full_name, phone, preferred_language, day_rate_inr, skills, availability, rating, total_shifts, last_worked_on)
VALUES
 ('d0000000-0000-4000-a000-000000000601','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Venkatesh Rao','+919700000001','te',750.00,'["STEWARD","HK_ATTENDANT"]'::jsonb,'{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":false}'::jsonb,4.5,42,'2026-10-26'),
 ('d0000000-0000-4000-a000-000000000602','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Lakshmi Devi','+919700000002','te',700.00,'["HK_ATTENDANT"]'::jsonb,'{"mon":true,"tue":true,"wed":false,"thu":true,"fri":true,"sat":true,"sun":true}'::jsonb,4.8,67,'2026-10-27'),
 ('d0000000-0000-4000-a000-000000000603','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Imran Shaikh','+919700000003','hi',800.00,'["COMMIS","STEWARD"]'::jsonb,'{"mon":false,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":true}'::jsonb,4.2,23,'2026-10-20'),
 ('d0000000-0000-4000-a000-000000000604','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Anitha Reddy','+919700000004','te',750.00,'["STEWARD"]'::jsonb,'{"mon":true,"tue":true,"wed":true,"thu":false,"fri":true,"sat":true,"sun":true}'::jsonb,4.0,15,'2026-10-18'),
 ('d0000000-0000-4000-a000-000000000605','d0000000-0000-4000-a000-000000000001','d0000000-0000-4000-a000-000000000010','Suresh Babu','+919700000005','te',900.00,'["SECURITY_GUARD"]'::jsonb,'{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":false,"sun":false}'::jsonb,4.6,51,'2026-10-25')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Occupancy forecast — 14 days, drives staffing demand
-- ---------------------------------------------------------------------------
INSERT INTO pms_occupancy_forecasts
    (org_id, property_id, business_date, rooms_available, rooms_sold, occupancy_pct, arrivals, departures, source)
SELECT 'd0000000-0000-4000-a000-000000000001',
       'd0000000-0000-4000-a000-000000000010',
       day::date, 120, sold, ROUND(sold * 100.0 / 120, 2),
       ROUND(sold * 0.42), ROUND(sold * 0.38), 'MOCK'
  FROM (
    SELECT day, (CASE WHEN EXTRACT(DOW FROM day) IN (5,6) THEN 96 ELSE 78 END)
                 + (EXTRACT(DAY FROM day)::int % 7) * 2 AS sold
      FROM generate_series(CURRENT_DATE, CURRENT_DATE + 13, '1 day') AS day
  ) s
ON CONFLICT (property_id, business_date) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Demo staff accounts
-- ---------------------------------------------------------------------------
-- auth.users belongs to Supabase and its columns vary by version, so this is
-- guarded. If it cannot run, everything above still works and employees can
-- be created through the application instead.
--
-- Password for every demo account: DemoStaffOps#2026
-- (bcrypt hash below; change it before exposing this to anyone.)
DO $$
DECLARE
    pwd  TEXT := '$2a$10$N9qo8uLOickgx2ZMRZoMye1VdLLDQ7Rbo6gKPQhNKWBFkLsQfVxKq';
    org  UUID := 'd0000000-0000-4000-a000-000000000001';
    prop UUID := 'd0000000-0000-4000-a000-000000000010';
    person RECORD;
    seq  INT := 0;
    membership_role TEXT;
BEGIN
    FOR person IN
        SELECT * FROM (VALUES
          ('d0000000-0000-4000-a000-000000000701'::uuid,'gm@demo-sarovar.example','Arun Mehta','GENERAL_MANAGER','FO_MANAGER','d0000000-0000-4000-a000-000000000101'::uuid,'PERMANENT','+919800000001','hi'),
          ('d0000000-0000-4000-a000-000000000702'::uuid,'hr@demo-sarovar.example','Priya Nair','HR_MANAGER','FO_MANAGER','d0000000-0000-4000-a000-000000000101'::uuid,'PERMANENT','+919800000002','en'),
          ('d0000000-0000-4000-a000-000000000703'::uuid,'hkhead@demo-sarovar.example','Ramesh Gupta','DEPARTMENT_HEAD','HK_SUPERVISOR','d0000000-0000-4000-a000-000000000102'::uuid,'PERMANENT','+919800000003','hi'),
          ('d0000000-0000-4000-a000-000000000704'::uuid,'hksup@demo-sarovar.example','Sunitha Rao','SUPERVISOR','HK_SUPERVISOR','d0000000-0000-4000-a000-000000000102'::uuid,'PERMANENT','+919800000004','te'),
          ('d0000000-0000-4000-a000-000000000705'::uuid,'gate@demo-sarovar.example','Mohan Singh','TIME_OFFICE','SECURITY_GUARD','d0000000-0000-4000-a000-000000000106'::uuid,'PERMANENT','+919800000005','hi'),
          ('d0000000-0000-4000-a000-000000000706'::uuid,'ra1@demo-sarovar.example','Kavitha Kumari','EMPLOYEE','HK_ATTENDANT','d0000000-0000-4000-a000-000000000102'::uuid,'PERMANENT','+919800000006','te'),
          ('d0000000-0000-4000-a000-000000000707'::uuid,'ra2@demo-sarovar.example','Sridhar Reddy','EMPLOYEE','HK_ATTENDANT','d0000000-0000-4000-a000-000000000102'::uuid,'PERMANENT','+919800000007','te'),
          ('d0000000-0000-4000-a000-000000000708'::uuid,'steward1@demo-sarovar.example','Joseph Fernandes','EMPLOYEE','STEWARD','d0000000-0000-4000-a000-000000000104'::uuid,'PERMANENT','+919800000008','en'),
          ('d0000000-0000-4000-a000-000000000709'::uuid,'commis1@demo-sarovar.example','Bhaskar Naidu','EMPLOYEE','COMMIS','d0000000-0000-4000-a000-000000000103'::uuid,'TRAINEE','+919800000009','te'),
          ('d0000000-0000-4000-a000-00000000070a'::uuid,'intern1@demo-sarovar.example','Divya Sharma','EMPLOYEE','COMMIS','d0000000-0000-4000-a000-000000000103'::uuid,'INDUSTRIAL_TRAINEE','+919800000010','hi'),
          ('d0000000-0000-4000-a000-00000000070b'::uuid,'guard1@demo-sarovar.example','Narayana Swamy','EMPLOYEE','SECURITY_GUARD','d0000000-0000-4000-a000-000000000106'::uuid,'AGENCY','+919800000011','te'),
          ('d0000000-0000-4000-a000-00000000070c'::uuid,'fo1@demo-sarovar.example','Meera Krishnan','EMPLOYEE','FO_AGENT','d0000000-0000-4000-a000-000000000101'::uuid,'PERMANENT','+919800000012','ta')
        ) AS t(uid, email, full_name, role, desig_code, dept_id, staff_type, phone, lang)
    LOOP
        seq := seq + 1;
        -- property_memberships.role has its own CHECK list, which is NOT the
        -- same vocabulary as users.role. Map across rather than fail.
        membership_role := CASE person.role
            WHEN 'GENERAL_MANAGER' THEN 'PROPERTY_MANAGER'
            WHEN 'HR_MANAGER'      THEN 'PROPERTY_HR'
            WHEN 'DEPARTMENT_HEAD' THEN 'PROPERTY_MANAGER'
            WHEN 'SUPERVISOR'      THEN 'PROPERTY_MANAGER'
            ELSE 'VIEWER'
        END;

        INSERT INTO auth.users (
            instance_id, id, aud, role, email, encrypted_password,
            email_confirmed_at, created_at, updated_at,
            raw_app_meta_data, raw_user_meta_data
        ) VALUES (
            '00000000-0000-0000-0000-000000000000', person.uid, 'authenticated', 'authenticated',
            person.email, pwd, NOW(), NOW(), NOW(),
            '{"provider":"email","providers":["email"]}'::jsonb, '{}'::jsonb
        ) ON CONFLICT (id) DO NOTHING;

        INSERT INTO users (id, org_id, email, full_name, role, phone, department_id,
                           active_property_id, employee_code, job_title,
                           employment_type, employment_status, joining_date, preferred_language)
        VALUES (person.uid, org, person.email, person.full_name, person.role, person.phone,
                person.dept_id, prop,
                'GSR' || LPAD(seq::text, 4, '0'),
                person.desig_code, person.staff_type, 'ACTIVE', DATE '2026-04-01', person.lang)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO property_memberships (org_id, property_id, user_id, role, is_default, is_active)
        VALUES (org, prop, person.uid, membership_role, TRUE, TRUE)
        ON CONFLICT DO NOTHING;

        INSERT INTO staff_ops_employee_profiles (
            org_id, property_id, employee_id, designation_id, staff_type, agency_id,
            status, joining_date, default_weekly_off, default_shift_template_id,
            wage_type, wage_amount_inr, bank_name, bank_account_last4, bank_ifsc,
            supervisor_id, skills
        )
        SELECT org, prop, person.uid,
               (SELECT id FROM staff_ops_designations
                 WHERE property_id = prop AND code = person.desig_code),
               person.staff_type,
               CASE WHEN person.staff_type = 'AGENCY'
                    THEN 'd0000000-0000-4000-a000-000000000501'::uuid END,
               'ACTIVE', DATE '2026-04-01',
               (EXTRACT(DAY FROM DATE '2026-04-01')::int % 7),
               'd0000000-0000-4000-a000-000000000201'::uuid,
               'MONTHLY',
               CASE person.staff_type WHEN 'INDUSTRIAL_TRAINEE' THEN 8000
                                      WHEN 'TRAINEE' THEN 14000 ELSE 22000 END,
               'State Bank of India', '4321', 'SBIN0001234',
               CASE WHEN person.role = 'EMPLOYEE'
                    THEN 'd0000000-0000-4000-a000-000000000704'::uuid END,
               '[]'::jsonb
        ON CONFLICT (employee_id, property_id) DO NOTHING;
    END LOOP;

    -- The VERIFIED agency rows need a verifier to satisfy their constraint.
    UPDATE staff_ops_agency_monthly_compliance
       SET verified_by = 'd0000000-0000-4000-a000-000000000702', verified_at = NOW()
     WHERE property_id = prop AND status = 'VERIFIED' AND verified_by IS NULL;

    RAISE NOTICE 'Demo staff seeded. Password for all accounts: DemoStaffOps#2026';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Demo staff accounts skipped (%). The hotel, departments, designations, settings, agency and casual pool are still seeded.', SQLERRM;
END $$;

COMMIT;
