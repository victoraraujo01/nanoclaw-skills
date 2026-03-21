#!/usr/bin/env python3
"""Google Hotels price search engine for the /hotels Claude Code skill.

Modes:
  1. Generic  (--location):  location-based search via Google Hotels + Playwright
  2. Specific (--hotel):     targeted search by hotel name via Google Hotels + Playwright
  3. Watchlist (--watchlist): search all saved entries in hotels.json

Prices are always output in BRL (R$) with USD equivalent.
"""

import argparse
import asyncio
import json
import re
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
    """Fetch live USD→BRL rate via frankfurter.app. Falls back to hardcoded value."""
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.frankfurter.app/latest?from=USD&to=BRL", timeout=8) as r:
            data = json.loads(r.read())
            rate = data["rates"]["BRL"]
            print(f"  Taxa de câmbio: 1 USD = R${rate:.4f} (ao vivo)", file=sys.stderr)
            return rate
    except Exception:
        pass
    fallback = 5.26
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
    filters: list


def load_watchlist() -> list:
    if not HOTELS_FILE.exists():
        return []
    with open(HOTELS_FILE) as f:
        return json.load(f)


def nights(checkin: str, checkout: str) -> int:
    from datetime import datetime
    return (datetime.strptime(checkout, "%Y-%m-%d") - datetime.strptime(checkin, "%Y-%m-%d")).days


def parse_brl(raw: str) -> float | None:
    """Parse a BRL price string like '2,056' or '2.056' → 2056.0"""
    # Remove spaces
    s = raw.strip().replace(" ", "")
    # Detect format: if ends with ,XX (2 digits after last comma) → decimal
    # Otherwise treat all . and , as thousands separators
    if re.match(r".*,\d{2}$", s):
        # Brazilian decimal: 1.234,56 → 1234.56
        s = s.replace(".", "").replace(",", ".")
    else:
        # Thousands separator only: 2,056 or 2.056 → 2056
        s = s.replace(",", "").replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def extract_brl_prices(text: str) -> list[float]:
    """Extract all R$ prices from page text, filtered to hotel price range."""
    prices = []
    for m in re.finditer(r"R\$\s*([\d.,]+)", text):
        val = parse_brl(m.group(1))
        if val and 300 <= val <= 100_000:
            prices.append(val)
    return prices


# ─── MODE 1: GENERIC (by location) ──────────────────────────────────────────

def search_one(query: SearchQuery, limit: int = 20, usd_to_brl: float | None = None) -> dict:
    """Location-based search using fast_hotels + local Playwright."""
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
            fetch_mode="local",
        )
    except Exception as e:
        print(f"  Erro ao buscar {query.location}: {e}", file=sys.stderr)
        return {"query": query.__dict__, "nights": n, "error": str(e), "hotels": []}

    hotels = []
    for h in result.hotels:
        if not h.price or h.price <= 1.0:
            continue
        rating = h.rating or 0.0
        if rating < query.min_stars:
            continue

        # h.price may be in BRL (page is geo-Brazil) or USD — detect by magnitude
        # BRL hotel prices are typically 5× USD; threshold ~500 separates them
        raw = h.price
        if raw >= 500:
            # Likely BRL per-night price captured from page
            price_per_night_brl = raw
            price_per_night_usd = raw / usd_to_brl
        else:
            # USD total for stay
            price_per_night_usd = raw / n if n > 0 else raw
            price_per_night_brl = price_per_night_usd * usd_to_brl

        hotels.append({
            "name": h.name,
            "rating": rating,
            "price_per_night_usd": round(price_per_night_usd, 2),
            "price_per_night_brl": round(price_per_night_brl, 2),
            "url": h.url or None,
        })

    hotels.sort(key=lambda x: (-x["rating"], x["price_per_night_brl"]))

    return {
        "mode": "generic",
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


# ─── MODE 2: SPECIFIC (by hotel name) ────────────────────────────────────────

async def _specific_async(hotel_name: str, checkin: str, checkout: str, adults: int, usd_to_brl: float, entity_url: str | None = None) -> dict:
    from playwright.async_api import async_playwright

    n = nights(checkin, checkout)
    print(f"  Buscando hotel específico: {hotel_name} ({checkin} → {checkout})...", file=sys.stderr)

    date_params = f"checkin={checkin}&checkout={checkout}&adults={adults}&hl=pt-BR&curr=BRL"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        if entity_url:
            # Direct navigation via known entity URL — most reliable
            sep = "&" if "?" in entity_url else "?"
            detail_url = f"{entity_url}{sep}{date_params}"
            print(f"  Navegando direto para entidade: {detail_url}", file=sys.stderr)
            await page.goto(detail_url)

            # Accept consent if needed, then re-navigate
            try:
                await page.click('button:has-text("Aceitar tudo")', timeout=3000)
                await page.goto(detail_url)
            except Exception:
                try:
                    await page.click('button:has-text("Accept all")', timeout=2000)
                    await page.goto(detail_url)
                except Exception:
                    pass

            await page.wait_for_timeout(5000)
        else:
            # Step 1: search by hotel name with dates
            q = hotel_name.replace(" ", "+")
            search_url = (
                f"https://www.google.com/travel/hotels"
                f"?q={q}&{date_params}"
            )
            await page.goto(search_url)

            # Accept consent if needed, then re-navigate to search URL
            consented = False
            try:
                await page.click('button:has-text("Aceitar tudo")', timeout=3000)
                consented = True
            except Exception:
                try:
                    await page.click('button:has-text("Accept all")', timeout=2000)
                    consented = True
                except Exception:
                    pass

            if consented:
                # Re-navigate to original search URL (consent redirect loses query params)
                await page.goto(search_url)

            await page.wait_for_timeout(4000)

            # Step 2: click first hotel entity link to get detail page with accurate price
            try:
                links = page.locator('a[href*="/travel/hotels/entity"]')
                count = await links.count()
                if count > 0:
                    href = await links.first.get_attribute("href")
                    detail_url = ("https://www.google.com" + href) if href.startswith("/") else href
                    print(f"  Navegando para entidade: {detail_url}", file=sys.stderr)
                    await page.goto(detail_url)
                    await page.wait_for_timeout(5000)
                else:
                    print(f"  Aviso: nenhum link de entidade encontrado na busca", file=sys.stderr)
            except Exception as e:
                print(f"  Aviso: não foi possível navegar para detalhe do hotel: {e}", file=sys.stderr)

        # Extract prices from page text
        text = await page.evaluate("() => document.body.innerText")
        title = await page.title()
        print(f"  Título da página: {title}", file=sys.stderr)
        await browser.close()

    # Parse R$ prices
    prices = extract_brl_prices(text)

    # Look for "from R$XXX" or "a partir de R$XXX" as the canonical starting price
    from_match = re.search(r"(?:from|a partir de)\s+R\$\s*([\d.,]+)", text, re.IGNORECASE)
    if from_match:
        starting = parse_brl(from_match.group(1))
        if starting and 300 <= starting <= 100_000:
            price_per_night_brl = starting
        else:
            price_per_night_brl = min(prices) if prices else None
    else:
        price_per_night_brl = min(prices) if prices else None

    # Try to extract hotel name from body text (appears just before the price line)
    # Pattern: hotel name appears as a standalone line followed shortly by the price
    extracted_name = None
    price_str_approx = str(int(price_per_night_brl)) if price_per_night_brl else ""
    if price_str_approx:
        # Find text block near the price; look for a hotel-name-like line before it
        price_pattern = re.compile(r"R\$\s*[\d.,]+")
        lines = text.split("\n")
        for idx, line in enumerate(lines):
            if price_pattern.search(line) and parse_brl(re.search(r"R\$\s*([\d.,]+)", line).group(1) if re.search(r"R\$\s*([\d.,]+)", line) else "") == price_per_night_brl:
                # Look up to 5 lines before for the hotel name
                for j in range(max(0, idx - 5), idx):
                    candidate = lines[j].strip()
                    if (len(candidate) > 5 and len(candidate) < 80
                            and not any(kw in candidate for kw in
                                        ["Pesquise", "Search", "resultado", "Pular", "Viagens", "Voos", "Hotéis",
                                         "Aluguel", "Fazer", "filtros", "Preço", "Oferta", "Classificação",
                                         "Comodidades", "Ordenar", "perto de", "Feedback"])):
                        extracted_name = candidate
                break

    # Try to extract rating from body text (e.g. "4,8\n(1,6 mil)")
    extracted_rating = None
    rating_match = re.search(r"\b([4-5],[0-9])\b", text)
    if rating_match:
        try:
            extracted_rating = float(rating_match.group(1).replace(",", "."))
        except Exception:
            pass

    # Fall back to page title, then hotel_name
    name_from_title = (
        title.replace(" - Google hotels", "")
             .replace(" - Google Hotels", "")
             .replace(": hotéis no Google", "")
             .replace(": hotels on Google", "")
             .strip()
    )
    if any(kw in name_from_title for kw in ["Pesquise", "Search", "acomodações", "accommodations"]):
        name_from_title = None

    final_name = extracted_name or name_from_title or hotel_name

    hotels = []
    if price_per_night_brl:
        hotels.append({
            "name": final_name,
            "rating": extracted_rating,
            "price_per_night_usd": round(price_per_night_brl / usd_to_brl, 2),
            "price_per_night_brl": round(price_per_night_brl, 2),
            "url": entity_url or None,
        })
    else:
        print(f"  Aviso: nenhum preço encontrado para '{hotel_name}'", file=sys.stderr)

    return {
        "mode": "specific",
        "query": {
            "hotel": hotel_name,
            "checkin": checkin,
            "checkout": checkout,
            "adults": adults,
        },
        "nights": n,
        "usd_to_brl": usd_to_brl,
        "hotels": hotels,
    }


def search_specific(hotel_name: str, checkin: str, checkout: str, adults: int, usd_to_brl: float, entity_url: str | None = None) -> dict:
    return asyncio.run(_specific_async(hotel_name, checkin, checkout, adults, usd_to_brl, entity_url=entity_url))


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Hotel price search — generic or specific mode")
    parser.add_argument("--location", help="[Generic] City or region (e.g. 'Cartagena, Colombia')")
    parser.add_argument("--hotel", help="[Specific] Hotel name (e.g. 'Sofitel Baru Cartagena')")
    parser.add_argument("--entity-url", help="[Specific] Google Hotels entity URL for direct navigation")
    parser.add_argument("--checkin", help="Check-in date YYYY-MM-DD")
    parser.add_argument("--checkout", help="Check-out date YYYY-MM-DD")
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--min-stars", type=float, default=0.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--watchlist", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    usd_to_brl = get_usd_to_brl()
    results = []

    if args.watchlist:
        entries = load_watchlist()
        if not entries:
            print("Watchlist vazia.", file=sys.stderr)
            sys.exit(1)
        for entry in entries:
            mode = entry.get("mode", "generic")
            if mode == "specific":
                results.append(search_specific(
                    entry["hotel"], entry["checkin"], entry["checkout"],
                    entry.get("adults", 2), usd_to_brl,
                ))
            else:
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

    elif args.hotel:
        if not args.checkin or not args.checkout:
            print("Erro: --checkin e --checkout são obrigatórios.", file=sys.stderr)
            sys.exit(1)
        results.append(search_specific(args.hotel, args.checkin, args.checkout, args.adults, usd_to_brl, entity_url=args.entity_url))

    elif args.location:
        if not args.checkin or not args.checkout:
            print("Erro: --checkin e --checkout são obrigatórios.", file=sys.stderr)
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

    else:
        print("Erro: use --location, --hotel ou --watchlist.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
