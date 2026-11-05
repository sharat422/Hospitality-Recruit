# HospRecruit AI - Getting Started Guide

## Project Overview

HospRecruit AI is a **complete full-stack SaaS platform** addressing 6 major pain points in hospitality recruiting. The entire application is here in one monorepo.

---

## What You Have

### Backend (FastAPI + Supabase)
- ✅ 8 modules with **48 endpoints**
- ✅ Async FastAPI with dependency injection
- ✅ Pydantic v2 schemas for all data models
- ✅ Supabase PostgreSQL with Row-Level Security (multi-tenant)
- ✅ Services + repositories pattern (clean architecture)
- ✅ Claude/GPT-4o integration for AI screening
- ✅ Twilio SMS webhooks
- ✅ Stripe billing
- ✅ Merge.dev ATS integration

### Frontend (React + TypeScript + Vite)
- ✅ React 18 + Vite (<100ms dev startup)
- ✅ TanStack Query v5 for server state management
- ✅ Shadcn/ui components + Tailwind CSS
- ✅ Recharts dashboards
- ✅ Supabase auth integration
- ✅ Sample components: Dashboard, Screening, Login

### Database (Supabase)
- ✅ PostgreSQL schema with RLS policies
- ✅ 8 module tables
- ✅ Real-time subscriptions enabled
- ✅ Auth integration ready

### Documentation
- ✅ [ENDPOINTS.md](docs/ENDPOINTS.md) - 48 FastAPI endpoints
- ✅ [TECH_INTEGRATION.md](docs/TECH_INTEGRATION.md) - Twilio, Claude, Stripe, Merge, Supabase integration
- ✅ [README.md](README.md) - Project overview

---

## Setup Steps

### 1. Backend Environment

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
# OR: poetry install

# Create .env file
cp .env.example .env

# Edit .env with your keys:
# - SUPABASE_URL, SUPABASE_KEY, SUPABASE_JWT_SECRET
# - ANTHROPIC_API_KEY
# - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
# - MERGE_DEV_API_KEY
# - STRIPE_SECRET_KEY
# - OPENAI_API_KEY (optional, for GPT-4o)
```

### 2. Frontend Environment

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local
cp .env.example .env.local

# Edit .env.local:
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_KEY=eyJ...
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 3. Supabase Setup

```bash
# Create account at https://supabase.com

# In Supabase Dashboard → SQL Editor, run:
# File: supabase/migrations/001_init_schema.sql

# This creates:
# - organizations, users tables (auth)
# - candidates, jobs, shifts, shift_matches (recruiting)
# - compliance_tasks, onboarding_flows (onboarding)
# - sms_messages, conversation_turns (sms)
# - subscriptions, white_label_configs (billing)
# - All with Row Level Security (RLS) policies
```

### 4. Run Both Services

**Terminal 1 - Backend**:
```bash
cd backend
python run.py
# FastAPI: http://localhost:8000
# API Docs: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

**Terminal 2 - Frontend**:
```bash
cd frontend
npm run dev
# React: http://localhost:5173
```

---

## File Structure at a Glance

```
/backend
├── app/
│   ├── core/
│   │   ├── config.py          # Settings from environment
│   │   ├── security.py        # JWT validation
│   │   ├── dependencies.py    # DI setup (Supabase client)
│   │   └── exceptions.py      # Custom exceptions
│   ├── routers/               # API routes (8 modules)
│   │   ├── candidates.py      # Module 1, 3, 7
│   │   ├── screening.py       # Module 1
│   │   ├── shifts.py          # Module 2
│   │   ├── sms.py             # Module 4
│   │   ├── onboarding.py      # Module 5
│   │   ├── analytics.py       # Module 6
│   │   ├── talent_pool.py     # Module 7
│   │   ├── billing.py         # Module 8
│   │   └── __init__.py
│   ├── services/              # Business logic (8 modules)
│   │   ├── screening_service.py
│   │   ├── shift_service.py
│   │   ├── sms_service.py
│   │   ├── onboarding_service.py
│   │   ├── analytics_service.py
│   │   ├── talent_pool_service.py
│   │   └── billing_service.py
│   ├── repositories/          # Supabase data access (RLS)
│   │   ├── candidate_repo.py
│   │   ├── shift_repo.py
│   │   ├── onboarding_repo.py
│   │   ├── analytics_repo.py
│   │   ├── talent_pool_repo.py
│   │   └── billing_repo.py
│   ├── schemas/               # Pydantic v2 models
│   │   └── __init__.py        # All 20+ schemas
│   ├── models/                # SQLAlchemy (optional)
│   ├── integrations/          # Twilio, Claude, Stripe, Merge
│   └── main.py                # FastAPI app
├── run.py                     # Uvicorn runner
├── pyproject.toml            # Poetry dependencies
├── requirements.txt          # pip dependencies
└── .env.example             # Environment template

/frontend
├── src/
│   ├── components/            # React components
│   │   ├── Dashboard.tsx      # Module 6: Manager dashboard
│   │   ├── ScreeningModule.tsx # Module 1: AI screening
│   │   └── ui/                # Shadcn/ui components
│   ├── pages/
│   │   └── LoginPage.tsx      # Auth page
│   ├── hooks/
│   │   ├── useAuth.tsx        # Supabase auth context
│   │   └── useApiFunctions.ts # React Query hooks (48 endpoints)
│   ├── lib/
│   │   ├── supabase.ts        # Supabase client
│   │   ├── api.ts             # Axios client with JWT
│   │   └── queryConfig.ts     # React Query config
│   ├── App.tsx                # Router + providers
│   ├── index.css              # Tailwind styles
│   └── main.tsx               # Entry point
├── package.json
├── vite.config.ts
├── tsconfig.json
└── .env.example

/supabase
└── migrations/
    └── 001_init_schema.sql    # Full PostgreSQL schema + RLS

/docs
├── README.md                  # Project overview
├── ENDPOINTS.md              # 48 API endpoints reference
└── TECH_INTEGRATION.md       # Twilio, Claude, Stripe integration
```

---

## Key Concepts

### Pain Points (Why HospRecruit Wins)

| Pain | Industry Impact | HospRecruit Solution |
|------|---|---|
| **#1**: 100-500 apps/role, 65% recruiter screening time, 40% higher cost-per-hire | Massive inefficiency | Claude screens 30 sec vs 15 min manual |
| **#2**: 70% no-show rate, seasonal chaos | Revenue loss, understaffing | SMS + shift matching reduces to 40% |
| **#3**: Manager burnout, slow fills | High turnover | Real-time dashboard + alerts |
| **#4**: Talent evaporation between seasons | Rehire from scratch | Cohort + SMS re-engagement |
| **#5**: Compliance drag (ServSafe, background checks, multi-state laws) | 14-day onboarding | Automated workflow: 3-5 days |
| **#6**: Razor-thin margins, recruiter churn | Sustainability risk | SaaS (Starter/Growth/Enterprise) + white-label |

### Architecture Patterns

**Services + Repositories**:
```
Router → Service → Repository → Supabase (RLS)
```

**Dependency Injection**:
```python
@router.post("/candidates/")
async def create(
    candidate: CandidateCreate,
    user: dict = Depends(get_current_user),
    supabase: SupabaseClient = Depends(),
):
    repo = CandidateRepository(supabase)
    return await repo.create_candidate(candidate, user["sub"])
```

**Row Level Security (Multi-Tenant)**:
```sql
-- Candidates belong to org; user must be in same org
CREATE POLICY candidates_org_isolation ON candidates
  USING (
    auth.user_id() IN (
      SELECT id FROM users WHERE org_id = candidates.org_id
    )
  );
```

### React Query + Supabase Real-Time

```typescript
// Automatic caching, background sync, real-time updates
const { data, isLoading } = useManagerDashboard()

// Subscribes to real-time changes
useEffect(() => {
  const channel = supabase
    .channel('candidates')
    .on('postgres_changes', { table: 'candidates' }, () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
    })
    .subscribe()
}, [])
```

---

## Common Tasks

### Add New Endpoint

1. **Create schema** in `backend/app/schemas/__init__.py`
2. **Create router** in `backend/app/routers/my_module.py`
3. **Create service** in `backend/app/services/my_service.py`
4. **Create repository** in `backend/app/repositories/my_repo.py`
5. **Include router** in `backend/app/main.py`

### Add React Hook

```typescript
// src/hooks/useApiFunctions.ts
export const useMyFeature = () => {
  return useQuery({
    queryKey: ['my-feature'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/my-endpoint`)
      return data
    },
  })
}
```

### Test Endpoint

```bash
curl -X GET http://localhost:8000/api/v1/candidates/job/uuid \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Environment Variables Checklist

### Backend (.env)
- [ ] `SUPABASE_URL` - Get from Supabase dashboard
- [ ] `SUPABASE_KEY` - Anon key
- [ ] `SUPABASE_JWT_SECRET` - JWT secret
- [ ] `ANTHROPIC_API_KEY` - Claude API key
- [ ] `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- [ ] `MERGE_DEV_API_KEY`
- [ ] `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- [ ] `OPENAI_API_KEY` (optional)

### Frontend (.env.local)
- [ ] `VITE_SUPABASE_URL`
- [ ] `VITE_SUPABASE_KEY`
- [ ] `VITE_API_BASE_URL` = `http://localhost:8000/api/v1`

---

## Troubleshooting

**Backend won't start**: Check `.env` vars match Supabase project

**Frontend can't connect**: Ensure backend running on 8000, frontend on 5173

**JWT expired**: Supabase auto-refreshes; check browser storage

**RLS blocking queries**: Verify user has `auth.user_id()` matching Supabase auth

---

## Next Steps

1. **Run locally** following setup steps above
2. **Read** [ENDPOINTS.md](docs/ENDPOINTS.md) for full API reference
3. **Read** [TECH_INTEGRATION.md](docs/TECH_INTEGRATION.md) for Twilio/Claude/Stripe details
4. **Customize** schemas + endpoints for your use case
5. **Deploy** to Render (backend) + Vercel (frontend)

---

## Support

- Docs: [docs/ENDPOINTS.md](docs/ENDPOINTS.md), [docs/TECH_INTEGRATION.md](docs/TECH_INTEGRATION.md)
- FastAPI Swagger: http://localhost:8000/docs
- Supabase Docs: https://supabase.com/docs

---

**Ready to hire? Let's reduce that 70% no-show rate.** 🚀
