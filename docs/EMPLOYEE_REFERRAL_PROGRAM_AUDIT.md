# Employee Referral Program Audit

## Result

The repository already contained the India portal, admin dashboard, INR programs, UPI collection, Razorpay services, Bull worker, WhatsApp templates, campaigns, badge engine, leaderboard and four payroll adapters. They were retained. Migration 042 and the shared lifecycle service complete the disconnected application-to-hire-to-payout path.

## Gaps resolved

1. Referral tokens are now retained in application `source_ref`; tracking uses a separate token.
2. Submitted applications are attributed through the secure referral token.
3. Single and bulk ATS HIRED transitions start retention eligibility.
4. Missing payout/payroll columns used by workers/adapters were migrated.
5. Missing hire dates and unverified UPI IDs now block payout.
6. Manual payouts require `financial.manage`, organization scope and a processing claim.
7. Queued Razorpay responses are no longer marked paid.
8. The direct mark-paid bypass now returns 410.
9. A serialized DB trigger prevents concurrent candidate/job referral duplication.
10. The open referrals RLS policy was replaced with employee-own/staff-organization policies.

## Remaining gaps

- Cashfree is not integrated; Razorpay is the production payout provider.
- Live Razorpay/WhatsApp verification requires provider test credentials and a migrated Supabase project.
- Python tests could not run because no Python installation is available in this shell.
- The full frontend build is blocked by pre-existing invalid characters in unrelated scheduler, billing and pricing files.

## Verification completed

- Referral/Razorpay/Bull: 96 tests passed.
- Payroll adapters: 48 tests passed.
- Full TypeScript build attempted; failed only in existing unrelated source corruption listed above.
