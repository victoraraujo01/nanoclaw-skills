---
name: hotels
description: Search Booking.com for hotel prices in BRL with taxes included — direct one-off queries or periodic watchlist tracking. Use when user asks about hotel prices, accommodation costs, or says /hotels.
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit]
---

# Booking.com Hotel Price Tracker

Source: **Booking.com**. Prices in BRL with taxes included.
Two modes: **direct query** (instant, one-off) and **watchlist** (saved, periodic checks).

The search engine is `/home/node/.claude/skills/hotels/search_hotels.py`.
The watchlist is stored in `hotels.json` at the project root.

**Important:** Playwright + Chromium required. If missing, run:
```bash
python3 -m playwright install chromium
```

---

## Mode 1: Direct Query (for itinerary building)

Use this when the user wants immediate hotel prices for a specific destination and dates. **No need to save to watchlist.**

### Natural language examples:
- "hotéis em Roma de 8 a 11 de novembro, 2 adultos, 4 estrelas"
- "quanto custa hotel em Riviera Maya de 8 a 17 de novembro"
- "buscar pousadas em Cartagena novembro, casal"
- "pesquisar hotéis Toscana 11-15 nov mínimo 4 estrelas"

### Run a direct query (by location):
```bash
python3 /home/node/.claude/skills/hotels/search_hotels.py \
  --location "Rome, Italy" \
  --checkin "2026-11-08" \
  --checkout "2026-11-11" \
  --adults 2 \
  --min-stars 4.0 \
  --limit 15 \
  | python3 /home/node/.claude/skills/hotels/format_whatsapp.py
```

### Run a specific hotel search (by name):

Use this when the user wants a specific hotel that may not appear in generic results (boutique hotels, resorts, etc.):

```bash
python3 /home/node/.claude/skills/hotels/search_hotels.py \
  --hotel "Bastión Luxury Hotel Cartagena" \
  --checkin "2026-11-08" \
  --checkout "2026-11-12" \
  --adults 2 \
  | python3 /home/node/.claude/skills/hotels/format_whatsapp.py
```

Parameters:
- `--location`: City or region name (e.g. "Riviera Maya", "Cartagena, Colombia", "Tuscany, Italy")
- `--hotel`: Specific hotel name — use when user asks about a particular hotel
- `--checkin` / `--checkout`: Dates in YYYY-MM-DD format
- `--adults`: Number of adult guests (default: 2)
- `--min-stars`: Minimum rating to include (default: 0.0, use 4.0 for quality hotels)
- `--limit`: Max hotels to retrieve (default: 15)
- `--label`: Custom label shown in output (optional, defaults to location)

### Also generate PDF:
```bash
python3 /home/node/.claude/skills/hotels/search_hotels.py \
  --location "Rome, Italy" --checkin "2026-11-08" --checkout "2026-11-11" \
  --adults 2 --min-stars 4.0 \
  | tee /tmp/hotels-raw.json \
  | python3 /home/node/.claude/skills/hotels/format_whatsapp.py

cat /tmp/hotels-raw.json \
  | python3 /home/node/.claude/skills/hotels/format_pdf.py \
  > /workspace/group/hotels-report.html

generate-pdf /workspace/group/hotels-report.html /workspace/group/hotels-report.pdf
```

---

## Mode 2: Watchlist (periodic tracking)

Use this when the user wants to save a hotel search and check prices periodically.

### hotels.json schema:
```json
[
  {
    "id": 1,
    "location": "Rome, Italy",
    "checkin": "2026-11-08",
    "checkout": "2026-11-11",
    "adults": 2,
    "min_stars": 4.0,
    "label": "Roma — Roteiro Itália Nov/26"
  }
]
```

### Watchlist commands:

**List saved searches:**
When user says "listar hotéis", "ver watchlist de hotéis", etc., read `hotels.json` and display:

```
*N busca(s) salva(s):*

*1.* Rome, Italy (GIG → Roma)
   8–11 nov  |  3n  |  2 adultos  |  ★4.0+
   Label: Roma — Roteiro Itália Nov/26
```

**Add to watchlist:**
Create/update `hotels.json` with a new entry. Auto-increment `id`.

**Remove from watchlist:**
Remove by id or label and confirm.

**Run watchlist search:**
```bash
python3 /home/node/.claude/skills/hotels/search_hotels.py --watchlist \
  | python3 /home/node/.claude/skills/hotels/format_whatsapp.py
```

---

## Output format

### Text card (always send first):
Wrap output in triple backticks for monospace rendering:
```
┌─────────────────────────────────┐
  📍 ROME, ITALY
  2026-11-08 → 2026-11-11  (3 noites)  2 adultos
  Câmbio: 1 USD = R$5.19
└─────────────────────────────────┘
  Filtro: 4.0★ mínimo  |  Fonte: Booking.com  c/ impostos

   1. Palazzo Navona Hotel
      ★★★★½ 4.6  |  R$1.789/noite  (US$345)
      Total 3n: R$5.367

   2. Hotel dei Mellini
      ★★★★½ 4.5  |  R$1.450/noite  (US$280)
      Total 3n: R$4.350

  💰 Mais barato: Hotel dei Mellini (R$1.450/noite)
  ⭐ Melhor avaliado: Palazzo Navona Hotel (4.6★)
```

Then add a brief plain-text note below the code block with key observations and booking tips.

### PDF (generate and send after text card):
Use the format_pdf.py pipeline described above.

---

## Tips for itinerary building

When building travel itineraries, use direct queries for each leg:
```bash
# Rome
python3 search_hotels.py --location "Rome, Italy" --checkin "2026-11-08" --checkout "2026-11-11" --adults 2 --min-stars 4.0

# Tuscany
python3 search_hotels.py --location "Tuscany, Italy" --checkin "2026-11-11" --checkout "2026-11-15" --adults 2 --min-stars 4.0

# Cinque Terre
python3 search_hotels.py --location "Cinque Terre, Italy" --checkin "2026-11-15" --checkout "2026-11-17" --adults 2
```

Prices are in BRL (converted from USD at the rate in search_hotels.py). Update `USD_TO_BRL` in search_hotels.py when the rate changes significantly.

---

## Limitations

- Generic `--location` search returns most popular hotels on Booking.com — boutique/resort hotels may not appear. Use `--hotel` for specific properties.
- Prices shown are per night with taxes included (as displayed by Booking.com without login)
- Logged-in users with Genius status see lower prices — the scraper cannot replicate those discounts
- Always recommend the user verify final price on Booking.com before committing

## Installation check:
```bash
python3 -c "from playwright.sync_api import sync_playwright; print('ok')" 2>&1
# If error: pip install playwright --break-system-packages && python3 -m playwright install chromium
```
