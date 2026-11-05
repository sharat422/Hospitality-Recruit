# India Employee Referral Program - Manual Testing

## Coverage status

| Capability | Status | Implementation |
|---|---|---|
| Referral programs, INR rewards and 90-day retention | Complete | Existing India schema plus lifecycle service |
| Secure links and codes | Complete | Unique `referral_code` and `link_token` |
| Employee UPI and validation | Complete | Employee API, regex and Razorpay VPA service |
| English/Hindi WhatsApp sharing and tracking | Complete | Share template and timestamp tracking |
| Application attribution | Complete | Referral token is retained and linked on submission |
| Hire-to-retention lifecycle | Complete | ATS HIRED transition sets hire/check dates |
| Razorpay payout | Complete when RazorpayX is configured | Production mock payouts are blocked |
| Duplicate referral and payout prevention | Complete | DB trigger/index, idempotency key and payout claim |
| Payroll adapters | Complete | greytHR, Keka, Darwinbox and Zoho Payroll |
| Leaderboard, festive campaigns and badges | Complete | Portal/admin UI and India services |
| Cashfree payout | Not implemented | Razorpay is the configured payout provider |

## Prerequisites

1. Apply Supabase migrations through `042_referral_lifecycle_integrity.sql` in order.
2. Start FastAPI at `http://localhost:8000` and React at `http://localhost:5173`.
3. Create a test organization, property, active job role, employee and referral program.
4. Configure Razorpay test credentials: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_FUND_ACCOUNT`.
5. Start Redis and the referral scheduler in `services/` for worker tests.
6. Never use a real employee VPA outside an approved production test.

## Employee to 90-day payout

1. Sign in as Employee and open `/referral-portal`.
2. Save `employee@okaxis`; confirm invalid VPAs (`employee`, `employee@123`, spaces) are rejected.
3. Confirm Razorpay validation sets `employee_upi_details.is_verified=true`. Regex-only validation must remain unverified.
4. Select an active INR program and job, then create a referral link.
5. Confirm distinct `referralCode`, secure `referralLink`, and encoded WhatsApp URL are returned.
6. Share in English and Hindi. Confirm property, role, INR salary, apply link and referral code appear.
7. Confirm `whatsapp_shared=true` and `whatsapp_shared_at` is populated.
8. Open the link incognito and submit the mobile application.
9. Confirm application `source=REFERRAL_LINK`, token remains in `source_ref`, and `tracking_token` is separate.
10. Confirm referral `application_id`, candidate email when supplied, and status `APPLIED`.
11. As Recruiter/HR, move the application to SHORTLISTED and HIRED in the ATS.
12. Confirm `hire_date`, `retention_check_date`, bonus amount/status and `reward_status=EARNED`.
13. Before day 90, call `POST /api/v1/referrals/trigger-upi-payout`; expect 400 and no payout.
14. In test data only, move `hire_date` at least 90 days back and run the daily scan or manual payout.
15. Confirm payout becomes `PROCESSING`; a queued Razorpay response must not set `bonus_paid_at`.
16. On processed payout, confirm `status=BONUS_PAID`, both payout IDs and `bonus_paid_at`.
17. Confirm the employee receives the Hindi WhatsApp paid notification.
18. Repeat worker/manual requests. Expect skip/409 and one Razorpay idempotency reference (`bonus-<referral-id>`).

## Duplicate and authorization tests

1. Refer the same candidate email/job from a second employee while active; expect 409.
2. Send concurrent create requests for the same candidate/job; expect one row and one database conflict.
3. Reuse a secure token for another application; expect 409.
4. As Employee A, request Employee B's UPI; expect 403/404.
5. As Employee, trigger payout; expect 403 (Owner or Group Admin/HR required).
6. As another organization, query/update the referral; expect no row/404.
7. Call legacy `POST /referrals/{id}/mark-paid`; expect 410.
8. Test missing hire date, unverified UPI, zero reward and missing Razorpay config; none may set `bonus_paid_at`.

## Campaign, badge and payroll tests

1. Create DIWALI, EID, HOLI, ONAM and PONGAL campaigns; verify date, INR multiplier/amount and banner.
2. Reach each badge threshold; run evaluation and confirm each badge is awarded once.
3. Verify leaderboard referral/hire/INR totals against source rows.
4. Sync a bonus through each configured payroll adapter and verify provider, reference and sync timestamp.
5. Force provider 500/429 errors and verify retries/error logging without a second UPI payout.

## Automated checks

```powershell
cd services
npm test -- --runInBand

cd ../payroll
npm test -- --runInBand

cd ../backend
python -m pytest tests/test_referral_create.py tests/test_whatsapp_sharing.py tests/test_upi.py tests/test_razorpay_payout.py -q
```

The Python command requires an installed Python runtime and project dependencies.
