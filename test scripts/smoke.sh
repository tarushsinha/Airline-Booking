#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="${STATE_FILE:-$ROOT_DIR/test scripts/testing_state.json}"
RESET_STATE="${RESET_STATE:-1}"
PRINT_STATE="${PRINT_STATE:-1}"
SELECTED_TEST="all"
HOLD_ID="${HOLD_ID:-}"
PURCHASE_ID="${PURCHASE_ID:-}"
ADMIN_FLIGHT_ID="F-SEA-LAX-20250302-1430"
SEED_FLIGHT_ID="F-SFO-PDX-20250301-0845"

if command -v rg >/dev/null 2>&1; then
  MATCHER="rg"
else
  MATCHER="grep"
fi

usage() {
  cat <<'EOF'
Usage:
  bash "test scripts/smoke.sh"                 # run all tests (default)
  bash "test scripts/smoke.sh" -test -1        # run test 1 only
  bash "test scripts/smoke.sh" -test 12        # run test 12 only

Options:
  -test <n>   Run one test only (1..12). Accepts n or -n.
  -h, --help  Show this help.

Env:
  STATE_FILE   Path to test state JSON (default: test scripts/testing_state.json)
  RESET_STATE  1 to reset state before run (default), 0 to keep existing state
  PRINT_STATE  1 to print state snapshots on hold/purchase/cancel tests (default), 0 to disable
EOF
}

contains_stdin() {
  local pattern="$1"
  if [[ "$MATCHER" == "rg" ]]; then
    rg -q "$pattern"
  else
    grep -q "$pattern"
  fi
}

contains_file() {
  local pattern="$1"
  local file="$2"
  if [[ "$MATCHER" == "rg" ]]; then
    rg -q "$pattern" "$file"
  else
    grep -q "$pattern" "$file"
  fi
}

extract_field() {
  local key="$1"
  sed -n "s/^${key}=//p" | head -n 1
}

run_cli() {
  python3 "$ROOT_DIR/airline.py" --state-file "$STATE_FILE" "$@"
}

print_state_snapshot() {
  local label="$1"
  if [[ "$PRINT_STATE" != "1" ]]; then
    return
  fi
  echo "[smoke][state] $label"
  echo "[smoke][state] seats for $SEED_FLIGHT_ID"
  run_cli seats "$SEED_FLIGHT_ID"
  echo "[smoke][state] holds/purchases snapshot"
  run_cli debug
}

ensure_hold_id() {
  if [[ -n "$HOLD_ID" ]]; then
    return
  fi
  local hold_output
  hold_output="$(run_cli hold "$SEED_FLIGHT_ID" --customer smoke-user --seats 12C)"
  echo "$hold_output"
  HOLD_ID="$(echo "$hold_output" | extract_field "hold_id")"
  [[ -n "$HOLD_ID" ]]
}

ensure_purchase_id() {
  if [[ -n "$PURCHASE_ID" ]]; then
    return
  fi
  ensure_hold_id
  local purchase_output
  purchase_output="$(run_cli purchase "$HOLD_ID")"
  echo "$purchase_output"
  PURCHASE_ID="$(echo "$purchase_output" | extract_field "purchase_id")"
  [[ -n "$PURCHASE_ID" ]]
}

ensure_admin_flight() {
  if run_cli search --departing-city "Seattle" | contains_stdin "$ADMIN_FLIGHT_ID"; then
    return
  fi
  run_cli admin-add-flight \
    --departure-city "Seattle" \
    --arrival-city "Los Angeles" \
    --departure-airport SEA \
    --arrival-airport LAX \
    --departure-datetime 2025-03-02T14:30 \
    --arrival-datetime 2025-03-02T17:10 >/dev/null
}

run_test_1() {
  echo "[smoke] 1/12 search by departure date (seeded flight)"
  run_cli search --departure-date 2025-03-01
  run_cli search --departure-date 2025-03-01 | contains_stdin "F-SFO-PDX-20250301-0845"
}

run_test_2() {
  echo "[smoke] 2/12 search by departure time substring (seeded flight)"
  run_cli search --departure-time "20250301 08:"
  run_cli search --departure-time "20250301 08:" | contains_stdin "F-SFO-PDX-20250301-0845"
}

run_test_3() {
  echo "[smoke] 3/12 hold seat on seeded flight"
  local hold_output
  hold_output="$(run_cli hold "$SEED_FLIGHT_ID" --customer smoke-user --seats 12C)"
  echo "$hold_output"
  HOLD_ID="$(echo "$hold_output" | extract_field "hold_id")"
  [[ -n "$HOLD_ID" ]]
  print_state_snapshot "after hold"
}

run_test_4() {
  echo "[smoke] 4/12 purchase held seat (persistence check across commands)"
  ensure_hold_id
  local purchase_output
  purchase_output="$(run_cli purchase "$HOLD_ID")"
  echo "$purchase_output"
  PURCHASE_ID="$(echo "$purchase_output" | extract_field "purchase_id")"
  [[ -n "$PURCHASE_ID" ]]
  print_state_snapshot "after purchase"
}

run_test_5() {
  echo "[smoke] 5/12 verify seat moved to PURCHASED in persisted state"
  ensure_purchase_id
  contains_file '"12C": "PURCHASED"' "$STATE_FILE"
}

run_test_6() {
  echo "[smoke] 6/12 cancel purchase"
  ensure_purchase_id
  run_cli cancel "$PURCHASE_ID"
  print_state_snapshot "after cancel"
}

run_test_7() {
  echo "[smoke] 7/12 verify seat returned to AVAILABLE in persisted state"
  if contains_file '"12C": "PURCHASED"' "$STATE_FILE"; then
    run_test_6 >/dev/null
  fi
  contains_file '"12C": "AVAILABLE"' "$STATE_FILE"
}

run_test_8() {
  echo "[smoke] 8/12 admin-list-flights (seeded data)"
  run_cli admin-list-flights
}

run_test_9() {
  echo "[smoke] 9/12 admin-add-flight (SEA -> LAX)"
  run_cli admin-add-flight \
    --departure-city "Seattle" \
    --arrival-city "Los Angeles" \
    --departure-airport SEA \
    --arrival-airport LAX \
    --departure-datetime 2025-03-02T14:30 \
    --arrival-datetime 2025-03-02T17:10
}

run_test_10() {
  echo "[smoke] 10/12 admin-list-flights (includes new flight)"
  ensure_admin_flight
  run_cli admin-list-flights
}

run_test_11() {
  echo "[smoke] 11/12 search --departing-city Seattle"
  ensure_admin_flight
  run_cli search --departing-city "Seattle"
}

run_test_12() {
  echo "[smoke] 12/12 seats for $ADMIN_FLIGHT_ID"
  ensure_admin_flight
  run_cli seats "$ADMIN_FLIGHT_ID"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -test|--test)
      shift
      if [[ $# -eq 0 ]]; then
        echo "ERROR: -test requires a value." >&2
        usage
        exit 2
      fi
      SELECTED_TEST="$1"
      if [[ "$SELECTED_TEST" =~ ^-[0-9]+$ ]]; then
        SELECTED_TEST="${SELECTED_TEST#-}"
      fi
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "$SELECTED_TEST" != "all" ]]; then
  if ! [[ "$SELECTED_TEST" =~ ^[0-9]+$ ]] || (( SELECTED_TEST < 1 || SELECTED_TEST > 12 )); then
    echo "ERROR: -test must be between 1 and 12." >&2
    exit 2
  fi
fi

if [[ "$RESET_STATE" == "1" ]]; then
  rm -f "$STATE_FILE" "$STATE_FILE.tmp"
fi

echo "[smoke] using state file: $STATE_FILE"
echo "[smoke] reset state before run: $RESET_STATE"
echo "[smoke] matcher: $MATCHER"

if [[ "$SELECTED_TEST" == "all" ]]; then
  for i in $(seq 1 12); do
    "run_test_${i}"
  done
else
  "run_test_${SELECTED_TEST}"
fi

echo "[smoke] PASS"
echo "[smoke] state retained at: $STATE_FILE"
