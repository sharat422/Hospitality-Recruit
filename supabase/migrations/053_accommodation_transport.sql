-- Property-scoped employee accommodation and transport operations.
BEGIN;
CREATE TABLE IF NOT EXISTS accommodation_buildings (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 name VARCHAR(160) NOT NULL,address TEXT,gender_policy VARCHAR(20) NOT NULL DEFAULT 'MIXED' CHECK(gender_policy IN('MALE','FEMALE','MIXED','OTHER')),
 warden_name VARCHAR(160),warden_phone VARCHAR(30),is_active BOOLEAN NOT NULL DEFAULT TRUE,created_by UUID REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(property_id,name)
);
CREATE TABLE IF NOT EXISTS accommodation_rooms (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 building_id UUID NOT NULL REFERENCES accommodation_buildings(id) ON DELETE CASCADE,room_number VARCHAR(40) NOT NULL,floor_label VARCHAR(40),room_type VARCHAR(30) DEFAULT 'SHARED',capacity SMALLINT NOT NULL CHECK(capacity>0),
 monthly_charge_inr NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(monthly_charge_inr>=0),status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN('AVAILABLE','FULL','MAINTENANCE','INACTIVE')),
 created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(building_id,room_number)
);
CREATE TABLE IF NOT EXISTS accommodation_beds (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 room_id UUID NOT NULL REFERENCES accommodation_rooms(id) ON DELETE CASCADE,bed_label VARCHAR(40) NOT NULL,status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN('AVAILABLE','OCCUPIED','MAINTENANCE','INACTIVE')),
 created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(room_id,bed_label)
);
CREATE TABLE IF NOT EXISTS accommodation_allocations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,bed_id UUID NOT NULL REFERENCES accommodation_beds(id) ON DELETE RESTRICT,
 status VARCHAR(20) NOT NULL DEFAULT 'ALLOCATED' CHECK(status IN('ALLOCATED','CHECKED_IN','CHECKED_OUT','CANCELLED')),
 allocated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),check_in_at TIMESTAMPTZ,expected_check_out DATE,check_out_at TIMESTAMPTZ,deposit_inr NUMERIC(12,2) DEFAULT 0 CHECK(deposit_inr>=0),
 notes TEXT,allocated_by UUID NOT NULL REFERENCES users(id),checked_out_by UUID REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_employee_accommodation ON accommodation_allocations(employee_id) WHERE status IN('ALLOCATED','CHECKED_IN');
CREATE UNIQUE INDEX IF NOT EXISTS one_active_bed_allocation ON accommodation_allocations(bed_id) WHERE status IN('ALLOCATED','CHECKED_IN');
CREATE TABLE IF NOT EXISTS accommodation_maintenance_requests (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 building_id UUID REFERENCES accommodation_buildings(id) ON DELETE SET NULL,room_id UUID REFERENCES accommodation_rooms(id) ON DELETE SET NULL,bed_id UUID REFERENCES accommodation_beds(id) ON DELETE SET NULL,
 reported_by UUID NOT NULL REFERENCES users(id),category VARCHAR(30) NOT NULL DEFAULT 'GENERAL',description TEXT NOT NULL,severity VARCHAR(15) NOT NULL DEFAULT 'MEDIUM' CHECK(severity IN('LOW','MEDIUM','HIGH','CRITICAL')),
 status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK(status IN('OPEN','ASSIGNED','IN_PROGRESS','RESOLVED','CANCELLED')),assigned_to UUID REFERENCES users(id),resolution_notes TEXT,resolved_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transport_routes (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 name VARCHAR(160) NOT NULL,origin VARCHAR(255),destination VARCHAR(255),distance_km NUMERIC(8,2),estimated_minutes INT,is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_by UUID REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(property_id,name)
);
CREATE TABLE IF NOT EXISTS transport_pickup_points (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 route_id UUID NOT NULL REFERENCES transport_routes(id) ON DELETE CASCADE,name VARCHAR(160) NOT NULL,address TEXT,latitude NUMERIC(10,7),longitude NUMERIC(10,7),stop_order SMALLINT NOT NULL,default_pickup_time TIME,
 created_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(route_id,stop_order),UNIQUE(route_id,name)
);
CREATE TABLE IF NOT EXISTS transport_vehicles (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 registration_number VARCHAR(30) NOT NULL,vehicle_type VARCHAR(40),capacity SMALLINT NOT NULL CHECK(capacity>0),provider_name VARCHAR(160),insurance_expiry DATE,fitness_expiry DATE,
 status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK(status IN('ACTIVE','MAINTENANCE','INACTIVE')),created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(org_id,registration_number)
);
CREATE TABLE IF NOT EXISTS transport_drivers (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 employee_id UUID REFERENCES users(id) ON DELETE SET NULL,name VARCHAR(160) NOT NULL,phone VARCHAR(30) NOT NULL,licence_number_masked VARCHAR(40),licence_expiry DATE,is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS transport_schedules (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 route_id UUID NOT NULL REFERENCES transport_routes(id) ON DELETE RESTRICT,vehicle_id UUID NOT NULL REFERENCES transport_vehicles(id) ON DELETE RESTRICT,driver_id UUID NOT NULL REFERENCES transport_drivers(id) ON DELETE RESTRICT,
 service_date DATE NOT NULL,departure_time TIME NOT NULL,arrival_time TIME,shift_type VARCHAR(30),status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED' CHECK(status IN('SCHEDULED','DEPARTED','COMPLETED','CANCELLED')),
 created_by UUID REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(vehicle_id,service_date,departure_time),UNIQUE(driver_id,service_date,departure_time)
);
CREATE TABLE IF NOT EXISTS employee_transport_assignments (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 employee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,schedule_id UUID NOT NULL REFERENCES transport_schedules(id) ON DELETE CASCADE,pickup_point_id UUID NOT NULL REFERENCES transport_pickup_points(id) ON DELETE RESTRICT,
 status VARCHAR(20) NOT NULL DEFAULT 'ASSIGNED' CHECK(status IN('ASSIGNED','BOARDED','NO_SHOW','COMPLETED','CANCELLED')),assigned_by UUID NOT NULL REFERENCES users(id),boarded_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ DEFAULT NOW(),updated_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(employee_id,schedule_id)
);
CREATE INDEX IF NOT EXISTS accommodation_property_idx ON accommodation_allocations(org_id,property_id,status);
CREATE INDEX IF NOT EXISTS transport_schedule_property_idx ON transport_schedules(org_id,property_id,service_date);

DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY['accommodation_buildings','accommodation_rooms','accommodation_beds','accommodation_allocations','accommodation_maintenance_requests','transport_routes','transport_pickup_points','transport_vehicles','transport_drivers','transport_schedules','employee_transport_assignments'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY %I_property_read ON %I FOR SELECT USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''employees.read''))',t,t);
 EXECUTE format('CREATE POLICY %I_property_manage ON %I FOR ALL USING(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''employees.manage'')) WITH CHECK(org_id=current_user_org_id() AND has_property_access(property_id) AND rbac_has_permission(''employees.manage''))',t,t);
 END LOOP; END $$;
CREATE POLICY accommodation_allocation_self_read ON accommodation_allocations FOR SELECT USING(employee_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY accommodation_maintenance_self_create ON accommodation_maintenance_requests FOR INSERT WITH CHECK(reported_by=auth.uid() AND org_id=current_user_org_id() AND has_property_access(property_id));
CREATE POLICY transport_assignment_self_read ON employee_transport_assignments FOR SELECT USING(employee_id=auth.uid() AND org_id=current_user_org_id());
CREATE POLICY transport_schedule_assignee_read ON transport_schedules FOR SELECT USING(EXISTS(SELECT 1 FROM employee_transport_assignments a WHERE a.schedule_id=transport_schedules.id AND a.employee_id=auth.uid()));
CREATE POLICY transport_route_assignee_read ON transport_routes FOR SELECT USING(EXISTS(SELECT 1 FROM transport_schedules s JOIN employee_transport_assignments a ON a.schedule_id=s.id WHERE s.route_id=transport_routes.id AND a.employee_id=auth.uid()));
CREATE POLICY pickup_assignee_read ON transport_pickup_points FOR SELECT USING(EXISTS(SELECT 1 FROM employee_transport_assignments a WHERE a.pickup_point_id=transport_pickup_points.id AND a.employee_id=auth.uid()));
COMMIT;
