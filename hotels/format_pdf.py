#!/usr/bin/env python3
"""Format hotel search results as an HTML report for PDF generation.

Reads JSON from stdin (output of search_hotels.py), writes HTML to stdout.
"""

import json
import sys
from datetime import datetime


def stars_html(rating: float) -> str:
    full = int(rating)
    half = 1 if (rating - full) >= 0.3 else 0
    empty = 5 - full - half
    return "★" * full + "½" * half + "☆" * empty


def brl(value: float) -> str:
    return f"R$ {value:,.0f}".replace(",", ".")


def usd(value: float) -> str:
    return f"US$ {value:,.0f}".replace(",", ".")


def render_result(res: dict) -> str:
    q = res["query"]
    n = res["nights"]
    hotels = res.get("hotels", [])
    rate = res.get("usd_to_brl", 5.19)
    error = res.get("error")

    label = q.get("label") or q["location"]
    checkin = q["checkin"]
    checkout = q["checkout"]
    adults = q["adults"]
    min_stars = q.get("min_stars", 0)

    html = f"""
<div class="dest-block">
  <div class="dest-header">
    <div class="dest-title">{label}</div>
    <div class="dest-meta">
      {checkin} → {checkout} &nbsp;·&nbsp; {n} noite{'s' if n != 1 else ''} &nbsp;·&nbsp;
      {adults} adulto{'s' if adults != 1 else ''} &nbsp;·&nbsp;
      Câmbio: 1 USD = R${rate:.2f}
      {f'&nbsp;·&nbsp; Mínimo {min_stars:.0f}★' if min_stars > 0 else ''}
    </div>
  </div>
"""

    if error:
        html += f'<div class="error">⚠️ Erro: {error}</div>'
    elif not hotels:
        html += '<div class="empty">Nenhum hotel encontrado com os filtros aplicados.</div>'
    else:
        html += '<table class="hotels-table"><thead><tr><th>#</th><th>Hotel</th><th>Rating</th><th>Por noite</th><th>Total</th></tr></thead><tbody>'
        for i, h in enumerate(hotels[:10], 1):
            per_night_brl = h["price_per_night_brl"]
            per_night_usd = h["price_per_night_usd"]
            total_brl = per_night_brl * n
            rating = h["rating"]
            url = h.get("url") or ""
            name_cell = f'<a href="{url}">{h["name"]}</a>' if url else h["name"]
            row_class = "best-value" if i == 1 else ""
            html += f"""
        <tr class="{row_class}">
          <td class="num">{i}</td>
          <td class="name">{name_cell}</td>
          <td class="rating">{stars_html(rating)} <span class="rating-num">{rating:.1f}</span></td>
          <td class="price">{brl(per_night_brl)}<br><span class="usd">{usd(per_night_usd)}</span></td>
          <td class="total">{brl(total_brl)}</td>
        </tr>"""

        html += "</tbody></table>"

        cheapest = min(hotels[:10], key=lambda x: x["price_per_night_brl"])
        best = max(hotels[:10], key=lambda x: x["rating"])
        html += f"""
  <div class="summary-row">
    <div class="badge cheap">💰 Mais barato: <strong>{cheapest['name']}</strong> — {brl(cheapest['price_per_night_brl'])}/noite</div>
    {'<div class="badge top">⭐ Melhor avaliado: <strong>' + best['name'] + '</strong> — ' + str(best['rating']) + '★</div>' if best['name'] != cheapest['name'] else ''}
  </div>"""

    html += "\n</div>"
    return html


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"<!-- Erro ao ler JSON: {e} -->", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        data = [data]

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    body = "\n".join(render_result(r) for r in data)

    print(f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  @page {{ size: A4; margin: 1.5cm 1.8cm; }}
  body {{ font-family: 'Inter', sans-serif; font-size: 9.5pt; color: #1e293b; line-height: 1.4; }}

  .report-header {{ border-bottom: 2px solid #0f4c75; padding-bottom: 0.4cm; margin-bottom: 0.6cm; display: flex; justify-content: space-between; align-items: flex-end; }}
  .report-title {{ font-size: 16pt; font-weight: 700; color: #0f4c75; }}
  .report-meta {{ font-size: 8pt; color: #64748b; text-align: right; }}

  .dest-block {{ margin-bottom: 1cm; page-break-inside: avoid; }}
  .dest-header {{ background: #0f4c75; color: white; padding: 0.25cm 0.4cm; border-radius: 6px 6px 0 0; }}
  .dest-title {{ font-size: 12pt; font-weight: 700; }}
  .dest-meta {{ font-size: 7.5pt; opacity: 0.85; margin-top: 0.1cm; }}

  .hotels-table {{ width: 100%; border-collapse: collapse; border-radius: 0 0 6px 6px; overflow: hidden; }}
  .hotels-table thead tr {{ background: #1e3a5f; color: white; font-size: 8pt; }}
  .hotels-table th {{ padding: 0.18cm 0.3cm; text-align: left; font-weight: 600; }}
  .hotels-table td {{ padding: 0.16cm 0.3cm; border-bottom: 1px solid #e2e8f0; font-size: 8.5pt; vertical-align: top; }}
  .hotels-table tbody tr:last-child td {{ border-bottom: none; }}
  .hotels-table tbody tr:nth-child(even) {{ background: #f8fafc; }}
  .hotels-table .best-value {{ background: #eff6ff !important; }}

  .num {{ width: 1.2cm; color: #64748b; font-size: 8pt; }}
  .name {{ font-weight: 500; }}
  .name a {{ color: #0f4c75; text-decoration: none; }}
  .rating {{ white-space: nowrap; color: #f59e0b; }}
  .rating-num {{ color: #1e293b; font-size: 8pt; }}
  .price {{ font-weight: 600; color: #0f4c75; white-space: nowrap; }}
  .usd {{ font-weight: 400; color: #64748b; font-size: 7.5pt; }}
  .total {{ font-weight: 600; color: #166534; white-space: nowrap; }}

  .summary-row {{ display: flex; gap: 0.3cm; flex-wrap: wrap; margin-top: 0.25cm; }}
  .badge {{ background: #f1f5f9; border-left: 3px solid #0f4c75; padding: 0.12cm 0.3cm; border-radius: 0 4px 4px 0; font-size: 8pt; flex: 1; }}
  .badge.top {{ border-left-color: #f59e0b; }}
  .badge.cheap {{ border-left-color: #16a34a; }}

  .error, .empty {{ padding: 0.3cm; color: #dc2626; font-size: 8.5pt; }}
  .footer {{ margin-top: 0.8cm; padding-top: 0.3cm; border-top: 1px solid #e2e8f0; font-size: 7.5pt; color: #94a3b8; text-align: center; }}
</style>
</head>
<body>

<div class="report-header">
  <div class="report-title">🏨 Pesquisa de Hotéis</div>
  <div class="report-meta">Fonte: Google Hotels &nbsp;·&nbsp; Gerado em {now}</div>
</div>

{body}

<div class="footer">
  Preços em BRL convertidos da taxa do dia (USD). Sujeitos a alteração. Verifique disponibilidade antes de reservar.
</div>

</body>
</html>
""")


if __name__ == "__main__":
    main()
