# HospRecruit AI Billing System
**Complete Stripe + Supabase Integration**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Pricing Tiers](#pricing-tiers)
3. [System Architecture](#system-architecture)
4. [Database Schema](#database-schema)
5. [API Endpoints](#api-endpoints)
6. [Stripe Webhook Handlers](#stripe-webhook-handlers)
7. [Tier Limit Enforcement](#tier-limit-enforcement)
8. [React Components](#react-components)
9. [Setup Instructions](#setup-instructions)
10. [Testing Guide](#testing-guide)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The HospRecruit AI billing system is a complete SaaS subscription and usage management solution with:

- **5 pricing tiers**: Free Trial, Pilot ($99), Starter ($149), Growth ($499), Scale ($999), Enterprise (custom)
- **Usage-based limits**: Enforced at middleware level
- **AI credit system**: Pay-as-you-go for video interviews ($0.50/credit)
- **Stripe integration**: Full checkout, subscriptions, invoicing
- **14-day free trial**: No credit card required
- **Annual 20% discount**: Built-in savings for committed customers
- **Real-time usage tracking**: Monitor consumption in dashboard
- **Comprehensive audit trail**: All billing events logged

---

## Pricing Tiers

| Tier | Price/mo | Price/yr | Roles/mo | Interviews/mo | AI Credits/mo | Features |
|------|----------|----------|----------|---------------|---------------|----------|
| **Free Trial** | Free | - | 5 | 10 | 20 | 14-day access, no CC |
| **Pilot** | $99 | - | 10 | 25 | 50 | Limited features, 1-month pilot |
| **Starter** | $149 | $1,432 | 25 | 50 | 100 | Core features |
| **Growth** | $499 | $4,790 | 100 | 250 | 500 | + Scheduling, branding |
| **Scale** | $999 | $9,590 | 500 | 1,000 | 2,000 | + SSO, API, priority |
| **Enterprise** | Custom | - | ∞ | ∞ | ∞ | Full customization |

### Feature Matrix

| Feature | Free Trial | Pilot | Starter | Growth | Scale | Enterprise |
|---------|-----------|-------|---------|--------|-------|------------|
| AI Screening | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SMS Screening | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Interview Scheduling | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Custom Branding | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| SSO & Security | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| API Access | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Priority Support | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
│  ┌──────────────────┐          ┌──────────────────┐    │
│  │  Pricing Page    │          │ Billing Dashboard│    │
│  │  - All 5 tiers   │          │ - Usage metrics  │    │
│  │  - Comparison    │          │ - Invoices       │    │
│  │  - Checkout      │          │ - Manage sub     │    │
│  └──────────────────┘          └──────────────────┘    │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│                   Backend (FastAPI)                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │         /billing Endpoints (12 total)           │  │
│  │  - /pricing/tiers                               │  │
│  │  - /checkout, /checkout/credits                 │  │
│  │  - /status, /limits                             │  │
│  │  - /invoices, /cancel-subscription              │  │
│  │  - /use-ai-credits, /webhook                    │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────┐        ┌────────────────────┐   │
│  │ tier_limits.py   │        │ stripe_webhooks.py │   │
│  │ - Enforce limits │        │ - Handle events    │   │
│  │ - Check features │        │ - Update records   │   │
│  └──────────────────┘        └────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐  │
│  │      stripe_service.py (500+ lines)             │  │
│  │  - Customer creation                            │  │
│  │  - Subscription management                      │  │
│  │  - Checkout sessions                            │  │
│  │  - Credit operations                            │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│              Stripe (Payment Provider)                   │
│  - Customer management                                 │
│  - Subscription lifecycle                              │
│  - Invoice generation                                  │
│  - Webhook notifications                               │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│             Supabase (Database & Auth)                  │
│  - tier_limits (pricing tiers)                          │
│  - organizations (customer accounts)                    │
│  - subscriptions (subscription tracking)                │
│  - usage_tracking (monthly consumption)                 │
│  - ai_credits_ledger (credit transactions)              │
│  - invoices (invoice history)                           │
│  - payment_methods (stored cards)                       │
│  - billing_events (webhook audit trail)                 │
│  - promo_codes (discount management)                    │
└─────────────────────────────────────────────────────────┘
```

---

## Database Schema

### 9 Core Tables

#### 1. **tier_limits**
Defines pricing, features, and limits for each tier.

```sql
CREATE TABLE tier_limits (
  id UUID PRIMARY KEY,
  tier_name VARCHAR(50) UNIQUE,
  display_name VARCHAR(100),
  base_price_monthly INT,        -- in cents
  base_price_annual INT,
  roles_per_month INT,
  video_interviews_per_month INT,
  ai_credits_per_month INT,
  custom_branding BOOLEAN,
  sso_enabled BOOLEAN,
  api_access BOOLEAN,
  priority_support BOOLEAN
);
```

#### 2. **organizations (extended)**
Customer accounts with billing metadata.

```sql
ALTER TABLE organizations ADD COLUMN (
  tier_name VARCHAR(50),                 -- free_trial, starter, growth, scale, enterprise
  stripe_customer_id VARCHAR(255),       -- Stripe customer ID
  stripe_subscription_id VARCHAR(255),   -- Current subscription
  subscription_status VARCHAR(50),       -- active, trialing, past_due, canceled
  trial_started_at TIMESTAMP,
  trial_ends_at TIMESTAMP,
  billing_cycle_start TIMESTAMP,
  billing_cycle_end TIMESTAMP,
  cancel_at_period_end BOOLEAN
);
```

#### 3. **subscriptions**
Track all active and historical Stripe subscriptions.

```sql
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  stripe_subscription_id VARCHAR(255) UNIQUE,
  tier_name VARCHAR(50),
  amount_paid INT,                       -- in cents
  billing_interval VARCHAR(10),          -- month or year
  status VARCHAR(50),                    -- active, trialing, canceled, etc
  started_at TIMESTAMP,
  current_period_start TIMESTAMP,
  current_period_end TIMESTAMP,
  trial_start TIMESTAMP,
  trial_end TIMESTAMP,
  canceled_at TIMESTAMP,
  auto_renew BOOLEAN
);
```

#### 4. **usage_tracking**
Monthly consumption counters (reset on billing cycle start).

```sql
CREATE TABLE usage_tracking (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  billing_month DATE,              -- First day of month
  roles_created INT DEFAULT 0,
  video_interviews_sent INT DEFAULT 0,
  ai_credits_used INT DEFAULT 0,
  UNIQUE(org_id, billing_month)
);
```

#### 5. **ai_credits_ledger**
Ledger of all AI credit transactions (purchase, use, refund, grant).

```sql
CREATE TABLE ai_credits_ledger (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  transaction_type VARCHAR(50),    -- monthly_grant, purchase, usage, refund
  amount INT,                       -- in credits (positive or negative)
  reference_type VARCHAR(50),       -- interview_id, invoice_id, etc
  reference_id VARCHAR(255),
  description TEXT,
  balance_after INT,                -- Running balance
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### 6. **invoices**
Invoice history and payment status tracking.

```sql
CREATE TABLE invoices (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  stripe_invoice_id VARCHAR(255) UNIQUE,
  amount_total INT,                 -- in cents
  amount_paid INT,
  currency VARCHAR(3),              -- USD
  invoice_number VARCHAR(50),
  issue_date TIMESTAMP,
  paid_date TIMESTAMP,
  status VARCHAR(50),               -- draft, open, paid, void
  hosted_invoice_url VARCHAR(2048),
  pdf_url VARCHAR(2048)
);
```

#### 7. **payment_methods**
Stored payment methods for each organization.

```sql
CREATE TABLE payment_methods (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  stripe_payment_method_id VARCHAR(255) UNIQUE,
  card_brand VARCHAR(20),           -- visa, mastercard, amex
  card_last4 VARCHAR(4),
  card_exp_month INT,
  card_exp_year INT,
  is_default BOOLEAN
);
```

#### 8. **billing_events**
Audit trail of all Stripe webhook events.

```sql
CREATE TABLE billing_events (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  event_type VARCHAR(100),          -- subscription_created, invoice_paid, etc
  stripe_event_id VARCHAR(255) UNIQUE,
  event_payload JSONB,
  processed_at TIMESTAMP,
  is_error BOOLEAN,
  error_message TEXT
);
```

#### 9. **promo_codes**
Discount code management.

```sql
CREATE TABLE promo_codes (
  id UUID PRIMARY KEY,
  code VARCHAR(50) UNIQUE,
  discount_type VARCHAR(20),        -- percent or fixed
  discount_value INT,
  valid_from TIMESTAMP,
  valid_until TIMESTAMP,
  max_uses INT,
  current_uses INT DEFAULT 0,
  applicable_tiers VARCHAR[],       -- Empty = all tiers
  is_active BOOLEAN
);
```

---

## API Endpoints

### Base URL: `/api/billing`

### Authentication
All endpoints (except `/pricing/tiers`) require JWT token.

### 1. Pricing Endpoints

#### GET `/pricing/tiers`
Get all available pricing tiers.

```bash
curl http://localhost:8000/api/billing/pricing/tiers
```

**Response:**
```json
[
  {
    "tier_name": "starter",
    "display_name": "Starter",
    "price_monthly": 14900,
    "price_annual": 143280,
    "roles_per_month": 25,
    "video_interviews_per_month": 50,
    "ai_credits_per_month": 100,
    "features": {
      "custom_branding": false,
      "sso_enabled": false,
      "api_access": false,
      "priority_support": false
    }
  }
]
```

### 2. Checkout Endpoints

#### POST `/checkout`
Create Stripe checkout session for subscription.

**Request:**
```json
{
  "tier": "growth",
  "billing_interval": "month",
  "promo_code": "SAVE20",
  "return_url": "https://app.example.com"
}
```

**Response:**
```json
{
  "session_id": "cs_live_...",
  "url": "https://checkout.stripe.com/pay/cs_live_..."
}
```

#### POST `/checkout/credits`
Create checkout session for AI credits purchase.

**Request:**
```json
{
  "num_credits": 100
}
```

**Response:**
```json
{
  "session_id": "cs_live_...",
  "url": "https://checkout.stripe.com/pay/cs_live_...",
  "amount_usd": 50.00
}
```

### 3. Subscription Endpoints

#### GET `/status`
Get current billing status and usage.

**Response:**
```json
{
  "tier": "growth",
  "tier_display": "Growth",
  "subscription_status": "active",
  "period_start": "2024-01-01T00:00:00Z",
  "period_end": "2024-02-01T00:00:00Z",
  "trial": {
    "status": "expired",
    "started_at": null,
    "ends_at": null
  },
  "usage": {
    "roles_per_month": {
      "limit": 100,
      "used": 42,
      "remaining": 58
    },
    "video_interviews_per_month": {
      "limit": 250,
      "used": 89,
      "remaining": 161
    },
    "ai_credits_per_month": {
      "limit": 500,
      "used": 127,
      "remaining": 373
    }
  }
}
```

#### GET `/limits`
Get tier limits and current usage.

**Response:**
```json
{
  "tier": "growth",
  "limits": {
    "roles_per_month": {
      "limit": 100,
      "used": 42,
      "remaining": 58
    },
    "video_interviews_per_month": {
      "limit": 250,
      "used": 89,
      "remaining": 161
    },
    "ai_credits_per_month": {
      "limit": 500,
      "used": 127,
      "remaining": 373
    }
  }
}
```

#### GET `/invoices?skip=0&limit=20`
Get invoice history.

**Response:**
```json
{
  "items": [
    {
      "id": "inv_uuid",
      "stripe_invoice_id": "in_1234567890",
      "amount_total": 49900,
      "amount_paid": 49900,
      "currency": "USD",
      "issue_date": "2024-01-01T00:00:00Z",
      "status": "paid",
      "paid_date": "2024-01-01T00:00:00Z",
      "pdf_url": "https://invoke.stripe.com/i/acct_..."
    }
  ],
  "total": 12
}
```

#### POST `/cancel-subscription`
Cancel subscription.

**Request:**
```json
{
  "at_period_end": true
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Subscription scheduled for cancellation at period end"
}
```

### 4. Usage & Credits Endpoints

#### POST `/use-ai-credits?num_credits=1`
Deduct AI credits (called internally by video interview system).

**Response:**
```json
{
  "success": true,
  "credits_used": 1,
  "remaining_credits": 372
}
```

### 5. Webhook Endpoint

#### POST `/webhook`
Stripe webhook handler (requires valid signature).

All Stripe events are routed to appropriate handlers.

---

## Stripe Webhook Handlers

The system handles 13 Stripe events:

### Customer Events
- `customer.created` - New customer created
- `customer.updated` - Customer information updated
- `customer.deleted` - Customer deleted

### Subscription Events
- `customer.subscription.created` - New subscription
- `customer.subscription.updated` - Subscription changes
- `customer.subscription.deleted` - Subscription canceled

### Invoice Events
- `invoice.created` - Invoice created
- `invoice.finalized` - Invoice ready for payment
- `invoice.paid` - Payment successful
- `invoice.payment_failed` - Payment failed

### Payment Intent Events
- `charge.succeeded` - One-time charge succeeded
- `charge.failed` - One-time charge failed
- `payment_intent.succeeded` - Payment intent successful
- `payment_intent.payment_failed` - Payment intent failed

### Event Handling Flow

```
Stripe Event
    ↓
POST /webhook (with signature verification)
    ↓
Extract event_type and data
    ↓
Route to appropriate handler:
    - store_subscription_data()
    - update_org_tier()
    - create_invoice()
    - grant_monthly_credits()
    - etc.
    ↓
Update Supabase tables
    ↓
Publish realtime update (organizations, subscriptions)
    ↓
Return 200 OK to Stripe
```

---

## Tier Limit Enforcement

### Middleware Checks

Tier limits are enforced at three layers:

#### 1. API Endpoint Level
```python
@router.post("/roles")
async def create_role(
    request: RoleRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    org_id = await get_org_id_from_user(db, current_user["id"])
    
    # Check limit before creating role
    can_create, limit, used = await TierLimitChecker.check_roles_limit(db, org_id)
    if not can_create:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Role limit reached ({used}/{limit} roles used this month)"
        )
    
    # Create role...
    await TierLimitChecker.increment_role_count(db, org_id)
```

#### 2. FastAPI Dependency
```python
async def require_roles_limit(db, org_id, limit_needed=1):
    can_create, limit, used = await TierLimitChecker.check_roles_limit(db, org_id)
    if not can_create:
        raise HTTPException(status_code=402, detail="Limit reached")
    return True
```

#### 3. Database Trigger
```sql
CREATE TRIGGER update_usage_on_role_creation
AFTER INSERT ON roles
FOR EACH ROW
EXECUTE FUNCTION increment_usage_tracking_roles()
```

### Response Codes

- `200 OK` - Operation allowed
- `402 Payment Required` - Usage limit exceeded
- `403 Forbidden` - Feature not available in tier
- `429 Too Many Requests` - Rate limit exceeded

---

## React Components

### 1. PricingPage.tsx

Display all pricing tiers with:
- Pricing toggle (month/year)
- Feature comparison table
- CTAs for each tier
- Trial/pilot promotional offers
- FAQ section

**Usage:**
```tsx
import { PricingPage } from '@/pages/PricingPage';

function App() {
  return <PricingPage />;
}
```

### 2. BillingDashboard.tsx

Manage subscription with tabs for:
- **Overview**: Current plan, period, trial info
- **Usage**: Monthly consumption metrics with progress bars
- **Invoices**: Invoice history with download links
- **Payment Methods**: Add/manage payment methods

**Usage:**
```tsx
import { BillingDashboard } from '@/pages/BillingDashboard';

function App() {
  return <BillingDashboard />;
}
```

---

## Setup Instructions

### Prerequisites
- Stripe account (free)
- Supabase project
- FastAPI 0.95+
- React 18+

### Step 1: Stripe Configuration

1. Go to [Stripe Dashboard](https://dashboard.stripe.com)
2. Create new API keys:
   - **Publishable Key** (starts with `pk_`)
   - **Secret Key** (starts with `sk_`)
3. Create Webhook Endpoint:
   - URL: `https://yourapp.com/api/billing/webhook`
   - Events: Select all relevant events
   - Save Signing Secret

### Step 2: Environment Configuration

```bash
# .env
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLIC_KEY=pk_live_...

# Database
DATABASE_URL=postgresql://...

# Frontend
REACT_APP_STRIPE_PUBLIC_KEY=pk_live_...
REACT_APP_API_URL=https://api.yourapp.com
```

### Step 3: Database Migration

```bash
# Apply billing schema
supabase migration up 005_billing_system.sql

# Verify tables created
supabase db push
```

### Step 4: Backend Setup

```python
# backend/app/main.py
from app.routers import billing

app.include_router(billing.router, prefix="/api", tags=["billing"])
```

### Step 5: Frontend Integration

```tsx
// src/routes.tsx
import { PricingPage } from '@/pages/PricingPage';
import { BillingDashboard } from '@/pages/BillingDashboard';

<Routes>
  <Route path="/pricing" component={PricingPage} />
  <Route path="/account/billing" component={BillingDashboard} />
</Routes>
```

### Step 6: Test End-to-End

1. Navigate to `/pricing`
2. Click "Start Free Trial"
3. Complete checkout (use Stripe test card: `4242 4242 4242 4242`)
4. Verify in `/account/billing`
5. Check database for records

---

## Testing Guide

### Test Cards
```
Success:        4242 4242 4242 4242 - Any exp/CVV
Decline:        4000 0000 0000 0002
Requires Auth:  4000 0025 0000 3155
```

### Test Workflows

#### 1. Free Trial Flow
1. Signup → Free trial initiated
2. Check `organizations.trial_ends_at` (14 days out)
3. Can create only 5 roles/month
4. On trial end, prompt for payment

#### 2. Paid Subscription Flow
1. Checkout for Starter tier
2. Complete Stripe payment
3. Webhook: `customer.subscription.created` received
4. `organizations.tier_name` = "starter"
5. `subscriptions` table updated
6. Dashboard shows "Active" status

#### 3. AI Credit Usage Flow
1. POST `/billing/use-ai-credits?num_credits=1`
2. Check `usage_tracking.ai_credits_used` incremented
3. Entry added to `ai_credits_ledger`
4. GET `/billing/status` shows updated remaining

#### 4. Upgrade Tier Flow
1. Checkout for Growth tier at `/checkout`
2. Stripe creates new subscription
3. Old subscription canceled
4. `organizations.tier_name` updated to "growth"
5. New limits applied

### Debugging

Enable webhook logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# All webhook events logged
```

Check billing events in database:
```sql
SELECT * FROM billing_events 
ORDER BY created_at DESC 
LIMIT 20;
```

---

## Troubleshooting

### Issue: Webhook events not received

**Solution:**
1. Verify webhook URL is public (not localhost)
2. Check Stripe Webhook Endpoint is enabled
3. Verify signing secret matches (`STRIPE_WEBHOOK_SECRET`)
4. Check server logs for webhook receipt

### Issue: Tier limits not enforcing

**Solution:**
1. Verify `usage_tracking` entry exists for org
2. Check `billing_month` matches current month
3. Ensure middleware is registered in FastAPI app
4. Verify JWT token includes `org_id`

### Issue: Trial not ending

**Solution:**
1. Check `organizations.trial_ends_at` date
2. Implement cron job to check expired trials:
```python
async def check_expired_trials():
    # Find orgs with expired trials
    # Send email reminder
    # Downgrade to free tier if no payment
```

### Issue: Credit purchase not working

**Solution:**
1. Verify org has `stripe_customer_id` set
2. Check `ai_credits_ledger` for transaction
3. Confirm `payment_intent.succeeded` webhook fired
4. Verify credit balance calculation in GET `/status`

---

## Deployment Checklist

- [ ] Stripe API keys added to production environment
- [ ] Database migration applied to production
- [ ] Webhook URL updated to production domain
- [ ] SSL certificate installed (webhooks require HTTPS)
- [ ] Monitoring setup (failed webhooks, payment failures)
- [ ] Email notifications configured:
  - Trial ending reminder
  - Payment failed alert
  - Invoice sent notification
- [ ] Support documentation updated
- [ ] Team trained on billing features
- [ ] Error monitoring (Sentry, etc.) enabled

---

## Success Metrics

Track these KPIs:

1. **Conversion**: Free trial → Paid subscriber (target: 25%)
2. **Retention**: Churn rate month-over-month (target: <5%)
3. **ARPU**: Average revenue per user (target: $400+)
4. **LTV**: Lifetime value (target: $4,800+)
5. **Webhook Success**: Event processing rate (target: 99.9%)
6. **Payment Success**: Charge success rate (target: 98%+)

---

## Future Enhancements

- [ ] Usage-based billing for Scale tier
- [ ] Custom tier creation for Enterprise
- [ ] Multi-currency support
- [ ] Tax calculation (Stripe Tax)
- [ ] Revenue recognition (ASC 606)
- [ ] Dunning management (automatic retry)
- [ ] Seat-based pricing
- [ ] Usage alerts before limit
- [ ] Auto-upgrade when approaching limit
- [ ] Bulk discounts for annual prepay

---

**Version**: 1.0.0
**Last Updated**: January 2024
**Status**: ✅ Production Ready
