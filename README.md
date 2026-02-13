# ✈️ Airline Reservation CLI (Python)

A modernized airline reservation system implemented as a command-line application.

It supports:

- Searching flights by city, time, and departure date
- Viewing seat availability for a flight
- Temporarily holding (reserving) seats for a customer
- Purchasing held seats (payment stubbed)
- Cancelling purchased seats
- Persistent state across runs (no double booking)

The plane layout is fixed at **24 rows × 6 seats (A–F)**.

---

## 📦 Requirements

- Python **3.10+**
- No external dependencies

---

## ▶️ Running the App

```bash
python airline.py <command> [options]
```

State is stored by default in:

```
airline_state.json
```

Override it if needed:

```bash
python airline.py --state-file my_state.json search --departing-city "San Francisco"
```

---

## 🔄 Seat Lifecycle

```
AVAILABLE → HOLD → PURCHASED
```

- **HOLD** temporarily locks seats (default TTL: 10 minutes)
- **PURCHASE** converts a hold into owned seats
- **CANCEL** releases seats back to AVAILABLE
- Expired holds are automatically swept on each command

> Purchases operate on a reservation token (`<HOLD_ID>`), not directly on seat numbers — mirroring real reservation systems.

---

## 🧭 Commands

Get help anytime:

```bash
python airline.py -h
python airline.py <command> -h
```

### 🔍 Search Flights

Examples:

```bash
python airline.py search --departing-city "San Francisco" --arriving-city "Portland"
python airline.py search --departure-date 2025-03-01
python airline.py search --departure-time "20250301 08:"
```

### 💺 View Seats

```bash
python airline.py seats F-SFO-PDX-20250301-0845
```

Legend:

| Symbol | Meaning |
|------:|---------|
| O     | AVAILABLE |
| H     | HOLD |
| X     | PURCHASED |

### 🕒 Hold (Reserve) Seats

Specific seats:

```bash
python airline.py hold F-SFO-PDX-20250301-0845 --customer jim --seats 12C
python airline.py hold F-SFO-PDX-20250301-0845 --customer tarush --seats 12A,12B
```

Auto-assign seats:

```bash
python airline.py hold F-SFO-PDX-20250301-0845 --customer jim --count 3
```

Custom TTL:

```bash
python airline.py hold F-SFO-PDX-20250301-0845 --customer jim --seats 12C --hold-minutes 2
```

Output includes:

```
hold_id=<HOLD_ID>
```

### 💳 Purchase a Hold

```bash
python airline.py purchase <HOLD_ID>
```

Output includes:

```
purchase_id=<PURCHASE_ID>
```

### ❌ Cancel a Purchase

```bash
python airline.py cancel <PURCHASE_ID>
```

### 🛠 Debug State (optional)

```bash
python airline.py debug
```

---

## 💾 State Persistence

All data is saved to JSON after every successful command:

- flights
- seat maps
- holds
- purchases

On first run, flights are seeded automatically.

This prevents double booking across CLI runs.

---

## 🔁 Example Flow

```bash
python airline.py search --departing-city "San Francisco" --arriving-city "Portland"
python airline.py seats F-SFO-PDX-20250301-0845
python airline.py hold F-SFO-PDX-20250301-0845 --customer jim --seats 12C
python airline.py purchase <HOLD_ID>
python airline.py cancel <PURCHASE_ID>
python airline.py seats F-SFO-PDX-20250301-0845
```

---

## 🧱 Architecture

### Components

- **CLI (argparse)**: parses commands and flags
- **AirlineService**: business logic (search/hold/purchase/cancel + TTL sweep)
- **InMemoryStore**: in-memory data layer for flights/holds/purchases
- **JSON persistence**: saves/loads state across runs

### Diagram

```text
+-------------------+
|   CLI (argparse)  |
+---------+---------+
          |
          v
+-------------------+
|  AirlineService   |
|  - search         |
|  - seats          |
|  - hold           |
|  - purchase       |
|  - cancel         |
|  - debug          |
|  - sweep TTL      |
+---------+---------+
          |
          v
+-------------------+
|  InMemoryStore    |
|  - flights        |
|  - holds          |
|  - purchases      |
+---------+---------+
          |
          v
+-------------------+
| JSON State File   |
| airline_state.json|
+-------------------+
```

---

## 🧠 Design Notes

- Holds prevent double booking by immediately marking seats as `HOLD` and persisting state to disk.
- TTL expiration is enforced lazily: expired holds are swept at the start of each command.
- Purchases require reservation tokens (`<HOLD_ID>`), preserving ownership and auditability.
- This CLI architecture maps cleanly to a future REST API.

---

## 🚀 Possible Extensions

- Multiple flights and aircraft types
- Date range search (`--from-date`, `--to-date`)
- Seat preference logic (window/aisle/grouping)
- REST API (FastAPI/Flask)
- Database-backed persistence
- Concurrency-safe locking
