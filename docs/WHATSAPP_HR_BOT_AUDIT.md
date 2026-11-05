# WhatsApp HR Bot Feature Audit

Audit date: 2026-08-28. The bot is a transport adapter over shared HR services; it does not own leave, shift, payroll or grievance business rules.

## End-to-End Coverage

| Capability | Status | Verified implementation | Remaining dependency |
|---|---|---|---|
| `LEAVE [date] [reason]` | COMPLETE | Structured parser, employee resolution, shared `leave_service.submit_leave_request`, manager notification and ticket response | Manager WhatsApp numbers and provider credentials |
| `PAYSLIP [month]` | COMPLETE | Owner-filtered finalized payslip lookup, request log, PDF generation/cache and provider document delivery | Public/presigned India S3 URL and approved WhatsApp document template where required |
| `SHIFT` | COMPLETE | Shared `employee_self_service.employee_shifts`; only published/confirmed employee shifts | Published schedule data |
| `BALANCE` | COMPLETE | Shared `employee_self_service.leave_snapshot`; same data as PWA | Current-year leave allocation |
| `COMPLAINT [text]` | COMPLETE | Shared `employee_self_service.submit_grievance`; anonymous by default, `NAMED` opt-in, POSH classification | HR escalation process and contacts |
| `CAREER` | COMPLETE | Shared career service detects current role, paths, certifications and internal openings | Role/certification/job data quality |
| `HELP` | COMPLETE | English/Hindi/Hinglish command menu | None |
| Meta webhook verification | COMPLETE | `GET /api/whatsapp/webhook`, verify-token challenge | `WHATSAPP_VERIFY_TOKEN` |
| Meta/Interakt inbound webhook | COMPLETE | Signature validation where configured, normalized parsing, background dispatch | Public HTTPS endpoint |
| Twilio inbound webhook | COMPLETE | `POST /api/v1/hr-bot/webhook` | Twilio sandbox/production configuration |
| Employee phone verification | COMPLETE | Canonical `whatsapp_users`; registered `users.phone` match establishes ownership of the sending WhatsApp number | HR must maintain unique E.164 employee phones |
| Inbound/outbound message storage | COMPLETE | Separate immutable-direction rows in `whatsapp_messages`; provider ID and send/failure status stored | Delivery/read receipt reconciliation is provider-dependent |
| Hindi support | COMPLETE | Devanagari and common Hinglish aliases, Hindi months/dates and bilingual replies | Free-form job/HR record data is not machine translated |
| Audit trail | COMPLETE | Command, arguments, status, source, inbound/outbound body, provider ID and timestamps in `whatsapp_messages`; domain records retain source/message linkage | Retention policy must be configured operationally |
| Anonymous complaints | COMPLETE | `hr_complaints.employee_id=NULL`, random tracking token, masked reporting view | Identity disclosure must follow legal/admin process |

## Shared-Service Contract

- WhatsApp `LEAVE`, web and PWA all call `leave_service.submit_leave_request`.
- WhatsApp `SHIFT` and the PWA call `employee_self_service.employee_shifts`.
- WhatsApp `BALANCE` and the PWA call `employee_self_service.leave_snapshot`.
- WhatsApp and PWA grievances call `employee_self_service.submit_grievance` and use `hr_complaints` only.
- WhatsApp and PWA read the same finalized `payslips`; WhatsApp additionally records each request in `payslip_requests`.
- The webhook contains provider verification, payload parsing, dispatch and delivery only. HR decisions remain in services.

## Security Findings

- Sensitive commands are scoped by the employee ID resolved from the sender's registered phone.
- Payslip queries include an employee filter plus a defense-in-depth owner check.
- Unknown and opted-out numbers cannot execute employee commands.
- Meta signatures are enforced when `WHATSAPP_APP_SECRET` is configured. Production must not leave it unset.
- RLS remains tenant-scoped, while public webhooks use the server-only Supabase admin client. Service-role credentials must never reach the browser.
- Phone numbers and message bodies are personal data; apply the organization DPDP retention and erasure policy.

## Remaining Enhancements

- Provider delivery/read receipt synchronization is not normalized across all three providers.
- Fully translated free-form content is not generated automatically.
- WhatsApp interactive buttons/templates are not used; the command flow remains text-first for maximum handset compatibility.
