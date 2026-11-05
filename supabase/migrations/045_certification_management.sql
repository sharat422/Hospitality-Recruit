-- Unified certification management layered on existing FSSAI and Employee 360.
BEGIN;

CREATE TABLE IF NOT EXISTS certification_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(40) NOT NULL,
    default_validity_months INT,
    issuing_authority TEXT,
    is_fssai_managed BOOLEAN NOT NULL DEFAULT FALSE,
    requires_document BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO certification_types(code,name,category,default_validity_months,issuing_authority,is_fssai_managed) VALUES
('FSSAI_LICENSE','FSSAI Licence','FOOD_SAFETY',12,'Food Safety and Standards Authority of India',TRUE),
('BASIC_FOOD_HYGIENE','Basic Food Hygiene','FOOD_SAFETY',12,'Approved food safety training provider',TRUE),
('FOSTAC','FoSTaC','FOOD_SAFETY',24,'Food Safety and Standards Authority of India',TRUE),
('FIRE_SAFETY','Fire Safety','SAFETY',12,'Fire department / approved training provider',FALSE),
('FIRST_AID','First Aid','SAFETY',24,'Recognised first-aid training provider',FALSE),
('MEDICAL_FITNESS','Medical Fitness','HEALTH',12,'Registered medical practitioner',FALSE),
('POLICE_VERIFICATION','Police Verification','BACKGROUND',36,'State police / authorised verification provider',FALSE)
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, category=EXCLUDED.category,
 default_validity_months=EXCLUDED.default_validity_months,
 issuing_authority=EXCLUDED.issuing_authority, is_fssai_managed=EXCLUDED.is_fssai_managed;

CREATE TABLE IF NOT EXISTS certification_alert_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    reminder_days INT[] NOT NULL DEFAULT ARRAY[90,60,30,7,0],
    notify_employee BOOLEAN NOT NULL DEFAULT TRUE,
    notify_manager BOOLEAN NOT NULL DEFAULT TRUE,
    preferred_channel VARCHAR(20) NOT NULL DEFAULT 'SMS' CHECK (preferred_channel IN ('SMS','WHATSAPP','BOTH')),
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE fssai_certificates
    ADD COLUMN IF NOT EXISTS verified_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verification_notes TEXT,
    ADD COLUMN IF NOT EXISTS renewal_of UUID REFERENCES fssai_certificates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS renewed_by UUID REFERENCES fssai_certificates(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS role_certification_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
    department_id UUID REFERENCES property_departments(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES job_roles(id) ON DELETE CASCADE,
    role_title VARCHAR(255) NOT NULL,
    certification_type_id UUID NOT NULL REFERENCES certification_types(id),
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    required_before_start BOOLEAN NOT NULL DEFAULT FALSE,
    validity_months_override INT,
    grace_days INT NOT NULL DEFAULT 0,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, property_id, department_id, role_title, certification_type_id)
);

CREATE TABLE IF NOT EXISTS employee_certifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    certification_type_id UUID NOT NULL REFERENCES certification_types(id),
    certificate_number VARCHAR(100),
    issuing_authority TEXT,
    issue_date DATE,
    expiry_date DATE,
    status VARCHAR(25) NOT NULL DEFAULT 'PENDING_VERIFICATION'
      CHECK (status IN ('PENDING_VERIFICATION','VERIFIED','REJECTED','EXPIRED','RENEWAL_DUE','RENEWED')),
    storage_key TEXT,
    file_name TEXT,
    mime_type VARCHAR(100),
    storage_region VARCHAR(20) NOT NULL DEFAULT 'ap-south-1' CHECK (storage_region='ap-south-1'),
    encryption_mode VARCHAR(20) NOT NULL DEFAULT 'SSE-S3',
    upload_confirmed_at TIMESTAMPTZ,
    verified_by UUID REFERENCES users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    verification_notes TEXT,
    renewal_of UUID REFERENCES employee_certifications(id) ON DELETE SET NULL,
    renewed_by UUID REFERENCES employee_certifications(id) ON DELETE SET NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date)
);

CREATE UNIQUE INDEX IF NOT EXISTS employee_cert_active_number_unique
 ON employee_certifications(org_id,employee_id,certification_type_id,certificate_number)
 WHERE certificate_number IS NOT NULL AND status NOT IN ('RENEWED','REJECTED');
CREATE INDEX IF NOT EXISTS employee_cert_expiry_idx
 ON employee_certifications(expiry_date,status) WHERE status IN ('VERIFIED','RENEWAL_DUE');

CREATE TABLE IF NOT EXISTS certification_reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('EMPLOYEE_CERT','FSSAI')),
    source_id UUID NOT NULL,
    employee_id UUID REFERENCES users(id) ON DELETE SET NULL,
    threshold_days INT NOT NULL,
    recipient_type VARCHAR(20) NOT NULL CHECK (recipient_type IN ('EMPLOYEE','MANAGER')),
    channel VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','SENT','FAILED','SKIPPED')),
    provider_message_id TEXT,
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source_type,source_id,threshold_days,channel,recipient_type)
);

ALTER TABLE certification_alert_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_certification_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_certifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE certification_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE certification_types ENABLE ROW LEVEL SECURITY;

CREATE POLICY certification_types_read ON certification_types FOR SELECT USING (TRUE);
CREATE POLICY cert_alert_settings_rbac ON certification_alert_settings FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.read'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));
CREATE POLICY role_cert_requirements_read ON role_certification_requirements FOR SELECT USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.read'));
CREATE POLICY role_cert_requirements_manage ON role_certification_requirements FOR ALL USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_has_permission('compliance.manage'));
CREATE POLICY employee_certifications_read ON employee_certifications FOR SELECT USING (
 employee_id=auth.uid() OR (org_id=current_user_org_id() AND rbac_employee_access(employee_id)
 AND rbac_has_permission('compliance.read')));
CREATE POLICY employee_certifications_manage ON employee_certifications FOR ALL USING (
 org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('compliance.manage'))
 WITH CHECK (org_id=current_user_org_id() AND rbac_employee_access(employee_id) AND rbac_has_permission('compliance.manage'));
CREATE POLICY certification_reminders_read ON certification_reminders FOR SELECT USING (
 org_id=current_user_org_id() AND rbac_has_permission('compliance.read'));

COMMIT;
