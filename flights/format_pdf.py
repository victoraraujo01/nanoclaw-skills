#!/usr/bin/env python3
"""Format flight search JSON as a beautiful HTML report for PDF generation.

Usage:
  python3 search_flights.py | python3 format_pdf.py > /workspace/group/flights.html
  python3 search_flights.py --detail ... | python3 format_pdf.py > /workspace/group/flights.html

Then convert to PDF:
  generate-pdf /workspace/group/flights.html /workspace/group/flights.pdf
"""

import json
import sys
from datetime import datetime

DAYS_PT   = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
MONTHS_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
             'jul', 'ago', 'set', 'out', 'nov', 'dez']


def fdate_short(d):
    """'2026-05-07' -> 'Sex, 7 mai'"""
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{DAYS_PT[dt.weekday()]}, {dt.day} {MONTHS_PT[dt.month - 1]}"


def fdate_mini(d):
    """'2026-05-07' -> 'Sex 7/5'"""
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{DAYS_PT[dt.weekday()]} {dt.day}/{dt.month}"


def fprice_str(obj):
    """Extract price string without R$ prefix, or '—'."""
    if not obj:
        return '—'
    return obj['price'].replace('R$', '').strip()


def fprice_num(obj):
    """Extract numeric price or infinity."""
    if not obj:
        return float('inf')
    return obj.get('price_numeric', float('inf'))


def fmt_price(n):
    """Format numeric price as 'R$ 1.850'."""
    if n is None or n == float('inf'):
        return '—'
    return f"R$ {int(n):,}".replace(',', '.')


def price_diff(price_num, base_num):
    """Return '+R$150 (+9%)' string or '' if same/base."""
    if price_num == float('inf') or base_num == float('inf') or price_num <= base_num:
        return ''
    diff = price_num - base_num
    pct  = (diff / base_num) * 100
    return f'+{fmt_price(diff)} (+{pct:.0f}%)'


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

@page { size: A4; margin: 1.8cm 1.8cm; }
* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --blue:       #1a3a5c;
  --blue-mid:   #2d5f8e;
  --blue-light: #e8f0f8;
  --orange:     #e8762a;
  --orange-lt:  #fdf0e6;
  --green:      #15803d;
  --green-lt:   #dcfce7;
  --red-lt:     #fef2f2;
  --text:       #1a1a2e;
  --muted:      #64748b;
  --border:     #e2e8f0;
  --surface:    #f8fafc;
}

body {
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 9.5pt;
  line-height: 1.6;
  color: var(--text);
}

/* ── Cover ── */
.cover {
  background: linear-gradient(135deg, var(--blue) 0%, var(--blue-mid) 100%);
  color: white;
  padding: 1.8em 2em;
  border-radius: 10px;
  margin-bottom: 1.5em;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}
.cover-left .tag {
  display: inline-block;
  background: var(--orange);
  color: white;
  font-size: 7pt;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  padding: 2px 10px;
  border-radius: 999px;
  margin-bottom: .5em;
}
.cover-left h1 { font-size: 18pt; font-weight: 700; line-height: 1.2; }
.cover-left p  { color: rgba(255,255,255,.65); font-size: 9pt; margin-top: .3em; }
.cover-right   { text-align: right; font-size: 8.5pt; color: rgba(255,255,255,.6); }
.cover-right strong { color: white; font-size: 13pt; font-weight: 700; display: block; }

/* ── Section headings ── */
h2 {
  font-size: 10pt;
  font-weight: 700;
  color: var(--blue);
  margin: 1.5em 0 .7em;
  display: flex;
  align-items: center;
  gap: .5em;
  text-transform: uppercase;
  letter-spacing: .04em;
}
h2::after { content: ''; flex: 1; height: 1px; background: var(--border); }
h3 {
  font-size: 9pt;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  margin: 1.2em 0 .5em;
}
.route-tag {
  background: var(--blue);
  color: white;
  font-size: 8pt;
  padding: 2px 8px;
  border-radius: 4px;
}

/* ── Cards ── */
.cards { display: grid; gap: .6em; margin-bottom: 1em; }
.cards-3 { grid-template-columns: repeat(3, 1fr); }
.cards-4 { grid-template-columns: repeat(4, 1fr); }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: .75em 1em;
  border-top: 3px solid var(--orange);
}
.card-label { font-size: 7.5pt; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: .15em; }
.card-value { font-size: 14pt; font-weight: 700; color: var(--blue); line-height: 1.1; }
.card-sub   { font-size: 8pt; color: var(--muted); margin-top: .1em; }
.card.best  { border-top-color: var(--green); background: var(--green-lt); }
.card.best .card-value { color: var(--green); }

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; font-size: 8.5pt; margin-bottom: 1em; }
thead tr { background: var(--blue); color: white; }
th { padding: 6px 8px; text-align: left; font-weight: 600; font-size: 8pt; white-space: nowrap; }
th.r { text-align: right; }
th.c { text-align: center; }
td { padding: 5px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }
td.r { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td.c { text-align: center; }
td.muted { color: var(--muted); font-size: 8pt; }
tr:nth-child(even) td { background: var(--surface); }
tr.best-row td { background: var(--green-lt) !important; font-weight: 600; }
tr.best-row td.diff { font-weight: 400; }

/* ── Airline matrix ── */
.matrix-wrap { overflow: visible; margin-bottom: 1em; }
.matrix-wrap table thead tr { background: var(--orange); }
.matrix-cell { text-align: center; white-space: nowrap; font-size: 8pt; }
.matrix-cell.best-cell { color: var(--green); font-weight: 700; }
.matrix-cell.empty { color: var(--border); }
.matrix-date { font-size: 8pt; white-space: nowrap; }
.matrix-best-mark { color: var(--green); font-weight: 700; }

/* ── Badges ── */
.badge {
  display: inline-block;
  font-size: 7pt;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  white-space: nowrap;
}
.badge-direct { background: var(--blue-light); color: var(--blue); }
.badge-stops  { background: #fef9c3; color: #854d0e; }
.badge-best   { background: var(--green-lt); color: var(--green); }

/* ── Best flight callout ── */
.best-flight {
  background: var(--green-lt);
  border: 1px solid #bbf7d0;
  border-left: 4px solid var(--green);
  border-radius: 0 8px 8px 0;
  padding: .7em 1em;
  margin: .5em 0 .8em;
}
.bf-label  { font-size: 7.5pt; color: var(--green); font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-bottom: .2em; }
.bf-price  { font-size: 16pt; font-weight: 700; color: var(--green); }
.bf-detail { color: var(--muted); font-size: 8.5pt; margin-top: .15em; line-height: 1.8; }
.bf-detail strong { color: var(--text); }

/* ── Two-col layout for callout + direct ── */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: .8em; margin-bottom: .8em; }
.direct-box {
  background: var(--blue-light);
  border: 1px solid #bfdbfe;
  border-left: 4px solid var(--blue-mid);
  border-radius: 0 8px 8px 0;
  padding: .7em 1em;
}
.direct-box .db-label  { font-size: 7.5pt; color: var(--blue); font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-bottom: .2em; }
.direct-box .db-price  { font-size: 16pt; font-weight: 700; color: var(--blue); }
.direct-box .db-detail { color: var(--muted); font-size: 8.5pt; margin-top: .15em; line-height: 1.8; }
.direct-box .db-detail strong { color: var(--text); }
.no-direct {
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: .7em 1em;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: 9pt;
}

/* ── Diff pill ── */
.diff-pill {
  font-size: 7.5pt;
  color: #b45309;
  background: #fef9c3;
  border-radius: 4px;
  padding: 1px 5px;
  font-weight: 500;
}

/* ── Footer ── */
.footer {
  margin-top: 2em;
  padding-top: .6em;
  border-top: 1px solid var(--border);
  font-size: 7.5pt;
  color: var(--muted);
  display: flex;
  justify-content: space-between;
}

/* ── Page breaks ── */
.page-break { page-break-after: always; }
h2 { page-break-after: avoid; }
h3 { page-break-after: avoid; }
tr, .card { page-break-inside: avoid; }
.two-col { page-break-inside: avoid; }
"""


def stops_badge(stops):
    val = str(stops)
    if val == '0':
        return '<span class="badge badge-direct">Direto</span>'
    return f'<span class="badge badge-stops">{val} esc.</span>'


def make_html(body_content, title, subtitle, search_time):
    ts = ''
    if search_time:
        try:
            dt = datetime.fromisoformat(search_time.replace('Z', '+00:00'))
            ts = dt.strftime('%d/%m/%Y às %H:%M')
        except Exception:
            ts = search_time

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>{CSS}</style>
</head>
<body>

<div class="cover">
  <div class="cover-left">
    <span class="tag">✈ Relatório de Voos</span>
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="cover-right">
    Pesquisado em<br>
    <strong>{ts}</strong>
  </div>
</div>

{body_content}

<div class="footer">
  <span>Preços em R$ · Google Flights via NanoClaw</span>
  <span>Gerado automaticamente pelo agente Claw</span>
</div>

</body>
</html>"""


# ── Summary mode ─────────────────────────────────────────────────────────────

def build_airline_matrix(combos, top_n=8):
    """Build an airline × date combination price matrix for the top N combos."""
    top = combos[:top_n]

    # Collect all airline names across top combos
    all_airlines = []
    seen = set()
    for combo in top:
        for airline in combo.get('by_airline', {}).keys():
            if airline not in seen:
                all_airlines.append(airline)
                seen.add(airline)
    if not all_airlines:
        return ''

    # Header row
    airline_headers = ''.join(
        f'<th class="c">{a}</th>' for a in all_airlines
    )
    header = f'<tr><th>Datas</th><th class="r">Dur.</th>{airline_headers}</tr>'

    # Data rows
    rows = []
    global_min = min(
        (fprice_num(c.get('best_overall')) for c in top),
        default=float('inf')
    )
    for i, combo in enumerate(top):
        dep  = combo['departure_date']
        ret  = combo['return_date']
        days = (datetime.strptime(ret, "%Y-%m-%d") - datetime.strptime(dep, "%Y-%m-%d")).days
        is_best = (i == 0)
        row_class = ' class="best-row"' if is_best else ''
        best_mark = ' <span class="matrix-best-mark">★</span>' if is_best else ''

        by_a = combo.get('by_airline', {})

        # Cheapest price in this combo (for highlighting)
        combo_min = min(
            (v.get('price_numeric', float('inf')) for v in by_a.values()),
            default=float('inf')
        )

        cells = []
        for airline in all_airlines:
            a_data = by_a.get(airline)
            if not a_data:
                cells.append('<td class="matrix-cell empty c">—</td>')
            else:
                p_num = a_data.get('price_numeric', float('inf'))
                p_str = fmt_price(p_num)
                dep_t = a_data.get('departure_time', '')
                arr_t = a_data.get('arrival_time', '')
                dur   = a_data.get('duration', '')
                stops = a_data.get('stops', '?')
                tip   = f"{dep_t}→{arr_t} {dur} {stops}esc."
                is_cheapest = (p_num == combo_min)
                cell_class = 'matrix-cell best-cell c' if is_cheapest else 'matrix-cell c'
                cells.append(f'<td class="{cell_class}" title="{tip}">'
                              f'<strong>{p_str}</strong><br>'
                              f'<span style="font-size:7pt;color:var(--muted)">{dep_t} · {dur} · {stops_badge(stops)}</span>'
                              f'</td>')

        cells_html = ''.join(cells)
        rows.append(
            f'<tr{row_class}>'
            f'<td class="matrix-date">{fdate_mini(dep)} → {fdate_mini(ret)}{best_mark}</td>'
            f'<td class="r">{days}d</td>'
            f'{cells_html}'
            f'</tr>'
        )

    rows_html = '\n'.join(rows)
    return f"""
<div class="matrix-wrap">
<table>
  <thead>{header}</thead>
  <tbody>{rows_html}</tbody>
</table>
</div>"""


def format_summary_html(data):
    trips       = data.get('trips', [])
    search_time = data.get('search_time', '')

    if not trips:
        return make_html('<p>Nenhuma viagem encontrada.</p>', 'Pesquisa de Voos', '', search_time)

    # Global best for cover card
    global_best_price = None
    global_best_label = ''
    for trip in trips:
        for c in trip.get('by_combination', []):
            bo = c.get('best_overall')
            if bo and (global_best_price is None or bo.get('price_numeric', 999999) < global_best_price):
                global_best_price = bo.get('price_numeric')
                global_best_label = trip.get('label', '')

    n_trips      = len(trips)
    total_combos = sum(t.get('total_combinations', 0) for t in trips)
    title        = trips[0]['label'] if n_trips == 1 else f'{n_trips} viagens monitoradas'
    subtitle     = f'{total_combos} combinações de datas pesquisadas'

    cover_cards = f"""
<div class="cards cards-3">
  <div class="card">
    <div class="card-label">Viagens monitoradas</div>
    <div class="card-value">{n_trips}</div>
    <div class="card-sub">trips no watchlist</div>
  </div>
  <div class="card">
    <div class="card-label">Combinações pesquisadas</div>
    <div class="card-value">{total_combos}</div>
    <div class="card-sub">datas × durações</div>
  </div>
  <div class="card best">
    <div class="card-label">Melhor preço encontrado</div>
    <div class="card-value">{fmt_price(global_best_price)}</div>
    <div class="card-sub">{global_best_label}</div>
  </div>
</div>"""

    blocks = [cover_cards]

    for trip in trips:
        combos = sorted(
            trip.get('by_combination', []),
            key=lambda x: fprice_num(x.get('best_overall'))
        )
        if not combos:
            continue

        best    = combos[0]
        bo      = best.get('best_overall', {})
        bd      = best.get('best_direct')
        route   = f"{trip['origin']} → {trip['destination']}"
        label   = trip['label']
        n_ok    = trip.get('successful_queries', 0)
        n_tot   = trip.get('total_combinations', 0)
        n_fail  = trip.get('failed_queries', 0)
        n_empty = trip.get('no_results', 0)

        dep_dt  = datetime.strptime(best['departure_date'], "%Y-%m-%d")
        ret_dt  = datetime.strptime(best['return_date'],    "%Y-%m-%d")
        days    = (ret_dt - dep_dt).days

        # ── Best overall callout ──────────────────────────────────────────
        best_callout = f"""
<div class="best-flight">
  <div class="bf-label">✓ Melhor preço geral</div>
  <div class="bf-price">{fmt_price(bo.get('price_numeric'))}</div>
  <div class="bf-detail">
    <strong>{fdate_short(best['departure_date'])} → {fdate_short(best['return_date'])}</strong>
    &nbsp;·&nbsp; {days} dias &nbsp;·&nbsp;
    <strong>{bo.get('airline','?')}</strong><br>
    Decolagem: <strong>{bo.get('departure_time','?')}</strong>
    &nbsp;·&nbsp; Chegada: <strong>{bo.get('arrival_time','?')}</strong>
    &nbsp;·&nbsp; Duração: <strong>{bo.get('duration','?')}</strong>
    &nbsp;·&nbsp; {stops_badge(bo.get('stops','?'))}
  </div>
</div>"""

        # ── Best direct callout ───────────────────────────────────────────
        if bd:
            direct_box = f"""
<div class="direct-box">
  <div class="db-label">✈ Melhor voo direto</div>
  <div class="db-price">{fmt_price(bd.get('price_numeric'))}</div>
  <div class="db-detail">
    <strong>{fdate_short(best['departure_date'])} → {fdate_short(best['return_date'])}</strong>
    &nbsp;·&nbsp; {days} dias &nbsp;·&nbsp;
    <strong>{bd.get('airline','?')}</strong><br>
    Decolagem: <strong>{bd.get('departure_time','?')}</strong>
    &nbsp;·&nbsp; Chegada: <strong>{bd.get('arrival_time','?')}</strong>
    &nbsp;·&nbsp; Duração: <strong>{bd.get('duration','?')}</strong>
    &nbsp;·&nbsp; <span class="badge badge-direct">Direto</span>
  </div>
</div>"""
        else:
            direct_box = '<div class="no-direct">Nenhum voo direto encontrado nesta janela de datas</div>'

        two_col = f'<div class="two-col">{best_callout}{direct_box}</div>'

        # ── Combinations table ────────────────────────────────────────────
        best_price_num = fprice_num(combos[0].get('best_overall'))
        combo_rows = []
        for i, combo in enumerate(combos):
            is_best = (i == 0)
            c_dep   = combo['departure_date']
            c_ret   = combo['return_date']
            c_days  = (datetime.strptime(c_ret, "%Y-%m-%d") - datetime.strptime(c_dep, "%Y-%m-%d")).days
            c_bo    = combo.get('best_overall')
            c_bd    = combo.get('best_direct')
            n_airlines = len(combo.get('by_airline', {}))

            bo_price_num = fprice_num(c_bo)
            bd_price_num = fprice_num(c_bd)
            bo_airline   = c_bo.get('airline', '—') if c_bo else '—'
            bo_dep       = c_bo.get('departure_time', '') if c_bo else ''
            bo_arr       = c_bo.get('arrival_time', '') if c_bo else ''
            bo_dur       = c_bo.get('duration', '') if c_bo else ''
            bo_stops     = c_bo.get('stops', '?') if c_bo else '?'

            bd_airline   = c_bd.get('airline', '—') if c_bd else '—'
            bd_dep       = c_bd.get('departure_time', '') if c_bd else ''
            bd_arr       = c_bd.get('arrival_time', '') if c_bd else ''
            bd_dur       = c_bd.get('duration', '') if c_bd else ''

            diff_html = ''
            if not is_best and bo_price_num != float('inf'):
                d = price_diff(bo_price_num, best_price_num)
                if d:
                    diff_html = f'<span class="diff-pill">{d}</span>'

            row_class  = ' class="best-row"' if is_best else ''
            best_mark  = ' ★' if is_best else ''

            # Best direct cell
            if c_bd:
                bd_cell = f'<strong>{fmt_price(bd_price_num)}</strong><br><span style="font-size:7.5pt;color:var(--muted)">{bd_airline} · {bd_dep}→{bd_arr} · {bd_dur}</span>'
            else:
                bd_cell = '<span style="color:var(--muted)">—</span>'

            combo_rows.append(f"""
<tr{row_class}>
  <td class="matrix-date">{fdate_mini(c_dep)} → {fdate_mini(c_ret)}{best_mark}</td>
  <td class="r">{c_days}d</td>
  <td><strong>{fmt_price(bo_price_num)}</strong><br><span style="font-size:7.5pt;color:var(--muted)">{bo_airline} · {bo_dep}→{bo_arr} · {bo_dur} · {stops_badge(bo_stops)}</span><br>{diff_html}</td>
  <td>{bd_cell}</td>
  <td class="c">{n_airlines}</td>
</tr>""")

        combo_table = f"""
<h3>Todas as combinações de datas</h3>
<table>
  <thead>
    <tr>
      <th>Datas (ida → volta)</th>
      <th class="r">Dur.</th>
      <th>Melhor preço &amp; detalhes</th>
      <th>Melhor direto</th>
      <th class="c">CIAs</th>
    </tr>
  </thead>
  <tbody>{''.join(combo_rows)}</tbody>
</table>"""

        # ── Airline matrix ────────────────────────────────────────────────
        matrix = build_airline_matrix(combos)
        matrix_section = ''
        if matrix:
            matrix_section = f'<h3>Comparativo por companhia (top {min(8, len(combos))} datas)</h3>{matrix}'

        # ── Search stats ─────────────────────────────────────────────────
        stats = f'<span style="color:var(--muted);font-weight:400;font-size:8pt">{n_ok}/{n_tot} combinações'
        if n_fail:
            stats += f' · {n_fail} falhas'
        if n_empty:
            stats += f' · {n_empty} sem resultado'
        stats += '</span>'

        block = f"""
<h2><span class="route-tag">{route}</span> {label} &nbsp;{stats}</h2>
{two_col}
{combo_table}
{matrix_section}"""
        blocks.append(block)

    return make_html('\n'.join(blocks), title, subtitle, search_time)


# ── Detail mode ───────────────────────────────────────────────────────────────

def format_detail_html(data):
    trip        = data.get('trip', {})
    flights     = trip.get('all_flights', [])
    dep         = trip.get('departure_date', '')
    ret         = trip.get('return_date', '')
    label       = trip.get('label', 'Detalhamento')
    origin      = trip.get('origin', '')
    destination = trip.get('destination', '')
    search_time = data.get('search_time', '')

    route      = f"{origin} → {destination}" if origin else ''
    dep_str    = fdate_short(dep) if dep else '?'
    ret_str    = fdate_short(ret) if ret else ''
    date_range = f"{dep_str} → {ret_str}" if ret_str else dep_str

    if dep and ret:
        days     = (datetime.strptime(ret, "%Y-%m-%d") - datetime.strptime(dep, "%Y-%m-%d")).days
        days_str = f"{days} dias"
    else:
        days_str = ''

    n_flights   = len(flights)
    cheapest    = flights[0] if flights else None
    base_price  = cheapest.get('price_numeric', float('inf')) if cheapest else float('inf')
    cheapest_price_str  = fmt_price(base_price)
    cheapest_airline    = cheapest.get('airline', '—') if cheapest else '—'

    direct      = [f for f in flights if str(f.get('stops', '1')) == '0']
    cheapest_dir = direct[0] if direct else None

    # ── Airline summary: cheapest per CIA ────────────────────────────────
    airlines_best: dict[str, dict] = {}
    for f in flights:
        main = f['airline'].split(',')[0].strip()
        if main not in airlines_best:
            airlines_best[main] = f
    airline_list = sorted(airlines_best.values(), key=lambda x: x.get('price_numeric', float('inf')))

    # Cover cards
    cover_cards = f"""
<div class="cards cards-4">
  <div class="card best">
    <div class="card-label">Menor preço</div>
    <div class="card-value">{cheapest_price_str}</div>
    <div class="card-sub">{cheapest_airline}</div>
  </div>
  <div class="card">
    <div class="card-label">Opções encontradas</div>
    <div class="card-value">{n_flights}</div>
    <div class="card-sub">combinações de voos</div>
  </div>
  <div class="card">
    <div class="card-label">Voos diretos</div>
    <div class="card-value">{len(direct)}</div>
    <div class="card-sub">sem escala · {'a partir de ' + fmt_price(cheapest_dir['price_numeric']) if cheapest_dir else 'nenhum disponível'}</div>
  </div>
  <div class="card">
    <div class="card-label">Companhias</div>
    <div class="card-value">{len(airlines_best)}</div>
    <div class="card-sub">{days_str} &nbsp;·&nbsp; {date_range}</div>
  </div>
</div>"""

    # ── Cheapest per airline table ────────────────────────────────────────
    airline_rows = []
    for i, f in enumerate(airline_list):
        is_best    = (i == 0)
        row_class  = ' class="best-row"' if is_best else ''
        best_mark  = ' ★' if is_best else ''
        p_num      = f.get('price_numeric', float('inf'))
        diff_html  = ''
        if not is_best:
            d = price_diff(p_num, base_price)
            if d:
                diff_html = f'<span class="diff-pill">{d}</span>'
        airline_rows.append(f"""
<tr{row_class}>
  <td><strong>{f['airline']}{best_mark}</strong></td>
  <td class="r"><strong>{fmt_price(p_num)}</strong></td>
  <td class="diff">{diff_html}</td>
  <td>{f.get('departure_time','—')} → {f.get('arrival_time','—')}</td>
  <td>{f.get('duration','—')}</td>
  <td>{stops_badge(f.get('stops','?'))}</td>
</tr>""")

    airline_table = f"""
<h3>Resumo por companhia (opção mais barata de cada CIA)</h3>
<table>
  <thead>
    <tr>
      <th>Companhia</th>
      <th class="r">Preço</th>
      <th>vs. melhor</th>
      <th>Horários</th>
      <th>Duração</th>
      <th>Paradas</th>
    </tr>
  </thead>
  <tbody>{''.join(airline_rows)}</tbody>
</table>"""

    # ── All flights table ─────────────────────────────────────────────────
    all_rows = []
    for i, f in enumerate(flights):
        is_best   = (i == 0)
        row_class = ' class="best-row"' if is_best else ''
        best_mark = ' ★' if is_best else ''
        p_num     = f.get('price_numeric', float('inf'))
        diff_html = ''
        if not is_best:
            d = price_diff(p_num, base_price)
            if d:
                diff_html = f'<span class="diff-pill">{d}</span>'
        all_rows.append(f"""
<tr{row_class}>
  <td>{f.get('airline','—')}{best_mark}</td>
  <td class="r"><strong>{fmt_price(p_num)}</strong></td>
  <td class="diff">{diff_html}</td>
  <td>{f.get('departure_time','—')} → {f.get('arrival_time','—')}</td>
  <td>{f.get('duration','—')}</td>
  <td>{stops_badge(f.get('stops','?'))}</td>
</tr>""")

    all_table = f"""
<h3>Todos os voos disponíveis</h3>
<table>
  <thead>
    <tr>
      <th>Companhia</th>
      <th class="r">Preço</th>
      <th>vs. melhor</th>
      <th>Horários</th>
      <th>Duração</th>
      <th>Paradas</th>
    </tr>
  </thead>
  <tbody>{''.join(all_rows)}</tbody>
</table>"""

    title    = label
    subtitle = f"{route} &nbsp;·&nbsp; {date_range} &nbsp;·&nbsp; {days_str}"

    body = f"""
<h2><span class="route-tag">{route}</span> {date_range}</h2>
{cover_cards}
{airline_table}
{all_table}"""

    return make_html(body, title, subtitle, search_time)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        sys.exit(f'JSON parse error: {e}')

    if data.get('mode') == 'detail':
        print(format_detail_html(data))
    else:
        print(format_summary_html(data))


if __name__ == '__main__':
    main()
