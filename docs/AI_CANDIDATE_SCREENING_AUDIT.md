# AI Candidate Screening Feature Audit

**Audit date:** 25 August 2026  
**Scope:** Resume parsing, deterministic candidate/job matching, explainability, blind review, recruiter controls, and decision auditing.

## Architecture Decision

The existing AI matching system was improved, not replaced. The production trust boundary is now:

1. Resume extraction and Claude parsing create structured candidate facts.
2. A deterministic service scores six job-related dimensions.
3. Claude may explain fixed scores but cannot generate or alter them.
4. Results are recommendations only.
5. A recruiter must explicitly confirm any shortlist and provide a reason.
6. Overrides are reversible, reasoned, attributed, and audited.
7. No screening endpoint can hire, reject, offer, or otherwise make an irreversible decision automatically.

## Feature Coverage

| Feature | Status | Existing and improved implementation | Remaining gap |
|---|---|---|---|
| Resume parsing | COMPLETE | `resume_parser_service.py`, `AIMatchingService.parse_resume`, `/ai-screening/upload-resume`, S3/local storage fallback | Scanned-image OCR depends on configured document provider. |
| Candidate scoring | COMPLETE | Existing six dimensions now calculated only by `deterministic_score_candidate()` | None for configured fields. |
| Skill matching | COMPLETE | Required skills, parsed skills, hospitality keywords, missing-skill reasons | Alias taxonomy expansion can improve spelling/synonym recall. |
| Hospitality experience | COMPLETE | Total years plus explicit or work-history-derived hotel/restaurant/resort years | Work history quality depends on resume parsing. |
| Language matching | COMPLETE | Candidate languages against job-required languages | Proficiency levels are not yet scored separately. |
| Location matching | COMPLETE | Same city, relocation willingness, and missing-data neutral handling | No commute-time/geospatial calculation. |
| Salary matching | COMPLETE | Candidate expected INR salary/CTC against job INR range | Monthly/annual unit normalization relies on correct source fields. |
| Availability matching | COMPLETE | Notice period and shift-requirement overlap | Calendar-level availability is not scored. |
| Cross-industry matching | COMPLETE | India-focused retail, BPO, domestic work, healthcare, restaurant, security, manufacturing, and driver mappings | Boost applies only when mapping targets the actual role. |
| Score explanation | COMPLETE | Deterministic per-dimension reasons plus optional Claude wording constrained to fixed results | Claude outage retains deterministic explanations. |
| Automatic shortlist | COMPLETE, SAFEGUARDED | System recommends top candidates; state changes require recruiter confirmation and reason | Fully automatic state mutation was intentionally removed. |
| Blind screening | COMPLETE | Names, email, phone, photo, gender, age, caste/religion indicators, exact location, company names, and dates are removed | Free-form text redaction remains heuristic. |
| Configurable weights | COMPLETE | Organization/job-level weights and thresholds via `/screen/weights`; sum-to-one validation | UI displays active weights; editing currently uses API/Swagger. |
| Recruiter override | COMPLETE | `/screen/results/{id}/override`; UI action; original deterministic score remains immutable | None. |
| Audit trail | COMPLETE | `screening_decision_audit`, weight changes, screening runs, shortlist confirmations, overrides | Retention policy follows organization audit policy. |

## Scoring Model

Default weights:

| Dimension | Weight |
|---|---:|
| Skill match | 30% |
| Hospitality experience | 25% |
| Location | 15% |
| Language | 10% |
| Salary | 10% |
| Availability | 10% |

Default recommendation thresholds are `shortlist >= 75`, `consider 45–74.99`, and `reject recommendation < 45`. “Reject” is only a recommendation label; it never changes application or candidate status.

## Data Model

Migration `033_ai_screening_governance.sql` preserves existing records and adds:

- `screening_weight_configs`: organization defaults and per-job overrides.
- Governance fields on `candidate_screening_results`: deterministic score, weights, scoring version, explanation source, recommendation reasons, recruiter override, and decision attribution.
- `screening_decision_audit`: append-only screening and recruiter decision history.
- Security-invoker leaderboard view and organization/RBAC RLS policies.

No duplicate candidate, application, job, or screening-result table was introduced.

## APIs

- `POST /api/v1/ai-screening/upload-resume`
- `POST /api/v1/ai-screening/screen/job/{jobId}`
- `GET /api/v1/ai-screening/screen/job/{jobId}/results`
- `GET /api/v1/ai-screening/screen/weights?job_id={jobId}`
- `PUT /api/v1/ai-screening/screen/weights?job_id={jobId}`
- `POST /api/v1/ai-screening/screen/job/{jobId}/shortlist?confirmed=true&reason=...`
- `PATCH /api/v1/ai-screening/screen/results/{resultId}/override`
- `GET /api/v1/ai-screening/screen/audit`
- `GET /api/v1/ai-screening/screen/candidate/{candidateId}/blind`
- `GET /api/v1/ai-screening/screen/cross-industry-map`

## Security and Safety Findings

- Blind profile lookup is now organization-scoped; the earlier endpoint could query a known candidate UUID without an explicit organization filter.
- The leaderboard now uses `security_invoker=true`, allowing underlying RLS to remain authoritative.
- Screening result, run, configuration, and audit tables have organization/RBAC RLS.
- The AI receives a blind candidate context when blind mode is selected.
- Model-returned numeric fields and recommendations are discarded by the explanation layer.
- Missing facts receive explicit neutral or gap explanations rather than fabricated evidence.
- Recruiter confirmation and override reason are mandatory for human actions.

## Realistic Test Coverage

`backend/tests/test_ai_screening_governance.py` tests:

- A Mumbai senior waiter with hotel experience, Hindi/English, matching INR salary, and shift availability.
- Salary and shift mismatch penalties.
- BPO experience transferring to front desk but not to chef roles.
- Reproducible score changes under configured weights.
- Invalid weight rejection.
- Blind removal of identity and hometown data.
- A hostile AI explanation attempting to change score/recommendation.
- Prevention of shortlist mutation without recruiter confirmation.

## Remaining Enhancements

1. Add a full weight editor UI with sliders and permission-specific save controls.
2. Add skill alias normalization directly from `skills_taxonomy` before deterministic comparison.
3. Add travel-time matching using a consented, India-resident geocoding provider.
4. Add calibration reporting comparing recommendations with later recruiter decisions and hires, without training on protected attributes.

