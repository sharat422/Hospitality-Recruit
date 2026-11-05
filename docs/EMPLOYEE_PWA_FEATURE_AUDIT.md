# Employee PWA Feature Audit

Audit date: 2026-08-28. The PWA is a presentation channel over existing domain services; it does not duplicate the WhatsApp HR Bot or its data.

## Coverage

| Capability | Status | Canonical implementation | Notes / dependency |
|---|---|---|---|
| Employee OTP login | COMPLETE | Supabase phone OTP in `EmployeeLogin.tsx`; unknown numbers cannot create users | Supabase India SMS provider must be configured and employee auth phone verified |
| Hindi / English | PARTIAL | Employee login/navigation/actions are bilingual and persisted locally | Record content and every validation response are not fully translated |
| PWA install/offline shell | COMPLETE | Manifest, service worker and offline page | Production HTTPS required; authenticated APIs are intentionally never cached |
| Shift | COMPLETE | `v_workforce_schedule`, `employee_shifts()` and compact PWA dashboard | Only published/confirmed own shifts are returned |
| Leave | COMPLETE | Canonical `submit_leave_request()` for WEB/PWA/WHATSAPP | Existing manager/HR approval workflow |
| Leave balance | COMPLETE | Canonical `leave_balances` snapshot | Current-year balances shown |
| Payslip | COMPLETE | Finalized `payslips` and authenticated PDF endpoint | Private India storage required when URLs are used |
| EPF | COMPLETE | Masked UAN/member ID and finalized payslip deduction | Statutory registration must be populated by HR |
| Salary / CTC | COMPLETE | Effective compensation structure and finalized payroll snapshot | Employee sees own values only |
| Shift swap | COMPLETE | Existing `shift_swap_requests` service/API | PWA creates manager-routed open-target swaps |
| Salary advance | COMPLETE | `employee_salary_advance_requests` and shared service/API | Approved amounts must later be added to payroll by authorized payroll workflow |
| Accommodation | COMPLETE | Property employee support profile and employee display | HR must configure details per property |
| Transport | COMPLETE | Property employee support profile and contact | HR must configure routes/contact per property |
| Benefits | COMPLETE | Property support profile JSON list | Benefits remain informational, not enrollment administration |
| ESIC clinic | COMPLETE | Property clinic name/address/phone/maps fields | HR must maintain local dispensary details |
| Grievance | COMPLETE | Canonical `hr_complaints`, shared PWA/WhatsApp creator | Anonymous status uses random tracking token |
| POSH | COMPLETE | `complaint_type=POSH`, harassment category and elevated severity | Organization must configure Internal Committee contacts and legal process |

## Shared Service Contract

- PWA leave and WhatsApp `LEAVE` call `leave_service.submit_leave_request`.
- PWA shifts and WhatsApp `SHIFT` call `employee_self_service.employee_shifts`.
- PWA and WhatsApp complaints call `employee_self_service.submit_grievance` and write only `hr_complaints`.
- PWA and WhatsApp payslips read the same finalized `payslips`; PWA uses the authenticated payroll PDF endpoint.
- Existing WhatsApp webhook, sessions and message logs are unchanged.

## Security and Low-Bandwidth Design

- Employee OTP sets a real Supabase session, so existing backend JWT verification and RLS remain authoritative.
- `shouldCreateUser=false` prevents unknown phone numbers from self-registering as employees.
- Employee dashboard is one compact request and returns only the signed-in employee's data.
- No authenticated API response or payslip is stored by the service worker.
- Static app shell is cached; mutations are disabled while offline rather than queued with stale credentials.
- Inputs/buttons are at least 44–48px and the UI is designed for 360px screens without heavy charts.
- Anonymous POSH/grievance records omit `employee_id`; identity access remains controlled and audited by existing complaint RBAC.

## Files

- `supabase/migrations/041_employee_pwa_self_service.sql`
- `backend/app/services/employee_self_service.py`
- `backend/app/routers/employee_self_service.py`
- `backend/app/services/hr_bot_service.py`
- `frontend/src/pages/EmployeeLogin.tsx`
- `frontend/src/pages/EmployeeApp.tsx`
- `frontend/public/manifest.webmanifest`, `sw.js`, `offline.html`
- `backend/tests/test_employee_self_service.py`

## Remaining Gaps

- Full Hindi translation of API errors and all record content is a P2 enhancement.
- Salary advance disbursement/recovery is intentionally not automatic; payroll approval and an explicit payroll adjustment are required.
- Benefits enrollment/claims are not implemented; current functionality publishes property benefit information.
- Production OTP delivery, ESIC clinic data, POSH Internal Committee contacts and property support information require tenant configuration.
