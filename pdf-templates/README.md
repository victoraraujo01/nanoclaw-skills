# PDF Templates

Custom HTML+CSS templates for generating PDFs via the `pdf-generator` skill.

## Usage

```bash
cp /home/node/.claude/skills/pdf-templates/relatorio.html /workspace/group/doc.html
# Edit doc.html replacing the placeholder sections
generate-pdf /workspace/group/doc.html /workspace/group/doc.pdf
```

## Color Palette

| Variable | Value | Usage |
|---|---|---|
| `--accent` | `#1e3a5f` | Dark blue — headings, cover background, table headers |
| `--accent2` | `#f0813a` | Orange — tags, numbered circles, card borders, callout border |
| `--accent-light` | `#e8eef5` | Light blue — callout background |
| `--text` | `#18181b` | Body text |
| `--muted` | `#71717a` | Secondary text, labels |
| `--border` | `#e4e4e7` | Borders, dividers |
| `--surface` | `#fafafa` | Card/table row backgrounds |

## Components

- **Cover** — full-width dark blue header with orange tag pill, title, subtitle
- **Cards** — 2 or 3-column metric cards with orange top border
- **Numbered sections (h2)** — orange circle number + blue heading + horizontal rule
- **Timeline** — vertical timeline with dark blue dots and connecting line
- **Badges** — inline status pills: `badge-ok` (green), `badge-warn` (yellow), `badge-info` (blue)
- **Callout** — highlighted box with orange left border
- **Table** — dark blue header, alternating row colors
- **Footer** — divider line with document info and "Gerado automaticamente pelo agente Claw"

## Templates

| File | Use case |
|---|---|
| `relatorio.html` | Session/development reports, summaries |
| `itinerario.html` | Travel itineraries, trip planning |
