# India KYC — Manual Testing Guide

All endpoints run in **sandbox mode** when `SUREPASS_API_TOKEN` is unset.
Sandbox OTP is always `123456`. No real API calls are made.

---

## Prerequisites

```bash
cd backend
uvicorn app.main:app --reload
# → http://localhost:8000
# Swagger UI: http://localhost:8000/docs
```

Obtain a Bearer token (login via Supabase auth) and set:
```bash
TOKEN="your_jwt_here"
BASE="http://localhost:8000/api/v1"
```

---

## 1. Aadhaar eKYC — Initiate OTP

```bash
curl -s -X POST "$BASE/kyc/aadhaar/initiate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "aadhaar_number": "234512349012",
    "candidate_id":   "<uuid-of-candidate>"
  }' | python -m json.tool
```

**Expected response (sandbox):**
```json
{
  "request_id": "sandbox-req-00000000",
  "message": "OTP sent to registered mobile (SANDBOX)",
  "sandbox": true,
  "expires_in_seconds": 600
}
```

**Validation errors to test:**
- Aadhaar starting with `0` → 422
- Less than 12 digits → 422
- Missing `candidate_id` → 422

---

## 2. Aadhaar eKYC — Verify OTP

```bash
curl -s -X POST "$BASE/kyc/aadhaar/verify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id":   "sandbox-req-00000000",
    "otp":          "123456",
    "candidate_id": "<uuid-of-candidate>"
  }' | python -m json.tool
```

**Expected response (sandbox):**
```json
{
  "verified": true,
  "aadhaar_last4": "9012",
  "aadhaar_masked": "XXXX XXXX 9012",
  "name_from_uid": "Ravi Kumar (Sandbox)",
  "gender": "M",
  "sandbox": true,
  "verification_id": "<uuid>"
}
```

**Confirm no full Aadhaar in response** — response must never contain 12 consecutive digits.

**Error cases to test:**
- Wrong OTP (`999999`) → 400 with "OTP verification failed"
- Same `request_id` second time → 409 Conflict (already verified)
- Non-existent `request_id` → 404

---

## 3. PAN Verification

```bash
curl -s -X POST "$BASE/kyc/pan/verify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pan_number":    "ABCDE1234F",
    "candidate_id":  "<uuid-of-candidate>",
    "name_to_match": "SANDBOX USER"
  }' | python -m json.tool
```

**Expected response (sandbox):**
```json
{
  "verified": true,
  "pan_masked": "ABCDE****F",
  "name_on_pan": "SANDBOX USER",
  "name_match": true,
  "sandbox": true,
  "verification_id": "<uuid>"
}
```

**Confirm masking:**
- Full PAN `ABCDE1234F` must NOT appear anywhere in the response
- `pan_masked` must be `ABCDE****F`

**Error cases:**
- Invalid format `INVALID` → 422
- Short PAN `ABCD1234` → 422
- Lowercase accepted: `abcde1234f` → 200, masked `ABCDE****F`

---

## 4. DigiLocker — Get OAuth URL

```bash
curl -s "$BASE/kyc/digilocker/auth-url?candidate_id=<uuid-of-candidate>" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Expected response (sandbox):**
```json
{
  "auth_url": "https://sandbox.digilocker.gov.in/oauth2/authorize?client_id=sandbox&state=<candidate_id>:<csrf>&...",
  "state": "<candidate_id>:<csrf-token>",
  "sandbox": true,
  "instructions": "Redirect the candidate browser to auth_url"
}
```

**Verify:** `state` field starts with the candidate UUID.

---

## 5. DigiLocker — OAuth Callback

```bash
curl -s -X POST "$BASE/kyc/digilocker/callback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code":         "sandbox-auth-code",
    "state":        "<candidate_id>:csrf-token",
    "candidate_id": "<uuid-of-candidate>"
  }' | python -m json.tool
```

**Expected response (sandbox):**
```json
{
  "verified": true,
  "name": "Sandbox User",
  "documents": [
    {"doc_name": "Aadhaar Card",    "id": "<uuid>"},
    {"doc_name": "Driving Licence", "id": "<uuid>"}
  ],
  "doc_count": 2,
  "sandbox": true
}
```

---

## 6. KYC Status Summary

```bash
curl -s "$BASE/kyc/status/<uuid-of-candidate>" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Expected after completing Aadhaar + PAN:**
```json
{
  "candidate_id": "<uuid>",
  "aadhaar_verified": true,
  "pan_verified": true,
  "kyc_complete": true,
  "total_verified": 3,
  "verifications": [...]
}
```

---

## 7. Database Verification

After running steps 1–5, check Supabase tables directly:

```sql
-- Aadhaar session (full Aadhaar must NOT appear)
SELECT id, provider, status, aadhaar_last4, aadhaar_masked,
       name_from_uid, dob_year, gender, address_state
FROM aadhaar_kyc_sessions
ORDER BY created_at DESC LIMIT 5;

-- Identity verifications (PAN must be masked, no full PAN)
SELECT candidate_id, doc_type, pan_masked, pan_number,
       aadhaar_last4, aadhaar_masked, status, kyc_provider
FROM india_identity_verifications
ORDER BY created_at DESC LIMIT 10;

-- Audit log entries
SELECT action, entity_type, entity_id, law_reference, created_at
FROM india_compliance_audit_logs
WHERE action LIKE '%AADHAAR%' OR action LIKE '%PAN%' OR action LIKE '%DIGILOCKER%'
ORDER BY created_at DESC LIMIT 20;

-- Candidate flags updated
SELECT id, aadhaar_verified, pan_verified
FROM candidates
WHERE id = '<uuid-of-candidate>';
```

---

## 8. Production Setup (Real Surepass API)

Add to `.env`:
```env
SUREPASS_API_TOKEN=your_surepass_bearer_token_here
DIGILOCKER_CLIENT_ID=your_digilocker_app_id
DIGILOCKER_CLIENT_SECRET=your_digilocker_app_secret
DIGILOCKER_REDIRECT_URI=https://your-domain.com/api/v1/kyc/digilocker/callback
```

Sign up for Surepass at https://surepass.io — free sandbox plan available.
DigiLocker credentials: apply at https://partners.digitallocker.gov.in

With real keys, the sandbox flag disappears from responses and OTPs are sent to the candidate's actual UIDAI-registered mobile.

---

## Security Checklist

- [ ] Response body never contains 12 consecutive digits (full Aadhaar)
- [ ] `pan_number` column in DB contains only masked value (`ABCDE****F`)
- [ ] `aadhaar_last4` column is exactly 4 digits
- [ ] `aadhaar_kyc_sessions` has no column storing the full Aadhaar
- [ ] Audit log has an entry for every successful and failed verification
- [ ] Expired/failed sessions (status=FAILED) return 410 on verify attempt
- [ ] Third verify attempt sets status=FAILED (max 3 OTP attempts)
