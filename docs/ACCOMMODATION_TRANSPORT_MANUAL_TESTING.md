# Accommodation and Transport Manual Testing

## Setup

1. Back up Supabase and apply migrations through `053_accommodation_transport.sql`.
2. Prepare Property A and Property B, a manager for each, Employee A assigned to Property A, and Employee B assigned to Property B.
3. Open `/facilities`, select Property A and confirm the page follows the global property switcher.

## Accommodation Inventory and Occupancy

1. Create Building A, Room 101 with capacity 2, then beds 101-A and 101-B.
2. Attempt a third bed; expect HTTP 409 because capacity is two.
3. Allocate 101-A to Employee A; expect ALLOCATED, occupied 1 and available 1.
4. Allocate 101-A again or allocate a second active bed to Employee A; expect conflict.
5. Attempt to allocate a Property A bed to Employee B; expect HTTP 422.
6. Check Employee A in and verify timestamp and CHECKED_IN.
7. Check out; verify timestamp, CHECKED_OUT and bed returns to AVAILABLE.
8. Repeat concurrent allocation from two browsers; exactly one request must succeed due to the unique index.

## Maintenance

1. Submit maintenance against building, room or bed with description and severity.
2. Assign it, move to IN_PROGRESS and resolve with notes.
3. Verify Property B manager cannot read or update Property A maintenance.
4. Verify the reporting employee cannot change assignment or resolution fields.

## Transport

1. Create a route, ordered pickup points, an active vehicle with capacity 2, and driver.
2. Create a dated schedule. Attempt a duplicate vehicle/date/time and duplicate driver/date/time; both must fail.
3. Assign Employee A using a pickup point on the route.
4. Try a pickup point from another route; expect HTTP 422.
5. Add a second employee, then attempt a third; expect vehicle-full HTTP 409.
6. Mark assignments BOARDED, COMPLETED and NO_SHOW and verify timestamps/status.
7. Attempt to assign Employee B from Property B; expect HTTP 422.

## Employee and Isolation Tests

1. Sign in as Employee A and open Employee App Help. Confirm only Employee A accommodation and transport status appears.
2. Query another employee's allocation/assignment with Employee A JWT; RLS must return no rows.
3. As Property B manager query Property A inventory/transport APIs; expect 403 or no rows.
4. As Group HR with authorized property membership verify portfolio access follows existing property switching rules.
5. Regression-test employee profile, shifts, leave, payroll, salary advances and grievances.

## Mobile

1. Test Employee App at 360x640 and manager page at 360px, tablet and desktop widths.
2. Confirm all controls remain at least 44px high, tables/forms remain usable and property changes reload the data.
