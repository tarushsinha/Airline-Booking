#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="${STATE_FILE:-$ROOT_DIR/test scripts/testing_state.json}"
RESET_STATE="${RESET_STATE:-1}"

if [[ "$RESET_STATE" == "1" ]]; then
  rm -f "$STATE_FILE" "$STATE_FILE.tmp"
fi

echo "[smoke] using state file: $STATE_FILE"
echo "[smoke] reset state before run: $RESET_STATE"

echo "[smoke] 1/12 search by departure date (seeded flight)"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" search --departure-date 2025-03-01
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" search --departure-date 2025-03-01 | rg -q "F-SFO-PDX-20250301-0845"

echo "[smoke] 2/12 search by departure time substring (seeded flight)"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" search --departure-time "20250301 08:"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" search --departure-time "20250301 08:" | rg -q "F-SFO-PDX-20250301-0845"

echo "[smoke] 3/12 hold seat on seeded flight"
HOLD_OUTPUT="$(
  python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" hold F-SFO-PDX-20250301-0845 \
    --customer smoke-user \
    --seats 12C
)"
echo "$HOLD_OUTPUT"
HOLD_ID="$(echo "$HOLD_OUTPUT" | rg '^hold_id=' | sed 's/^hold_id=//')"
[[ -n "$HOLD_ID" ]]

echo "[smoke] 4/12 purchase held seat (persistence check across commands)"
PURCHASE_OUTPUT="$(python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" purchase "$HOLD_ID")"
echo "$PURCHASE_OUTPUT"
PURCHASE_ID="$(echo "$PURCHASE_OUTPUT" | rg '^purchase_id=' | sed 's/^purchase_id=//')"
[[ -n "$PURCHASE_ID" ]]

echo "[smoke] 5/12 verify seat moved to PURCHASED in persisted state"
rg -q '"12C": "PURCHASED"' "$STATE_FILE"

echo "[smoke] 6/12 cancel purchase"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" cancel "$PURCHASE_ID"

echo "[smoke] 7/12 verify seat returned to AVAILABLE in persisted state"
rg -q '"12C": "AVAILABLE"' "$STATE_FILE"

echo "[smoke] 8/12 admin-list-flights (seeded data)"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" admin-list-flights

echo "[smoke] 9/12 admin-add-flight (SEA -> LAX)"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" admin-add-flight \
  --departure-city "Seattle" \
  --arrival-city "Los Angeles" \
  --departure-airport SEA \
  --arrival-airport LAX \
  --departure-datetime 2025-03-02T14:30 \
  --arrival-datetime 2025-03-02T17:10

echo "[smoke] 10/12 admin-list-flights (includes new flight)"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" admin-list-flights

echo "[smoke] 11/12 search --departing-city Seattle"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" search --departing-city "Seattle"

echo "[smoke] 12/12 seats for F-SEA-LAX-20250302-1430"
python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" seats F-SEA-LAX-20250302-1430

echo "[smoke] PASS"
echo "[smoke] state retained at: $STATE_FILE"
