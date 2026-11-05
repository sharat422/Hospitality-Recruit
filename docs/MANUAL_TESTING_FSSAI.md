# FSSAI Certificate Tracking — Manual Testing Guide

Step-by-step testing for every feature: S3 upload, cert management, expiry alerts, UI.

---

## Prerequisites

### 1. Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

### 2. Start the frontend

```bash
cd frontend
npm run dev
# http://localhost:5173
```

### 3. Environment variables (backend `.env`)

```env
# Minimum required for manual testing (sandbox mode if AWS vars absent)
SUPABASE_URL=...
SUPABASE_KEY=...
SUPABASE_JWT_SECRET=...
ANTHROPIC_API_KEY=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX

# Optional — omit for sandbox S3 mode
AWS_S3_BUCKET=your-fssai-bucket-ap-south-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
# Region is hard-coded to ap-south-1 for FSSAI (data residency)
```

### 4. Get a JWT token

```bash
# Sign in via Supabase and copy the access_token
TOKEN="paste_your_jwt_here"
BASE="http://localhost:8000/api/v1"
```

---

## Step 1 — Create a FSSAI_LICENSE cert (no file upload)

```bash
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cert_type":       "FSSAI_LICENSE",
    "license_number":  "12345678901234",
    "license_type":    "STATE",
    "licensed_entity": "Grand Taj Hotel Mumbai",
    "activity_category": "Hotel",
    "expiry_date":     "2026-12-31",
    "state_code":      "MH",
    "candidate_phone": "+919876543210",
    "recruiter_email": "hr@grandtaj.in"
  }' | python -m json.tool
```

**Expected response:**
```json
{
  "id": "<uuid>",
  "cert_type": "FSSAI_LICENSE",
  "license_number": "12345678901234",
  "status": "ACTIVE",
  "expiry_date": "2026-12-31",
  ...
}
```

**Save the cert ID:**
```bash
CERT_ID="<uuid from response>"
```

---

## Step 2 — Create FSSAI_LICENSE cert WITH file upload (presigned S3 URL)

```bash
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cert_type":       "FSSAI_LICENSE",
    "license_number":  "98765432109876",
    "licensed_entity": "Spice Garden Bengaluru",
    "expiry_date":     "2027-03-31",
    "state_code":      "KA",
    "filename":        "fssai_license.pdf",
    "content_type":    "application/pdf"
  }' | python -m json.tool
```

**Expected response includes `upload` block:**
```json
{
  "id": "<cert_id>",
  "upload": {
    "upload_url": "https://sandbox-s3.example.com/fssai-certificates/...",
    "s3_key":     "fssai-certificates/fssai_license/<cert_id>/<uuid>.pdf",
    "sandbox":    true,
    "expires_in": 300,
    "region":     "ap-south-1"
  }
}
```

**Save values:**
```bash
CERT_ID2="<id>"
S3_KEY="<s3_key from upload block>"
UPLOAD_URL="<upload_url from upload block>"
```

---

## Step 3 — PUT the file directly to S3

> In sandbox mode, this PUT will fail (sandbox URL is fake) but confirm-upload still works.
> In production mode with real AWS credentials, this actually uploads to S3.

```bash
# Real S3 upload (production mode):
curl -s -X PUT "$UPLOAD_URL" \
  -H "Content-Type: application/pdf" \
  --data-binary @/path/to/your/fssai_license.pdf
# Expected: HTTP 200 with empty body
```

---

## Step 4 — Confirm the S3 upload

```bash
curl -s -X PATCH "$BASE/fssai/certificates/$CERT_ID2/confirm-upload" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"s3_key\": \"$S3_KEY\"}" | python -m json.tool
```

**Expected:**
```json
{
  "confirmed": true,
  "cert_id":   "<cert_id>",
  "doc_url":   "https://...<s3_key>",
  "s3_key":    "fssai-certificates/..."
}
```

**Verify in Supabase:**
```sql
SELECT id, cert_type, doc_url, s3_key, upload_confirmed_at
FROM fssai_certificates
WHERE id = '<cert_id>';
-- doc_url and s3_key must be populated; upload_confirmed_at must be set
```

---

## Step 5 — Get presigned download URL

```bash
curl -s "$BASE/fssai/certificates/$CERT_ID2/download-url" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Expected:**
```json
{
  "download_url": "https://...",
  "expires_in":   3600,
  "sandbox":      true
}
```

---

## Step 6 — Create a BASIC_FOOD_HYGIENE cert (individual training)

```bash
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cert_type":         "BASIC_FOOD_HYGIENE",
    "candidate_id":      "<your-candidate-uuid>",
    "fostac_course":     "BASIC_HYGIENE",
    "training_provider": "SafeFood Training Centre",
    "expiry_date":       "2025-06-30",
    "state_code":        "MH",
    "candidate_phone":   "+919876543210"
  }' | python -m json.tool
```

**Verify candidate flag set:**
```sql
SELECT id, fssai_trained FROM candidates WHERE id = '<candidate_uuid>';
-- fssai_trained must be TRUE
```

---

## Step 7 — Create an ALCOHOL_LICENSE_FORM_FL cert

```bash
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cert_type":             "ALCOHOL_LICENSE_FORM_FL",
    "alcohol_license_number": "MH-FL-2024-99999",
    "alcohol_license_form":  "FL-11",
    "issuing_authority":     "Maharashtra State Excise Dept",
    "licensed_entity":       "Grand Taj Hotel Bar",
    "expiry_date":           "2025-03-31",
    "state_code":            "MH"
  }' | python -m json.tool
```

---

## Step 8 — List all certificates

```bash
curl -s "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Filter by type:**
```bash
curl -s "$BASE/fssai/certificates?cert_type=FSSAI_LICENSE" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

---

## Step 9 — Get expiring certificates

```bash
# Certs expiring within 30 days (default)
curl -s "$BASE/fssai/certificates/expiring" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# Certs expiring within 60 days
curl -s "$BASE/fssai/certificates/expiring?days=60" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**To test an expiry alert, create a cert that expires in 25 days:**
```bash
EXPIRE_DATE=$(date -d "+25 days" +%Y-%m-%d 2>/dev/null || date -v+25d +%Y-%m-%d)
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"cert_type\":   \"FOSTAC\",
    \"expiry_date\": \"$EXPIRE_DATE\",
    \"candidate_phone\": \"+919876543210\",
    \"recruiter_email\": \"recruiter@hotel.in\"
  }" | python -m json.tool

# Then fetch expiring — this cert should appear
curl -s "$BASE/fssai/certificates/expiring?days=30" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

---

## Step 10 — Trigger the expiry worker manually

```bash
curl -s -X POST "$BASE/fssai/worker/run" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Expected (no Redis/Celery running → sync fallback):**
```json
{
  "queued": false,
  "sync":   true,
  "result": {
    "alerted_30d":    1,
    "alerted_7d":     0,
    "marked_expired": 0,
    "errors":         0
  },
  "message": "Ran synchronously (Celery not available)"
}
```

**Expected (Redis running):**
```json
{
  "queued":  true,
  "job_id":  "celery-task-uuid",
  "message": "FSSAI expiry worker enqueued"
}
```

**Verify alert flags in Supabase after worker run:**
```sql
SELECT id, cert_type, expiry_date,
       alert_30_day_sent, alert_7_day_sent, alert_expired_sent, status
FROM fssai_certificates
ORDER BY expiry_date;
-- alert_30_day_sent should be TRUE for certs expiring ≤ 30 days
-- alert_expired_sent should be TRUE and status='EXPIRED' for past certs
```

---

## Step 11 — Test validation errors

```bash
# Invalid cert_type
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cert_type": "INVALID", "expiry_date": "2027-01-01"}' | python -m json.tool
# Expected: 422 Unprocessable Entity

# FSSAI license number < 14 digits
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cert_type": "FSSAI_LICENSE", "license_number": "1234", "expiry_date": "2027-01-01"}' | python -m json.tool
# Expected: 422, detail contains "14 digits"

# Wrong S3 key on confirm-upload
curl -s -X PATCH "$BASE/fssai/certificates/$CERT_ID/confirm-upload" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"s3_key": "fssai-certificates/some/other/path.pdf"}' | python -m json.tool
# Expected: 400, detail contains "s3_key"

# Disallowed content type for upload
curl -s -X POST "$BASE/fssai/certificates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cert_type": "FOSTAC", "expiry_date": "2027-01-01", "filename": "cert.csv", "content_type": "text/csv"}' | python -m json.tool
# Expected: 422
```

---

## Step 12 — Test UI in the browser

1. Open http://localhost:5173 → sign in → go to **India Compliance**
2. Click the **FSSAI** tab

### Test the form:
- Select each certificate type (Basic Food Hygiene / FoSTaC / FSSAI License / Alcohol License FL) → form fields change per type
- Fill in required fields for FSSAI License:
  - License No: `12345678901234`
  - Expiry Date: pick 20 days from today
  - Candidate Phone: `+919876543210`
- **Without file:** click "Add Certificate" → row appears in table
- **With file:** drag or click the upload zone to pick a PDF → button label changes to "Add Certificate & Upload File" → click → watch upload progress bar

### Verify expiry colouring in table:
| Days left | Expected colour |
|-----------|----------------|
| > 30      | Gray |
| 8–30      | Amber |
| ≤ 7       | Red bold |
| Negative  | Red bold + "⚠ EXPIRED" |

### Verify expiry banner:
- Create a cert expiring in 25 days → refresh FSSAI tab → amber alert banner appears at top

### Verify download link:
- Create a cert with a file upload → "View" link appears in table → click opens cert (sandbox: fake URL)

---

## Step 13 — Run Celery worker (production mode)

```bash
# Install celery if not already: pip install celery redis
cd backend

# Start Redis (Docker)
docker run -d -p 6379:6379 redis:7

# Start Celery worker
celery -A app.celery_app worker --loglevel=info

# Start Celery beat (scheduler — sends tasks daily at 09:00 IST)
celery -A app.celery_app beat --loglevel=info
```

---

## Step 14 — Database audit log

```sql
SELECT action, entity_type, entity_id, law_reference, created_at
FROM india_compliance_audit_logs
WHERE action IN ('FSSAI_CERT_ADDED', 'FSSAI_CERT_UPLOADED')
ORDER BY created_at DESC
LIMIT 20;
```

Every certificate creation and every file confirmation must have an audit log entry with `law_reference = 'Food Safety and Standards Act 2006 / FSSAI Regulations'`.

---

## S3 Checklist (production)

Before going live:
- [ ] `AWS_S3_BUCKET` set and bucket exists in `ap-south-1`
- [ ] Bucket policy: private (no public ACL)
- [ ] CORS rule allows `PUT` from your frontend domain
- [ ] Presigned URL expiry is 5 minutes (`UPLOAD_EXPIRY_S = 300`)
- [ ] Download URL expiry is 1 hour (`DOWNLOAD_EXPIRY_S = 3600`)
- [ ] `sandbox` field in all upload responses is `false`

**S3 CORS rule (paste in AWS Console → Bucket → Permissions → CORS):**
```json
[
  {
    "AllowedHeaders": ["Content-Type"],
    "AllowedMethods": ["PUT"],
    "AllowedOrigins": ["https://your-frontend-domain.com", "http://localhost:5173"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 300
  }
]
```
