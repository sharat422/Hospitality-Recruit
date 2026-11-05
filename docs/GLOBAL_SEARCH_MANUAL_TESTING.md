# Global Search Manual Testing

## Prerequisites

1. Apply Supabase migrations through `057_global_search.sql`.
2. Start FastAPI on `http://localhost:8000` and React on the configured Vite port.
3. Create two properties in one organization and a second organization.
4. Prepare Owner, HR Manager, Department Head, Recruiter and Employee accounts.
5. Seed at least one record in every search category. Add a POSH complaint and a normal complaint; assign only one case to the test HR Manager.

## Functional Flow

1. Sign in as Owner and press `Ctrl+K`. Confirm the header search receives focus.
2. Enter an exact candidate name. Confirm the candidate appears first with `exact` ranking behavior and opens the pipeline candidate view.
3. Search with a prefix, then a contained email fragment.
4. Introduce a typo such as `houeskeeping`. Confirm the intended Housekeeping job or department is suggested.
5. Select each category filter and verify results contain only that category.
6. Press Enter on a query. Clear the input, reopen search, and verify the query appears under Recent searches.
7. Click a recent query and verify it runs again. Click Clear and verify recent history is empty after reopening.
8. Test at 360px width. Confirm the category selector is usable, rows do not overflow, and each result has a large touch target.
9. Search with one character and confirm no API search runs. Search with an unknown category via API and confirm HTTP 422.

## Authorization and Isolation

1. Sign in as a Recruiter assigned only to Property A. Search the exact names/codes of Property B employees, jobs, applications, candidates, documents and departments. Confirm no results.
2. Sign in as a Department Head. Confirm records from another department do not appear, even when their exact identifier is entered.
3. Sign in as Employee A. Confirm employee/candidate/job categories are omitted when the role lacks those permissions. Confirm only Employee A's own referrals can be found.
4. Sign in as Employee B and call `GET /api/v1/search/recent`. Confirm Employee A's history is absent.
5. Use a token from Organization A to search an exact unique value in Organization B. Confirm no result.
6. Sign in as an unassigned HR Manager and search an exact normal complaint ticket and POSH ticket. Confirm neither appears.
7. Assign the manager to the normal case and repeat. Confirm only the safe ticket/category/severity/status projection appears.
8. Sign in as Owner without POSH assignment. Confirm the POSH ticket remains absent. Assign the Owner explicitly and confirm it appears.
9. Inspect network responses. Confirm no complaint body/reporter/phone/token/evidence, document URL/storage key, UPI ID, bank data, payout ID or payroll amount is returned.

## API Checks

```text
GET /api/v1/search?q=Ravi&limit=20
GET /api/v1/search/autocomplete?q=houeskeeping&categories=jobs,departments
GET /api/v1/search/recent
DELETE /api/v1/search/recent
```

Expected failures: no token = 401; unauthorized category is silently excluded rather than leaked; malformed/unknown category = 422; query shorter than two characters = 422.

## Regression

1. Switch the active property and verify existing property navigation still works.
2. Open candidate pipeline, Employee 360, Smart Recruitment, Hotels, Referrals and Grievances from their normal navigation entries.
3. Confirm sidebar route filtering and sign-out still work.
4. Confirm search selection routes to an existing screen and retains the selected record ID in the URL.
