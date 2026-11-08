"""A GarageBand project (.band) from the GarageBand stems, built by GarageBand itself.

Apple doesn't document the .band format, so GarageBand is driven through its interface: it opens the
stems as one track each, the tempo is typed into its display (the slider only moves in steps of 10) and
the key is picked from its menu, then the project is saved next to the stems. This needs GarageBand
installed and the app running it allowed under Privacy & Security › Accessibility; GarageBand is on
screen for about half a minute meanwhile.
"""

import ctypes
import shutil
import subprocess
import time
from pathlib import Path

GARAGEBAND = Path("/Applications/GarageBand.app")
# Where GarageBand saves a project it makes from opened audio files, before it's given a name.
UNTITLED_DIR = Path.home() / "Music" / "GarageBand"
ACCESS_HINT = ("Playalong needs to control GarageBand: allow it under System Settings › Privacy & Security › "
               "Accessibility (the app, or the terminal you run playalong in), then try again.")

# Finds a control in GarageBand's main window by role and description; the window's layout nests deep.
_FIND = """
on findEl(el, depth, wantedRole, wantedName)
	tell application "System Events"
		try
			if role of el is wantedRole and description of el is wantedName then return el
		end try
		if depth > 7 then return missing value
		try
			repeat with c in UI elements of el
				set r to my findEl(c, depth + 1, wantedRole, wantedName)
				if r is not missing value then return r
			end repeat
		end try
	end tell
	return missing value
end findEl
"""

_WAIT_FOR_PROJECT = """
tell application "System Events" to tell process "GarageBand"
	repeat 300 times
		try
			if exists (first window whose name ends with " - Tracks") then exit repeat
		end try
		delay 0.2
	end repeat
	if not (exists (first window whose name ends with " - Tracks")) then return ""
	set frontmost to true
	set w to first window whose name ends with " - Tracks"
	perform action "AXRaise" of w
	return name of w
end tell
"""

_TEMPO_SPOT = _FIND + """
tell application "System Events" to tell process "GarageBand"
	set s to my findEl(window 1, 0, "AXSlider", "Tempo")
	set {px, py} to position of s
	set {sw, sh} to size of s
	return ((px + sw / 2) as integer as text) & " " & ((py + sh / 2) as integer as text)
end tell
"""

_TYPE_TEMPO = _FIND + """
on run argv
	tell application "System Events"
		keystroke (item 1 of argv)
		key code 36
	end tell
	delay 0.5
	tell application "System Events" to tell process "GarageBand"
		return value of my findEl(window 1, 0, "AXSlider", "Tempo") as text
	end tell
end run
"""

_KEY = _FIND + """
on run argv
	tell application "System Events" to tell process "GarageBand"
		set frontmost to true
		set p to my findEl(window 1, 0, "AXPopUpButton", "Key Signature")
		perform action "AXShowMenu" of p
		delay 0.4
		click menu item (item 1 of argv) of menu 1 of p
		delay 0.3
		return value of p as text
	end tell
end run
"""

# Save As, since GarageBand has already saved the new project as "Untitled" and Save wouldn't ask where.
# The folder path is pasted, never typed: typing "~" or accents goes through dead keys.
_SAVE = """
on run argv
	set the clipboard to (item 1 of argv)
	tell application "System Events" to tell process "GarageBand"
		set frontmost to true
		click menu item "Save As…" of menu 1 of menu bar item "File" of menu bar 1
		repeat 50 times
			if exists window "Save" then exit repeat
			delay 0.2
		end repeat
		set w to window "Save"
		set value of text field "Save As:" of splitter group 1 of w to (item 2 of argv)
		keystroke "g" using {command down, shift down}
		delay 0.8
		keystroke "v" using command down
		delay 0.3
		key code 36
		delay 0.8
		click button "Save" of splitter group 1 of w
		repeat 150 times
			if not (exists window "Save") then exit repeat
			delay 0.2
		end repeat
		keystroke "w" using command down
	end tell
end run
"""


class BandError(RuntimeError):
    pass


def key_menu_name(key: str) -> str:
    """'F# minor' as GarageBand's key menu writes it: 'F♯ Minor'."""
    tonic, mode = key.split()
    return f"{tonic[0]}{tonic[1:].replace('#', '♯').replace('b', '♭')} {mode.title()}"


def _osascript(script: str, *args: str) -> str:
    done = subprocess.run(["osascript", "-", *args], input=script, text=True, capture_output=True)
    if done.returncode:
        reason = done.stderr.strip()
        if "assistive" in reason or "-25211" in reason or "-1743" in reason or "not allowed" in reason:
            raise BandError(ACCESS_HINT)
        raise BandError(f"GarageBand didn't do what was expected: {reason}")
    return done.stdout.strip()


def _double_click(x: float, y: float) -> None:
    """A real double-click: GarageBand only makes its tempo editable on one, and AppleScript can't send it."""
    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, Point, ctypes.c_uint32]
    cg.CGEventSetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64]
    cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    left_down, left_up, click_state, hid_tap = 1, 2, 1, 0
    for click in (1, 2):
        for kind in (left_down, left_up):
            event = cg.CGEventCreateMouseEvent(None, kind, Point(x, y), 0)
            cg.CGEventSetIntegerValueField(event, click_state, click)
            cg.CGEventPost(hid_tap, event)
            cf.CFRelease(event)
            time.sleep(0.03)


def _drive(stems: list[Path], dest: Path, bpm: int | None, key: str | None) -> None:
    subprocess.run(["open", "-a", str(GARAGEBAND), *map(str, stems)], check=True)
    if not _osascript(_WAIT_FOR_PROJECT):
        raise BandError("GarageBand didn't show the new project. macOS keeps an app in the background while "
                        "you're working in another one: try again and leave the Mac alone for half a minute.")
    time.sleep(1.5)
    if bpm:
        x, y = map(float, _osascript(_TEMPO_SPOT).split())
        _double_click(x, y)
        time.sleep(0.6)
        got = _osascript(_TYPE_TEMPO, str(bpm))
        if round(float(got.replace(",", "."))) != bpm:
            raise BandError(f"GarageBand's tempo is {got}, not {bpm}; set it by hand and save the project")
    if key:
        _osascript(_KEY, key_menu_name(key))
    _osascript(_SAVE, str(dest.parent), dest.stem)
    for _ in range(50):
        if dest.exists():
            return
        time.sleep(0.2)
    raise BandError("GarageBand didn't save the project")


def build_project(stems_dir: Path, bpm: int | None, key: str | None) -> Path:
    """Make `<stems_dir>.band` next to the stems folder and return it."""
    if not GARAGEBAND.exists():
        raise BandError("GarageBand isn't installed; the stems are in place to drag into a project by hand.")
    stems = sorted(stems_dir.glob("*.wav"))
    if not stems:
        raise BandError(f"No stems in {stems_dir}")
    dest = stems_dir.with_name(stems_dir.name + ".band")
    if dest.exists():
        shutil.rmtree(dest)
    was_running = subprocess.run(["pgrep", "-x", "GarageBand"], capture_output=True).returncode == 0
    untitled = set(UNTITLED_DIR.glob("Untitled*.band"))
    try:
        _drive(stems, dest, bpm, key)
    finally:
        # GarageBand saves a project made from opened files as "Untitled" right away; only one that
        # appeared during this build goes, whether or not the build got through.
        for leftover in set(UNTITLED_DIR.glob("Untitled*.band")) - untitled:
            shutil.rmtree(leftover, ignore_errors=True)
    # GarageBand hides the extension; show it so the file reads as a GarageBand project in Finder.
    subprocess.run(["osascript", "-e", 'on run argv', "-e", 'tell application "Finder" to set extension hidden of '
                    '(POSIX file (item 1 of argv) as alias) to false', "-e", "end run", str(dest)],
                   capture_output=True)
    if not was_running:
        # Quit doesn't wait for an answer: GarageBand can take a while to wind down, and the project is saved.
        subprocess.Popen(["osascript", "-e", 'tell application "GarageBand" to quit'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest
