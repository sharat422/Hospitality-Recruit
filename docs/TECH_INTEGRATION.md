# HospRecruit AI - Technology Integration Plan

**Document Date**: April 2026  
**Status**: Live Integration Architecture

---

## Overview

HospRecruit AI integrates with 5 major external systems:
1. **Twilio**: SMS recruiting + conversational AI
2. **Merge.dev**: Unified ATS (Bullhorn + iCIMS)
3. **Claude/GPT-4o**: AI screening + SMS intent analysis
4. **Stripe**: Billing + subscription management
5. **Supabase**: Auth, DB, real-time subscriptions

---

## 1. Twilio Integration (Module 4: SMS-First Recruiting)

### Overview
Twilio enables inbound SMS from candidates and AI-driven outbound recruiting. Pain #2: mobile-first, SMS-first engagement for 70% no-show reduction via availability confirmation.

### Setup

**1. Create Twilio Account**
- Sign up: https://www.twilio.com/console
- Purchase Twilio phone number (e.g., +1-800-RECRUITER)
- Get `ACCOUNT_SID` and `AUTH_TOKEN` from console

**2. Configure Webhook**
In Twilio Console → Phone Numbers → <your number>:
- **Inbound Messages**: Webhook URL = `https://hosprecruit.ai/api/v1/sms/webhook/twilio`
- **Method**: HTTP POST
- Twilio will send form-encoded data on inbound SMS

**3. Set Environment Variables**
```bash
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxxxx
TWILIO_PHONE_NUMBER=+1-800-RECRUITER
```

### Request Flow

**Candidate sends SMS**: `"Hi, interested in server position at Olive Garden"`

**Twilio Webhook** → FastAPI `/sms/webhook/twilio`:
```
POST /api/v1/sms/webhook/twilio
AccountSid=AC...
AuthToken=...
From=+1-555-234-5678
To=+1-800-RECRUITER
Body=Hi, interested in server position at Olive Garden
MessageSid=SMxxx
```

**FastAPI Processing**:
1. Validate Twilio signature
2. Call Claude API to analyze intent + extract data
3. Generate AI response
4. Send SMS reply via Twilio
5. Log conversation turn to Supabase

### Claude Intent Analysis

**Input**: `"Hi, interested in server position at Olive Garden"`

**Prompt** (in sms_service.py):
```
Analyze SMS intent: apply, availability, questions, decline, other
Extract structured data (location, availability, role preference, etc)
Return JSON: {intent, data: {<fields>}, confidence}
```

**Output**:
```json
{
  "intent": "apply",
  "data": {
    "interest_level": "high",
    "role_preference": "server",
    "location": "Olive Garden"
  },
  "confidence": 0.95
}
```

**AI Reply** (Claude generates):
```
"Great! We have server shifts available. What days/hours work best for you?"
```

### Outbound SMS Campaign (Module 7: Engagement)

Staffing agency launches campaign to 250 summer 2025 candidates:

```python
# talent_pool_service.py
await service.launch_engagement_campaign(
    cohort_id="summer_2025",
    message="⏰ Heading into summer? Ready for premium shifts? We're hiring + training.",
    channel="sms",
    user_id="org_123"
)
```

**Execution**:
1. Query all candidates in cohort
2. Queue SMS via Celery/Redis for rate limiting
3. Each SMS via `twilio_client.messages.create()`
4. Hits Twilio rate limit: 100 SMS/min
5. Retry failed sends automatically

### Webhook Validation (Security)

Twilio signs all webhooks. In production, validate before processing:

```python
from twilio.request_validator import RequestValidator

validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
url = "https://hosprecruit.ai/api/v1/sms/webhook/twilio"
params = dict(request.form)
signature = request.headers.get("X-Twilio-Signature")

if not validator.validate(url, params, signature):
    raise HTTPException(status_code=403, detail="Invalid Twilio signature")
```

---

## 2. Merge.dev Integration (Module 1: ATS Sync)

### Overview
Merge.dev provides **unified API** to Bullhorn (top ATS for staffing) and iCIMS. Sync candidates, jobs, placements bi-directionally.

Pain #1: Reduce manual ATS data entry; auto-populate candidate profiles from existing ATS records.

### Setup

**1. Create Merge.dev Account**
- Sign up: https://merge.dev
- Link Bullhorn/iCIMS accounts via OAuth
- Get `MERGE_API_KEY` and `MERGE_ACCOUNT_TOKEN`

**2. Generate Integration Link**
Merge provides iframe for user to authorize their Bullhorn account.

**3. Set Environment Variables**
```bash
MERGE_DEV_API_KEY=sk_merge_xxx
MERGE_DEV_BASE_URL=https://api.merge.dev/api
```

### Candidate Sync (Inbound)

**Use Case**: Staffing agency has 500 existing candidates in Bullhorn. Pull into HospRecruit.

**Endpoint** (to implement):
```
GET /api/v1/candidates/sync/ats
```

**Implementation**:
```python
# In services/ats_service.py
async def sync_candidates_from_ats(self, user_id: str):
    """Fetch candidates from Bullhorn via Merge.dev."""
    
    headers = {"Authorization": f"Bearer {settings.MERGE_DEV_API_KEY}"}
    url = f"{settings.MERGE_DEV_BASE_URL}/crm/candidates"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        candidates = response.json()["results"]
    
    # Transform + upsert to Supabase
    for ats_candidate in candidates:
        candidate_data = {
            "first_name": ats_candidate["first_name"],
            "last_name": ats_candidate["last_name"],
            "email": ats_candidate["email_addresses"][0]["email_address"],
            "phone": ats_candidate["phone_numbers"][0]["phone_number"],
            "source": "ats_bullhorn",
            "raw_data": ats_candidate,  # Store full ATS record
        }
        await candidate_repo.create_candidate(candidate_data, user_id)
    
    return {"synced": len(candidates)}
```

### Job Sync (Bidirectional)

**Scenario 1: Create job in HospRecruit → Push to Bullhorn**

```python
async def push_job_to_ats(job_id: str):
    """Create/update job in Bullhorn via Merge."""
    
    job = await jobs_repo.get_job(job_id)
    
    payload = {
        "name": job["title"],
        "description": job["description"],
        "address": {"city": job["city"], "state": job["state"]},
        "is_open": job["status"] == "open",
    }
    
    headers = {"Authorization": f"Bearer {settings.MERGE_DEV_API_KEY}"}
    url = f"{settings.MERGE_DEV_BASE_URL}/crm/opportunities"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        ats_job = response.json()
    
    # Store mapping
    await jobs_repo.update_job(job_id, {"ats_id": ats_job["id"]})
```

**Scenario 2: Bullhorn logs placement → Sync back to HospRecruit**

Merge webhooks (configure in dashboard):
```
POST /api/v1/billing/webhook/merge
```

**Payload**:
```json
{
  "type": "placement_created",
  "data": {
    "candidate_id": "merge_cand_123",
    "job_id": "merge_job_456",
    "position_start_date": "2026-04-15",
    "placement_status": "accepted"
  }
}
```

**Handler**:
```python
@router.post("/webhook/merge")
async def handle_merge_webhook(body: dict):
    """Sync placements from ATS back to HospRecruit."""
    
    if body["type"] == "placement_created":
        # Find matching candidate + shift
        # Update pipeline_stage to "filled"
        # Mark as no longer available
```

---

## 3. Claude API Integration (Module 1 & 4)

### Overview
Claude 3.5 Sonnet for:
- **Candidate screening** (Pain #1: reduce 65% manual screening)
- **SMS intent analysis** (Module 4)
- **Conversation generation** (multi-turn recruiting)

### Setup

**1. Create Anthropic Account**
- Sign up: https://console.anthropic.com
- Create API key
- Set rate limit: 10 req/sec for free tier

**2. Set Environment Variables**
```bash
ANTHROPIC_API_KEY=sk-ant-xxxx
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

### Candidate Screening Flow

**Input**: Candidate profile + job requirements

```python
# screening_service.py
async def screen_candidate(candidate_id, job_requirements):
    prompt = f"""
    Evaluate candidate fit for role.
    
    JOB REQUIREMENTS:
    {job_requirements}
    
    PAIN POINT: We receive 100-500 apps/role, 65% screening time spent on unqualified.
    Only recommend "proceed" if 70%+ confident.
    
    Return JSON:
    {{
      "ai_score": <0-100>,
      "key_qualifications": [],
      "red_flags": [],
      "recommend_proceed": <bool>
    }}
    """
    
    response = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return parse_response(response.content[0].text)
```

**Typical Response Time**: 800ms  
**Cost**: $0.0027 per screening (vs $0.10 recruiter time @ 15 min/candidate)

### SMS Intent Analysis

**Input**: Inbound SMS from candidate

```python
# sms_service.py → _analyze_sms_intent()
prompt = f"""
SMS from potential candidate: "{message}"

Extract intent (apply, availability, questions, decline, other) + structured data.

Return JSON:
{{
  "intent": "...",
  "data": {{ extracted fields }},
  "confidence": 0-1
}}
"""

response = anthropic_client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=200,
    messages=[{"role": "user", "content": prompt}]
)
```

### Multi-Turn Conversation

**Example**: SMS recruiting conversation over 3+ turns

```
Turn 1:
User: "Hi, interested in server position at Olive Garden"
AI Intent: "apply" → Respond with "Great! What's your availability?"

Turn 2:
User: "I work weekends, flexible weekdays"
AI Intent: "availability" → Extract + Respond with shift options

Turn 3:
User: "Summer only"
AI Intent: "availability" → Filter to seasonal shifts only
```

**Implementation**: Store conversation state + last N turns for context:

```python
async def continue_conversation(candidate_id, user_message):
    # Fetch conversation history
    history = await get_conversation_turns(candidate_id)
    
    # Build context from last 5 turns
    context = "\n".join([
        f"Candidate: {turn['user_message']}\nAI: {turn['ai_response']}"
        for turn in history[-5:]
    ])
    
    prompt = f"""
    Conversation so far:
    {context}
    
    New message from candidate: "{user_message}"
    
    Respond naturally, max 160 chars (SMS). Extract any new data.
    """
    
    response = await anthropic_client.messages.create(...)
    ai_reply = response.content[0].text[:160]
    
    # Save turn
    await save_conversation_turn(candidate_id, user_message, ai_reply)
    
    # Send SMS
    await send_sms(candidate["phone"], ai_reply)
```

---

## 4. Stripe Integration (Module 8: SaaS Billing)

### Overview
Multi-tenant SaaS subscription (Pain #6: thin margins → recurring revenue model)

Tiers:
- **Starter**: $99/mo, 50 hires/month
- **Growth**: $299/mo, 200 hires/month
- **Enterprise**: Custom, unlimited

### Setup

**1. Create Stripe Account**
- Sign up: https://stripe.com
- Get `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY`

**2. Create Products + Prices**
In Stripe Dashboard:
```
Product: HospRecruit AI - Starter
  Price: $99/month (recurring)
  Price ID: price_starter_monthly

Product: HospRecruit AI - Growth
  Price: $299/month (recurring)
  Price ID: price_growth_monthly

Product: HospRecruit AI - Enterprise
  Price: Custom quote
  Price ID: price_enterprise_monthly
```

**3. Set Environment Variables**
```bash
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
```

### Subscription Creation Flow

**User navigates to `/billing` → Selects tier → Redirected to Stripe Checkout**

**Frontend** (React):
```typescript
const handleSubscribe = async (tier: "starter" | "growth") => {
  const response = await apiClient.post("/billing/subscription/create", {
    tier
  })
  
  // Redirect to Stripe Checkout
  window.location.href = response.data.checkout_url
}
```

**Backend** (FastAPI):
```python
@router.post("/subscription/create")
async def create_subscription(tier: str, user: dict = Depends(get_current_user)):
    org_id = user["org_id"]
    
    # Create Stripe customer
    customer = stripe.Customer.create(
        email=user["email"],
        metadata={"org_id": org_id}
    )
    
    # Get price for tier
    price_id = TIER_MAPPING[tier]  # "price_starter_monthly"
    
    # Create checkout session
    session = stripe.checkout.Session.create(
        customer=customer.id,
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url="https://hosprecruit.ai/dashboard?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://hosprecruit.ai/billing",
    )
    
    # Save customer mapping
    await billing_repo.create_subscription(
        org_id, tier, user["email"], customer.id
    )
    
    return {"checkout_url": session.url}
```

### Webhook: Payment Succeeded

Stripe webhook → `/webhook/stripe`:

```python
@router.post("/webhook/stripe")
async def handle_stripe_webhook(request: Request):
    """Handle Stripe events."""
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return {"error": "Invalid payload"}, 400
    except stripe.error.SignatureVerificationError:
        return {"error": "Invalid signature"}, 400
    
    if event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        customer_id = invoice["customer"]
        
        # Update subscription status
        await billing_repo.update_subscription_status(
            customer_id, "active"
        )
    
    elif event["type"] == "customer.subscription.deleted":
        # Handle cancellation
        subscription = event["data"]["object"]
        await billing_repo.update_subscription_status(
            subscription["customer"], "cancelled"
        )
    
    return {"received": True}
```

### Feature Gating by Tier

```python
@router.post("/screening/job/{job_id}/bulk-screen")
async def bulk_screen(job_id: str, user: dict = Depends(get_current_user)):
    org_id = user["org_id"]
    
    # Check subscription tier
    subscription = await billing_repo.get_subscription(org_id)
    if not subscription or subscription["tier"] == "starter":
        raise HTTPException(
            status_code=403,
            detail="Bulk screening requires Growth tier or higher"
        )
    
    # Proceed...
```

---

## 5. Supabase Integration (Auth, DB, Realtime, RLS)

### Overview
- **Auth**: Supabase Auth (JWT) via email/password
- **Database**: PostgreSQL with Row Level Security
- **Realtime**: Subscriptions on key tables for live dashboard
- **Row Level Security**: Enforce org isolation at database level

### Setup

**1. Create Supabase Project**
- Sign up: https://supabase.com
- Create new project
- Get `SUPABASE_URL` and `SUPABASE_KEY` (anon key)

**2. Run Migrations**
In Supabase SQL Editor, run: [`supabase/migrations/001_init_schema.sql`](../supabase/migrations/001_init_schema.sql)

This creates:
- `organizations`, `users` tables
- `candidates`, `jobs`, `shifts`, `shift_matches`
- `compliance_tasks`, `onboarding_flows`
- `sms_messages`, `conversation_turns`
- `subscriptions`, `white_label_configs`

**3. Enable RLS Policies**

Example: Candidates table
```sql
-- All candidates belong to org; user must be in same org
ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;

CREATE POLICY candidates_org_isolation ON candidates
  USING (
    auth.user_id() IN (
      SELECT id FROM users WHERE org_id = candidates.org_id
    )
  )
  WITH CHECK (
    auth.user_id() IN (
      SELECT id FROM users WHERE org_id = candidates.org_id
    )
  );
```

This ensures:
- No SQL injection via JWTs
- Multi-tenant data isolation at DB layer
- No recruiter from Company A sees Company B's candidates

**4. Enable Realtime**

In Supabase Dashboard → Database → Publications:
```sql
ALTER PUBLICATION supabase_realtime ADD TABLE candidates;
ALTER PUBLICATION supabase_realtime ADD TABLE shift_matches;
ALTER PUBLICATION supabase_realtime ADD TABLE compliance_tasks;
```

### Auth Flow

**Frontend (React)**:
```typescript
// hooks/useAuth.tsx
const signIn = async (email: string, password: string) => {
  const { error } = await supabase.auth.signInWithPassword({
    email, password
  })
  if (error) throw error
  
  // JWT stored in localStorage automatically
}
```

**Backend (FastAPI)**:
Called on every request via dependency injection:

```python
# core/security.py
async def get_current_user(credentials: HTTPAuthCredentials = Depends(security)):
    token = credentials.credentials
    payload = jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"])
    user_id = payload["sub"]
    return payload
```

### Real-time Dashboard

Frontend subscribes to real-time events:

```typescript
// UseEffect in Dashboard component
useEffect(() => {
  const channel = supabase
    .channel('candidates')
    .on(
      'postgres_changes',
      { event: '*', schema: 'public', table: 'candidates' },
      (payload) => {
        // Candidate screened / added → refetch dashboard
        queryClient.invalidateQueries({ queryKey: ['candidates'] })
      }
    )
    .subscribe()
    
  return () => {
    channel.unsubscribe()
  }
}, [])
```

---

## Integration Sequence Diagram

```
Candidate SMS
     ↓
  Twilio Webhook
     ↓
  FastAPI /sms/webhook/twilio
     ↓
  Claude API (intent analysis + data extraction)
     ↓
  Supabase INSERT conversation_turns (RLS enforced)
     ↓
  Generate SMS reply via Claude
     ↓
  Twilio send_sms()
     ↓
  Candidate receives SMS
     ↓
  [Loop: candidate → SMS → analysis → reply]
     ↓
  On acceptance: Twilio → Merge.dev (push to Bullhorn ATS)
     ↓
  Stripe webhook: invoice.payment_succeeded
     ↓
  Update subscription tier → unlock features
```

---

## Performance & Scaling

| Integration | Latency | QPS | Notes |
|---|---|---|---|
| Claude Screening | 800ms | 10 | Batched via Celery for bulk |
| Twilio SMS | 2-10s | 100 | Webhooks <5s, rate limit 100/min |
| Merge.dev ATS | 30s | 1 | Call on-demand, cache results |
| Stripe Checkout | instant | 100 | Webhook ~1s |
| Supabase Realtime | <100ms | 1000 | WebSocket channel |

---

## Error Handling & Retries

**Twilio SMS fails**: Stored in `sms_messages` table with `status: failed`. Celery job retries after 5 min, max 3 attempts.

**Claude API timeout (>10s)**: Return cached screening from recent same role, flag for async reprocessing.

**Stripe webhook missed**: Webhook storage in Supabase; cron job checks for pending subscriptions every hour.

**Merge.dev rate limit**: Queue requests in Redis, max 1 req/sec per org.

---

## Testing Integration Endpoints

### Test Twilio Webhook (Local)
```bash
# Use ngrok to tunnel local FastAPI
ngrok http 8000
# Configure in Twilio: https://abc123.ngrok.io/api/v1/sms/webhook/twilio

# Send test SMS to Twilio number
curl https://abc123.ngrok.io/api/v1/sms/webhook/twilio \
  -d "From=+15551234567&To=+18005RECRUITER&Body=Hi%20there&MessageSid=SMxxx"
```

### Test Screening (Sandbox)
```bash
curl -X POST http://localhost:8000/api/v1/screening/cand_123/screen \
  -H "Authorization: Bearer $JWT" \
  -d '{"job_requirements": "2+ server", "use_claude": true}'
```

### Test Merge.dev Sync
```bash
curl http://localhost:8000/api/v1/candidates/sync/ats \
  -H "Authorization: Bearer $JWT"
```

---

## Production Checklist

- [ ] Twilio webhook signature validation enabled
- [ ] Stripe webhook signature validation enabled
- [ ] Claude API key rate limits configured
- [ ] Supabase RLS policies tested (no data leaks)
- [ ] Redis/Celery job queue monitoring
- [ ] SMS rate limiting: 50 SMS/min per org
- [ ] Claude screening cache: 24h TTL
- [ ] Error logging: Sentry + CloudWatch
- [ ] Backups: Daily Supabase automated backups
- [ ] Monitoring: PagerDuty alerts for >5% error rate

---

**Last Updated**: April 2026
