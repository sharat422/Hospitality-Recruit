# Application-Wide Search Audit

## Outcome

Before this change, HospRecruit had page-level filters and a skill-taxonomy search icon, but no shared search API, autocomplete, recent-search history, or global search UI. Global search was therefore **MISSING** end to end.

## Implemented Coverage

| Category | Before | Current data source | Authorization and safe projection |
|---|---|---|---|
| Candidates | MISSING | `candidates` + scoped `applications` | `candidates.read`; tenant, property and department scope; name/contact summary only |
| Employees | MISSING | `users` | `employees.read`; tenant/property/department scope; no payroll, bank, UPI or statutory fields |
| Jobs | MISSING | `jobs` | `jobs.read`; tenant/property/department scope |
| Applications | MISSING | `applications`, candidate/job display maps | `applications.read`; tenant/property/department scope |
| Referrals | MISSING | `referrals` | Employee sees own referrals; reporting/financial roles see tenant referrals; no payout identifiers or UPI data |
| Documents | MISSING | `candidate_documents` | `documents.read` plus accessible candidate scope; no storage key, signed URL or document content |
| Properties | MISSING | `properties` | `properties.read`; assigned properties only except group roles |
| Departments | MISSING | `property_departments` | `properties.read`; property and department scope |
| Complaints | MISSING | `hr_complaints`, `complaint_case_members` | `complaints.read` plus strict case membership. POSH always requires assignment, including Owner. Only ticket/category/severity/status are returned. |

## Files

- Migration: `supabase/migrations/057_global_search.sql`
- Ranking and scope helpers: `backend/app/services/global_search_service.py`
- API: `backend/app/routers/global_search.py`
- Router registration: `backend/app/main.py`
- React command palette: `frontend/src/components/GlobalSearch.tsx`
- Shared app header: `frontend/src/components/AppLayout.tsx`
- Tests: `backend/tests/test_global_search.py`

## API

- `GET /api/v1/search?q=...&categories=...&limit=...` performs a search and records it in the caller's recent history.
- `GET /api/v1/search/autocomplete?q=...&categories=...&limit=...` returns suggestions without recording history.
- `GET /api/v1/search/recent` returns only the authenticated user's recent searches.
- `DELETE /api/v1/search/recent` clears only the authenticated user's recent searches.

Queries require 2-100 characters. Categories and result counts are capped. Unknown categories return HTTP 422. Ranking is deterministic: exact, prefix, contains, all-token, then fuzzy similarity. The frontend debounces autocomplete by 250 ms and supports `Ctrl/Cmd+K`.

## Security Notes

- The browser never queries domain tables directly. The API derives the caller's canonical RBAC context first.
- Standard tables are queried with the caller JWT, so Postgres RLS remains active. Backend scope checks are a second layer.
- The service-role client is used only to obtain complaint candidates, followed by the same explicit assignment rules as the grievance case list.
- Complaint text, reporter identity, anonymous token, evidence, resolution text, document storage paths, payroll data and referral payout data never enter a search response.
- Recent searches have self-only RLS and cannot be read across users or organizations.

## Remaining Scale Consideration

The current service ranks a bounded authorized candidate set in Python to support deterministic typo matching across heterogeneous fields. Trigram indexes are ready for a future database RPC when a tenant routinely exceeds the per-category candidate cap. This is a scaling enhancement, not an authorization bypass; no broader result set should be introduced without retaining RLS and case-level complaint checks.
