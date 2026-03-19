#!/usr/bin/env python3
"""Format hotel search results as a WhatsApp-friendly text card.

Reads JSON from stdin (output of search_hotels.py), writes formatted text to stdout.
"""

import json
import sys


def stars_str(rating: float) -> str:
    if rating >= 4.8:
        return "★★★★★"
    elif rating >= 4.3:
        return "★★★★½"
    elif rating >= 3.8:
        return "★★★★"
    elif rating >= 3.3:
        return "★★★½"
    else:
        return "★★★"


def brl(value: float) -> str:
    return f"R${value:,.0f}".replace(",", ".")


def usd(value: float) -> str:
    return f"US${value:,.0f}".replace(",", ".")


def format_result(res: dict) -> str:
    q = res["query"]
    n = res["nights"]
    hotels = res.get("hotels", [])
    rate = res.get("usd_to_brl", 5.19)
    error = res.get("error")

    label = q.get("label") or q["location"]
    lines = []
    lines.append(f"┌─────────────────────────────────┐")
    lines.append(f"  📍 {label.upper()}")
    lines.append(f"  {q['checkin']} → {q['checkout']}  ({n} noite{'s' if n != 1 else ''})  {q['adults']} adulto{'s' if q['adults'] != 1 else ''}")
    lines.append(f"  Câmbio: 1 USD = R${rate:.2f}")
    lines.append(f"└─────────────────────────────────┘")

    if error:
        lines.append(f"  ⚠️  Erro: {error}")
        return "\n".join(lines)

    if not hotels:
        lines.append("  Nenhum hotel encontrado com os filtros aplicados.")
        return "\n".join(lines)

    min_stars = q.get("min_stars", 0)
    if min_stars > 0:
        lines.append(f"  Filtro: {min_stars}★ mínimo  |  Fonte: Google Hotels")
    else:
        lines.append(f"  Fonte: Google Hotels")
    lines.append("")

    for i, h in enumerate(hotels[:10], 1):
        per_night_brl = h["price_per_night_brl"]
        per_night_usd = h["price_per_night_usd"]
        total_brl = per_night_brl * n
        rating = h["rating"]

        lines.append(f"  {i:2}. {h['name']}")
        lines.append(f"      {stars_str(rating)} {rating:.1f}  |  {brl(per_night_brl)}/noite  ({usd(per_night_usd)})")
        lines.append(f"      Total {n}n: {brl(total_brl)}")

    lines.append("")
    cheapest = min(hotels[:10], key=lambda x: x["price_per_night_brl"])
    best = max(hotels[:10], key=lambda x: x["rating"])
    lines.append(f"  💰 Mais barato: {cheapest['name']} ({brl(cheapest['price_per_night_brl'])}/noite)")
    if best["name"] != cheapest["name"]:
        lines.append(f"  ⭐ Melhor avaliado: {best['name']} ({best['rating']:.1f}★)")

    return "\n".join(lines)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Erro ao ler JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        data = [data]

    blocks = [format_result(r) for r in data]
    print("\n\n".join(blocks))


if __name__ == "__main__":
    main()
