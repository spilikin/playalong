"""A printable chord sheet: chord diagrams for every chord used, then the song in bars, eight to a line."""

import html
from dataclasses import dataclass

from playalong.countin import BEATS_PER_BAR

BARS_PER_LINE = 4
PITCH = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
         "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
MUTED = -1


@dataclass(frozen=True)
class Voicing:
    frets: tuple[int, ...]  # low E to high e; -1 muted, 0 open
    fingers: tuple[int, ...]  # 1 index … 4 little, 0 none
    barre: int | None = None  # fret the index finger lies across
    barre_from: int = 0  # lowest string under the barre


# Open-position shapes a player reaches for first.
OPEN = {
    (0, "maj"): Voicing((MUTED, 3, 2, 0, 1, 0), (0, 3, 2, 0, 1, 0)),
    (2, "maj"): Voicing((MUTED, MUTED, 0, 2, 3, 2), (0, 0, 0, 1, 3, 2)),
    (4, "maj"): Voicing((0, 2, 2, 1, 0, 0), (0, 2, 3, 1, 0, 0)),
    (7, "maj"): Voicing((3, 2, 0, 0, 0, 3), (2, 1, 0, 0, 0, 3)),
    (9, "maj"): Voicing((MUTED, 0, 2, 2, 2, 0), (0, 0, 1, 2, 3, 0)),
    (2, "min"): Voicing((MUTED, MUTED, 0, 2, 3, 1), (0, 0, 0, 2, 3, 1)),
    (4, "min"): Voicing((0, 2, 2, 0, 0, 0), (0, 2, 3, 0, 0, 0)),
    (9, "min"): Voicing((MUTED, 0, 2, 2, 1, 0), (0, 0, 2, 3, 1, 0)),
}


def _barre(root: int, minor: bool) -> Voicing:
    """The lower of the E-shape (root on the low E string) and A-shape (root on the A string) barres."""
    e_fret, a_fret = (root - 4) % 12 or 12, (root - 9) % 12 or 12
    if e_fret <= a_fret:
        f = e_fret
        if minor:
            return Voicing((f, f + 2, f + 2, f, f, f), (1, 3, 4, 1, 1, 1), barre=f, barre_from=0)
        return Voicing((f, f + 2, f + 2, f + 1, f, f), (1, 3, 4, 2, 1, 1), barre=f, barre_from=0)
    f = a_fret
    if minor:
        return Voicing((MUTED, f, f + 2, f + 2, f + 1, f), (0, 1, 3, 4, 2, 1), barre=f, barre_from=1)
    return Voicing((MUTED, f, f + 2, f + 2, f + 2, f), (0, 1, 2, 3, 4, 1), barre=f, barre_from=1)


def parse(name: str) -> tuple[int, bool]:
    minor = name.endswith("m")
    return PITCH[name[:-1] if minor else name], minor


def voicing(name: str) -> Voicing:
    root, minor = parse(name)
    return OPEN.get((root, "min" if minor else "maj")) or _barre(root, minor)


def diagram_svg(name: str, width: int = 100) -> str:
    """A chord box: strings vertical (low E left), frets down, dots with finger numbers."""
    shape = voicing(name)
    fretted = [f for f in shape.frets if f > 0]
    base = 1 if max(fretted, default=0) <= 4 else min(fretted)

    def x(string: int) -> float:
        return 8 + string * 9

    def y(row: float) -> float:
        return 18 + row * 11

    parts = [f'<svg class="dg" viewBox="0 0 70 66" width="{width}" height="{round(width * 66 / 70)}" '
             f'role="img" aria-label="{html.escape(name)} chord">']
    for s in range(6):
        parts.append(f'<line x1="{x(s)}" y1="{y(0)}" x2="{x(s)}" y2="{y(4)}"/>')
    for row in range(5):
        parts.append(f'<line x1="{x(0)}" y1="{y(row)}" x2="{x(5)}" y2="{y(row)}"/>')
    if base == 1:
        parts.append(f'<line class="nut" x1="{x(0) - 0.5}" y1="{y(0)}" x2="{x(5) + 0.5}" y2="{y(0)}"/>')
    else:
        parts.append(f'<text class="pos" x="{x(5) + 5}" y="{y(0) + 8}">{base}fr</text>')
    for s, f in enumerate(shape.frets):
        if f == MUTED:
            parts.append(f'<text class="top" x="{x(s)}" y="{y(0) - 4}">×</text>')
        elif f == 0:
            parts.append(f'<text class="top" x="{x(s)}" y="{y(0) - 4}">○</text>')
    if shape.barre is not None:
        row = shape.barre - base
        parts.append(f'<rect class="barre" x="{x(shape.barre_from) - 3.6}" y="{y(row) + 1.9}" '
                     f'width="{x(5) - x(shape.barre_from) + 7.2}" height="7.2" rx="3.6"/>')
        parts.append(f'<text class="finger" x="{(x(shape.barre_from) + x(5)) / 2}" y="{y(row) + 7.6}">1</text>')
    for s, (f, finger) in enumerate(zip(shape.frets, shape.fingers)):
        if f <= 0 or (shape.barre is not None and f == shape.barre and s >= shape.barre_from):
            continue
        row = f - base
        parts.append(f'<circle cx="{x(s)}" cy="{y(row) + 5.5}" r="3.6"/>')
        if finger:
            parts.append(f'<text class="finger" x="{x(s)}" y="{y(row) + 7.6}">{finger}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _clock(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


STYLE = """
:root { --paper: #ffffff; --ink: #1f1f22; --muted: #9a9a9f; --panel: #eeeef0; --cell: #ffffff;
  --barline: #56565c; --rule: #dcdce0; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
  font: 15px/1.4 ui-sans-serif, -apple-system, "Helvetica Neue", sans-serif; }
main { max-width: 1240px; margin: 0 auto; padding: 32px 24px 48px; }
header h1 { font: 600 28px/1.15 ui-sans-serif, -apple-system, sans-serif; margin: 0 0 6px; letter-spacing: -0.015em; }
header p { margin: 0; color: var(--muted); }
header { margin-bottom: 24px; }
header p b { color: var(--ink); font-weight: 600; }
h2 { font-size: 17px; font-weight: 600; margin: 32px 0 0; }
.legend { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 24px; }
.legend figure { margin: 0; padding: 8px 8px 6px; border: 1px solid var(--rule); border-radius: 10px; text-align: center; }
.legend figcaption { font-weight: 600; font-size: 16px; margin-top: 2px; }
.dg { color: var(--ink); display: block; }
.dg line { stroke: currentColor; stroke-width: 0.8; }
.dg .nut { stroke-width: 2.6; }
.dg circle, .dg .barre { fill: var(--ink); }
.dg text { font: 600 6px ui-sans-serif, -apple-system, sans-serif; text-anchor: middle; fill: currentColor; }
.dg .finger { fill: #fff; font-size: 5.4px; }
.dg .top { font-size: 7px; }
.dg .pos { text-anchor: start; font-size: 6.5px; fill: var(--muted); }
.chart { background: var(--panel); border-radius: 8px; padding: 6px 0; }
.row { display: grid; grid-template-columns: 2.6rem repeat(4, minmax(0, 1fr)) 3.4rem; padding: 8px 0;
  break-inside: avoid; }
.num, .time { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; padding-top: 10px; }
.num { text-align: center; }
.time { text-align: right; padding-right: 10px; }
/* Every bar opens with a heavy bar line, as on a lead sheet; the last one in a row also closes it. */
.bar { position: relative; padding: 0 4px 4px 10px; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.bar::before { content: ""; position: absolute; left: 2px; top: 0; bottom: 0; width: 4px; border-radius: 2px;
  background: var(--barline); }
.row .bar:nth-last-child(2)::after { content: ""; position: absolute; right: -3px; top: 0; bottom: 0; width: 4px;
  border-radius: 2px; background: var(--barline); }
.beats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 3px; }
.beat { background: var(--cell); border-radius: 5px; min-height: 48px; padding: 11px 8px 0;
  font-size: 21px; font-weight: 600; letter-spacing: -0.02em; white-space: nowrap; }
/* A name may run on over the beats that follow it; those are empty until the next change. */
.beat:not(:empty) { position: relative; z-index: 1; }
.beat.same { color: var(--muted); font-weight: 500; }
.beat.none { color: var(--muted); font-weight: 500; font-size: 12px; }
.beat.end { background: transparent; }
.shapes { display: flex; flex-wrap: wrap; gap: 6px; padding-left: 2px; }
/* Diagrams follow the bar's width, so a narrow window shrinks them instead of wrapping bars. */
.shapes .dg { width: clamp(44px, 6vw, 80px); height: auto; }
.pickup { color: var(--muted); margin: 0 0 8px; font-size: 13px; }
.pickup b { color: var(--ink); }
footer { margin-top: 18px; color: var(--muted); font-size: 12px; }
@media (max-width: 760px) {
  main { padding: 20px 12px 32px; }
  .row { grid-template-columns: 1.6rem repeat(4, minmax(0, 1fr)); }
  .time { display: none; }
  .bar { padding: 0 2px 4px 8px; }
  .beat { min-height: 34px; padding: 7px 3px 0; font-size: 14px; }
}
@media print {
  main { padding: 0; max-width: none; }
  .legend { break-after: avoid; }
  .chart { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""


def render_page(result, title: str, subtitle: str = "") -> str:
    """The whole sheet as one self-contained HTML page."""
    def chord_at(t: float) -> str:
        return next((c.name for c in result.chords if c.start <= t + 1e-6 < c.end), "N")

    grid = result.beats[:-1]
    names_in_order = []
    for c in result.chords:
        if c.name != "N" and c.name not in names_in_order:
            names_in_order.append(c.name)

    previous = None

    def bar(beats: list[float]) -> str:
        """Four beat cells naming each chord where it starts, then a diagram for every chord in the bar,
        including one carried over from the bar before (named in grey)."""
        nonlocal previous
        names = [chord_at(t) for t in beats]
        cells, shown = [], []
        for i, name in enumerate(names):
            starts = i == 0 or name != names[i - 1]
            label = ("N.C." if name == "N" else name) if starts else ""
            if i == 0 and name == previous:
                kind = "beat same"
            elif starts and name == "N":
                kind = "beat none"
            else:
                kind = "beat"
            cells.append(f'<span class="{kind}">{html.escape(label)}</span>')
            if starts and name != "N" and name not in shown:
                shown.append(name)
            previous = name
        cells += ['<span class="beat end"></span>'] * (BEATS_PER_BAR - len(names))
        shapes = "".join(diagram_svg(n, 72) for n in shown)
        return f'<div class="beats">{"".join(cells)}</div><div class="shapes">{shapes}</div>'

    body = []
    if result.pickup:
        lead_in = []
        for t in grid[: result.pickup]:
            name = chord_at(t)
            if not lead_in or lead_in[-1] != name:
                lead_in.append(name)
            previous = name
        body.append(f'<p class="pickup">Pickup: <b>{html.escape("  ".join(lead_in))}</b></p>')
    bar_starts = list(range(result.pickup, len(grid), BEATS_PER_BAR))
    for i in range(0, len(bar_starts), BARS_PER_LINE):
        line = bar_starts[i : i + BARS_PER_LINE]
        bars = "".join(f'<div class="bar">{bar(grid[b : b + BEATS_PER_BAR])}</div>' for b in line)
        body.append(f'<div class="row"><span class="num">{i + 1}</span>{bars}'
                    f'<span class="time">{_clock(grid[line[0]] - grid[0])}</span></div>')

    legend = "".join(f"<figure>{diagram_svg(n)}<figcaption>{html.escape(n)}</figcaption></figure>"
                     for n in names_in_order)
    meta = f"Key <b>{html.escape(result.key)}</b> · <b>{result.bpm:.0f}</b> BPM"
    if subtitle:
        meta = f"{html.escape(subtitle)} · {meta}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{html.escape(title)} – chords</title>
<style>{STYLE}</style>
</head>
<body>
<main>
<header><h1>{html.escape(title)}</h1><p>{meta}</p></header>
<section class="chart" aria-label="Chords by bar">
{chr(10).join(body)}
</section>
<h2>Chord shapes</h2>
<section class="legend" aria-label="Chord shapes">{legend}</section>
<footer>Detected from the recording; bar numbers and times from the song start. N.C. = no chord.</footer>
</main>
</body>
</html>
"""
