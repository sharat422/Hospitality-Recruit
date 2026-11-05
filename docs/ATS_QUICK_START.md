# ATS Integration - Quick Start Checklist

**HospRecruit AI | Bi-Directional ATS Sync via Merge.dev**

---

## Pre-Integration Verification

### Code Files Location
- [ ] `supabase/migrations/004_ats_integration.sql` exists (480 lines)
- [ ] `backend/app/services/ats_merge_dev_service.py` exists (550 lines)
- [ ] `backend/app/routers/ats.py` exists (480 lines)
- [ ] `frontend/src/components/ATSSettings.tsx` exists (580 lines)

### Documentation
- [ ] `docs/ATS_MERGE_DEV_GUIDE.md` read and understood
- [ ] `docs/ATS_IMPLEMENTATION_SUMMARY.md` reviewed

---

## Step 1: Database Setup (5 minutes)

### 1.1 Apply Migration
```bash
# Terminal
cd supabase
supabase migration up 004_ats_integration.sql

# Or via CLI:
supabase db push
```

### 1.2 Verify Tables Created
```bash
# In Supabase dashboard → SQL Editor, run:
SELECT table_name FROM information_schema.tables 
WHERE table_schema='public' 
AND table_name LIKE 'ats_%';

# Should show:
# - ats_configurations
# - ats_synced_jobs
# - candidate_ats_mappings
# - ats_sync_logs
# - ats_events
```

### 1.3 Verify RLS Policies
```bash
# In Supabase dashboard:
# Go to Authentication → Policies
# Verify each ATS table has RLS policy enabled
# Status: Check mark next to each table
```

### 1.4 Enable Realtime
```bash
# In Supabase dashboard → Replication:
# Enable realtime for:
# ✅ ats_configurations
# ✅ ats_synced_jobs
# ✅ ats_events
```

---

## Step 2: Backend Setup (10 minutes)

### 2.1 Copy Files
```bash
# Copy service file
cp ats_merge_dev_service.py backend/app/services/

# Copy router file
cp ats.py backend/app/routers/
```

### 2.2 Configure Environment
```bash
# Edit .env
MERGE_API_KEY=your_merge_api_key_here
MERGE_BASE_URL=https://api.mergeapi.com
```

**Where to get MERGE_API_KEY:**
1. Go to https://merge.dev
2. Sign up / login
3. Dashboard → API Keys
4. Copy your API key
5. Paste into .env

### 2.3 Register Router in FastAPI App
```python
# backend/app/main.py

# Add imports at top:
from app.routers import ats

# In app initialization, after other routers:
app.include_router(
    ats.router,
    prefix="/api",
    tags=["ats"]
)

# Verify app starts:
uvicorn app.main:app --reload
```

### 2.4 Test Backend Endpoints
```bash
# Test OAuth URL endpoint
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/ats/oauth-url

# Should return:
# {"oauth_url": "https://app.merge.dev/oauth?..."}
```

---

## Step 3: Frontend Setup (10 minutes)

### 3.1 Copy Component File
```bash
cp ATSSettings.tsx frontend/src/components/
```

### 3.2 Create Route
```tsx
// frontend/src/pages/settings/ats.tsx
import React from 'react';
import { ATSSettings } from '@/components/ATSSettings';

export default function ATSSettingsPage() {
  return <ATSSettings />;
}
```

### 3.3 Add Navigation Link
```tsx
// frontend/src/components/SettingsNav.tsx
<Link to="/settings/ats">
  <Icon name="link" />
  ATS Integration
</Link>
```

### 3.4 Verify API Calls
```bash
# Start frontend dev server
npm start

# Open browser DevTools → Network → Filter "ats"
# Navigate to /settings/ats
# Verify API calls appear in network tab
```

---

## Step 4: Merge.dev Setup (15 minutes)

### 4.1 Create Merge.dev Account
1. Go to https://merge.dev
2. Sign up (free tier OK)
3. Create "Production" environment
4. Create integration for "ATS"

### 4.2 Configure ATS OAuth (Choose One)

#### For Bullhorn:
1. In Merge.dev dashboard → ATS Integration → Settings
2. Click "Connect Bullhorn"
3. Enter Bullhorn OAuth credentials
4. Authorize

#### For iCIMS:
1. In Merge.dev dashboard → ATS Integration → Settings
2. Click "Connect iCIMS"
3. Enter iCIMS API key
4. Save

#### For Greenhouse:
1. In Merge.dev dashboard → ATS Integration → Settings
2. Click "Connect Greenhouse"
3. Enter Greenhouse Harvest API token
4. Save

**Repeat for each ATS platform you want to support**

### 4.3 Configure Webhook
1. In Merge.dev dashboard → Webhooks
2. Create new webhook:
   - URL: `https://yourapp.com/api/ats/webhook`
   - Events: All ATS events
   - Secret: Generate (copy to .env → MERGE_WEBHOOK_SECRET)

### 4.4 Test Webhook
1. In Merge.dev → Webhooks → Select your webhook
2. Click "Send test event"
3. Check HospRecruit logs for receipt

---

## Step 5: Integration Testing (15 minutes)

### Test 1: OAuth Connection
```
Steps:
1. Open http://localhost:3000/settings/ats
2. Click "Connect ATS"
3. You're redirected to Merge.dev
4. Click "Continue"
5. Choose ATS provider (Bullhorn, iCIMS, etc)
6. Enter provider credentials
7. Authorize
8. Redirected back to app with "Connected" status

Expected Result:
✅ See "Connected" badge
✅ Last sync time displays
✅ Sync buttons enabled
```

### Test 2: Job Sync (Manual)
```
Steps:
1. Click "Sync Jobs Now" button
2. Wait for completion message
3. Check "Synced Jobs" tab

Expected Result:
✅ Jobs appear in list
✅ Shows job titles, departments, locations
✅ Sync log shows "success"
```

### Test 3: View Synced Jobs
```
Steps:
1. Go to Settings → ATS Integration
2. Click "Synced Jobs" tab
3. Scroll through job list

Expected Result:
✅ See 5-20 jobs from ATS
✅ Each shows title, department, location
✅ Hiring manager name displays
```

### Test 4: Disconnect
```
Steps:
1. Click "Disconnect" button
2. Confirm in dialog
3. Wait for completion

Expected Result:
✅ Badge changes to "Disconnected"
✅ All buttons disabled
✅ Sync can't proceed
```

---

## Step 6: Production Checklist (5 minutes)

### Pre-Deployment
- [ ] Environment variables set in production (.env)
- [ ] Database migration applied to production DB
- [ ] Backend service deployed to production
- [ ] Frontend code deployed to production
- [ ] Webhook URL updated to production domain

### Post-Deployment
- [ ] Test OAuth flow in production
- [ ] Test job sync in production
- [ ] Check logs for any errors
- [ ] Verify sync logs in database
- [ ] Test webhook receipt

### Monitoring Setup
- [ ] Monitor `ats_sync_logs` for failures
- [ ] Alert if sync fails >5% in last hour
- [ ] Alert if pending syncs >50
- [ ] Monitor response times (should be <1s)

---

## File Locations Reference

```
Root/
├── backend/
│   └── app/
│       ├── services/
│       │   └── ats_merge_dev_service.py ✅ Place here
│       ├── routers/
│       │   └── ats.py ✅ Place here
│       └── main.py (Edit to register router)
│
├── frontend/
│   └── src/
│       └── components/
│           └── ATSSettings.tsx ✅ Place here
│
├── supabase/
│   └── migrations/
│       └── 004_ats_integration.sql ✅ Run this
│
└── docs/
    ├── ATS_MERGE_DEV_GUIDE.md ✅ Reference
    └── ATS_IMPLEMENTATION_SUMMARY.md ✅ Reference
```

---

## Troubleshooting Quick Links

| Problem | Solution |
|---------|----------|
| OAuth won't connect | See ATS_MERGE_DEV_GUIDE.md → Troubleshooting → ATS Won't Connect |
| Jobs not syncing | Check ats_sync_logs table for errors |
| Webhook not received | Verify webhook URL is public + HTTPS |
| 401 Unauthorized | Check JWT token validity |
| 429 Rate Limited | Wait 1-2 minutes, retry |
| Candidates won't push | Verify candidate has required fields |

---

## Commands & Queries

### Database - Check Migration Status
```sql
SELECT * FROM supabase_migrations 
WHERE name LIKE '%ats%';
```

### Database - View Sync Logs
```sql
SELECT operation_type, status, created_at 
FROM ats_sync_logs 
ORDER BY created_at DESC 
LIMIT 20;
```

### Database - View Pending Syncs
```sql
SELECT * FROM candidate_ats_mappings 
WHERE requires_resync = true;
```

### Backend - Start Dev Server
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Frontend - Start Dev Server
```bash
cd frontend
npm start
```

### Test HTTP Endpoints
```bash
# Get OAuth URL
curl -H "Authorization: Bearer YOUR_JWT" \
  http://localhost:8000/api/ats/oauth-url

# Get connected ATS status
curl -H "Authorization: Bearer YOUR_JWT" \
  http://localhost:8000/api/ats/status

# Sync jobs (POST)
curl -X POST \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/ats/jobs/sync
```

---

## Success Criteria

✅ **Database**: 5 tables created with RLS + triggers
✅ **Backend**: Service imports without errors + 12 endpoints accessible
✅ **Frontend**: Component renders without console errors
✅ **OAuth**: "Connect ATS" button works + redirects to Merge.dev
✅ **Sync**: Jobs appear after clicking "Sync Now"
✅ **Logs**: Operations logged in `ats_sync_logs` table

---

## Support Resources

- **Merge.dev Docs**: https://merge.dev/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **React Docs**: https://react.dev
- **Supabase Docs**: https://supabase.com/docs
- **This Project Guide**: docs/ATS_MERGE_DEV_GUIDE.md

---

## Time Estimate

| Phase | Time | Status |
|-------|------|--------|
| Database Setup | 5 min | ⏱️ |
| Backend Setup | 10 min | ⏱️ |
| Frontend Setup | 10 min | ⏱️ |
| Merge.dev Config | 15 min | ⏱️ |
| Integration Testing | 15 min | ⏱️ |
| **Total** | **55 min** | ✅ |

---

## Sign-Off

- [ ] Integration completed
- [ ] All tests passed
- [ ] No errors in logs
- [ ] Team trained on usage
- [ ] Monitoring setup
- [ ] Documentation shared

**Integration Completed By**: ________________
**Date**: ________________
**Notes**: ________________________________________________

---

**Version**: 1.0.0
**Last Updated**: January 2024
**Status**: Ready for Integration
