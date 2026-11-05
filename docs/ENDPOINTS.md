# HospRecruit AI - Complete FastAPI Endpoint Reference

## Base URL
`http://localhost:8000/api/v1`

## Authentication
All endpoints (except `/health` and webhook endpoints) require JWT token in `Authorization: Bearer <token>` header.

---

## Module 1: Candidate Management & AI Screening (Pain #1)

### Create Candidate
**POST** `/candidates/`
- **Description**: Create candidate from SMS/web form (bulk inbound)
- **Auth**: Required
- **Body**:
  ```json
  {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+15551234567",
    "location": "Portland, OR",
    "job_id": "uuid",
    "source": "sms"
  }
  ```
- **Response**: Candidate object with ID
- **Pain Reference**: #1 - Handle 100-500 apps efficiently

### List Candidates for Job
**GET** `/candidates/job/{job_id}?limit=100&offset=0`
- **Description**: Paginated list of all candidates for a job
- **Auth**: Required
- **Response**: `{count, candidates: []}`

### Get Qualified Candidates Only
**GET** `/candidates/job/{job_id}/qualified`
- **Description**: Pre-screened qualified candidates (Pain #1: fast pipeline)
- **Auth**: Required
- **Response**: `{count, candidates: []}`

### Get Single Candidate
**GET** `/candidates/{candidate_id}`
- **Description**: Fetch candidate with full profile
- **Auth**: Required
- **Response**: Candidate object with screening result

### Update Candidate Availability
**PUT** `/candidates/{candidate_id}/availability`
- **Description**: Update availability from mobile portal (Pain #2)
- **Auth**: Required
- **Body**:
  ```json
  [
    {"day": "Monday", "start": "09:00", "end": "17:00"},
    {"day": "Tuesday", "start": "18:00", "end": "22:00"}
  ]
  ```
- **Response**: Updated candidate

---

## Module 1: AI Screening

### Screen Single Candidate
**POST** `/screening/{candidate_id}/screen`
- **Description**: AI screening using Claude/GPT-4o (Pain #1: reduce 65% screening time)
- **Auth**: Required
- **Body**:
  ```json
  {
    "job_requirements": "2+ years server experience, food handler cert, weekends",
    "use_claude": true
  }
  ```
- **Response**:
  ```json
  {
    "candidate_id": "uuid",
    "ai_score": 85,
    "ai_model": "claude-3-5-sonnet-20241022",
    "key_qualifications": ["Experience", "Availability"],
    "red_flags": [],
    "recommend_proceed": true,
    "reasoning": "..."
  }
  ```

### Bulk Screen Candidates
**POST** `/screening/job/{job_id}/bulk-screen`
- **Description**: Screen all unscreened candidates for a job (Pain #1: efficiency at scale)
- **Auth**: Required
- **Body**:
  ```json
  {
    "job_requirements": "..."
  }
  ```
- **Response**:
  ```json
  {
    "total_screened": 150,
    "qualified_count": 42,
    "qualification_rate_percent": 28,
    "avg_score": 72.5
  }
  ```
- **Note**: Large batches may be queued as Celery jobs

### Get Screening Stats
**GET** `/screening/{job_id}/screening-stats`
- **Description**: Screening performance metrics for a job (Pain #1)
- **Auth**: Required
- **Response**:
  ```json
  {
    "job_id": "uuid",
    "total_candidates": 200,
    "screened_count": 150,
    "qualified_count": 42,
    "qualification_rate_percent": 28,
    "avg_ai_score": 72.5,
    "estimated_hours_saved": 37.5
  }
  ```
- **Pain Reference**: #1 - 15 min manual screen → 30 sec AI screen

---

## Module 2: Shifts & Availability Matching

### Create Shift
**POST** `/shifts/create`
- **Description**: Create new shift (Pain #2: seasonal demand tracking)
- **Auth**: Required
- **Query Params**:
  ```
  job_id=uuid&role=server&shift_type=seasonal&
  start_date=2026-06-01T00:00:00&end_date=2026-08-31T23:59:59&
  hours_per_week=40&urgency=urgent
  ```
- **Response**: Shift object

### List Open Shifts
**GET** `/shifts/open`
- **Description**: All open shifts (Pain #2: immediate fills)
- **Auth**: Required
- **Response**: `{count, shifts: []}`

### Get Shift Matches for Candidate
**POST** `/shifts/{candidate_id}/match`
- **Description**: Find best matching shifts (Pain #2: reduce 70% no-show)
- **Auth**: Required
- **Response**:
  ```json
  {
    "candidate_id": "uuid",
    "match_count": 3,
    "matches": [
      {
        "shift_id": "uuid",
        "match_score": 0.92,
        "conflicts": []
      }
    ]
  }
  ```

### Get Seasonal Shifts
**GET** `/shifts/season/{season}?`
- **Description**: Shifts for specific season (Pain #2: summer/holiday spikes)
- **Auth**: Required
- **Example Season**: `summer_2026`, `holiday_2025`
- **Response**: `{season, shift_count, total_positions, shifts: []}`

### Bulk Match Candidates to Shift
**POST** `/shifts/bulk-match`
- **Description**: Match all qualified candidates to a shift (Pain #2)
- **Auth**: Required
- **Query Params**: `shift_id=uuid`
- **Response**: `{shift_id, matches_found}`

---

## Module 4: SMS & Conversational Recruiting

### Twilio Webhook (Inbound SMS)
**POST** `/sms/webhook/twilio`
- **Description**: Inbound SMS handler (Pain #2: SMS-first recruiting)
- **Auth**: None (Twilio validates signature)
- **Body**: Twilio webhook payload (form-encoded)
- **Response**: `{status: "ok", intent: "apply|availability|questions|decline|other"}`
- **Side Effects**: 
  - Analyzes SMS intent using Claude
  - Generates and sends AI reply
  - Updates conversation history

### Send SMS
**POST** `/sms/send`
- **Description**: Send SMS to candidate
- **Auth**: Optional
- **Query Params**: `to_number=+1555...&message=Hi John...`
- **Response**: `{status: "sent", twilio_sid: "..."}`

### Start Recruitment Conversation
**POST** `/sms/start-conversation/{candidate_id}`
- **Description**: Initiate multi-turn SMS recruiting flow
- **Auth**: Required
- **Query Params**: `job_id=uuid`
- **Response**: `{status: "started", candidate_id, twilio_sid}`
- **Pain Reference**: #2 - Mobile-first immediate engagement

### Get Conversation History
**GET** `/sms/conversation/{candidate_id}`
- **Description**: Full SMS conversation transcript with candidate
- **Auth**: Required
- **Response**: `{candidate_id, turns: [{user_message, ai_response, intent}, ...]}`

---

## Module 5: Onboarding & Compliance (Pain #5)

### Initialize Onboarding Flow
**POST** `/onboarding/{candidate_id}/{job_id}/init-flow`
- **Description**: Launch onboarding with auto-populated compliance tasks
- **Auth**: Required
- **Body**: `{job_role: "server"}`
- **Response**:
  ```json
  {
    "flow_id": "uuid",
    "candidate_id": "uuid",
    "tasks": [
      {
        "id": "uuid",
        "task_type": "background_check",
        "status": "pending",
        "due_date": "2026-04-12T00:00:00"
      }
    ],
    "estimated_days": 5
  }
  ```
- **Pain Reference**: #5 - Compliance drag reduction

### Get Onboarding Status
**GET** `/onboarding/{candidate_id}/status`
- **Description**: Current progress on onboarding (Pain #3, #5: visibility)
- **Auth**: Required
- **Response**: Full flow with all tasks + completion %

### Mark Task Complete
**POST** `/onboarding/task/{task_id}/complete`
- **Description**: Mark compliance task done
- **Auth**: Required
- **Body**: 
  ```json
  {
    "result": {
      "verified": true,
      "cert_date": "2026-04-10"
    }
  }
  ```
- **Response**: Updated task

### Get Pending Compliance Tasks
**GET** `/onboarding/job/{job_id}/pending`
- **Description**: All pending tasks for a job (Pain #5, #3: manager dashboard)
- **Auth**: Required
- **Response**:
  ```json
  {
    "job_id": "uuid",
    "total_pending": 15,
    "overdue_count": 3,
    "tasks": []
  }
  ```

---

## Module 6: Analytics & Dashboard (Pain #3: Manager Burnout)

### Manager Dashboard
**GET** `/analytics/manager-dashboard`
- **Description**: Real-time KPI dashboard (Pain #3: reduce burnout)
- **Response**:
  ```json
  {
    "total_active_jobs": 5,
    "total_applications": 450,
    "total_qualified": 120,
    "avg_qualification_score": 72.3,
    "avg_fill_time_days": 14.2,
    "no_show_rate_percent": 35,
    "pipeline_summary": [],
    "alerts": ["Shift on 2026-04-20 unfilled"]
  }
  ```
- **Auth**: Required

### Job Pipeline Breakdown
**GET** `/analytics/job/{job_id}/pipeline`
- **Description**: Candidate flow by stage (applied→screened→interviewed→offered→accepted→filled)
- **Auth**: Required
- **Response**:
  ```json
  {
    "job_id": "uuid",
    "stages": [
      {"stage": "applied", "count": 200},
      {"stage": "screened", "count": 50}
    ],
    "bottleneck_stage": "interviewed"
  }
  ```

### Cost Per Hire Analysis
**GET** `/analytics/cost-per-hire?days=90`
- **Description**: Cost-per-hire metrics vs industry (Pain #1: 40% higher norm)
- **Auth**: Required
- **Response**:
  ```json
  {
    "avg_fill_time_days": 14.2,
    "industry_average_days": 18,
    "efficiency_ratio": 1.27,
    "estimated_cost_per_hire": 945
  }
  ```

### No-Show Analysis
**GET** `/analytics/no-show-analysis?days=30`
- **Description**: Track show rate improvement (Pain #2: 70% no-show)
- **Auth**: Required
- **Response**:
  ```json
  {
    "no_show_rate_percent": 35,
    "industry_average_percent": 70,
    "goal_percent": 40,
    "estimated_lost_productivity": "$5250"
  }
  ```

---

## Module 7: Talent Pool & Retention (Pain #4)

### Create Talent Cohort
**POST** `/talent-pool/cohort/create`
- **Description**: Create seasonal talent pool (Pain #4: retain between seasons)
- **Auth**: Required
- **Query Params**: `cohort_name=Summer 2026&season=summer_2026`
- **Response**: Cohort object

### Get Cohort Candidates
**GET** `/talent-pool/cohort/{cohort_id}/candidates`
- **Description**: All candidates in cohort
- **Auth**: Required
- **Response**: `{cohort_id, candidate_count, candidates: []}`

### Launch Engagement Campaign
**POST** `/talent-pool/campaign/launch`
- **Description**: Off-season engagement to keep candidates warm (Pain #4)
- **Auth**: Required
- **Query Params**:
  ```
  cohort_id=uuid&campaign_name=Summer Followup&
  message=Hey! Ready for seasonals?&channel=sms
  ```
- **Response**: `{campaign_id, sent_count, cohort_size}`

### Get Retention Metrics
**GET** `/talent-pool/retention-metrics?season=summer_2026`
- **Description**: Cohort retention analysis
- **Auth**: Required
- **Response**:
  ```json
  {
    "season": "summer_2026",
    "total_candidates": 250,
    "re_hired_percent": 68,
    "avg_days_since_engagement": 45
  }
  ```

---

## Module 8: Billing & White-Label (Pain #6: Thin Margins)

### Create Subscription
**POST** `/billing/subscription/create`
- **Description**: Set up Stripe subscription (multi-tenant SaaS)
- **Auth**: Required
- **Query Params**: `tier=starter|growth|enterprise`
- **Tiers**:
  - `starter`: AI + SMS, 50 hires/month, $99/mo
  - `growth`: + shifts + analytics, 200 hires/month, $299/mo
  - `enterprise`: + white-label + API, unlimited, custom
- **Response**:
  ```json
  {
    "subscription_id": "sub_xxx",
    "stripe_customer_id": "cus_xxx",
    "tier": "growth",
    "status": "active",
    "next_billing_date": "2026-05-09"
  }
  ```

### Get Active Subscription
**GET** `/billing/subscription`
- **Description**: Current org subscription
- **Auth**: Required
- **Response**: Subscription object

### Get Feature Access
**GET** `/billing/subscription/features`
- **Description**: Determine available features by tier
- **Auth**: Required
- **Response**:
  ```json
  {
    "tier": "growth",
    "features": [
      "ai_screening",
      "sms_recruiting",
      "shift_matching",
      "advanced_dashboard",
      "talent_pool_retention"
    ]
  }
  ```

### Setup White-Label
**POST** `/billing/white-label/setup`
- **Description**: Configure white-label reseller (Pain #6: reseller model)
- **Auth**: Required (Enterprise tier required)
- **Query Params**:
  ```
  custom_domain=mycorp.hosprecruit.ai&
  logo_url=https://...&brand_color=%23FF0000
  ```
- **Response**: `{org_id, custom_domain, brand_color, api_key}`

### Get White-Label Config
**GET** `/billing/white-label/config`
- **Description**: Fetch white-label customization
- **Auth**: Required
- **Response**: Config object with `api_key` for Zapier integrations

---

## System Endpoints

### Health Check
**GET** `/health`
- **Description**: Service health status
- **Auth**: None
- **Response**: `{status: "ok"}`

### Root
**GET** `/`
- **Description**: API info
- **Auth**: None
- **Response**: `{name, version, docs}`

---

## Error Responses

All error responses follow this format:
```json
{
  "detail": "Error message",
  "status_code": 400
}
```

### Common Status Codes
- `200 OK`: Success
- `201 Created`: Resource created
- `400 Bad Request`: Invalid input
- `401 Unauthorized`: Missing/invalid JWT
- `403 Forbidden`: Insufficient permissions (RLS)
- `404 Not Found`: Resource doesn't exist
- `500 Internal Server Error`: Server error

---

## Rate Limiting & Quotas

- **Screening**: 100 candidates/job bulk screen per hour
- **SMS**: 50 SMS per minute (Twilio limit: 100/min)
- **API**: 1000 requests per hour per org

---

## Webhooks

### Twilio Inbound SMS
Configure in Twilio Console:
- **Request URL**: `https://your-domain.com/api/v1/sms/webhook/twilio`
- **Method**: POST
- **Validation**: Twilio signs all requests with SHA1

### Stripe Webhooks
Configure in Stripe Dashboard:
- **Events**: `customer.subscription.created`, `customer.subscription.deleted`, `invoice.payment_failed`
- **Endpoint**: (To be implemented in `/billing/webhook/stripe`)

---

## Testing

### cURL Examples

**Screen a candidate:**
```bash
curl -X POST http://localhost:8000/api/v1/screening/{candidate_id}/screen \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"job_requirements": "2+ years experience", "use_claude": true}'
```

**Get manager dashboard:**
```bash
curl http://localhost:8000/api/v1/analytics/manager-dashboard \
  -H "Authorization: Bearer YOUR_JWT"
```

---

## Integration Notes

- **Claude API**: Responses typically 500-1000ms, cached for identical requirements
- **Twilio SMS**: Delivery 2-10s, webhook callback within 5s
- **Stripe**: Subscription creation instant, webhooks within 1s
- **Merge.dev**: Bullhorn/iCIMS sync on-demand, ~30s per ATS fetch

---

**Last Updated**: April 2026
**API Version**: v1
**Status**: Production-Ready
