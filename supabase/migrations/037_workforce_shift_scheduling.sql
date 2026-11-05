-- Workforce shift scheduling. Existing shifts remain the canonical timed shift.
BEGIN;

CREATE TABLE IF NOT EXISTS shift_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
  name VARCHAR(120) NOT NULL,
  role VARCHAR(100),
  shift_type VARCHAR(50),
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  break_minutes INT NOT NULL DEFAULT 30 CHECK (break_minutes BETWEEN 0 AND 240),
  color VARCHAR(7) NOT NULL DEFAULT '#2563EB' CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, property_id, name)
);

CREATE TABLE IF NOT EXISTS workforce_schedules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
  name VARCHAR(180) NOT NULL,
  period_type VARCHAR(10) NOT NULL CHECK (period_type IN ('WEEKLY','MONTHLY')),
  period_start DATE NOT NULL,
  period_end DATE NOT NULL CHECK (period_end >= period_start),
  status VARCHAR(24) NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT','PENDING_APPROVAL','APPROVED','PUBLISHED','CANCELLED')),
  submitted_by UUID REFERENCES users(id) ON DELETE SET NULL,
  submitted_at TIMESTAMPTZ,
  approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
  approved_at TIMESTAMPTZ,
  published_by UUID REFERENCES users(id) ON DELETE SET NULL,
  published_at TIMESTAMPTZ,
  created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, property_id, department_id, period_start, period_end)
);
CREATE UNIQUE INDEX IF NOT EXISTS workforce_schedule_period_unique
  ON workforce_schedules(org_id, property_id, COALESCE(department_id, '00000000-0000-0000-0000-000000000000'::uuid), period_start, period_end);

ALTER TABLE shifts
  ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS schedule_id UUID REFERENCES workforce_schedules(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS template_id UUID REFERENCES shift_templates(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS break_minutes INT NOT NULL DEFAULT 30,
  ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

-- Recruitment shifts historically required a job. Workforce roster shifts are
-- property/department owned and do not require an open recruitment job.
ALTER TABLE shifts ALTER COLUMN job_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS employee_availability_windows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
  available_start TIME NOT NULL,
  available_end TIME NOT NULL,
  effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
  effective_to DATE,
  is_available BOOLEAN NOT NULL DEFAULT TRUE,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE TABLE IF NOT EXISTS employee_weekly_offs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
  effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
  effective_to DATE,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(employee_id, property_id, day_of_week, effective_from)
);

CREATE TABLE IF NOT EXISTS employee_shift_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  shift_id UUID NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status VARCHAR(24) NOT NULL DEFAULT 'ASSIGNED'
    CHECK (status IN ('ASSIGNED','PUBLISHED','CONFIRMED','DECLINED','CANCELLED','SWAPPED')),
  assigned_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  employee_confirmed_at TIMESTAMPTZ,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(shift_id, employee_id)
);
CREATE INDEX IF NOT EXISTS employee_shift_assignment_lookup
  ON employee_shift_assignments(org_id, employee_id, status);

CREATE TABLE IF NOT EXISTS shift_swap_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  assignment_id UUID NOT NULL REFERENCES employee_shift_assignments(id) ON DELETE CASCADE,
  requested_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  target_employee_id UUID REFERENCES users(id) ON DELETE SET NULL,
  reason TEXT NOT NULL CHECK (length(trim(reason)) >= 5),
  status VARCHAR(24) NOT NULL DEFAULT 'PENDING_PEER'
    CHECK (status IN ('PENDING_PEER','PENDING_MANAGER','APPROVED','REJECTED','CANCELLED')),
  peer_responded_at TIMESTAMPTZ,
  reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
  reviewed_at TIMESTAMPTZ,
  review_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS shift_swap_one_active
  ON shift_swap_requests(assignment_id) WHERE status IN ('PENDING_PEER','PENDING_MANAGER');

CREATE TABLE IF NOT EXISTS shift_schedule_audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  schedule_id UUID REFERENCES workforce_schedules(id) ON DELETE CASCADE,
  shift_id UUID REFERENCES shifts(id) ON DELETE CASCADE,
  assignment_id UUID REFERENCES employee_shift_assignments(id) ON DELETE CASCADE,
  swap_request_id UUID REFERENCES shift_swap_requests(id) ON DELETE CASCADE,
  actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
  action VARCHAR(60) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shift_notification_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  shift_id UUID REFERENCES shifts(id) ON DELETE CASCADE,
  swap_request_id UUID REFERENCES shift_swap_requests(id) ON DELETE CASCADE,
  channel VARCHAR(20) NOT NULL DEFAULT 'WHATSAPP',
  event_type VARCHAR(40) NOT NULL,
  provider_message_id TEXT,
  delivery_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  error_message TEXT,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION enforce_employee_shift_assignment()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  new_shift shifts%ROWTYPE;
  overlap_count INT;
  leave_count INT;
  weekly_off_count INT;
  previous_end TIMESTAMP;
  next_start TIMESTAMP;
  weekly_minutes NUMERIC;
BEGIN
  IF NEW.status IN ('DECLINED','CANCELLED','SWAPPED') THEN RETURN NEW; END IF;
  SELECT * INTO new_shift FROM shifts WHERE id=NEW.shift_id;
  IF new_shift.id IS NULL THEN RAISE EXCEPTION 'Shift not found'; END IF;
  IF new_shift.end_date <= new_shift.start_date THEN RAISE EXCEPTION 'Shift end must be after start'; END IF;

  SELECT COUNT(*) INTO overlap_count
  FROM employee_shift_assignments a JOIN shifts s ON s.id=a.shift_id
  WHERE a.employee_id=NEW.employee_id AND a.id<>COALESCE(NEW.id, gen_random_uuid())
    AND a.status NOT IN ('DECLINED','CANCELLED','SWAPPED')
    AND s.start_date < new_shift.end_date AND s.end_date > new_shift.start_date;
  IF overlap_count>0 THEN RAISE EXCEPTION 'Employee has an overlapping shift'; END IF;

  SELECT COUNT(*) INTO leave_count FROM leave_requests l
  WHERE l.employee_id=NEW.employee_id AND l.status='APPROVED'
    AND l.leave_date=new_shift.start_date::date;
  IF leave_count>0 THEN RAISE EXCEPTION 'Employee is on approved leave'; END IF;

  SELECT COUNT(*) INTO weekly_off_count FROM employee_weekly_offs w
  WHERE w.employee_id=NEW.employee_id AND w.property_id=new_shift.property_id
    AND w.day_of_week=EXTRACT(ISODOW FROM new_shift.start_date)::INT
    AND w.effective_from<=new_shift.start_date::date
    AND (w.effective_to IS NULL OR w.effective_to>=new_shift.start_date::date);
  IF weekly_off_count>0 THEN RAISE EXCEPTION 'Shift falls on employee weekly off'; END IF;

  SELECT MAX(s.end_date) INTO previous_end
  FROM employee_shift_assignments a JOIN shifts s ON s.id=a.shift_id
  WHERE a.employee_id=NEW.employee_id AND a.id<>COALESCE(NEW.id, gen_random_uuid())
    AND a.status NOT IN ('DECLINED','CANCELLED','SWAPPED') AND s.end_date<=new_shift.start_date;
  IF previous_end IS NOT NULL AND new_shift.start_date-previous_end<INTERVAL '12 hours'
    THEN RAISE EXCEPTION 'Insufficient rest: minimum 12 hours required'; END IF;

  SELECT MIN(s.start_date) INTO next_start
  FROM employee_shift_assignments a JOIN shifts s ON s.id=a.shift_id
  WHERE a.employee_id=NEW.employee_id AND a.id<>COALESCE(NEW.id, gen_random_uuid())
    AND a.status NOT IN ('DECLINED','CANCELLED','SWAPPED') AND s.start_date>=new_shift.end_date;
  IF next_start IS NOT NULL AND next_start-new_shift.end_date<INTERVAL '12 hours'
    THEN RAISE EXCEPTION 'Insufficient rest: minimum 12 hours required'; END IF;

  SELECT COALESCE(SUM(EXTRACT(EPOCH FROM (s.end_date-s.start_date))/60-s.break_minutes),0)
    INTO weekly_minutes
  FROM employee_shift_assignments a JOIN shifts s ON s.id=a.shift_id
  WHERE a.employee_id=NEW.employee_id AND a.id<>COALESCE(NEW.id, gen_random_uuid())
    AND a.status NOT IN ('DECLINED','CANCELLED','SWAPPED')
    AND date_trunc('week',s.start_date)=date_trunc('week',new_shift.start_date);
  weekly_minutes:=weekly_minutes+(EXTRACT(EPOCH FROM (new_shift.end_date-new_shift.start_date))/60-new_shift.break_minutes);
  IF weekly_minutes>2880 THEN RAISE EXCEPTION 'Excessive weekly hours: maximum 48 hours'; END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS employee_shift_assignment_guard ON employee_shift_assignments;
CREATE TRIGGER employee_shift_assignment_guard BEFORE INSERT OR UPDATE
ON employee_shift_assignments FOR EACH ROW EXECUTE FUNCTION enforce_employee_shift_assignment();

CREATE OR REPLACE VIEW v_workforce_schedule WITH (security_invoker=true) AS
SELECT a.id assignment_id, a.employee_id, a.status assignment_status, a.employee_confirmed_at,
       s.id shift_id, s.org_id, s.property_id, s.department_id, s.schedule_id, s.template_id,
       s.job_id, s.role, s.shift_type, s.start_date, s.end_date, s.break_minutes,
       s.location, s.manager_id, s.published_at, p.name property_name,
       d.name department, u.full_name employee_name, u.phone employee_phone
FROM employee_shift_assignments a
JOIN shifts s ON s.id=a.shift_id
LEFT JOIN properties p ON p.id=s.property_id
LEFT JOIN property_departments d ON d.id=s.department_id
JOIN users u ON u.id=a.employee_id
WHERE a.status NOT IN ('CANCELLED','DECLINED','SWAPPED');

ALTER TABLE shift_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_availability_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_weekly_offs ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_shift_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE shift_swap_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE shift_schedule_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shift_notification_logs ENABLE ROW LEVEL SECURITY;

-- Replace the recruitment-job-only shift policy with one that also understands
-- property/department-owned workforce shifts.
DROP POLICY IF EXISTS shifts_rbac ON shifts;
CREATE POLICY shifts_rbac ON shifts FOR ALL USING (
  org_id=current_user_org_id() AND rbac_has_permission('attendance.read') AND (
    (property_id IS NOT NULL AND has_property_access(property_id)
      AND rbac_department_access(department_id))
    OR EXISTS (SELECT 1 FROM jobs j WHERE j.id=shifts.job_id
      AND (j.property_id IS NULL OR has_property_access(j.property_id))
      AND rbac_department_access(j.department_id))
  )
) WITH CHECK (
  org_id=current_user_org_id() AND rbac_has_permission('attendance.manage')
  AND (property_id IS NULL OR has_property_access(property_id))
  AND rbac_department_access(department_id)
);

DROP POLICY IF EXISTS shift_template_read ON shift_templates;
DROP POLICY IF EXISTS shift_template_manage ON shift_templates;
CREATE POLICY shift_template_read ON shift_templates FOR SELECT USING
 (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.read'));
CREATE POLICY shift_template_manage ON shift_templates FOR ALL USING
 (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.manage'));

DROP POLICY IF EXISTS workforce_schedule_read ON workforce_schedules;
DROP POLICY IF EXISTS workforce_schedule_manage ON workforce_schedules;
CREATE POLICY workforce_schedule_read ON workforce_schedules FOR SELECT USING
 (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission('attendance.read'));
CREATE POLICY workforce_schedule_manage ON workforce_schedules FOR ALL USING
 (org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_department_access(department_id)
  AND rbac_has_permission('attendance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND has_property_access(property_id)
  AND rbac_department_access(department_id) AND rbac_has_permission('attendance.manage'));

DROP POLICY IF EXISTS availability_self ON employee_availability_windows;
DROP POLICY IF EXISTS availability_manage ON employee_availability_windows;
CREATE POLICY availability_self ON employee_availability_windows FOR ALL USING
 (employee_id=auth.uid()) WITH CHECK (employee_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY availability_manage ON employee_availability_windows FOR ALL USING
 (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'));

DROP POLICY IF EXISTS weekly_off_read ON employee_weekly_offs;
DROP POLICY IF EXISTS weekly_off_manage ON employee_weekly_offs;
CREATE POLICY weekly_off_read ON employee_weekly_offs FOR SELECT USING
 (employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
  AND rbac_has_permission('attendance.read')));
CREATE POLICY weekly_off_manage ON employee_weekly_offs FOR ALL USING
 (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'));

DROP POLICY IF EXISTS employee_shift_read ON employee_shift_assignments;
DROP POLICY IF EXISTS employee_shift_manage ON employee_shift_assignments;
CREATE POLICY employee_shift_read ON employee_shift_assignments FOR SELECT USING
 (employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
  AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE') AND rbac_has_permission('attendance.read')));
CREATE POLICY employee_shift_manage ON employee_shift_assignments FOR ALL USING
 (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('attendance.manage'));

DROP POLICY IF EXISTS shift_swap_read ON shift_swap_requests;
DROP POLICY IF EXISTS shift_swap_self_insert ON shift_swap_requests;
DROP POLICY IF EXISTS shift_swap_manage ON shift_swap_requests;
CREATE POLICY shift_swap_read ON shift_swap_requests FOR SELECT USING
 (requested_by=auth.uid() OR target_employee_id=auth.uid() OR (org_id=current_user_org_id()
  AND rbac_employee_access(requested_by) AND rbac_has_permission('attendance.read')));
CREATE POLICY shift_swap_self_insert ON shift_swap_requests FOR INSERT WITH CHECK
 (requested_by=auth.uid() AND org_id=current_user_org_id() AND EXISTS
  (SELECT 1 FROM employee_shift_assignments a WHERE a.id=assignment_id AND a.employee_id=auth.uid()));
CREATE POLICY shift_swap_manage ON shift_swap_requests FOR UPDATE USING
 (target_employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(requested_by)
  AND rbac_has_permission('attendance.manage')));

DROP POLICY IF EXISTS shift_schedule_audit_read ON shift_schedule_audit_logs;
DROP POLICY IF EXISTS shift_schedule_audit_insert ON shift_schedule_audit_logs;
CREATE POLICY shift_schedule_audit_read ON shift_schedule_audit_logs FOR SELECT USING
 (org_id=current_user_org_id() AND rbac_has_permission('attendance.read'));
CREATE POLICY shift_schedule_audit_insert ON shift_schedule_audit_logs FOR INSERT WITH CHECK
 (org_id=current_user_org_id() AND actor_id=auth.uid() AND rbac_has_permission('attendance.manage'));
DROP POLICY IF EXISTS shift_notification_read ON shift_notification_logs;
DROP POLICY IF EXISTS shift_notification_manage ON shift_notification_logs;
CREATE POLICY shift_notification_read ON shift_notification_logs FOR SELECT USING
 (employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
  AND rbac_has_permission('attendance.manage')));
CREATE POLICY shift_notification_manage ON shift_notification_logs FOR ALL USING
 (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
  AND rbac_has_permission('attendance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
  AND rbac_has_permission('attendance.manage'));

COMMIT;
