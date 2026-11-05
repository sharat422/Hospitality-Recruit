# Unified Leave Management Audit

## Coverage

| Capability | Before | After | Evidence / remaining gap |
|---|---|---|---|
| Leave types | Hard-coded four types | COMPLETE | `leave_types`, five seeded types, per-org configuration |
| Leave balances | COMPLETE | COMPLETE | Existing `leave_balances` retained |
| Leave request | WHATSAPP ONLY | COMPLETE | One service used by WEB, PWA and WHATSAPP |
| Approval | PARTIAL | COMPLETE | Canonical review service and audited transitions |
| Rejection/cancellation | PARTIAL | COMPLETE | Balance restoration and immutable audit event |
| Leave calendar | MISSING | COMPLETE | Property/date scoped leave calendar API and UI |
| Holiday calendar | MISSING | COMPLETE | `property_holidays`, API and UI display |
| Leave history | Employee 360 read-only | COMPLETE | `/leave` history plus scoped API |
| Manager approval | PARTIAL and weakly authorized | COMPLETE | `leave.manage`, property/department checks |
| HR approval | MISSING | COMPLETE | Explicit second stage for configured leave types |
| WhatsApp requests | COMPLETE but separate logic | COMPLETE | `handle_leave` delegates to canonical service |

## Architecture and security

- Existing `leave_requests` and `leave_balances` remain canonical; no duplicate leave subsystem was created.
- Source is attribution only (`WEB`, `PWA`, `WHATSAPP`, `ADMIN`) and never changes validation or approval logic.
- Employee APIs are self-scoped. Managers require `leave.manage`; property and department restrictions are enforced in FastAPI and RLS.
- Active duplicate date ranges are rejected, balances are reserved once on submission and restored once on rejection/cancellation.
- Standard leave completes after manager approval. Leave types configured with `requires_hr_approval` remain pending until HR/Owner approval.
- Every submission, approval, rejection and cancellation writes `leave_audit_logs`.

## Remaining gaps

- Holiday creation is API-only; the leave UI displays holidays but does not include a holiday administration form.
- Half-day leave is represented by `total_days` but the current request UI submits full dates only.
- Provider delivery receipts for approval/rejection WhatsApp messages are not reconciled into leave audit logs.
