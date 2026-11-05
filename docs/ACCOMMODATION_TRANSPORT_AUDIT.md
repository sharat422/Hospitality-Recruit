# Employee Accommodation and Transport Audit

Date: 2026-08-30

## Coverage

| Capability | Before | Current |
|---|---|---|
| Accommodation availability | UI/DATABASE PLACEHOLDER | Retained as property support summary |
| Buildings | MISSING | COMPLETE |
| Rooms and capacity | MISSING | COMPLETE |
| Beds | MISSING | COMPLETE |
| Allocation | MISSING | COMPLETE |
| Occupancy | MISSING | COMPLETE |
| Check-in/out | MISSING | COMPLETE |
| Maintenance | MISSING | COMPLETE CORE |
| Transport routes | MISSING | COMPLETE |
| Pickup points | MISSING | COMPLETE |
| Vehicles | MISSING | COMPLETE |
| Drivers | MISSING | COMPLETE |
| Schedules | MISSING | COMPLETE |
| Employee assignments | MISSING | COMPLETE |

## Architecture and Security

- Existing `property_employee_support_profiles` remains the availability/contact summary; it was not duplicated.
- Operational entities are linked to the canonical `properties` and `users` tables.
- Employee property membership is validated automatically before bed or transport assignment.
- Every operational row includes `org_id` and `property_id`; RLS requires tenant, property membership and employee permissions.
- Employees receive self-read access only to their own active accommodation and transport assignments.
- Partial unique indexes prevent two active occupants on one bed and two active beds for one employee.
- Vehicle capacity and route/pickup consistency are checked server-side.
- Vehicle, driver and route schedule uniqueness blocks identical simultaneous resource bookings.

## Files

- `supabase/migrations/053_accommodation_transport.sql`
- `backend/app/services/accommodation_transport_service.py`
- `backend/app/routers/accommodation_transport.py`
- `backend/app/services/employee_self_service.py`
- `frontend/src/pages/AccommodationTransport.tsx`
- `frontend/src/pages/EmployeeApp.tsx`
- `backend/tests/test_accommodation_transport.py`

## Remaining Gaps

- GPS vehicle tracking and live ETA require a fleet/GPS provider integration.
- Maintenance vendor work orders, invoices and stock consumption are not included.
- Transport recurring schedule generation and WhatsApp departure alerts are future enhancements.
- Accommodation deposits are recorded but are not automatically deducted from payroll.
