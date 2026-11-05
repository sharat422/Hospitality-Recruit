# Attendance Feature Audit

Audit date: 2026-08-26  
Canonical employee: `users.id`  
Canonical roster: existing `shifts` / `v_employee_shifts`  
Canonical actual time: new immutable `attendance_punches`

## Coverage

| Capability | Before | After | Implementation | Remaining gap |
|---|---|---|---|---|
| Punch in/out | MISSING | COMPLETE | Self-service mobile/web punch API and UI; immutable punch ledger | Offline punch queue is not included. |
| GPS capture | MISSING | COMPLETE | Coordinates and GPS accuracy stored per punch | Browser/device location accuracy varies. |
| Geofencing | MISSING | COMPLETE | Haversine distance against property policy; configurable radius | Polygon and multi-entrance geofences are future work. |
| Late detection | MISSING | COMPLETE | Roster start plus property grace minutes | Unscheduled shifts cannot be marked late. |
| Absence | MISSING | COMPLETE | No-punch scheduled day becomes `ABSENT`; leave and weekly off remain distinct | Automated nightly materialization requires a scheduler task. |
| Early departure | MISSING | COMPLETE | Roster end minus configured grace | Unscheduled shifts cannot be marked early. |
| Overtime | PARTIAL | COMPLETE (calculation) | Actual paired minutes compared with property threshold | Approval/payment remains payroll-owned. |
| Weekly off | PARTIAL | COMPLETE | ISO weekday policy and `WEEKLY_OFF` daily status | Rotating employee-specific weekly-off roster is future work. |
| Corrections | MISSING | COMPLETE | Employee request and scoped manager approve/reject | Attachment evidence is not included. |
| Manager approval | MISSING | COMPLETE | RBAC/property/department scoped; approval validates corrected day | Bulk approval is not included. |
| Attendance history | UI ONLY (Employee 360 compliance rows) | COMPLETE | Dedicated `/attendance` UI plus Employee 360 daily history | Monthly export is not included. |
| Biometric integration | MISSING | ADAPTER READY | Abstract adapter registry, authenticated canonical JSON adapter, event ledger | No commercial vendor adapter is claimed; each vendor requires its current webhook contract and credentials. |
| Payroll safety | MISSING | COMPLETE | All calculations default to `PENDING`; security-invoker payroll view exposes only `VALIDATED` days | Payroll engine must explicitly adopt the validated view. |
| Correction audit | MISSING | COMPLETE | Database trigger writes immutable before/after audit rows | Central SIEM export is future work. |

## Design Decisions

- Existing `working_hours_compliance` remains the labour-law compliance log. It is not reused as a punch ledger.
- Existing shifts remain the expected roster. Attendance daily records reconcile actual punches against that roster.
- No employee, property, shift, payroll or candidate table was duplicated.
- Punches cannot be edited or deleted through RLS. Corrections update the calculated daily record while retaining raw evidence.
- Payroll cannot use `PENDING` attendance. `validated_attendance_for_payroll` contains only manager-validated rows.
- Biometric devices use `BiometricProviderAdapter`; no vendor payload is embedded in attendance business logic.

## API

- `POST /api/v1/attendance/punch`
- `GET /api/v1/attendance/me/history`
- `GET /api/v1/attendance/employees/{employeeId}/history`
- `POST /api/v1/attendance/corrections`
- `GET /api/v1/attendance/corrections`
- `PATCH /api/v1/attendance/corrections/{correctionId}`
- `PATCH /api/v1/attendance/daily/{dailyRecordId}/validate`
- `POST /api/v1/attendance/policies`
- `POST /api/v1/attendance/biometric/{providerCode}/webhook`

## Security

- Employee punch/history/correction policies are tied to `auth.uid()`.
- Manager reads and writes require attendance permission plus employee property/department scope.
- Cross-tenant IDs are constrained by `org_id` in API queries and RLS.
- Biometric webhooks require a configured secret and use the service client only after adapter authentication.
- Provider secrets are never sent to the frontend; the database stores only a secret-manager reference/hash.
- Correction audit rows are trigger-generated and have no client insert/update/delete policy.

## Files

- `supabase/migrations/036_attendance_engine.sql`
- `backend/app/services/attendance_service.py`
- `backend/app/services/biometric_adapters.py`
- `backend/app/routers/attendance.py`
- `backend/tests/test_attendance.py`
- `frontend/src/pages/AttendanceDashboard.tsx`
- `frontend/src/pages/Employee360.tsx`
- `frontend/src/AppRouter.tsx`
- `frontend/src/components/AppLayout.tsx`

## Priorities

- **P0**: Apply migration 036 and configure property policies before enabling punch actions.
- **P1**: Nightly absence materialization, rotating rosters, correction evidence and commercial vendor adapters selected by customers.
- **P2**: Monthly exports, team dashboard, offline mobile queue and anomaly notifications.
- **Implemented in payroll migration 039**: payroll reads only `validated_attendance_for_payroll`; validation remains attendance-manager owned and snapshots remain immutable after finalization.
