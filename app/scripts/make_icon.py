"""Draws the app icon: the Fmaj7 shape as plain lines and three solid finger dots, in Latvian carmine.

Writes src-tauri/icons/AppIcon.icon, an Icon Composer document with a light appearance (carmine tile, white
shape) and a dark one (dark tile, carmine shape) that actool compiles, and icon.svg, the flat light icon Tauri
turns into .icns/.ico for older systems.
"""

import json
from pathlib import Path

ICONS = Path(__file__).resolve().parent.parent / "src-tauri" / "icons"

FRETS = [-1, -1, 3, 2, 1, 0]  # Fmaj7, low E to high e; only the fretted strings get a dot
CENTRE = 512  # middle of the 1024 canvas, and of the tile
DX, DY = 112, 152  # string and fret spacing: five gaps across, four frets down
X0 = CENTRE - 5 * DX / 2
TOP = CENTRE - 4 * DY / 2
R = 64  # finger dot radius
XS = [X0 + i * DX for i in range(6)]

# The flag's carmine; on the dark tile a brighter one, as the app's dark appearance uses, so it doesn't sink.
RED, RED_LIGHT, RED_ON_DARK, WHITE, NEAR_BLACK = "#9E3039", "#B8434C", "#C94450", "#FFFFFF", "#1C1C1E"


def shape() -> str:
    """The grid and dots as an SVG fragment in currentColor, on a 1024 canvas."""
    bottom = TOP + 4 * DY
    lines = "".join(f'<line x1="{x}" y1="{TOP}" x2="{x}" y2="{bottom}"/>' for x in XS)
    lines += "".join(f'<line x1="{XS[0]}" y1="{TOP + k * DY}" x2="{XS[-1]}" y2="{TOP + k * DY}"/>' for k in range(5))
    dots = "".join(
        f'<circle cx="{x}" cy="{TOP + (fret - 0.5) * DY}" r="{R}"/>' for x, fret in zip(XS, FRETS) if fret > 0
    )
    return (f'<g stroke="currentColor" stroke-width="16" stroke-linecap="round" fill="none">{lines}</g>'
            f'<g fill="currentColor">{dots}</g>')


def svg(body: str, color: str = WHITE) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024" '
            f'color="{color}">{body}</svg>\n')


def srgb(hex_color: str) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return f"srgb:{r:.5f},{g:.5f},{b:.5f},1.00000"


def appearances(light: dict, dark: dict) -> list[dict]:
    return [{"value": light}, {"appearance": "dark", "value": dark}]


def main() -> None:
    # macOS draws the tile and its glass; each appearance only recolours the shape.
    doc = ICONS / "AppIcon.icon"
    for old in (doc / "Assets").glob("*.svg"):
        old.unlink()
    (doc / "Assets").mkdir(parents=True, exist_ok=True)
    (doc / "Assets" / "shape.svg").write_text(svg(shape()))
    spec = {
        "fill-specializations": appearances({"automatic-gradient": srgb(RED)}, {"solid": srgb(NEAR_BLACK)}),
        "groups": [{
            "layers": [
                {"name": "shape", "image-name": "shape.svg",
                 "fill-specializations": appearances({"solid": srgb(WHITE)}, {"solid": srgb(RED_ON_DARK)})},
            ],
            "shadow": {"kind": "neutral", "opacity": 0.5},
            "translucency": {"enabled": False, "value": 0.5},
        }],
        "supported-platforms": {"squares": ["macOS"]},
    }
    (doc / "icon.json").write_text(json.dumps(spec, indent=2) + "\n")

    tile = (f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{RED_LIGHT}"/>'
            f'<stop offset="1" stop-color="{RED}"/></linearGradient></defs>'
            f'<rect x="100" y="100" width="824" height="824" rx="185" fill="url(#bg)"/>')
    (ICONS / "icon.svg").write_text(svg(tile + shape()))
    # A dark preview with its own tile, for looking at the design without building the app.
    dark_tile = f'<rect x="100" y="100" width="824" height="824" rx="185" fill="{NEAR_BLACK}"/>'
    (ICONS / "icon-dark-preview.svg").write_text(svg(dark_tile + f'<g color="{RED_ON_DARK}">{shape()}</g>'))


if __name__ == "__main__":
    main()
