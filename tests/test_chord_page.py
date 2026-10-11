import re

import pytest

from playalong.chord_page import diagram_svg, render_page, voicing
from playalong.chords import Chord, ChordResult

TUNING = (4, 9, 2, 7, 11, 4)  # E A D G B E
PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
      "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


@pytest.mark.parametrize("root", sorted(PC))
@pytest.mark.parametrize("minor", [False, True])
def test_every_voicing_plays_exactly_the_triad(root, minor):
    shape = voicing(root + ("m" if minor else ""))
    sounding = {(TUNING[s] + f) % 12 for s, f in enumerate(shape.frets) if f >= 0}
    r = PC[root]
    assert sounding == {r, (r + (3 if minor else 4)) % 12, (r + 7) % 12}
    # The lowest sounding string is the root, so the chord doesn't come out inverted.
    lowest = next(s for s, f in enumerate(shape.frets) if f >= 0)
    assert (TUNING[lowest] + shape.frets[lowest]) % 12 == r
    # Playable: at most four fingers, all within a four-fret span.
    fretted = [f for f in shape.frets if f > 0]
    assert max(fretted, default=0) - min(fretted, default=0) <= 3
    assert len({n for n in shape.fingers if n > 0}) <= 4


def test_open_chords_where_they_exist_and_barres_elsewhere():
    assert voicing("C").frets == (-1, 3, 2, 0, 1, 0)
    assert voicing("Am").frets == (-1, 0, 2, 2, 1, 0)
    assert voicing("F").frets == (1, 3, 3, 2, 1, 1) and voicing("F").barre == 1
    assert voicing("Bb").frets == (-1, 1, 3, 3, 3, 1) and voicing("Bb").barre == 1


def test_diagram_marks_muted_open_strings_and_position():
    svg = diagram_svg("C")
    assert svg.startswith("<svg") and ">×<" in svg and ">○<" in svg
    assert "fr" not in svg  # open position: the nut is drawn, no fret number
    assert "6fr" in diagram_svg("Eb")  # A-shape barre at the 6th fret


def result(names, bars=10):
    beats = [i * 0.5 for i in range(bars * 4 + 1)]
    chords = [Chord(beats[i * 4], beats[i * 4 + 4], names[i % len(names)]) for i in range(bars)]
    return ChordResult(key="C major", bpm=120.0, first_beat=0.0, chords=chords, beats=beats)


def test_page_has_four_bars_per_line_then_a_diagram_per_chord():
    page = render_page(result(["C", "G", "Am", "F"]), title="Song <1>")
    rows = page.split('<div class="row">')[1:]
    assert [r.count('class="bar"') for r in rows] == [4, 4, 2]
    # The song comes first; the overview of chord shapes follows it.
    assert page.index('class="chart"') < page.index('class="legend"')
    legend = page.split('class="legend"')[1].split("</section>")[0]
    assert legend.count("<svg") == 4
    assert "Song &lt;1&gt;" in page and "Song <1>" not in page


def test_no_chord_has_no_diagram():
    page = render_page(result(["C", "N"], bars=2), title="x")
    legend = page.split('class="legend"')[1].split("</section>")[0]
    assert legend.count("<svg") == 1


def test_every_bar_has_four_beat_cells_and_its_chord_diagrams():
    # Bar 1: C. Bar 2: C, then G from beat 2. Bar 3: G carried over.
    beats = [i * 0.5 for i in range(4 * 3 + 1)]
    chords = [Chord(0.0, 2.5, "C"), Chord(2.5, 6.0, "G")]
    page = render_page(ChordResult("C major", 120.0, 0.0, chords, beats), title="x")
    bars = page.split('<div class="bar">')[1:]
    cells = [re.findall(r'<span class="beat[^"]*">([^<]*)</span>', b) for b in bars]
    assert cells == [["C", "", "", ""], ["C", "G", "", ""], ["G", "", "", ""]]
    # A chord carried over from the previous bar is named in grey, but still gets its diagram.
    assert 'class="beat same">C<' in bars[1] and 'class="beat same">G<' in bars[2]
    shapes = [b.split('class="shapes"')[1].split("</div>")[0].count("<svg") for b in bars]
    assert shapes == [1, 2, 1]
