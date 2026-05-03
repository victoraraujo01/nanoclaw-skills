#!/usr/bin/env python3
"""Format flight search JSON as a WhatsApp monospaced card.

Usage:
  python3 search_flights.py | python3 format_whatsapp.py
  python3 search_flights.py --detail ... | python3 format_whatsapp.py
"""

import json
import sys
from datetime import datetime

# ── Layout constants ────────────────────────────────────────
# Summary mode: 3 columns, total line width = 32 chars
# │ W1=14 │ W2=7 │ W3=7 │  →  1+14+1+7+1+7+1 = 32
# Prices shown without "R$" prefix (currency noted in header)
W1, W2, W3 = 14, 7, 7
SPAN = W1 + 1 + W2 + 1 + W3  # = 30 (inner width for full-width rows)

# Detail mode: 3 columns, same total width = 32 chars
# │ WD1=7 │ WD2=7 │ WD3=14 │  →  1+7+1+7+1+14+1 = 32
WD1, WD2, WD3 = 7, 7, 14
SPAN_D = WD1 + 1 + WD2 + 1 + WD3  # = 30

DAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
MONS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
        'jul', 'ago', 'set', 'out', 'nov', 'dez']


def fdate(d):
    """'2026-05-07' -> 'Sex7'  (day name + day number, no month)"""
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{DAYS[dt.weekday()]}{dt.day}"


def fprice(obj):
    """Extract numeric price string (no R$ prefix) or return '--'."""
    if not obj:
        return '--'
    return obj['price'].replace('R$', '').strip()


def p(s, w, align='<'):
    """Pad string s to exactly w chars; truncate with ~ if too long."""
    s = str(s)
    if len(s) > w:
        s = s[:w - 1] + '~'
    return f'{s:{align}{w}}'


# ── Summary mode box parts ──────────────────────────────────
TOP = '┌' + '─' * SPAN + '┐'               # full-width top (before span rows)
TOP_COLS = '├' + '─'*W1 + '┬' + '─'*W2 + '┬' + '─'*W3 + '┤'  # transition → columns
MID = '├' + '─' * W1 + '┼' + '─' * W2 + '┼' + '─' * W3 + '┤'
BOT = '└' + '─' * SPAN + '┘'               # full-width bottom (after span rows)
DIV = '├' + '─' * SPAN + '┤'


def srow(text):
    """Full-width span row (summary mode)."""
    return '│' + p(' ' + text, SPAN) + '│'


def hrow():
    """Header row for summary table."""
    return (f'│{p(" Datas", W1)}'
            f'│{p("Direto", W2, "^")}'
            f'│{p("Melhor", W3, "^")}│')


def drow(dep, ret, direct_obj, best_obj, hi=False):
    """Data row for summary table."""
    mark = '*' if hi else ' '
    date = f'{fdate(dep)}->{fdate(ret)}'
    c1 = mark + p(date, W1 - 1)          # W1-1 because mark takes 1 char
    c2 = p(fprice(direct_obj), W2, '>')
    c3 = p(fprice(best_obj), W3, '>')
    return f'│{c1}│{c2}│{c3}│'


# ── Detail mode box parts ───────────────────────────────────
TOP_D      = '┌' + '─' * SPAN_D + '┐'                                    # full-width top
TOP_D_COLS = '├' + '─'*WD1 + '┬' + '─'*WD2 + '┬' + '─'*WD3 + '┤'      # transition → columns
MID_D      = '├' + '─' * WD1 + '┼' + '─' * WD2 + '┼' + '─' * WD3 + '┤'
BOT_D      = '└' + '─' * SPAN_D + '┘'                                    # full-width bottom
DIV_D      = '├' + '─' * SPAN_D + '┤'


def srow_d(text):
    """Full-width span row (detail mode)."""
    return '│' + p(' ' + text, SPAN_D) + '│'


def hrow_d():
    return (f'│{p("Cia", WD1, "^")}'
            f'│{p("Preco", WD2, "^")}'
            f'│{p("Hora  Dur  Esc", WD3, "^")}│')


def drow_d(flight, hi=False):
    mark    = '*' if hi else ' '
    airline = mark + p(flight.get('airline', '?'), WD1 - 1)
    price   = p(flight.get('price', '?').replace('R$', '').strip(), WD2, '>')
    dep     = flight.get('departure_time', '?')
    dur     = flight.get('duration', '?').replace(' ', '')   # "6h 55m" → "6h55m"
    dur     = dur.rjust(5)                                   # fixed 5-char width → stops always at right
    stops   = flight.get('stops', '?')
    info    = p(f'{dep} {dur} {stops}e', WD3)
    return f'│{airline}│{price}│{info}│'


# ── Formatters ──────────────────────────────────────────────

def format_summary(data):
    blocks = []
    for trip in data.get('trips', []):
        combos = sorted(
            trip['by_combination'],
            key=lambda x: x['best_overall']['price_numeric']
        )
        if not combos:
            route = f"{trip['origin']}->{trip['destination']}"
            n_tot = trip['total_combinations']
            blocks.append(f"⚠️ {route}: nenhum resultado ({n_tot} combinacoes falharam)")
            continue
        best  = combos[0]
        route = f"{trip['origin']}->{trip['destination']}"
        label = trip['label'].split('-')[-1].strip()
        n_ok  = trip['successful_queries']
        n_tot = trip['total_combinations']

        out = [TOP]
        out.append(srow(f'{route}: {label}'))
        out.append(srow(f'{n_ok}/{n_tot} combinacoes  (R$)'))
        out.append(TOP_COLS)
        out.append(hrow())
        out.append(MID)

        for i, combo in enumerate(combos):
            out.append(drow(
                combo['departure_date'], combo['return_date'],
                combo.get('best_direct'), combo.get('best_overall'),
                hi=(i == 0)
            ))

        out.append(DIV)

        # Best combo detail footer
        dep_dt = datetime.strptime(best['departure_date'], "%Y-%m-%d")
        ret_dt = datetime.strptime(best['return_date'], "%Y-%m-%d")
        days   = (ret_dt - dep_dt).days
        bo     = best['best_overall']
        esc    = bo.get('stops', '?')

        price_num = bo['price'].replace('R$', '').strip()
        out.append(srow(f">> {fdate(best['departure_date'])}->{fdate(best['return_date'])} ({days}d)"))
        out.append(srow(f"   R$ {price_num}  {bo['airline']}  {esc} esc."))
        out.append(srow(f"   {bo.get('departure_time','?')}->{bo.get('arrival_time','?')} {bo.get('duration','?')}"))
        out.append(BOT)

        blocks.append('\n'.join(out))

    return '\n\n'.join(blocks)


def format_detail(data):
    trip    = data.get('trip', {})
    flights = trip.get('all_flights', [])
    dep     = trip.get('departure_date', '')
    ret     = trip.get('return_date', '')
    label   = trip.get('label', '')

    dep_str = fdate(dep) if dep else '?'
    ret_str = fdate(ret) if ret else ''
    date_range = f'{dep_str}->{ret_str}' if ret_str else dep_str

    out = [TOP_D]
    out.append(srow_d(label))
    out.append(srow_d(f'{date_range}  (R$)  {len(flights)} opcoes'))
    out.append(TOP_D_COLS)
    out.append(hrow_d())
    out.append(MID_D)

    for i, flight in enumerate(flights):
        out.append(drow_d(flight, hi=(i == 0)))

    out.append('└' + '─'*WD1 + '┴' + '─'*WD2 + '┴' + '─'*WD3 + '┘')
    return '\n'.join(out)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        sys.exit(f'JSON parse error: {e}')

    if data.get('mode') == 'detail':
        print(format_detail(data))
    else:
        print(format_summary(data))


if __name__ == '__main__':
    main()
