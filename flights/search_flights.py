#!/usr/bin/env python3
"""Google Flights price search engine for the /flights Claude Code skill.

Reads trips.json, queries Google Flights via fast-flights, and outputs
a structured JSON report to stdout. Progress messages go to stderr.
"""

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights
    from fast_flights import fetcher as _ff_fetcher
except ImportError:
    print("Error: fast-flights is not installed. Run: pip install --pre fast-flights==3.0rc0", file=sys.stderr)
    sys.exit(1)

try:
    import primp as _primp

    def _patched_fetch_html(q, /, *, proxy=None, integration=None):
        if integration is not None:
            return integration.fetch_html(q)
        from fast_flights.querying import Query
        client = _primp.Client(
            impersonate="edge_145",
            impersonate_os="macos",
            referer=True,
            proxy=proxy,
            cookie_store=True,
        )
        params = q.params() if isinstance(q, Query) else {"q": q}
        return client.get(_ff_fetcher.URL, params=params).text

    _ff_fetcher.fetch_flights_html = _patched_fetch_html
except Exception:
    pass  # If patch fails, fall back to default behavior

TRIPS_FILE = Path(__file__).parent / "trips.json"


def load_trips() -> list:
    if not TRIPS_FILE.exists():
        print(f"Error: {TRIPS_FILE} not found. Add trips first.", file=sys.stderr)
        sys.exit(1)
    with open(TRIPS_FILE) as f:
        trips = json.load(f)
    if not trips:
        print("Error: trips.json is empty. Add trips first.", file=sys.stderr)
        sys.exit(1)
    return trips


def generate_combinations(trip: dict) -> list:
    """Generate date combinations for a trip based on its window and trip length."""
    start = datetime.strptime(trip["date_window_start"], "%Y-%m-%d")
    end = datetime.strptime(trip["date_window_end"], "%Y-%m-%d")
    combos = []

    if trip["type"] == "one-way":
        d = start
        while d <= end:
            combos.append({"departure": d.strftime("%Y-%m-%d"), "return": None})
            d += timedelta(days=1)
    else:
        length_min = trip.get("trip_length_min") or 1
        length_max = trip.get("trip_length_max") or length_min
        d = start
        while d <= end:
            for length in range(length_min, length_max + 1):
                ret = d + timedelta(days=length)
                combos.append({
                    "departure": d.strftime("%Y-%m-%d"),
                    "return": ret.strftime("%Y-%m-%d"),
                })
            d += timedelta(days=1)

    return combos


def fmt_time(t) -> str:
    h = t[0] if len(t) > 0 else 0
    m = t[1] if len(t) > 1 else 0
    return f"{h:02d}:{m:02d}"


def fmt_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"


def query_one(trip: dict, combo: dict) -> list:
    """Query flights for a single date combination. Returns list of result dicts."""
    origin = trip["origin"]
    dest = trip["destination"]
    seat = trip.get("seat_class", "economy")
    passengers = Passengers(adults=trip.get("passengers", 1))

    flights_list = [FlightQuery(date=combo["departure"], from_airport=origin, to_airport=dest)]
    trip_type = "one-way"

    if trip["type"] == "round-trip" and combo["return"]:
        flights_list.append(FlightQuery(date=combo["return"], from_airport=dest, to_airport=origin))
        trip_type = "round-trip"

    query = create_query(
        flights=flights_list,
        seat=seat,
        trip=trip_type,
        passengers=passengers,
        currency="BRL",
    )

    result = get_flights(query)

    results = []
    for fl in result:
        total_duration = sum(f.duration for f in fl.flights)
        first_leg = fl.flights[0]
        last_leg = fl.flights[-1]
        stops = len(fl.flights) - 1

        results.append({
            "departure_date": combo["departure"],
            "return_date": combo["return"],
            "price_numeric": float(fl.price),
            "airline": ", ".join(fl.airlines) if fl.airlines else "Unknown",
            "duration": fmt_duration(total_duration),
            "stops": stops,
            "departure_time": fmt_time(first_leg.departure.time),
            "arrival_time": fmt_time(last_leg.arrival.time),
        })

    return results


def search_trip(trip: dict) -> dict:
    """Search all date combinations for a single trip."""
    combos = generate_combinations(trip)
    total = len(combos)
    label = trip.get("label", f"{trip['origin']}->{trip['destination']}")

    print(f"\n--- Trip {trip['id']}: {label} ({total} combinations) ---", file=sys.stderr)

    all_results = []
    successful = 0
    no_results = 0
    failed = 0
    errors = []

    for i, combo in enumerate(combos):
        if i > 0:
            delay = random.uniform(2.0, 5.0)
            time.sleep(delay)

        desc = combo["departure"]
        if combo["return"]:
            desc += f" -> {combo['return']}"

        print(f"  [{i + 1}/{total}] {desc}...", file=sys.stderr, end=" ", flush=True)

        try:
            results = query_one(trip, combo)
            if results:
                all_results.extend(results)
                successful += 1
                print(f"OK ({len(results)} flights)", file=sys.stderr)
            else:
                no_results += 1
                print("no results", file=sys.stderr)

        except Exception as e:
            # Retry once after 10s
            print("error, retrying...", file=sys.stderr, end=" ", flush=True)
            time.sleep(10)
            try:
                results = query_one(trip, combo)
                if results:
                    all_results.extend(results)
                    successful += 1
                    print(f"OK ({len(results)} flights)", file=sys.stderr)
                else:
                    no_results += 1
                    print("no results", file=sys.stderr)
            except Exception as e2:
                failed += 1
                err_msg = f"Trip {trip['id']}: {desc} - {str(e2)[:100]}"
                errors.append(err_msg)
                print(f"FAILED: {e2}", file=sys.stderr)

    # Deduplicate by (airline, departure_time, arrival_time, price, departure_date, return_date)
    seen = set()
    unique = []
    for r in all_results:
        key = (r["airline"], r["departure_time"], r["arrival_time"], r["price_numeric"],
               r["departure_date"], r["return_date"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # Group by date combination
    combos_map = defaultdict(list)
    for r in unique:
        key = (r["departure_date"], r["return_date"])
        combos_map[key].append(r)

    by_combination = []
    for (dep, ret), flights in sorted(combos_map.items()):
        flights_sorted = sorted(flights, key=lambda x: x["price_numeric"])

        # Best direct flight
        direct_flights = [f for f in flights_sorted if f["stops"] == 0]
        best_direct = None
        if direct_flights:
            f = direct_flights[0]
            best_direct = {
                "price": f"R${int(f['price_numeric'])}",
                "price_numeric": f["price_numeric"],
                "airline": f["airline"],
                "departure_time": f["departure_time"],
                "arrival_time": f["arrival_time"],
                "duration": f["duration"],
            }

        # Best overall
        best_overall = None
        if flights_sorted:
            f = flights_sorted[0]
            best_overall = {
                "price": f"R${int(f['price_numeric'])}",
                "price_numeric": f["price_numeric"],
                "airline": f["airline"],
                "stops": f["stops"],
                "departure_time": f["departure_time"],
                "arrival_time": f["arrival_time"],
                "duration": f["duration"],
            }

        # Cheapest option per airline
        airlines_map = {}
        for f in flights_sorted:
            main_airline = f["airline"].split(",")[0].strip()
            if main_airline not in airlines_map:
                airlines_map[main_airline] = {
                    "price": f"R${int(f['price_numeric'])}",
                    "price_numeric": f["price_numeric"],
                    "departure_time": f["departure_time"],
                    "arrival_time": f["arrival_time"],
                    "duration": f["duration"],
                    "stops": f["stops"],
                }

        by_combination.append({
            "departure_date": dep,
            "return_date": ret,
            "best_direct": best_direct,
            "best_overall": best_overall,
            "by_airline": dict(sorted(airlines_map.items())),
        })

    return {
        "id": trip["id"],
        "label": label,
        "origin": trip["origin"],
        "destination": trip["destination"],
        "type": trip["type"],
        "total_combinations": total,
        "successful_queries": successful,
        "no_results": no_results,
        "failed_queries": failed,
        "by_combination": by_combination,
        "errors": errors,
    }


def search_detail(trip: dict, departure: str, return_date: str | None) -> dict:
    """Query all flights for a single specific date combination."""
    if trip["type"] == "one-way" and return_date is not None:
        print("Warning: trip is one-way but --return was provided; ignoring.", file=sys.stderr)
        return_date = None

    combo = {"departure": departure, "return": return_date}
    label = trip.get("label", f"{trip['origin']}->{trip['destination']}")
    desc = departure + (f" -> {return_date}" if return_date else "")

    print(f"--- Detail mode: Trip {trip['id']}: {label} ---", file=sys.stderr)
    print(f"  Querying {desc}...", file=sys.stderr, end=" ", flush=True)

    try:
        results = query_one(trip, combo)
    except Exception as e:
        print("error, retrying...", file=sys.stderr, end=" ", flush=True)
        time.sleep(10)
        results = query_one(trip, combo)

    results_sorted = sorted(results, key=lambda x: x["price_numeric"])
    for r in results_sorted:
        r["price"] = f"R${int(r['price_numeric'])}"

    print(f"OK ({len(results_sorted)} flights)", file=sys.stderr)

    return {
        "id": trip["id"],
        "label": label,
        "origin": trip["origin"],
        "destination": trip["destination"],
        "type": trip["type"],
        "departure_date": departure,
        "return_date": return_date,
        "total_flights": len(results_sorted),
        "all_flights": results_sorted,
    }


def main():
    parser = argparse.ArgumentParser(description="Google Flights price search")
    parser.add_argument("--detail", action="store_true", help="Fetch all flights for a specific date combination")
    parser.add_argument("--trip-id", type=int, help="Trip ID (required for --detail)")
    parser.add_argument("--departure", help="Departure date YYYY-MM-DD (required for --detail)")
    parser.add_argument("--return", dest="return_date", help="Return date YYYY-MM-DD (for round-trips)")
    args = parser.parse_args()

    if args.detail:
        if not args.trip_id or not args.departure:
            parser.error("--detail requires --trip-id and --departure")
        try:
            datetime.strptime(args.departure, "%Y-%m-%d")
            if args.return_date:
                datetime.strptime(args.return_date, "%Y-%m-%d")
        except ValueError:
            parser.error("Dates must be in YYYY-MM-DD format")

        trips = load_trips()
        trip = next((t for t in trips if t["id"] == args.trip_id), None)
        if not trip:
            print(f"Error: trip ID {args.trip_id} not found.", file=sys.stderr)
            sys.exit(1)

        result = search_detail(trip, args.departure, args.return_date)
        report = {
            "mode": "detail",
            "search_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "trip": result,
            "errors": [],
        }
    else:
        trips = load_trips()
        total_combos = sum(len(generate_combinations(t)) for t in trips)
        est_time = total_combos * 3.5

        print(f"Searching {len(trips)} trip(s), {total_combos} total combinations", file=sys.stderr)
        print(f"Estimated time: ~{int(est_time)}s ({int(est_time / 60)}m {int(est_time % 60)}s)", file=sys.stderr)

        all_errors = []
        trip_results = []
        for trip in trips:
            result = search_trip(trip)
            all_errors.extend(result.pop("errors", []))
            trip_results.append(result)

        report = {
            "mode": "summary",
            "search_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "trips": trip_results,
            "errors": all_errors,
        }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
