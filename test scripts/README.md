# Test Scripts

## Smoke Test

Use `smoke.sh` to run a quick end-to-end CLI sanity check before changes and after changes.

Run:

```bash
bash "test scripts/smoke.sh"
```

Run one test only:

```bash
bash "test scripts/smoke.sh" -test -1
bash "test scripts/smoke.sh" -test 12
```

### What It Verifies

The script runs these checks in sequence:

1. `search --departure-date` finds the seeded flight.
2. `search --departure-time` finds the seeded flight.
3. `hold` creates a reservation on the seeded flight.
4. `purchase <hold_id>` converts the hold into a purchase.
5. Persisted state shows the seat as `PURCHASED`.
6. `cancel <purchase_id>` cancels the purchase.
7. Persisted state shows the seat as `AVAILABLE`.
8. `admin-list-flights` returns the seeded flight set.
9. `admin-add-flight` successfully creates a new flight.
10. `admin-list-flights` now includes the newly added flight.
11. `search --departing-city "Seattle"` finds the new flight.
12. `seats <new_flight_id>` prints a valid seat map for that flight.

### Testing Methodology

- Uses a dedicated repo-local test state file by default: `test scripts/testing_state.json`.
- Does not touch your main `airline_state.json`.
- Uses `set -euo pipefail` so any failing command stops the run immediately.
- Prints step markers (`[smoke] N/12 ...`) so failures are easy to locate.
- Prints state snapshots (seat map + hold/purchase debug view) after hold/purchase/cancel steps.
- Retains the test state file after the run so results can be inspected.
- Resets the test state before each run by default (`RESET_STATE=1`) for consistent test outcomes.

### Optional Override

Use a custom state file path:

```bash
STATE_FILE=/tmp/airline_smoke_manual.json bash "test scripts/smoke.sh"
```

Run without resetting existing test state first:

```bash
RESET_STATE=0 bash "test scripts/smoke.sh"
```

Disable state snapshot printing:

```bash
PRINT_STATE=0 bash "test scripts/smoke.sh"
```
