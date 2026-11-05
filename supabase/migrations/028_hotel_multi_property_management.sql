-- =============================================================================
-- 028_hotel_multi_property_management.sql
-- Hotel group and multi-property management built on existing organizations
-- and properties tables. Forward-only and safe for existing rows.
-- =============================================================================

BEGIN;

-- organizations is the existing tenant and hotel-group/company record.
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS legal_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS group_code VARCHAR(40),
    ADD COLUMN IF NOT EXISTS registered_address JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(30),
    ADD COLUMN IF NOT EXISTS website_url TEXT,
    ADD COLUMN IF NOT EXISTS logo_url TEXT,
    ADD COLUMN IF NOT EXISTS brand_color VARCHAR(7) DEFAULT '#7C3AED',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS organizations_group_code_unique
    ON organizations(group_code) WHERE group_code IS NOT NULL;

-- Extend the existing seasonal properties table into the canonical hotel profile.
ALTER TABLE properties
    ADD COLUMN IF NOT EXISTS code VARCHAR(40),
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(255),
    ADD COLUMN IF NOT EXISTS address_line2 VARCHAR(255),
    ADD COLUMN IF NOT EXISTS city VARCHAR(100),
    ADD COLUMN IF NOT EXISTS state VARCHAR(100),
    ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20),
    ADD COLUMN IF NOT EXISTS latitude NUMERIC(10,7),
    ADD COLUMN IF NOT EXISTS longitude NUMERIC(10,7),
    ADD COLUMN IF NOT EXISTS star_rating NUMERIC(2,1),
    ADD COLUMN IF NOT EXISTS room_count INTEGER,
    ADD COLUMN IF NOT EXISTS employee_capacity INTEGER,
    ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(30),
    ADD COLUMN IF NOT EXISTS website_url TEXT,
    ADD COLUMN IF NOT EXISTS payroll_settings JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS hr_settings JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS compliance_settings JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS branding_settings JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id) ON DELETE SET NULL;

DO $$ BEGIN
    ALTER TABLE properties ADD CONSTRAINT properties_star_rating_check
        CHECK (star_rating IS NULL OR star_rating BETWEEN 1 AND 5);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE properties ADD CONSTRAINT properties_type_check
        CHECK (type IN ('HOTEL','RESTAURANT','RESORT','EVENTS_VENUE','CRUISE',
                        'THEME_PARK','HOSTEL','SERVICED_APARTMENT','CLOUD_KITCHEN','OTHER'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE UNIQUE INDEX IF NOT EXISTS properties_org_code_unique
    ON properties(org_id, code) WHERE code IS NOT NULL;
CREATE INDEX IF NOT EXISTS properties_org_active_idx ON properties(org_id, is_active);

-- Legacy seed data did not always carry org_id. Attach orphan properties only
-- when the database has exactly one tenant; multi-tenant databases require an
-- explicit administrative assignment to avoid guessing ownership.
UPDATE properties
SET org_id = (SELECT id FROM organizations LIMIT 1)
WHERE org_id IS NULL
  AND (SELECT COUNT(*) FROM organizations) = 1;

-- Property access is explicit and supports group-level and property-level users.
CREATE TABLE IF NOT EXISTS property_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(40) NOT NULL DEFAULT 'PROPERTY_RECRUITER',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(property_id, user_id),
    CONSTRAINT property_membership_role_check CHECK (role IN (
        'PROPERTY_ADMIN','PROPERTY_HR','PROPERTY_RECRUITER','PROPERTY_MANAGER',
        'PAYROLL_ADMIN','COMPLIANCE_ADMIN','VIEWER'
    ))
);

CREATE INDEX IF NOT EXISTS property_memberships_user_idx
    ON property_memberships(user_id, is_active);
CREATE INDEX IF NOT EXISTS property_memberships_property_idx
    ON property_memberships(property_id, is_active);

CREATE TABLE IF NOT EXISTS property_departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    head_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    budgeted_headcount INTEGER NOT NULL DEFAULT 0 CHECK (budgeted_headcount >= 0),
    current_headcount INTEGER NOT NULL DEFAULT 0 CHECK (current_headcount >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(property_id, code)
);

CREATE INDEX IF NOT EXISTS property_departments_property_idx
    ON property_departments(property_id, is_active);

-- Link the existing job model to the canonical property without removing the
-- legacy property_name field used by current screens.
ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES property_departments(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS jobs_property_id_idx ON jobs(org_id, property_id);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS active_property_id UUID REFERENCES properties(id) ON DELETE SET NULL;

-- Preserve current access: each existing user receives membership to existing
-- properties in their own organization. Administrators can narrow this later.
INSERT INTO property_memberships (org_id, property_id, user_id, role, is_default)
SELECT p.org_id, p.id, u.id,
       CASE WHEN u.role IN ('admin','super_admin','owner')
            THEN 'PROPERTY_ADMIN' ELSE 'PROPERTY_RECRUITER' END,
       ROW_NUMBER() OVER (PARTITION BY u.id ORDER BY p.created_at, p.id) = 1
FROM properties p
JOIN users u ON u.org_id = p.org_id
WHERE p.org_id IS NOT NULL
ON CONFLICT (property_id, user_id) DO NOTHING;

UPDATE users u
SET active_property_id = pm.property_id
FROM property_memberships pm
WHERE pm.user_id = u.id AND pm.is_default = TRUE AND u.active_property_id IS NULL;

-- Security helper functions avoid recursive RLS lookups.
CREATE OR REPLACE FUNCTION current_user_org_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT org_id FROM users WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION current_user_is_group_admin()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT COALESCE(role IN ('admin','super_admin','owner','group_admin'), FALSE)
    FROM users WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION has_property_access(target_property UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT EXISTS (
        SELECT 1 FROM properties p
        WHERE p.id = target_property
          AND p.org_id = current_user_org_id()
          AND (current_user_is_group_admin() OR EXISTS (
              SELECT 1 FROM property_memberships pm
              WHERE pm.user_id = auth.uid()
                AND pm.property_id = target_property
                AND pm.org_id = p.org_id
                AND pm.is_active = TRUE
          ))
    )
$$;

ALTER TABLE property_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_departments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS properties_policy ON properties;
DROP POLICY IF EXISTS properties_select_policy ON properties;
DROP POLICY IF EXISTS properties_manage_policy ON properties;
CREATE POLICY properties_select_policy ON properties FOR SELECT
    USING (org_id = current_user_org_id() AND has_property_access(id));
CREATE POLICY properties_manage_policy ON properties FOR ALL
    USING (org_id = current_user_org_id() AND current_user_is_group_admin())
    WITH CHECK (org_id = current_user_org_id() AND current_user_is_group_admin());

DROP POLICY IF EXISTS property_memberships_select_policy ON property_memberships;
DROP POLICY IF EXISTS property_memberships_manage_policy ON property_memberships;
CREATE POLICY property_memberships_select_policy ON property_memberships FOR SELECT
    USING (org_id = current_user_org_id() AND
          (user_id = auth.uid() OR current_user_is_group_admin()));
CREATE POLICY property_memberships_manage_policy ON property_memberships FOR ALL
    USING (org_id = current_user_org_id() AND current_user_is_group_admin())
    WITH CHECK (org_id = current_user_org_id() AND current_user_is_group_admin());

DROP POLICY IF EXISTS property_departments_select_policy ON property_departments;
DROP POLICY IF EXISTS property_departments_manage_policy ON property_departments;
CREATE POLICY property_departments_select_policy ON property_departments FOR SELECT
    USING (org_id = current_user_org_id() AND has_property_access(property_id));
CREATE POLICY property_departments_manage_policy ON property_departments FOR ALL
    USING (org_id = current_user_org_id() AND
          (current_user_is_group_admin() OR EXISTS (
              SELECT 1 FROM property_memberships pm
              WHERE pm.user_id = auth.uid() AND pm.property_id = property_departments.property_id
                AND pm.role IN ('PROPERTY_ADMIN','PROPERTY_HR','PROPERTY_MANAGER')
                AND pm.is_active = TRUE)))
    WITH CHECK (org_id = current_user_org_id() AND has_property_access(property_id));

-- Repair the seasonal module's permissive policies with property isolation.
DROP POLICY IF EXISTS campaigns_policy ON hiring_campaigns;
CREATE POLICY campaigns_policy ON hiring_campaigns FOR ALL
    USING (has_property_access(property_id)) WITH CHECK (has_property_access(property_id));
DROP POLICY IF EXISTS forecasts_policy ON seasonal_forecasts;
CREATE POLICY forecasts_policy ON seasonal_forecasts FOR ALL
    USING (has_property_access(property_id)) WITH CHECK (has_property_access(property_id));
DROP POLICY IF EXISTS seasonal_workers_policy ON seasonal_workers;
CREATE POLICY seasonal_workers_policy ON seasonal_workers FOR ALL
    USING (has_property_access(property_id)) WITH CHECK (has_property_access(property_id));

DROP POLICY IF EXISTS campaign_roles_policy ON campaign_roles;
CREATE POLICY campaign_roles_policy ON campaign_roles FOR ALL
    USING (EXISTS (
        SELECT 1 FROM hiring_campaigns hc
        WHERE hc.id = campaign_roles.campaign_id AND has_property_access(hc.property_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM hiring_campaigns hc
        WHERE hc.id = campaign_roles.campaign_id AND has_property_access(hc.property_id)
    ));

DROP POLICY IF EXISTS bulk_imports_policy ON bulk_imports;
CREATE POLICY bulk_imports_policy ON bulk_imports FOR ALL
    USING (EXISTS (
        SELECT 1 FROM hiring_campaigns hc
        WHERE hc.id = bulk_imports.campaign_id AND has_property_access(hc.property_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM hiring_campaigns hc
        WHERE hc.id = bulk_imports.campaign_id AND has_property_access(hc.property_id)
    ));

-- Existing jobs remain organization-scoped when property_id is NULL. Once a
-- property is assigned, property users only see their memberships while group
-- administrators retain portfolio access.
DROP POLICY IF EXISTS jobs_org_isolation ON jobs;
DROP POLICY IF EXISTS jobs_property_isolation ON jobs;
CREATE POLICY jobs_property_isolation ON jobs FOR ALL
    USING (
        org_id = current_user_org_id()
        AND (property_id IS NULL OR has_property_access(property_id))
    )
    WITH CHECK (
        org_id = current_user_org_id()
        AND (property_id IS NULL OR has_property_access(property_id))
    );

DROP POLICY IF EXISTS jobs_public_open_select ON jobs;
CREATE POLICY jobs_public_open_select ON jobs FOR SELECT
    USING (status = 'open');

COMMIT;
