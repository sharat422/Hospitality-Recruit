# Hospitality AI Assistant Audit

## Audit Result

The application previously contained multiple **feature-specific AI integrations**, but no application-wide management assistant.

| Existing AI feature | Status | Architecture | Main risk before this module |
|---|---|---|---|
| Candidate resume parsing and matching | Complete/partial by workflow | Dedicated Claude services and deterministic screening layer | Older matching paths allow Claude-generated scoring; newer screening governance correctly keeps scores deterministic |
| Screening chatbot | Feature-specific assistant | SMS screening session service, Claude prompts, Supabase transcript tables | Candidate-only scope; not suitable for workforce analytics |
| JD generation | Complete | Claude generation with deterministic fallback | Generated copy requires recruiter review |
| Engagement/NPS wording | Complete | Direct Claude calls in engagement/NPS services | Narrative output can be inaccurate if displayed without source metrics |
| Cross-application analytics assistant | Missing before migration `058` | No tool registry, assistant conversation store, source disclosure, or assistant-specific RBAC | A generic LLM prompt would risk cross-property disclosure and invented calculations |

## Implemented Architecture

The Hospitality AI Assistant is a **read-only analytics orchestration layer**:

1. FastAPI authenticates the caller and builds the canonical RBAC/property/department context.
2. A deterministic intent classifier selects one tool from a fixed allowlist. The LLM cannot select tables, write SQL, or call arbitrary endpoints.
3. The tool checks both `reports.read` and its domain permission before reading data.
4. Supabase executes queries with the caller JWT, retaining table RLS. Backend property and department filters provide a second boundary.
5. Existing deterministic business calculations or explicit assistant metric functions compute the answer.
6. Claude may rewrite aggregate, non-PII metrics only. Retention-risk employee rows always use deterministic wording and are never sent to Claude.
7. The API returns narrative, verified metrics, supporting rows, methodology, table sources, filters, and generation mode separately.
8. Conversation messages and tool runs are persisted for the current user with self-only RLS.

## Available Tools

| Tool | Permission | Authoritative data | Calculation |
|---|---|---|---|
| `attrition_analysis` | `reports.read` + `employees.read` | `employee_turnover_history`, `property_departments` | Equal-period exit comparison and recorded reason counts |
| `property_overtime` | `reports.read` + `attendance.read` | `attendance_daily_records`, `properties` | Sum validated overtime minutes by authorized property |
| `hardest_jobs` | `reports.read` + `jobs.read` + `applications.read` | `jobs`, `applications` | Transparent index using open age, vacancies and application volume |
| `retention_risk` | `reports.read` + `employees.read` | `employee_retention_risk_scores`, `users` | Current persisted explainable rules-based scores |
| `aged_vacancies` | `reports.read` + `jobs.read` | `jobs` | OPEN/ACTIVE jobs older than the threshold |
| `recruitment_performance` | `reports.read` + jobs/applications access | `applications`, `jobs` | Existing deterministic recruitment analytics aggregation |

All tools are read-only. `POST /api/v1/assistant/actions` returns HTTP 405. There is no destructive tool, SQL tool, payroll-detail tool, document tool, or complaint tool.

## Database Access and Authorization

- Assistant tables: `ai_assistant_conversations`, `ai_assistant_messages`, `ai_assistant_tool_runs`.
- Domain data remains in its canonical tables; no analytics copy or vector database was introduced.
- Owner and Group HR may use group scope. Other roles are limited to assigned properties; Department Heads are also limited to their departments.
- Tool discovery itself is permission-aware. A recruiter does not see overtime or employee-risk tools without the corresponding permissions.
- The assistant never returns payslip rows, compensation, bank/UPI data, Aadhaar/PAN, complaint information, or documents.
- Employee-risk identities are returned only to callers already authorized for those employees and never transmitted to Claude.

## Hallucination Risks and Controls

| Risk | Control | Residual limitation |
|---|---|---|
| Invented metrics | Metrics and rows are backend-computed and displayed separately; Claude wording is discarded if it introduces a number absent from the verified payload | Claude can still phrase a supported metric ambiguously; users should rely on displayed verified metrics |
| False causality | Attrition answer labels reasons as recorded correlation, not causal proof | Reason quality depends on manager-entered exit categories |
| Wrong tool selection | Deterministic phrase classifier; unsupported questions return 422 | Natural-language coverage is intentionally narrower than an unconstrained chatbot |
| Data leakage through prompts | Only aggregate/non-PII payloads may reach Claude; employee-risk tool disables Claude | Job/property names are business data and may still be processed by the configured external provider |
| Stale data | Sources and sample sizes are returned for every answer | The assistant reflects the latest persisted data, not uncommitted operational changes |
| Automated harmful action | No mutating tools; action endpoint returns 405 | Future write tools must add explicit preview, confirmation token, permission check and idempotency |

## Files

- `supabase/migrations/058_hospitality_ai_assistant.sql`
- `backend/app/services/hospitality_ai_assistant_service.py`
- `backend/app/routers/hospitality_ai_assistant.py`
- `frontend/src/pages/HospitalityAIAssistant.tsx`
- `backend/tests/test_hospitality_ai_assistant.py`
- Router and navigation updates in `backend/app/main.py`, `frontend/src/AppRouter.tsx`, and `frontend/src/components/AppLayout.tsx`

## Remaining Enhancements

- Add a reviewed synonym dictionary from real user queries instead of allowing unconstrained LLM intent routing.
- Add optional India-hosted narrative provider if organizational policy prohibits aggregate business data leaving India.
- Add freshness timestamps per source table once update-watermark infrastructure exists.
- Before introducing any write action, implement a short-lived signed confirmation challenge and a separate audited command service.
