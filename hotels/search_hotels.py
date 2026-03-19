#!/usr/bin/env python3
"""Google Hotels price search engine for the /hotels Claude Code skill.

Two modes:
  1. Watchlist mode: reads hotels.json, searches all saved queries
  2. Direct mode:   single query passed via CLI args (--location, --checkin, etc.)

Outputs structured JSON to stdout. Progress messages go to stderr.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from fast_hotels.hotels_impl import HotelData, Guests
    from fast_hotels import get_hotels
except ImportError:
    print("Error: fast-hotels is not installed. Run: pip install fast-hotels --break-system-packages", file=sys.stderr)
    sys.exit(1)

HOTELS_FILE = Path(__file__).parent / "hotels.json"


def get_usd_to_brl() -> float:
    """Fetch live USD→BRL rate via `exchange` CLI. Falls back to hardcoded value."""
    import subprocess
    try:
        result = subprocess.run(
            ["exchange", "USD", "BRL"],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode == 0:
            rate = float(result.stdout.strip())
            print(f"  Taxa de câmbio: 1 USD = R${rate:.4f} (ao vivo)", file=sys.stderr)
            return rate
    except Exception:
        pass
    fallback = 5.19
    print(f"  Taxa de câmbio: 1 USD = R${fallback} (fallback)", file=sys.stderr)
    return fallback


@dataclass
class SearchQuery:
    id: int
    location: str
    checkin: str
    checkout: str
    adults: int
    min_stars: float
    label: str
    filters: list  # e.g. ["all-inclusive", "adults-only", "pool"]


def load_watchlist() -> list:
    if not HOTELS_FILE.exists():
        return []
    with open(HOTELS_FILE) as f:
        return json.load(f)


def nights(checkin: str, checkout: str) -> int:
    from datetime import datetime
    d1 = datetime.strptime(checkin, "%Y-%m-%d")
    d2 = datetime.strptime(checkout, "%Y-%m-%d")
    return (d2 - d1).days


def search_one(query: SearchQuery, limit: int = 20, usd_to_brl: float | None = None) -> dict:
    """Run a single hotel search and return structured results."""
    print(f"  Buscando: {query.location} ({query.checkin} → {query.checkout}, {query.adults} adultos)...", file=sys.stderr)

    if usd_to_brl is None:
        usd_to_brl = get_usd_to_brl()

    n = nights(query.checkin, query.checkout)

    try:
        result = get_hotels(
            hotel_data=[HotelData(
                checkin_date=query.checkin,
                checkout_date=query.checkout,
                location=query.location,
            )],
            guests=Guests(adults=query.adults),
            limit=limit,
        )
    except Exception as e:
        print(f"  Erro ao buscar {query.location}: {e}", file=sys.stderr)
        return {
            "query": query.__dict__,
            "nights": n,
            "error": str(e),
            "hotels": [],
        }

    hotels = []
    for h in result.hotels:
        if not h.price or h.price <= 1.0:
            continue
        rating = h.rating or 0.0
        if rating < query.min_stars:
            continue

        price_total_usd = h.price
        price_per_night_usd = price_total_usd / n if n > 0 else price_total_usd
        price_per_night_brl = price_per_night_usd * usd_to_brl

        hotels.append({
            "name": h.name,
            "rating": rating,
            "price_total_usd": round(price_total_usd, 2),
            "price_per_night_usd": round(price_per_night_usd, 2),
            "price_per_night_brl": round(price_per_night_brl, 2),
            "url": h.url or None,
        })

    # Sort by rating desc, then price asc
    hotels.sort(key=lambda x: (-x["rating"], x["price_per_night_usd"]))

    return {
        "query": {
            "id": query.id,
            "location": query.location,
            "checkin": query.checkin,
            "checkout": query.checkout,
            "adults": query.adults,
            "min_stars": query.min_stars,
            "label": query.label,
        },
        "nights": n,
        "usd_to_brl": usd_to_brl,
        "hotels": hotels,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Hotel price search")
    parser.add_argument("--location", help="City or region name")
    parser.add_argument("--checkin", help="Check-in date YYYY-MM-DD")
    parser.add_argument("--checkout", help="Check-out date YYYY-MM-DD")
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--min-stars", type=float, default=0.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--watchlist", action="store_true", help="Search all saved watchlist entries")
    return parser.parse_args()


def main():
    args = parse_args()

    # Fetch exchange rate once for all searches
    usd_to_brl = get_usd_to_brl()

    results = []

    if args.watchlist or (not args.location):
        # Watchlist mode
        entries = load_watchlist()
        if not entries:
            print("Watchlist vazia. Adicione hotéis com /hotels adicionar.", file=sys.stderr)
            sys.exit(1)
        print(f"Buscando {len(entries)} hotel(is) da watchlist...", file=sys.stderr)
        for entry in entries:
            q = SearchQuery(
                id=entry.get("id", 0),
                location=entry["location"],
                checkin=entry["checkin"],
                checkout=entry["checkout"],
                adults=entry.get("adults", 2),
                min_stars=entry.get("min_stars", 0.0),
                label=entry.get("label", ""),
                filters=entry.get("filters", []),
            )
            results.append(search_one(q, limit=args.limit, usd_to_brl=usd_to_brl))
    else:
        # Direct query mode
        if not args.checkin or not args.checkout:
            print("Erro: --checkin e --checkout são obrigatórios no modo direto.", file=sys.stderr)
            sys.exit(1)
        q = SearchQuery(
            id=0,
            location=args.location,
            checkin=args.checkin,
            checkout=args.checkout,
            adults=args.adults,
            min_stars=args.min_stars,
            label=args.label or args.location,
            filters=[],
        )
        results.append(search_one(q, limit=args.limit, usd_to_brl=usd_to_brl))

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
