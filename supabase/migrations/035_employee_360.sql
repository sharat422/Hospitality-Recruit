-- Unified Employee 360: additive employment metadata plus missing HR domains.
-- Existing users/candidates/payroll/leave/attendance/compliance records remain canonical.

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS employee_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS job_title VARCHAR(150),
    ADD COLUMN IF NOT EXISTS employment_type VARCHAR(30) DEFAULT 'FULL_TIME',
    ADD COLUMN IF NOT EXISTS employment_status VARCHAR(30) DEFAULT 'ACTIVE',
    ADD COLUMN IF NOT EXISTS joining_date DATE,
    ADD COLUMN IF NOT EXISTS manager_id UUID REFERENCES users(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS users_org_employee_code_unique
    ON users(org_id, employee_code) WHERE employee_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS users_manager_idx ON users(manager_id);

CREATE OR REPLACE FUNCTION rbac_employee_access(target_employee UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
    SELECT EXISTS (
        SELECT 1 FROM users target
        WHERE target.id=target_employee AND target.org_id=current_user_org_id()
          AND (
            target.id=auth.uid()
            OR current_user_role() IN ('OWNER','GROUP_ADMIN_HR')
            OR ((target.active_property_id IS NULL OR has_property_access(target.active_property_id))
                AND rbac_department_access(target.department_id))
          )
    )
$$;

CREATE OR REPLACE FUNCTION rbac_candidate_access(target_candidate UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
    SELECT EXISTS (
      SELECT 1 FROM candidates c
      WHERE c.id=target_candidate AND c.org_id=current_user_org_id() AND (
        current_user_role() IN ('OWNER','GROUP_ADMIN_HR')
        OR (c.user_id IS NOT NULL AND rbac_employee_access(c.user_id))
        OR EXISTS (SELECT 1 FROM applications a WHERE a.candidate_id=c.id
                   AND (a.property_id IS NULL OR has_property_access(a.property_id))
                   AND rbac_department_access(a.department_id))
      )
    )
$$;

-- Correct legacy permission policies: self-service permissions are not
-- organization-wide permissions. Staff branches explicitly exclude employees
-- and candidates, while self branches remain tied to auth.uid().
DROP POLICY IF EXISTS payslips_self_select ON payslips;
DROP POLICY IF EXISTS payslips_360_select ON payslips;
CREATE POLICY payslips_360_select ON payslips FOR SELECT USING (
    employee_id=auth.uid() OR (
        org_id=current_user_org_id() AND rbac_employee_access(employee_id)
        AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('payroll.read')
    )
);

DROP POLICY IF EXISTS lb_policy ON leave_balances;
DROP POLICY IF EXISTS leave_balances_360_select ON leave_balances;
CREATE POLICY leave_balances_360_select ON leave_balances FOR SELECT USING (
    employee_id=auth.uid() OR (
        org_id=current_user_org_id() AND rbac_employee_access(employee_id)
        AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('leave.read')
    )
);

DROP POLICY IF EXISTS leave_self_select ON leave_requests;
DROP POLICY IF EXISTS leave_manage ON leave_requests;
CREATE POLICY leave_self_select ON leave_requests FOR SELECT USING (
    employee_id=auth.uid() OR (
        org_id=current_user_org_id() AND rbac_employee_access(employee_id)
        AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('leave.read')
    )
);
CREATE POLICY leave_manage ON leave_requests FOR UPDATE USING (
    org_id=current_user_org_id() AND rbac_employee_access(employee_id)
    AND rbac_has_permission('leave.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
    AND rbac_has_permission('leave.manage'));

DROP POLICY IF EXISTS working_hours_rbac ON working_hours_compliance;
DROP POLICY IF EXISTS working_hours_360_select ON working_hours_compliance;
DROP POLICY IF EXISTS working_hours_manage_360 ON working_hours_compliance;
CREATE POLICY working_hours_360_select ON working_hours_compliance FOR SELECT USING (
    employee_id=auth.uid() OR (
        org_id=current_user_org_id() AND rbac_employee_access(employee_id)
        AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('attendance.read')
    )
);
CREATE POLICY working_hours_manage_360 ON working_hours_compliance FOR ALL USING (
    org_id=current_user_org_id() AND (employee_id IS NULL OR rbac_employee_access(employee_id))
    AND rbac_has_permission('attendance.manage')
) WITH CHECK (org_id=current_user_org_id() AND (employee_id IS NULL OR rbac_employee_access(employee_id))
    AND rbac_has_permission('attendance.manage'));

DROP POLICY IF EXISTS shift_matches_rbac ON shift_matches;
DROP POLICY IF EXISTS shift_matches_manage ON shift_matches;
DROP POLICY IF EXISTS shift_matches_360_select ON shift_matches;
DROP POLICY IF EXISTS shift_matches_360_manage ON shift_matches;
CREATE POLICY shift_matches_360_select ON shift_matches FOR SELECT USING (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=shift_matches.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_candidate_access(shift_matches.candidate_id)
        AND rbac_has_permission('attendance.read'))
);
CREATE POLICY shift_matches_360_manage ON shift_matches FOR ALL USING (
    org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('attendance.manage')
) WITH CHECK (
    org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('attendance.manage')
);

DROP POLICY IF EXISTS candidate_documents_rbac ON candidate_documents;
DROP POLICY IF EXISTS candidate_documents_360_select ON candidate_documents;
DROP POLICY IF EXISTS candidate_documents_360_manage ON candidate_documents;
CREATE POLICY candidate_documents_360_select ON candidate_documents FOR SELECT USING (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=candidate_documents.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('documents.read') AND (
          rbac_candidate_access(candidate_documents.candidate_id)
        ))
);
CREATE POLICY candidate_documents_360_manage ON candidate_documents FOR ALL USING (
    org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('documents.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('documents.manage'));

DROP POLICY IF EXISTS employee_upi_self ON employee_upi_details;
DROP POLICY IF EXISTS employee_upi_360_select ON employee_upi_details;
CREATE POLICY employee_upi_360_select ON employee_upi_details FOR SELECT USING (
    user_id=auth.uid() OR (
        current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('financial.read') AND rbac_employee_access(user_id)
    )
);

DROP POLICY IF EXISTS india_identity_rbac ON india_identity_verifications;
DROP POLICY IF EXISTS india_identity_360_select ON india_identity_verifications;
DROP POLICY IF EXISTS india_identity_360_manage ON india_identity_verifications;
CREATE POLICY india_identity_360_select ON india_identity_verifications FOR SELECT USING (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=india_identity_verifications.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('compliance.read') AND (
          rbac_candidate_access(india_identity_verifications.candidate_id)
        ))
);
CREATE POLICY india_identity_360_manage ON india_identity_verifications FOR ALL USING (
    org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('compliance.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('compliance.manage'));

DROP POLICY IF EXISTS epf_esic_rbac ON epf_esic_registrations;
DROP POLICY IF EXISTS epf_esic_360_select ON epf_esic_registrations;
DROP POLICY IF EXISTS epf_esic_360_manage ON epf_esic_registrations;
CREATE POLICY epf_esic_360_select ON epf_esic_registrations FOR SELECT USING (
    org_id=current_user_org_id() AND (
      EXISTS (SELECT 1 FROM candidates c WHERE c.id=epf_esic_registrations.candidate_id AND c.user_id=auth.uid())
      OR (current_user_role() NOT IN ('EMPLOYEE','CANDIDATE') AND rbac_has_permission('compliance.read') AND (
        rbac_candidate_access(epf_esic_registrations.candidate_id)
      ))
    )
);
CREATE POLICY epf_esic_360_manage ON epf_esic_registrations FOR ALL USING (
    org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('compliance.manage')
) WITH CHECK (org_id=current_user_org_id() AND rbac_candidate_access(candidate_id)
    AND rbac_has_permission('compliance.manage'));

DROP POLICY IF EXISTS fssai_rbac ON fssai_certificates;
DROP POLICY IF EXISTS fssai_360_select ON fssai_certificates;
DROP POLICY IF EXISTS fssai_360_manage ON fssai_certificates;
CREATE POLICY fssai_360_select ON fssai_certificates FOR SELECT USING (
    EXISTS (SELECT 1 FROM candidates c WHERE c.id=fssai_certificates.candidate_id AND c.user_id=auth.uid())
    OR (org_id=current_user_org_id() AND current_user_role() NOT IN ('EMPLOYEE','CANDIDATE')
        AND rbac_has_permission('compliance.read') AND (
          rbac_candidate_access(fssai_certificates.candidate_id)
        ))
);
CREATE POLICY fssai_360_manage ON fssai_certificates FOR ALL USING (
    org_id=current_user_org_id() AND (candidate_id IS NULL OR rbac_candidate_access(candidate_id))
    AND rbac_has_permission('compliance.manage')
) WITH CHECK (org_id=current_user_org_id() AND (candidate_id IS NULL OR rbac_candidate_access(candidate_id))
    AND rbac_has_permission('compliance.manage'));

ALTER VIEW v_employee_shifts SET (security_invoker = true);

CREATE TABLE IF NOT EXISTS employee_performance_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    review_period_start DATE NOT NULL,
    review_period_end DATE NOT NULL,
    rating NUMERIC(3,2) CHECK (rating BETWEEN 1 AND 5),
    goals JSONB NOT NULL DEFAULT '[]',
    strengths TEXT,
    development_areas TEXT,
    employee_comments TEXT,
    manager_comments TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','SHARED','ACKNOWLEDGED','CLOSED')),
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (review_period_end >= review_period_start)
);

CREATE TABLE IF NOT EXISTS employee_training_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    training_name VARCHAR(255) NOT NULL,
    provider VARCHAR(255),
    category VARCHAR(50) DEFAULT 'ROLE_SKILL',
    status VARCHAR(20) NOT NULL DEFAULT 'ASSIGNED'
        CHECK (status IN ('ASSIGNED','IN_PROGRESS','COMPLETED','EXPIRED','CANCELLED')),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    due_date DATE,
    completed_at TIMESTAMPTZ,
    score NUMERIC(5,2),
    certificate_url TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_hr_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    event_type VARCHAR(40) NOT NULL
        CHECK (event_type IN ('WARNING','APPRECIATION','GRIEVANCE','INVESTIGATION','PIP','SUSPENSION','OTHER')),
    event_date DATE NOT NULL DEFAULT CURRENT_DATE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    severity VARCHAR(20) DEFAULT 'INFO'
        CHECK (severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')),
    status VARCHAR(20) DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','UNDER_REVIEW','RESOLVED','CLOSED')),
    is_confidential BOOLEAN NOT NULL DEFAULT TRUE,
    resolution TEXT,
    resolved_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    source_table VARCHAR(80),
    source_id UUID,
    event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    visibility VARCHAR(20) NOT NULL DEFAULT 'EMPLOYEE'
        CHECK (visibility IN ('EMPLOYEE','MANAGER','HR_ONLY')),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS performance_employee_idx ON employee_performance_reviews(employee_id, review_period_end DESC);
CREATE INDEX IF NOT EXISTS training_employee_idx ON employee_training_records(employee_id, status, due_date);
CREATE INDEX IF NOT EXISTS hr_events_employee_idx ON employee_hr_events(employee_id, event_date DESC);
CREATE INDEX IF NOT EXISTS lifecycle_employee_idx ON employee_lifecycle_events(employee_id, event_at DESC);

ALTER TABLE employee_performance_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_training_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_hr_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_lifecycle_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS performance_self_read ON employee_performance_reviews;
DROP POLICY IF EXISTS performance_manage ON employee_performance_reviews;
CREATE POLICY performance_self_read ON employee_performance_reviews FOR SELECT USING (
    employee_id=auth.uid() OR (
        org_id=current_user_org_id() AND rbac_has_permission('employees.read')
        AND (property_id IS NULL OR has_property_access(property_id))
        AND rbac_department_access(department_id)
    )
);
CREATE POLICY performance_manage ON employee_performance_reviews FOR ALL USING (
    org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id)
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id));

DROP POLICY IF EXISTS training_self_read ON employee_training_records;
DROP POLICY IF EXISTS training_manage ON employee_training_records;
CREATE POLICY training_self_read ON employee_training_records FOR SELECT USING (
    employee_id=auth.uid() OR (
        org_id=current_user_org_id() AND rbac_has_permission('employees.read')
        AND (property_id IS NULL OR has_property_access(property_id))
        AND rbac_department_access(department_id)
    )
);
CREATE POLICY training_manage ON employee_training_records FOR ALL USING (
    org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id)
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id));

-- Disciplinary/HR events are intentionally not self-readable. Only scoped HR
-- managers and organizational administrators with employees.manage can access them.
DROP POLICY IF EXISTS hr_events_manage_only ON employee_hr_events;
CREATE POLICY hr_events_manage_only ON employee_hr_events FOR ALL USING (
    org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id)
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id));

DROP POLICY IF EXISTS lifecycle_self_read ON employee_lifecycle_events;
DROP POLICY IF EXISTS lifecycle_manage ON employee_lifecycle_events;
CREATE POLICY lifecycle_self_read ON employee_lifecycle_events FOR SELECT USING (
    (employee_id=auth.uid() AND visibility='EMPLOYEE') OR (
        org_id=current_user_org_id() AND rbac_has_permission('employees.read')
        AND (property_id IS NULL OR has_property_access(property_id))
        AND rbac_department_access(department_id)
        AND (visibility <> 'HR_ONLY' OR rbac_has_permission('employees.manage'))
    )
);
CREATE POLICY lifecycle_manage ON employee_lifecycle_events FOR ALL USING (
    org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id)
) WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('employees.manage')
    AND (property_id IS NULL OR has_property_access(property_id))
    AND rbac_department_access(department_id));

COMMIT;
