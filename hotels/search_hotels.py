#!/usr/bin/env python3
"""Booking.com hotel price search engine for the /hotels Claude Code skill.

Modes:
  1. Generic  (--location):  location-based search via Booking.com + Playwright
  2. Specific (--hotel):     targeted search by hotel name via Booking.com + Playwright
  3. Watchlist (--watchlist): search all saved entries in hotels.json

Prices are in BRL (R$) as shown by Booking.com (taxes included).
"""

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HOTELS_FILE = Path(__file__).parent / "hotels.json"
BASE_URL = "https://www.booking.com"

# Use system Chromium if available (already installed in Docker image),
# otherwise fall back to Playwright's bundled version.
import os as _os
_SYSTEM_CHROMIUM = "/usr/bin/chromium"
CHROMIUM_PATH = _SYSTEM_CHROMIUM if _os.path.exists(_SYSTEM_CHROMIUM) else None


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
    fallback = 5.85
    print(f"  Taxa de câmbio: 1 USD = R${fallback} (fallback)", file=sys.stderr)
    return fallback


def nights(checkin: str, checkout: str) -> int:
    from datetime import datetime
    return (datetime.strptime(checkout, "%Y-%m-%d") - datetime.strptime(checkin, "%Y-%m-%d")).days


def parse_brl(raw: str) -> float | None:
    """Parse a BRL price string like '2.056' or '1.234,56' → float."""
    s = raw.strip().replace(" ", "").replace("\xa0", "")
    if re.match(r".*,\d{2}$", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "").replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def booking_score_to_stars(score: float) -> float:
    """Convert Booking.com 0–10 score to 0–5 stars."""
    return round(score / 2, 1)


def load_watchlist() -> list:
    if not HOTELS_FILE.exists():
        return []
    with open(HOTELS_FILE) as f:
        return json.load(f)


async def _accept_consent(page) -> None:
    """Dismiss Booking.com consent/cookie popup if present."""
    for selector in [
        '#onetrust-accept-btn-handler',
        'button[data-gdpr-consent="accept"]',
        'button:has-text("Aceitar")',
        'button:has-text("Accept")',
        'button:has-text("Aceitar tudo")',
    ]:
        try:
            await page.click(selector, timeout=3000)
            await page.wait_for_timeout(1500)
            return
        except Exception:
            continue


def _build_search_url(location: str, checkin: str, checkout: str, adults: int) -> str:
    loc = location.replace(" ", "+").replace(",", "%2C")
    # checkin/checkout use YYYY-MM-DD format (confirmed working by Booking.com)
    # sb_price_type=total + type=total → show total price including taxes
    return (
        f"{BASE_URL}/searchresults.html"
        f"?ss={loc}"
        f"&checkin={checkin}"
        f"&checkout={checkout}"
        f"&group_adults={adults}"
        f"&group_children=0"
        f"&no_rooms=1"
        f"&selected_currency=BRL"
        f"&lang=pt-br"
        f"&sb_price_type=total"
        f"&type=total"
        f"&order=popularity"
    )


async def _extract_hotels_from_page(page, limit: int, min_stars: float, usd_to_brl: float, n: int) -> list:
    """Extract hotel cards from a Booking.com search results page."""
    hotels = []

    try:
        await page.wait_for_selector('[data-testid="property-card"]', timeout=15000)
    except Exception:
        print("  Aviso: nenhum card encontrado na página", file=sys.stderr)
        return hotels

    await page.wait_for_timeout(1500)
    cards = await page.query_selector_all('[data-testid="property-card"]')
    print(f"  Encontrados {len(cards)} resultados", file=sys.stderr)

    for card in cards[:limit]:
        try:
            # Name
            name = None
            name_el = await card.query_selector('[data-testid="title"]')
            if name_el:
                name = (await name_el.inner_text()).strip()
            if not name:
                continue

            # Rating (Booking.com uses 0–10 scale)
            rating = None
            score_el = await card.query_selector('[data-testid="review-score"]')
            if score_el:
                score_text = await score_el.inner_text()
                m = re.search(r'(\d+[,\.]\d+|\d+)', score_text)
                if m:
                    raw_score = float(m.group(1).replace(",", "."))
                    rating = booking_score_to_stars(raw_score) if raw_score > 5 else raw_score

            # Price — try data-testid selectors first
            price_brl = None
            for sel in [
                '[data-testid="price-and-discounted-price"]',
                '[data-testid="price"]',
                'span[data-testid*="price"]',
            ]:
                els = await card.query_selector_all(sel)
                for el in els:
                    text = (await el.inner_text()).replace("\xa0", "")
                    m = re.search(r'R\$\s*([\d.,]+)', text)
                    if m:
                        val = parse_brl(m.group(1))
                        if val and 80 <= val <= 500_000:
                            price_brl = val
                            break
                if price_brl:
                    break

            # Fallback: scan all text in card
            if price_brl is None:
                card_text = (await card.inner_text()).replace("\xa0", "")
                for m in re.finditer(r'R\$\s*([\d.,]+)', card_text):
                    val = parse_brl(m.group(1))
                    if val and 80 <= val <= 500_000:
                        price_brl = val
                        break

            if price_brl is None:
                continue

            # With sb_price_type=total, Booking.com shows the TOTAL for the stay.
            # Divide by number of nights to get per-night price.
            total_brl = price_brl
            price_per_night_brl = round(price_brl / n, 2) if n > 0 else price_brl
            price_per_night_usd = round(price_per_night_brl / usd_to_brl, 2)

            # Apply rating filter
            if min_stars > 0 and rating is not None and rating < min_stars:
                continue

            # URL
            hotel_url = None
            url_el = await card.query_selector('a[href*="/hotel/"]')
            if url_el:
                href = await url_el.get_attribute("href")
                if href:
                    hotel_url = href if href.startswith("http") else BASE_URL + href
                    hotel_url = hotel_url.split("?")[0]

            hotels.append({
                "name": name,
                "rating": rating,
                "price_per_night_brl": price_per_night_brl,
                "price_per_night_usd": price_per_night_usd,
                "total_brl": round(total_brl, 2),
                "url": hotel_url,
                "taxes_included": True,
            })

        except Exception as e:
            print(f"  Aviso: erro no card: {e}", file=sys.stderr)
            continue

    return hotels


# ─── MODE 1: GENERIC (by location) ──────────────────────────────────────────

async def _generic_async(
    location: str, checkin: str, checkout: str, adults: int,
    min_stars: float, limit: int, usd_to_brl: float, label: str
) -> dict:
    from playwright.async_api import async_playwright

    n = nights(checkin, checkout)
    url = _build_search_url(location, checkin, checkout, adults)
    print(f"  Buscando: {location} ({checkin} → {checkout}, {adults} adultos)...", file=sys.stderr)

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM_PATH) if CHROMIUM_PATH else await p.chromium.launch()
        context = await browser.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await _accept_consent(page)
        hotels = await _extract_hotels_from_page(page, limit, min_stars, usd_to_brl, n)
        await browser.close()

    hotels.sort(key=lambda x: (-(x.get("rating") or 0), x["price_per_night_brl"]))

    return {
        "mode": "generic",
        "source": "Booking.com",
        "query": {
            "location": location,
            "checkin": checkin,
            "checkout": checkout,
            "adults": adults,
            "min_stars": min_stars,
            "label": label or location,
        },
        "nights": n,
        "usd_to_brl": usd_to_brl,
        "hotels": hotels,
    }


def search_one(location: str, checkin: str, checkout: str, adults: int,
               min_stars: float = 0.0, limit: int = 15,
               usd_to_brl: float | None = None, label: str = "") -> dict:
    if usd_to_brl is None:
        usd_to_brl = get_usd_to_brl()
    return asyncio.run(_generic_async(location, checkin, checkout, adults, min_stars, limit, usd_to_brl, label))


# ─── MODE 2: SPECIFIC (by hotel name) ────────────────────────────────────────

async def _specific_async(
    hotel_name: str, checkin: str, checkout: str, adults: int, usd_to_brl: float
) -> dict:
    from playwright.async_api import async_playwright

    n = nights(checkin, checkout)
    url = _build_search_url(hotel_name, checkin, checkout, adults)
    print(f"  Buscando hotel específico: {hotel_name} ({checkin} → {checkout})...", file=sys.stderr)

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM_PATH) if CHROMIUM_PATH else await p.chromium.launch()
        context = await browser.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await _accept_consent(page)
        hotels = await _extract_hotels_from_page(page, 5, 0.0, usd_to_brl, n)
        await browser.close()

    hotels.sort(key=lambda x: (-(x.get("rating") or 0), x["price_per_night_brl"]))

    return {
        "mode": "specific",
        "source": "Booking.com",
        "query": {
            "hotel": hotel_name,
            "checkin": checkin,
            "checkout": checkout,
            "adults": adults,
        },
        "nights": n,
        "usd_to_brl": usd_to_brl,
        "hotels": hotels[:3],
    }


def search_specific(hotel_name: str, checkin: str, checkout: str, adults: int, usd_to_brl: float) -> dict:
    return asyncio.run(_specific_async(hotel_name, checkin, checkout, adults, usd_to_brl))


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Hotel price search via Booking.com")
    parser.add_argument("--location", help="[Generic] City or region (e.g. 'Rome, Italy')")
    parser.add_argument("--hotel", help="[Specific] Hotel name (e.g. 'Sofitel Baru')")
    parser.add_argument("--checkin", help="Check-in date YYYY-MM-DD")
    parser.add_argument("--checkout", help="Check-out date YYYY-MM-DD")
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--min-stars", type=float, default=0.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--limit", type=int, default=15)
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
                results.append(search_one(
                    location=entry["location"],
                    checkin=entry["checkin"],
                    checkout=entry["checkout"],
                    adults=entry.get("adults", 2),
                    min_stars=entry.get("min_stars", 0.0),
                    limit=args.limit,
                    usd_to_brl=usd_to_brl,
                    label=entry.get("label", ""),
                ))

    elif args.hotel:
        if not args.checkin or not args.checkout:
            print("Erro: --checkin e --checkout são obrigatórios.", file=sys.stderr)
            sys.exit(1)
        results.append(search_specific(args.hotel, args.checkin, args.checkout, args.adults, usd_to_brl))

    elif args.location:
        if not args.checkin or not args.checkout:
            print("Erro: --checkin e --checkout são obrigatórios.", file=sys.stderr)
            sys.exit(1)
        results.append(search_one(
            location=args.location,
            checkin=args.checkin,
            checkout=args.checkout,
            adults=args.adults,
            min_stars=args.min_stars,
            limit=args.limit,
            usd_to_brl=usd_to_brl,
            label=args.label,
        ))

    else:
        print("Erro: use --location, --hotel ou --watchlist.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
