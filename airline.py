#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import uuid
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------
# Enums / Data Model
# ---------------------------

class SeatStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    HOLD = "HOLD"
    PURCHASED = "PURCHASED"


class HoldStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"


class PurchaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


@dataclass
class Flight:
    id: str
    departure_city: str
    arrival_city: str
    departure_airport: str
    arrival_airport: str
    departure_time: str  # "YYYYMMDD HH:MM:SS"
    arrival_time: str    # "YYYYMMDD HH:MM:SS"
    departure_date: str  # "YYYY-MM-DD"
    seat_map: Dict[str, SeatStatus] = field(default_factory=dict)


@dataclass
class Hold:
    id: str
    flight_id: str
    seats: List[str]
    customer: str
    time_expires: datetime
    hold_status: HoldStatus


@dataclass
class Purchase:
    id: str
    flight_id: str
    seats: List[str]
    customer: str
    time_purchased: datetime
    purchased_status: PurchaseStatus


# ---------------------------
# In-memory Store (swap later)
# ---------------------------

class InMemoryStore:
    def __init__(self) -> None:
        self.flights: Dict[str, Flight] = {}
        self.holds: Dict[str, Hold] = {}
        self.purchases: Dict[str, Purchase] = {}

    def seed_flights(self) -> None:
        """
        Fixed list of flights. Add more here.
        Example requested:
        2025-03-01 San Francisco -> Portland,
        Departing 8:45 am, arriving 10:05 am
        """
        flight_id = "F-SFO-PDX-20250301-0845"
        dep_dt = datetime(2025, 3, 1, 8, 45, 0, tzinfo=timezone.utc)
        arr_dt = datetime(2025, 3, 1, 10, 5, 0, tzinfo=timezone.utc)

        flight = Flight(
            id=flight_id,
            departure_city="San Francisco",
            arrival_city="Portland",
            departure_airport="SFO",
            arrival_airport="PDX",
            departure_time=dep_dt.strftime("%Y%m%d %H:%M:%S"),
            arrival_time=arr_dt.strftime("%Y%m%d %H:%M:%S"),
            departure_date="2025-03-01",
            seat_map=build_seat_map(rows=24, seats_per_row=6),
        )
        self.flights[flight.id] = flight


# ---------------------------
# Seat Helpers
# ---------------------------

SEAT_LETTERS_6 = ["A", "B", "C", "D", "E", "F"]


def build_seat_map(rows: int, seats_per_row: int) -> Dict[str, SeatStatus]:
    if seats_per_row != 6:
        raise ValueError("This starter assumes 6 seats/row (A-F).")
    seat_map: Dict[str, SeatStatus] = {}
    for r in range(1, rows + 1):
        for letter in SEAT_LETTERS_6:
            seat_map[f"{r}{letter}"] = SeatStatus.AVAILABLE
    return seat_map


def normalize_seat(seat: str) -> str:
    s = seat.strip().upper()
    if not s:
        raise ValueError("Empty seat.")
    return s


def seat_sort_key(seat: str) -> Tuple[int, str]:
    # "14A" -> (14, "A")
    num = ""
    letter = ""
    for ch in seat:
        if ch.isdigit():
            num += ch
        else:
            letter += ch
    return (int(num), letter)


def infer_rows_from_seat_map(seat_map: Dict[str, SeatStatus], default_rows: int = 24) -> int:
    max_row = 0
    for seat in seat_map.keys():
        digits = ""
        for ch in seat:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            max_row = max(max_row, int(digits))
    return max_row if max_row > 0 else default_rows


def format_seat_grid(seat_map: Dict[str, SeatStatus], rows: int = 24) -> str:
    # Simple ASCII grid: A B C  D E F with aisle gap
    out: List[str] = []
    out.append("Row  A   B   C     D   E   F")
    out.append("--------------------------------")
    for r in range(1, rows + 1):
        row_seats = [f"{r}{l}" for l in SEAT_LETTERS_6]
        statuses = [seat_map[s] for s in row_seats]
        def sym(st: SeatStatus) -> str:
            return {"AVAILABLE": "O", "HOLD": "H", "PURCHASED": "X"}[st.value]
        a, b, c, d, e, f = [sym(st) for st in statuses]
        out.append(f"{r:>3}  {a}   {b}   {c}     {d}   {e}   {f}")
    out.append("")
    out.append("Legend: O=AVAILABLE, H=HOLD, X=PURCHASED")
    return "\n".join(out)


# ---------------------------
# Core Service
# ---------------------------

class AirlineService:
    def __init__(self, store: InMemoryStore, hold_minutes_default: int = 10) -> None:
        self.store = store
        self.hold_minutes_default = hold_minutes_default

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def sweep_expired_holds(self) -> int:
        """Expire holds past time_expires and free seats."""
        now = self._now()
        expired_count = 0

        for hold in list(self.store.holds.values()):
            if hold.hold_status != HoldStatus.ACTIVE:
                continue
            if hold.time_expires <= now:
                # expire + free seats
                flight = self._get_flight(hold.flight_id)
                for seat in hold.seats:
                    # Only free if still HOLD (defensive)
                    if flight.seat_map.get(seat) == SeatStatus.HOLD:
                        flight.seat_map[seat] = SeatStatus.AVAILABLE
                hold.hold_status = HoldStatus.EXPIRED
                expired_count += 1

        return expired_count

    def _get_flight(self, flight_id: str) -> Flight:
        if flight_id not in self.store.flights:
            raise ValueError(f"Unknown flight_id: {flight_id}")
        return self.store.flights[flight_id]

    def list_flights(self) -> List[Flight]:
        flights = list(self.store.flights.values())
        flights.sort(key=lambda x: x.departure_time)
        return flights

    def add_flight(
        self,
        departure_city: str,
        arrival_city: str,
        departure_airport: str,
        arrival_airport: str,
        departure_dt: datetime,
        arrival_dt: datetime,
        rows: int = 24,
        flight_id: Optional[str] = None,
    ) -> Flight:
        if rows <= 0:
            raise ValueError("--rows must be > 0.")
        if departure_dt >= arrival_dt:
            raise ValueError("departure time must be before arrival time.")

        dep_airport_norm = departure_airport.strip().upper()
        arr_airport_norm = arrival_airport.strip().upper()

        if len(dep_airport_norm) != 3 or not dep_airport_norm.isalpha():
            raise ValueError("departure airport must be a 3-letter IATA code (e.g. SFO).")
        if len(arr_airport_norm) != 3 or not arr_airport_norm.isalpha():
            raise ValueError("arrival airport must be a 3-letter IATA code (e.g. PDX).")

        generated_id = (
            f"F-{dep_airport_norm}-{arr_airport_norm}-"
            f"{departure_dt.strftime('%Y%m%d-%H%M')}"
        )
        final_flight_id = flight_id.strip() if flight_id else generated_id

        if final_flight_id in self.store.flights:
            raise ValueError(f"flight_id already exists: {final_flight_id}")

        flight = Flight(
            id=final_flight_id,
            departure_city=departure_city.strip(),
            arrival_city=arrival_city.strip(),
            departure_airport=dep_airport_norm,
            arrival_airport=arr_airport_norm,
            departure_time=departure_dt.strftime("%Y%m%d %H:%M:%S"),
            arrival_time=arrival_dt.strftime("%Y%m%d %H:%M:%S"),
            departure_date=departure_dt.strftime("%Y-%m-%d"),
            seat_map=build_seat_map(rows=rows, seats_per_row=6),
        )
        self.store.flights[flight.id] = flight
        return flight

    # --- Operations requested ---

    def search_flights(
    self,
    departing_city: Optional[str] = None,
    arriving_city: Optional[str] = None,
    departure_time_substr: Optional[str] = None,
    arrival_time_substr: Optional[str] = None,
    departure_date: Optional[str] = None,   # <-- add
    ) -> List[Flight]:
        self.sweep_expired_holds()

        def norm(s: str) -> str:
            return s.strip().lower()

        results: List[Flight] = []
        for f in self.store.flights.values():
            ok = True
            if departing_city:
                ok = ok and norm(departing_city) in norm(f.departure_city)
            if arriving_city:
                ok = ok and norm(arriving_city) in norm(f.arrival_city)
            if departure_time_substr:
                ok = ok and departure_time_substr.strip() in f.departure_time
            if arrival_time_substr:
                ok = ok and arrival_time_substr.strip() in f.arrival_time
            if departure_date:
                # exact match on "YYYY-MM-DD"
                ok = ok and f.departure_date == departure_date.strip()
            if ok:
                results.append(f)

        results.sort(key=lambda x: x.departure_time)
        return results


    def view_available_seats(self, flight_id: str) -> Dict[str, SeatStatus]:
        self.sweep_expired_holds()
        flight = self._get_flight(flight_id)
        return flight.seat_map

    def reserve_seats(
        self,
        flight_id: str,
        customer: str,
        seats: Optional[List[str]] = None,
        count: Optional[int] = None,
        hold_minutes: Optional[int] = None,
    ) -> Hold:
        """
        Reserve specific seats OR reserve 'count' seats automatically.
        Creates a HOLD record and flips seat_map status to HOLD.
        """
        self.sweep_expired_holds()
        flight = self._get_flight(flight_id)

        if seats and count:
            raise ValueError("Use either --seats or --count, not both.")
        if not seats and not count:
            raise ValueError("Must provide --seats or --count.")
        if count is not None and count <= 0:
            raise ValueError("--count must be > 0.")

        requested: List[str]
        if seats:
            requested = [normalize_seat(s) for s in seats]
        else:
            # auto-assign first N available seats (front-to-back, A-F)
            available = [s for s, st in flight.seat_map.items() if st == SeatStatus.AVAILABLE]
            available.sort(key=seat_sort_key)
            if count is None:
                raise ValueError("count missing (unexpected).")
            if len(available) < count:
                raise ValueError(f"Not enough available seats. Requested={count}, available={len(available)}")
            requested = available[:count]

        # validate seats exist + available
        for seat in requested:
            if seat not in flight.seat_map:
                raise ValueError(f"Invalid seat for this plane: {seat}")
            if flight.seat_map[seat] != SeatStatus.AVAILABLE:
                raise ValueError(f"Seat not available: {seat} (status={flight.seat_map[seat].value})")

        hold_id = f"H-{uuid.uuid4().hex[:10]}"
        minutes = hold_minutes if hold_minutes is not None else self.hold_minutes_default
        expires = self._now() + timedelta(minutes=minutes)

        # apply hold
        for seat in requested:
            flight.seat_map[seat] = SeatStatus.HOLD

        hold = Hold(
            id=hold_id,
            flight_id=flight_id,
            seats=requested,
            customer=customer,
            time_expires=expires,
            hold_status=HoldStatus.ACTIVE,
        )
        self.store.holds[hold.id] = hold
        return hold

    def purchase_hold(self, hold_id: str) -> Purchase:
        """
        Stub payment: assumes payment ok.
        Converts hold -> purchase, flips seat_map HOLD -> PURCHASED.
        """
        self.sweep_expired_holds()

        if hold_id not in self.store.holds:
            raise ValueError(f"Unknown hold_id: {hold_id}")
        hold = self.store.holds[hold_id]

        if hold.hold_status == HoldStatus.EXPIRED:
            raise ValueError("Hold is expired; cannot purchase.")
        if hold.hold_status == HoldStatus.CONVERTED:
            raise ValueError("Hold already converted to a purchase.")
        if hold.hold_status != HoldStatus.ACTIVE:
            raise ValueError(f"Hold not ACTIVE (status={hold.hold_status.value})")

        flight = self._get_flight(hold.flight_id)

        # defensive check seats are still HOLD
        for seat in hold.seats:
            if flight.seat_map.get(seat) != SeatStatus.HOLD:
                raise ValueError(f"Seat state mismatch for {seat}. Expected HOLD.")

        purchase_id = f"P-{uuid.uuid4().hex[:10]}"
        now = self._now()

        # flip seats
        for seat in hold.seats:
            flight.seat_map[seat] = SeatStatus.PURCHASED

        hold.hold_status = HoldStatus.CONVERTED

        purchase = Purchase(
            id=purchase_id,
            flight_id=hold.flight_id,
            seats=list(hold.seats),
            customer=hold.customer,
            time_purchased=now,
            purchased_status=PurchaseStatus.ACTIVE,
        )
        self.store.purchases[purchase.id] = purchase
        return purchase

    def cancel_purchase(self, purchase_id: str) -> Purchase:
        """
        Cancels an ACTIVE purchase and returns seats to AVAILABLE.
        """
        self.sweep_expired_holds()

        if purchase_id not in self.store.purchases:
            raise ValueError(f"Unknown purchase_id: {purchase_id}")
        purchase = self.store.purchases[purchase_id]

        if purchase.purchased_status == PurchaseStatus.CANCELLED:
            raise ValueError("Purchase already cancelled.")
        if purchase.purchased_status != PurchaseStatus.ACTIVE:
            raise ValueError(f"Purchase not ACTIVE (status={purchase.purchased_status.value})")

        flight = self._get_flight(purchase.flight_id)

        # flip seats back
        for seat in purchase.seats:
            # If seat isn't PURCHASED, something drifted; still make best effort.
            flight.seat_map[seat] = SeatStatus.AVAILABLE

        purchase.purchased_status = PurchaseStatus.CANCELLED
        return purchase


# ---------------------------
# CLI
# ---------------------------

def print_flights(flights: List[Flight]) -> None:
    if not flights:
        print("No flights found.")
        return

    for f in flights:
        print(f"- flight_id={f.id}")
        print(f"  {f.departure_city} ({f.departure_airport}) -> {f.arrival_city} ({f.arrival_airport})")
        print(f"  depart={f.departure_time}  arrive={f.arrival_time}")
        print("")


def cmd_search(args: argparse.Namespace, svc: AirlineService) -> int:
    flights = svc.search_flights(
        departing_city=args.departing_city,
        arriving_city=args.arriving_city,
        departure_time_substr=args.departure_time,
        arrival_time_substr=args.arrival_time,
        departure_date=args.departure_date,  # <-- add
    )
    print_flights(flights)
    return 0


def cmd_seats(args: argparse.Namespace, svc: AirlineService) -> int:
    seat_map = svc.view_available_seats(args.flight_id)
    rows = infer_rows_from_seat_map(seat_map)
    print(f"Flight: {args.flight_id}")
    print(format_seat_grid(seat_map, rows=rows))
    return 0


def cmd_hold(args: argparse.Namespace, svc: AirlineService) -> int:
    seats = args.seats.split(",") if args.seats else None
    hold = svc.reserve_seats(
        flight_id=args.flight_id,
        customer=args.customer,
        seats=seats,
        count=args.count,
        hold_minutes=args.hold_minutes,
    )
    print("HOLD CREATED")
    print(f"hold_id={hold.id}")
    print(f"flight_id={hold.flight_id}")
    print(f"customer={hold.customer}")
    print(f"seats={','.join(hold.seats)}")
    print(f"expires_utc={hold.time_expires.isoformat()}")
    print(f"status={hold.hold_status.value}")
    return 0


def cmd_purchase(args: argparse.Namespace, svc: AirlineService) -> int:
    purchase = svc.purchase_hold(args.hold_id)
    print("PURCHASE COMPLETED (payment stubbed)")
    print(f"purchase_id={purchase.id}")
    print(f"flight_id={purchase.flight_id}")
    print(f"customer={purchase.customer}")
    print(f"seats={','.join(purchase.seats)}")
    print(f"purchased_utc={purchase.time_purchased.isoformat()}")
    print(f"status={purchase.purchased_status.value}")
    return 0


def cmd_cancel(args: argparse.Namespace, svc: AirlineService) -> int:
    purchase = svc.cancel_purchase(args.purchase_id)
    print("PURCHASE CANCELLED")
    print(f"purchase_id={purchase.id}")
    print(f"flight_id={purchase.flight_id}")
    print(f"customer={purchase.customer}")
    print(f"seats={','.join(purchase.seats)}")
    print(f"status={purchase.purchased_status.value}")
    return 0


def cmd_debug(args: argparse.Namespace, svc: AirlineService) -> int:
    # useful while iterating
    svc.sweep_expired_holds()
    print("=== Holds ===")
    for h in svc.store.holds.values():
        print(f"{h.id} flight={h.flight_id} seats={h.seats} cust={h.customer} exp={h.time_expires.isoformat()} status={h.hold_status.value}")
    print("")
    print("=== Purchases ===")
    for p in svc.store.purchases.values():
        print(f"{p.id} flight={p.flight_id} seats={p.seats} cust={p.customer} t={p.time_purchased.isoformat()} status={p.purchased_status.value}")
    return 0


def _parse_admin_datetime(raw: str, field_name: str) -> datetime:
    candidate = raw.strip()
    formats = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M")
    for fmt in formats:
        try:
            parsed = datetime.strptime(candidate, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(
        f"Invalid {field_name}. Use 'YYYY-MM-DDTHH:MM' (or 'YYYY-MM-DD HH:MM')."
    )


def cmd_admin_add_flight(args: argparse.Namespace, svc: AirlineService) -> int:
    dep_dt = _parse_admin_datetime(args.departure_datetime, "departure datetime")
    arr_dt = _parse_admin_datetime(args.arrival_datetime, "arrival datetime")

    flight = svc.add_flight(
        departure_city=args.departure_city,
        arrival_city=args.arrival_city,
        departure_airport=args.departure_airport,
        arrival_airport=args.arrival_airport,
        departure_dt=dep_dt,
        arrival_dt=arr_dt,
        rows=args.rows,
        flight_id=args.flight_id,
    )
    print("FLIGHT ADDED")
    print(f"flight_id={flight.id}")
    print(f"route={flight.departure_airport}->{flight.arrival_airport}")
    print(f"depart={flight.departure_time}")
    print(f"arrive={flight.arrival_time}")
    print(f"rows={infer_rows_from_seat_map(flight.seat_map)}")
    return 0


def cmd_admin_list_flights(args: argparse.Namespace, svc: AirlineService) -> int:
    flights = svc.list_flights()
    print_flights(flights)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="airline", description="Airline reservation CLI (starter)")
    parser.add_argument(
        "--state-file",
        default="airline_state.json",
        help="Path to persisted state JSON (default: airline_state.json)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="Search flights")
    p_search.add_argument("--departing-city", default=None)
    p_search.add_argument("--arriving-city", default=None)
    p_search.add_argument("--departure-time", default=None, help='substring match against "YYYYMMDD HH:MM:SS"')
    p_search.add_argument("--arrival-time", default=None, help='substring match against "YYYYMMDD HH:MM:SS"')
    p_search.add_argument("--departure-date", default=None, help='Exact match "YYYY-MM-DD"')
    p_search.set_defaults(func=cmd_search)

    p_seats = sub.add_parser("seats", help="View seat map for a flight")
    p_seats.add_argument("flight_id")
    p_seats.set_defaults(func=cmd_seats)

    p_hold = sub.add_parser("hold", help="Reserve seats (create a hold)")
    p_hold.add_argument("flight_id")
    p_hold.add_argument("--customer", required=True)
    p_hold.add_argument("--seats", default=None, help="Comma-separated seats, e.g. 12A,12B")
    p_hold.add_argument("--count", type=int, default=None, help="Auto-assign first N available seats")
    p_hold.add_argument("--hold-minutes", type=int, default=None, help="Override default hold TTL")
    p_hold.set_defaults(func=cmd_hold)

    p_purchase = sub.add_parser("purchase", help="Purchase a hold (payment stubbed)")
    p_purchase.add_argument("hold_id")
    p_purchase.set_defaults(func=cmd_purchase)

    p_cancel = sub.add_parser("cancel", help="Cancel a purchase")
    p_cancel.add_argument("purchase_id")
    p_cancel.set_defaults(func=cmd_cancel)

    p_debug = sub.add_parser("debug", help="Print holds/purchases (dev helper)")
    p_debug.set_defaults(func=cmd_debug)

    p_admin_add = sub.add_parser("admin-add-flight", help="Admin: add a flight")
    p_admin_add.add_argument("--departure-city", required=True)
    p_admin_add.add_argument("--arrival-city", required=True)
    p_admin_add.add_argument("--departure-airport", required=True, help="3-letter IATA code, e.g. SFO")
    p_admin_add.add_argument("--arrival-airport", required=True, help="3-letter IATA code, e.g. PDX")
    p_admin_add.add_argument(
        "--departure-datetime",
        required=True,
        help="UTC datetime: YYYY-MM-DDTHH:MM",
    )
    p_admin_add.add_argument(
        "--arrival-datetime",
        required=True,
        help="UTC datetime: YYYY-MM-DDTHH:MM",
    )
    p_admin_add.add_argument("--rows", type=int, default=24, help="Number of seat rows (A-F layout)")
    p_admin_add.add_argument("--flight-id", default=None, help="Optional explicit flight_id")
    p_admin_add.set_defaults(func=cmd_admin_add_flight)

    p_admin_list = sub.add_parser("admin-list-flights", help="Admin: list all flights")
    p_admin_list.set_defaults(func=cmd_admin_list_flights)

    return parser

def _seatstatus_from_str(s: str) -> SeatStatus:
    return SeatStatus(s)

def _holdstatus_from_str(s: str) -> HoldStatus:
    return HoldStatus(s)

def _purchasestatus_from_str(s: str) -> PurchaseStatus:
    return PurchaseStatus(s)

def store_to_dict(store: InMemoryStore) -> dict:
    return {
        "flights": {
            fid: {
                "id": f.id,
                "departure_city": f.departure_city,
                "arrival_city": f.arrival_city,
                "departure_airport": f.departure_airport,
                "arrival_airport": f.arrival_airport,
                "departure_time": f.departure_time,
                "arrival_time": f.arrival_time,
                "departure_date": f.departure_date,
                "seat_map": {k: v.value for k, v in f.seat_map.items()},
            }
            for fid, f in store.flights.items()
        },
        "holds": {
            hid: {
                "id": h.id,
                "flight_id": h.flight_id,
                "seats": list(h.seats),
                "customer": h.customer,
                "time_expires": h.time_expires.isoformat(),
                "hold_status": h.hold_status.value,
            }
            for hid, h in store.holds.items()
        },
        "purchases": {
            pid: {
                "id": p.id,
                "flight_id": p.flight_id,
                "seats": list(p.seats),
                "customer": p.customer,
                "time_purchased": p.time_purchased.isoformat(),
                "purchased_status": p.purchased_status.value,
            }
            for pid, p in store.purchases.items()
        },
    }

def dict_to_store(data: dict) -> InMemoryStore:
    store = InMemoryStore()
    # flights
    for fid, f in data.get("flights", {}).items():
        store.flights[fid] = Flight(
            id=f["id"],
            departure_city=f["departure_city"],
            arrival_city=f["arrival_city"],
            departure_airport=f["departure_airport"],
            arrival_airport=f["arrival_airport"],
            departure_time=f["departure_time"],
            arrival_time=f["arrival_time"],
            departure_date=f["departure_date"],
            seat_map={k: _seatstatus_from_str(v) for k, v in f["seat_map"].items()},
        )
    # holds
    for hid, h in data.get("holds", {}).items():
        store.holds[hid] = Hold(
            id=h["id"],
            flight_id=h["flight_id"],
            seats=list(h["seats"]),
            customer=h["customer"],
            time_expires=datetime.fromisoformat(h["time_expires"]),
            hold_status=_holdstatus_from_str(h["hold_status"]),
        )
    # purchases
    for pid, p in data.get("purchases", {}).items():
        store.purchases[pid] = Purchase(
            id=p["id"],
            flight_id=p["flight_id"],
            seats=list(p["seats"]),
            customer=p["customer"],
            time_purchased=datetime.fromisoformat(p["time_purchased"]),
            purchased_status=_purchasestatus_from_str(p["purchased_status"]),
        )
    return store

def load_store(path: str) -> InMemoryStore:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return dict_to_store(data)

    # first run: seed initial flights
    store = InMemoryStore()
    store.seed_flights()
    return store

def save_store(store: InMemoryStore, path: str) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store_to_dict(store), f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # load persisted state (or seed on first run)
    store = load_store(args.state_file)
    svc = AirlineService(store=store, hold_minutes_default=10)

    try:
        rc = args.func(args, svc)
        # save state after successful command
        save_store(store, args.state_file)
        return rc
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
