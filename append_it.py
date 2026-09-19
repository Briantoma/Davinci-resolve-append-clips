#!/usr/bin/env python3
"""
Append It
append_it_V1.0.py

Appends the clips selected in the Media Pool to the end of the current
timeline, leaving a gap after the last frame on any track, optionally a gap
between reels, a coloured marker per reel and a clip colour per camera.

Target: DaVinci Resolve Studio 21.1, macOS, Python 3.
Install to:
  ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/
then run from Workflow > Scripts.

Studio only. Python scripting and UIManager both became Studio features in
21.1, so nothing here runs on the free edition.

Notes, all found by testing on Studio 21.1. They are the reason several
things are written the way they are, so read before changing them.

  clipInfo "endFrame" is exclusive: a clip's length is endFrame minus
  startFrame, not plus one. FRAME_OFFSET compensates, and the first pad
  recalibrates automatically if a future build changes it.

  TimelineItem.GetEnd() is exclusive and agrees with Timeline.GetEndFrame().
  TimelineItem.GetDuration() is the only unambiguous length, so calibration
  uses it.

  Timeline.AddMarker takes a frame relative to the timeline start, not the
  absolute frame. The fallback to the absolute frame has never been needed.

  A video only filler is enough to move the append point. Linked audio
  follows the video anchor. AppendToTimeline returns video items only, so
  audio is matched by name and start frame when colouring.

  UIManager: a widget that is created hidden only takes up space after a
  real hidden to visible transition, so every conditional group is built
  hidden and toggled after Show(). A field nested in a group must not carry
  MinimumSize unless the group is pinned too, or it vanishes. Two rows only
  align if they have the same number of children as well as the same
  widths, because a gap is inserted between every child. A ComboBox cannot
  colour its items, which is why colours are picked from a popup grid.

  There is no undo in the API, and no way to group operations into one undo
  step, so an append costs a dozen presses of cmd+Z.

  Resolve runs every script inside its own process, so a pid based single
  instance lock is useless. The window registry is the real check.
"""

VERSION = "1.0"

SHOW_GUI = 1              # 1 = window, 0 = headless with the last settings
                          # saved by the window, or the defaults below if the
                          # settings file does not exist yet

# ------------------------------------------------------------- defaults

DEFAULTS = {
    "gap_seconds": 30.0,
    "clip_order": "name",          # pool, name, timecode, duration
    "clip_order_reverse": False,
    "reel_gaps": True,
    "reel_preset": "cam_letter",   # see REEL_PRESETS
    "reel_pattern": r"^(?P<cam>[A-Za-z]{1,2})[ _-]?(?P<reel>\d{2,4})",
    "reel_chars": 4,               # used by the "first N characters" preset
    "reel_gap_same": True,         # reel gap equals the head gap
    "reel_gap_seconds": 30.0,
    "reel_markers": True,
    "colour_clips": False,
    "jump_to_colour": False,
    # letter:marker/clip. The clip part is optional, CLIP_COLOUR_FOR_MARKER
    # fills it in when a saved file predates the clip colour column.
    "marker_colors": "A:Red/Violet, B:Blue/Navy, *:Cream/Tan",
    # A and B come from DEFAULT_CAMERA_COLOURS, kept literal so the file
    # still loads if that table is edited.
}

GAP_BASIS = "wallclock"   # not exposed: real time rather than timecode seconds
GAP_ROUNDING = "nearest"  # not exposed
FRAME_OFFSET = 1          # clipInfo endFrame is exclusive on 21.1
USE_RECORD_FRAME = False  # not exposed, see header
FILLER_VIDEO_ONLY = True  # not exposed

RESTORE_PAGE = True       # go back to the page you were on when done
COLOUR_AUDIO = True       # colour the linked audio items as well as video

MAX_CALIBRATION_TRIES = 3
MAX_FILLER_SEGMENTS = 200

SETTINGS_FILE = "append_it_settings.json"
LEGACY_SETTINGS_FILE = "append_clips_settings.json"

KEY_ESCAPE = 16777216     # Qt.Key_Escape

# Resolve accepts only these marker colours. There is no orange.
MARKER_COLOURS = ["Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple",
                  "Fuchsia", "Rose", "Lavender", "Sky", "Mint", "Lemon",
                  "Sand", "Cocoa", "Cream"]

# Approximations for the swatches only. Resolve does not expose the real
# values, so these are eyeballed and do not affect what is written.
COLOUR_HEX = {
    # measured from the Resolve 21.1 menus, see resolve_colour_reference.md
    "Blue": "#0281ec", "Cyan": "#01d2d2", "Green": "#01af00",
    "Yellow": "#fd9800", "Red": "#f60100", "Pink": "#ff24ce",
    "Purple": "#9d00ff", "Fuchsia": "#cf136f", "Rose": "#ff9ab9",
    "Lavender": "#a493ca", "Sky": "#76e5fe", "Mint": "#3edc04",
    "Lemon": "#d7e938", "Sand": "#c68e54", "Cocoa": "#684e41",
    "Cream": "#f0e9df",
}

MARKER_PAIR_ROWS = 8      # rows of two cameras, so 16 camera slots
MARKER_SLOTS = MARKER_PAIR_ROWS * 2
# The camera grid sits at the left margin, so this is just the margin now.
# Every row in the block starts with a spacer of this width, which is what
# keeps the grid, the fallback row and the buttons in one column.
MARKER_LABEL_WIDTH = 4

# Column widths for the camera grid. The header row and the widget rows use
# these same numbers with minimum equal to maximum, and both have the same
# number of children per cell, so the layout spacing accumulates identically
# and the titles sit over their columns. A label left unpinned shrinks to
# its text and the whole row drifts.
COL_LETTER = 46
COL_COMBO = 104           # width of a colour button
PALETTE_COLS = 4


def palette_cell():
    """Just wide enough for the longest colour name in either palette."""
    longest = max(len(n) for n in MARKER_COLOURS + CLIP_COLOURS)
    return [longest * 8 + 18, FIELD_HEIGHT]
COL_SWATCH = 22
COL_PAD = 10

WINDOW_WIDTH = 570
BASE_HEIGHT = 270         # window with the colour block and preview hidden
BLOCK_CHROME = 92         # header, fallback, buttons and padding         # everything except the camera rows and the preview
CAMERA_ROW_HEIGHT = 28
DETAIL_ROW_HEIGHT = 30    # the reel pattern or character count row
PREVIEW_HEIGHT = 320

# Nearest marker and clip colour to the standard camera letter colours,
# computed as Lab distance against the measured swatches and adjusted by
# eye. Duplicates are deliberate: sixteen cameras do not map onto sixteen
# markers without repeats, and forcing uniqueness gives worse matches.
# See resolve_colour_reference.md for the working.
CAMERA_LETTERS = "ABCDEFGHIJKLMNOP"
DEFAULT_CAMERA_COLOURS = {
    "A": ("Red", "Violet"),             # red
    "B": ("Blue", "Navy"),              # blue
    "C": ("Lemon", "Yellow"),          # yellow
    "D": ("Green", "Green"),              # fluo green
    "E": ("Purple", "Purple"),          # purple
    "F": ("Yellow", "Orange"),          # fluo orange
    "G": ("Fuchsia", "Violet"),         # fluo pink
    "H": ("Lemon", "Lime"),             # fluo yellow
    "I": ("Cyan", "Teal"),              # fluo cyan
    "J": ("Fuchsia", "Chocolate"),      # burgundy
    "K": ("Rose", "Pink"),              # baby pink
    "L": ("Cocoa", "Olive"),            # olive drab
    "M": ("Cocoa", "Chocolate"),        # brown
    "N": ("Sky", "Blue"),               # light blue
    "O": ("Lavender", "Purple"),        # light purple
    "P": ("Cyan", "Teal"),              # cyan
}

# Clip colours are a different list from marker colours. Only Yellow, Green,
# Blue, Purple and Pink exist in both, so the rest are nearest equivalents.
# Change any of these to taste; every value must be a real clip colour.
CLIP_COLOURS = ["Orange", "Apricot", "Yellow", "Lime", "Olive", "Green",
                "Teal", "Navy", "Blue", "Purple", "Violet", "Pink", "Tan",
                "Beige", "Brown", "Chocolate"]

# Approximations for the clip colour swatches, same caveat as COLOUR_HEX.
CLIP_COLOUR_HEX = {
    # measured the same way. Note these share five names with the marker
    # colours and not one of the five is the same colour
    "Orange": "#fb6400", "Apricot": "#ffa302", "Yellow": "#dbab02",
    "Lime": "#93c801", "Olive": "#499b00", "Green": "#18915f",
    "Teal": "#019b9c", "Navy": "#005379", "Blue": "#3077a4",
    "Purple": "#a16fa2", "Violet": "#e34a92", "Pink": "#f787b7",
    "Tan": "#bab093", "Beige": "#ca9f77", "Brown": "#a16303",
    "Chocolate": "#93583c",
}

CLIP_COLOUR_FOR_MARKER = {
    "Blue": "Blue",          # exact
    "Green": "Green",        # exact
    "Yellow": "Yellow",      # exact
    "Purple": "Purple",      # exact
    "Pink": "Pink",          # exact
    "Red": "Orange",         # no red clip colour exists
    "Cyan": "Teal",
    "Fuchsia": "Violet",
    "Rose": "Apricot",
    "Lavender": "Violet",
    "Sky": "Navy",
    "Mint": "Lime",
    "Lemon": "Yellow",
    "Sand": "Apricot",   # camera F, fluo orange
    "Cocoa": "Brown",
    "Cream": "Beige",
}

# Timeline.AddMarker takes a frame relative to the timeline start frame, so a
# timeline starting at 01:00:00:00 needs the offset subtracted. If that call
# fails the script retries with the absolute frame and says which worked.
MARKER_FRAME_RELATIVE = True

# Sizing rules learned the hard way on Studio 21.1:
#   - a field sitting directly in a row can take MinimumSize safely
#   - a field nested inside a group must not, it vanishes. Give the group a
#     Weight so it gets space, give the field a Weight so it fills, and cap
#     it with MaximumSize
# Each call builds a fresh list rather than sharing one object.
FIELD_WIDTH = 80
FIELD_HEIGHT = 24
LABEL_WIDTH = 200


def field_min():
    """Safe only for a field that is a direct child of a row."""
    return [FIELD_WIDTH, 0]


def field_max():
    return [FIELD_WIDTH, FIELD_HEIGHT]


def label_min():
    return [LABEL_WIDTH, 0]

# key, label shown in the dropdown, regex or None for a non regex mode
REEL_PRESETS = [
    ("cam_letter", "Camera letter + reel number (A001, A_0001)",
     r"^(?P<cam>[A-Za-z]{1,2})[ _-]?(?P<reel>\d{2,4})"),
    ("cam_word", "Camera name + reel number (CAM001)",
     r"^(?P<cam>[A-Za-z]{1,4})[ _-]?(?P<reel>\d{2,4})"),
    ("number", "Reel number only (001)",
     r"^(?P<reel>\d{2,4})"),
    ("first_n", "First N characters", None),
    ("custom", "Custom regex", None),
]
PRESET_KEYS = [k for k, _, _ in REEL_PRESETS]
PRESET_REGEX = dict((k, r) for k, _, r in REEL_PRESETS)

# ------------------------------------------------------------- plumbing

import json
import math
import os
import re
import sys


def log(message):
    print(message)


class Config(object):
    """Everything the placement code needs, so nothing reads the GUI."""

    def __init__(self, **kw):
        for key, value in DEFAULTS.items():
            setattr(self, key, kw.get(key, value))
        # Session only, deliberately not saved: the window always opens
        # compact. Move it into DEFAULTS to have it remembered.
        self.show_preview = False

    def as_dict(self):
        return dict((k, getattr(self, k)) for k in DEFAULTS)

    def head_gap_seconds(self):
        return float(self.gap_seconds)

    def preset_key(self):
        return self.reel_preset if self.reel_preset in PRESET_KEYS \
            else PRESET_KEYS[0]

    def effective_pattern(self):
        """Regex for the chosen preset, or None for 'first N characters'."""
        key = self.preset_key()
        if key == "custom":
            return self.reel_pattern
        return PRESET_REGEX[key]

    def reel_gap_value(self):
        if self.reel_gap_same:
            return float(self.gap_seconds)
        return float(self.reel_gap_seconds)


def settings_path():
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
        else os.path.expanduser("~")
    if os.access(here, os.W_OK):
        return os.path.join(here, SETTINGS_FILE)
    return os.path.join(os.path.expanduser("~"), SETTINGS_FILE)


def legacy_settings_path():
    return os.path.join(os.path.dirname(settings_path()),
                        LEGACY_SETTINGS_FILE)


def load_settings(verbose=False):
    path = settings_path()
    if not os.path.exists(path):
        legacy = legacy_settings_path()
        if os.path.exists(legacy):
            if verbose:
                log("carrying over the settings from %s" % LEGACY_SETTINGS_FILE)
            path = legacy
        else:
            if verbose:
                log("no saved settings at %s, using defaults" % path)
            return Config()
    try:
        with open(path, "r") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("not a settings object")
        cfg = Config(**data)
        if verbose:
            log("settings from %s" % path)
        return cfg
    except Exception as err:
        log("could not read %s (%s), using defaults" % (path, err))
        return Config()


def save_settings(cfg):
    try:
        with open(settings_path(), "w") as handle:
            json.dump(cfg.as_dict(), handle, indent=2)
    except Exception as err:
        log("could not save settings: %s" % err)


def get_resolve():
    g = globals()
    if g.get("resolve") is not None:
        return g["resolve"]
    try:
        import DaVinciResolveScript as dvr_script
    except ImportError:
        mod = os.environ.get("RESOLVE_SCRIPT_API")
        mod = os.path.join(mod, "Modules") if mod else (
            "/Library/Application Support/Blackmagic Design/"
            "DaVinci Resolve/Developer/Scripting/Modules")
        sys.path.append(mod)
        import DaVinciResolveScript as dvr_script
    return dvr_script.scriptapp("Resolve")


def as_list(obj):
    if not obj:
        return []
    if isinstance(obj, dict):
        return [obj[k] for k in sorted(obj.keys())]
    return list(obj)


def items_in_track(timeline, track_type, index):
    getter = (getattr(timeline, "GetItemListInTrack", None) or
              getattr(timeline, "GetItemsInTrack", None))
    return as_list(getter(track_type, index)) if getter else []


def timeline_content_end(timeline, verbose=False):
    """Exclusive end of the last clip on any track."""
    scanned = 0
    for kind in ("video", "audio", "subtitle"):
        count = timeline.GetTrackCount(kind) or 0
        for i in range(1, int(count) + 1):
            for item in items_in_track(timeline, kind, i):
                try:
                    scanned = max(scanned, int(item.GetEnd()))
                except Exception:
                    pass
    reported = timeline.GetEndFrame()
    reported = int(reported) if reported is not None else 0
    if verbose:
        log("  scanned track end: %d" % scanned)
        log("  Timeline.GetEndFrame(): %d" % reported)
        if scanned != reported:
            log("  NOTE: the two disagree, using the larger")
    return max(scanned, reported)


def item_duration(item):
    try:
        d = item.GetDuration()
        if d:
            return int(d)
    except Exception:
        pass
    return int(item.GetEnd()) - int(item.GetStart())


def timeline_fps(timeline):
    raw = timeline.GetSetting("timelineFrameRate")
    try:
        fps = float(raw)
    except (TypeError, ValueError):
        fps = 0.0
    if fps <= 0 or fps > 1000:
        raise RuntimeError("timelineFrameRate came back as %r" % raw)
    return fps, raw


def frames_to_tc(frames, fps):
    nominal = int(round(fps)) or 1
    total = int(frames)
    f = total % nominal
    s = (total // nominal) % 60
    m = (total // (nominal * 60)) % 60
    h = total // (nominal * 3600)
    return "%02d:%02d:%02d:%02d" % (h, m, s, f)


# ------------------------------------------------------------- gap maths


def gap_frames_from_seconds(fps, seconds, quiet=False):
    rate = round(fps) if GAP_BASIS == "timecode" else fps
    exact = seconds * rate
    if GAP_ROUNDING == "nearest":
        frames = int(round(exact))
    elif GAP_ROUNDING == "up":
        frames = int(math.ceil(exact))
    else:
        frames = int(math.floor(exact))
    if frames < 0:
        raise RuntimeError("gap works out to %d frames" % frames)
    if not quiet:
        log("  gap: %.4f s at %.6f fps = %.4f frames -> %d"
            % (seconds, rate, exact, frames))
        if abs(exact - frames) > 0.0001:
            log("  note: real gap is %.6f s" % (frames / rate))
    return frames


# ------------------------------------------------------------- selection


def clip_extent(mpi):
    def prop(key):
        try:
            return mpi.GetClipProperty(key)
        except Exception:
            return None

    frames = prop("Frames")
    frames = int(frames) if frames else 0
    try:
        start, end = int(prop("Start")), int(prop("End"))
    except (TypeError, ValueError):
        start, end = None, None
    if start is None or end is None or end < start:
        if frames < 1:
            return None
        start, end = 0, frames - 1
    return start, end


def natural_key(text):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", text or "")]


def tc_to_frames(tc, fps):
    if not tc:
        return None
    parts = re.split(r"[:;]", tc.strip())
    if len(parts) != 4:
        return None
    try:
        h, m, s, f = (int(p) for p in parts)
    except ValueError:
        return None
    nominal = int(round(fps)) or 1
    total = ((h * 60 + m) * 60 + s) * nominal + f
    if ";" in tc:
        per_min = 2 * (nominal // 30)
        minutes = h * 60 + m
        total -= per_min * (minutes - minutes // 10)
    return total


SORT_ALIASES = {
    "pool": "pool", "selection": "pool", "media pool": "pool", "none": "pool",
    "name": "name", "filename": "name", "clipname": "name", "clip name": "name",
    "timecode": "timecode", "tc": "timecode", "start tc": "timecode",
    "source tc": "timecode",
    "duration": "duration", "length": "duration", "frames": "duration",
}

SORT_LABELS = [
    ("pool", "Media pool order"),
    ("name", "Clip name"),
    ("timecode", "Source timecode"),
    ("duration", "Duration"),
]


def resolve_sort_mode(raw):
    if not isinstance(raw, str):
        raise RuntimeError("sort order must be a string, got %r" % (raw,))
    mode = SORT_ALIASES.get(" ".join(raw.strip().lower().split()))
    if mode is None:
        raise RuntimeError("sort order %r is not recognised" % (raw,))
    return mode


def sort_clips(clips, fps, cfg):
    mode = resolve_sort_mode(cfg.clip_order)
    if mode == "pool":
        ordered = list(clips)
    elif mode == "name":
        ordered = sorted(clips, key=lambda c: natural_key(c[0].GetName()))
    elif mode == "duration":
        ordered = sorted(clips, key=lambda c: c[2] - c[1])
    else:
        def key(c):
            try:
                tc = c[0].GetClipProperty("Start TC")
            except Exception:
                tc = None
            frames = tc_to_frames(tc, fps)
            if frames is None:
                return (1, 0, natural_key(c[0].GetName()))
            return (0, frames, [])
        ordered = sorted(clips, key=key)
    if cfg.clip_order_reverse:
        ordered.reverse()
    return ordered


def usable_clips(media_pool):
    out = []
    for mpi in as_list(media_pool.GetSelectedClips()):
        name = mpi.GetName()
        try:
            kind = mpi.GetClipProperty("Type")
        except Exception:
            kind = None
        if kind and str(kind).lower() == "timeline":
            log("  skipping timeline item: %s" % name)
            continue
        extent = clip_extent(mpi)
        if not extent:
            log("  skipping, no frame count: %s" % name)
            continue
        out.append((mpi, extent[0], extent[1]))
    return out


# ------------------------------------------------------------- reels


def parse_marker_pairs(text):
    """
    'A:Red/Orange, B:Blue, *:Cream' to [('A', 'Red', 'Orange'), ...].
    The clip colour after the slash is optional and defaults from
    CLIP_COLOUR_FOR_MARKER, so a mapping without it still loads.
    """
    pairs, seen = [], set()
    for part in re.split(r"[,;\n]", text or ""):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise RuntimeError("%r should look like A:Red" % part)
        letter, colours = part.split(":", 1)
        letter = letter.strip().upper()[:2]
        if not letter:
            raise RuntimeError("%r has no camera letter" % part)
        if "/" in colours:
            marker, clip = colours.split("/", 1)
        else:
            marker, clip = colours, ""
        marker = marker.strip().title()
        clip = clip.strip().title()
        if marker not in MARKER_COLOURS:
            raise RuntimeError("%s is not a Resolve marker colour. Use one "
                               "of: %s" % (marker, ", ".join(MARKER_COLOURS)))
        if not clip:
            clip = CLIP_COLOUR_FOR_MARKER.get(marker, CLIP_COLOURS[0])
        if clip not in CLIP_COLOURS:
            raise RuntimeError("%s is not a Resolve clip colour. Use one "
                               "of: %s" % (clip, ", ".join(CLIP_COLOURS)))
        if letter in seen:
            raise RuntimeError("%s is listed twice" % letter)
        seen.add(letter)
        pairs.append((letter, marker, clip))
    if not pairs:
        raise RuntimeError("no camera colours set")
    return pairs


def marker_maps(text):
    """Returns (letter to marker colour, letter to clip colour)."""
    pairs = parse_marker_pairs(text)
    return (dict((l, m) for l, m, _ in pairs),
            dict((l, c) for l, _, c in pairs))


def colour_for(key, mapping):
    """
    Colour for a reel key. The leading letters are tried two characters
    first so a two letter camera can have its own colour, then one, then
    the '*' fallback.
    """
    letters = ""
    for char in key or "":
        if not char.isalpha():
            break
        letters += char.upper()
        if len(letters) == 2:
            break
    for candidate in (letters, letters[:1]):
        if candidate and candidate in mapping:
            return mapping[candidate]
    return mapping.get("*")


def reel_key(name, cfg):
    """Reel name for a clip, or None if it does not match."""
    if not name:
        return None
    pattern = cfg.effective_pattern()
    if pattern is None:                      # first N characters
        count = int(cfg.reel_chars)
        if count < 1 or len(name) < count:
            return None
        return name[:count].upper()
    try:
        m = re.match(pattern, name)
    except re.error as err:
        raise RuntimeError("reel pattern is not valid: %s" % err)
    if not m:
        return None
    try:
        cut = m.end("reel")
    except Exception:
        raise RuntimeError("reel pattern needs a named group called 'reel'")
    return name[:cut].upper()


def group_by_reel(clips, cfg):
    groups, unmatched, current = [], [], None
    for clip in clips:
        key = reel_key(clip[0].GetName(), cfg)
        if key is None:
            unmatched.append(clip)
            continue
        if key != current:
            groups.append((key, []))
            current = key
        groups[-1][1].append(clip)
    if unmatched:
        groups.append(("unmatched", unmatched))
    return groups


def build_plan(clips, fps, cfg, quiet=False):
    """Returns (plan, groups). plan is [("pad", frames) | ("clips", [...])]."""
    head = gap_frames_from_seconds(fps, cfg.head_gap_seconds(), quiet)
    mode = resolve_sort_mode(cfg.clip_order)
    use_reel_gaps = bool(cfg.reel_gaps) and mode == "name"
    if cfg.reel_gaps and not use_reel_gaps and not quiet:
        log("  reel gaps need 'Clip name' order, skipped")
    # Groups are useful for markers even when no reel gaps are wanted, so
    # work them out whenever the order is by name.
    groups = group_by_reel(clips, cfg) if mode == "name" else None

    if not use_reel_gaps:
        plan = [("pad", head)] if head > 0 else []
        return plan + [("clips", clips)], groups

    reel = head if cfg.reel_gap_same else \
        gap_frames_from_seconds(fps, cfg.reel_gap_value(), quiet)
    plan = []
    for index, (_, members) in enumerate(groups):
        frames = head if index == 0 else reel
        if frames > 0:
            plan.append(("pad", frames))
        plan.append(("clips", members))
    return plan, groups


# ------------------------------------------------------------- placement


def plan_head_gap(plan):
    return plan[0][1] if plan and plan[0][0] == "pad" else 0


def place_with_record_frame(media_pool, plan, content_end, offset):
    infos, cursor = [], content_end
    for kind, payload in plan:
        if kind == "pad":
            cursor += payload
            continue
        for mpi, s, e in payload:
            infos.append({"mediaPoolItem": mpi, "startFrame": s,
                          "endFrame": e + offset, "trackIndex": 1,
                          "recordFrame": cursor})
            cursor += (e - s + 1)
    return as_list(media_pool.AppendToTimeline(infos))


def run_filler(media_pool, filler, needed, offset):
    f_mpi, f_start, f_max = filler
    items, delivered = [], 0
    while delivered < needed:
        if len(items) >= MAX_FILLER_SEGMENTS:
            raise RuntimeError("gave up after %d filler segments"
                               % MAX_FILLER_SEGMENTS)
        want = min(needed - delivered, f_max - max(offset, 0))
        if want < 1:
            raise RuntimeError("filler source too short for a %d frame gap"
                               % needed)
        info = {"mediaPoolItem": f_mpi, "startFrame": f_start,
                "endFrame": f_start + want - 1 + offset}
        if FILLER_VIDEO_ONLY:
            info["mediaType"] = 1
        got = as_list(media_pool.AppendToTimeline([info]))
        if not got:
            raise RuntimeError("filler append returned nothing (asked %d "
                               "frames)" % want)
        got_len = item_duration(got[0])
        items.extend(got)
        delivered += got_len
        if got_len != want:
            return items, delivered, want - got_len
    return items, delivered, 0


def pad(media_pool, timeline, filler, needed, offset):
    """Insert `needed` frames of filler, recalibrating if the build differs."""
    for attempt in range(1, MAX_CALIBRATION_TRIES + 1):
        items, delivered, mismatch = run_filler(
            media_pool, filler, needed, offset)
        if mismatch == 0 and delivered == needed:
            return items, offset
        if items:
            timeline.DeleteClips(items, False)
        log("  filler came back %d frames off at offset %d, retrying"
            % (mismatch, offset))
        offset += mismatch
        if abs(offset) > 2:
            raise RuntimeError("calibration ran away, offset %d" % offset)
        del attempt
    raise RuntimeError("could not calibrate clip length")


def place_with_filler(media_pool, timeline, plan, all_clips):
    filler_mpi, f_start, f_end = max(all_clips, key=lambda c: c[2] - c[1])
    filler = (filler_mpi, f_start, f_end - f_start + 1)
    log("  filler source: %s (%d frames)" % (filler_mpi.GetName(), filler[2]))

    offset = int(FRAME_OFFSET)
    filler_items, appended_all, landings = [], [], []

    for kind, payload in plan:
        if kind == "pad":
            if payload <= 0:
                continue
            items, offset = pad(media_pool, timeline, filler, payload, offset)
            filler_items.extend(items)
            continue
        expected = timeline_content_end(timeline)
        infos = [{"mediaPoolItem": m, "startFrame": s, "endFrame": e + offset}
                 for m, s, e in payload]
        appended = as_list(media_pool.AppendToTimeline(infos))
        if not appended:
            raise RuntimeError("AppendToTimeline returned nothing")
        appended_all.extend(appended)
        landings.append((expected, appended[0]))
        for (mpi, s, e), item in zip(payload, appended):
            want, got = e - s + 1, item_duration(item)
            if got != want:
                log("  WARNING: %s appended as %d frames, source is %d"
                    % (mpi.GetName(), got, want))

    if filler_items:
        ok = timeline.DeleteClips(filler_items, False)  # False = no ripple
        log("  removed %d filler item(s): %s" % (len(filler_items), ok))
    if offset != FRAME_OFFSET:
        log("  NOTE: this build needed endFrame offset %d, not %d"
            % (offset, FRAME_OFFSET))
    return appended_all, landings


def reel_runs(items, cfg):
    """Consecutive runs of appended items sharing a reel key."""
    runs = []
    for item in items:
        key = reel_key(item.GetName(), cfg) or "unmatched"
        if runs and runs[-1][0] == key:
            runs[-1][2] = item
        else:
            runs.append([key, item, item])
    return runs


def add_marker(timeline, frame, colour, name, note, duration):
    """Returns True if the marker was written."""
    offset = int(timeline.GetStartFrame() or 0) if MARKER_FRAME_RELATIVE else 0
    for position in (frame - offset, frame):
        try:
            ok = timeline.AddMarker(position, colour, name, note, duration)
        except Exception:
            ok = False
        if not ok:
            try:
                ok = timeline.AddMarker(position, colour, name, note,
                                        duration, "")
            except Exception:
                ok = False
        if ok:
            if position != frame - offset:
                log("  NOTE: markers needed the absolute frame, not the "
                    "frame relative to the timeline start")
            return True
        if offset == 0:
            break
    return False


def add_reel_markers(timeline, appended, cfg):
    """One marker spanning each reel. Returns a short summary."""
    mapping, _ = marker_maps(cfg.marker_colors)
    written, skipped = 0, []
    for key, first, last in reel_runs(appended, cfg):
        colour = colour_for(key, mapping)
        if colour is None:
            skipped.append("%s (no colour set)" % key)
            continue
        start = int(first.GetStart())
        duration = int(last.GetEnd()) - start
        if add_marker(timeline, start, colour, key, "", duration):
            written += 1
            log("  marker %s %s at %d for %d frames"
                % (key, colour, start, duration))
        else:
            skipped.append("%s (refused, marker already at that frame?)" % key)
    if skipped:
        log("  markers not written: %s" % ", ".join(skipped))
    return written


def matching_audio(timeline, appended):
    """
    Audio items belonging to the clips just appended. AppendToTimeline only
    hands back the video items, so the audio is found by name and start
    frame, falling back to an exact start and end match when the audio item
    carries a different name.
    """
    by_name = {}
    by_span = {}
    for item in appended:
        try:
            start = int(item.GetStart())
            by_name[(item.GetName(), start)] = item
            by_span[(start, int(item.GetEnd()))] = item
        except Exception:
            continue

    found = []
    try:
        count = int(timeline.GetTrackCount("audio") or 0)
    except Exception:
        return found
    for track in range(1, count + 1):
        for item in items_in_track(timeline, "audio", track):
            try:
                start = int(item.GetStart())
                video = by_name.get((item.GetName(), start))
                if video is None:
                    video = by_span.get((start, int(item.GetEnd())))
            except Exception:
                continue
            if video is not None:
                found.append((item, video))
    return found


def colour_appended_clips(timeline, appended, cfg):
    """Colour each appended item, video and audio, to match its reel."""
    _, clips = marker_maps(cfg.marker_colors)

    targets = [(item, item) for item in appended]
    audio = matching_audio(timeline, appended) if COLOUR_AUDIO else []
    targets.extend(audio)

    done, failed, audio_done = 0, 0, 0
    for item, source in targets:
        key = reel_key(source.GetName(), cfg) or "unmatched"
        clip_colour = colour_for(key, clips)
        if clip_colour is None:
            failed += 1
            continue
        try:
            ok = item.SetClipColor(clip_colour)
        except Exception:
            ok = False
        if ok:
            done += 1
            if item is not source:
                audio_done += 1
        else:
            failed += 1
    if audio:
        log("  %d audio item(s) matched, %d coloured"
            % (len(audio), audio_done))
    elif COLOUR_AUDIO:
        log("  no audio items matched the appended clips")
    if failed:
        log("  %d item(s) could not be coloured" % failed)
    return done


# ------------------------------------------------------------- run


def current_page(res):
    """Page name, or None if Resolve will not say."""
    try:
        page = res.GetCurrentPage()
    except Exception:
        return None
    return page if isinstance(page, str) and page else None


def open_page(res, page, why):
    now = current_page(res)
    if now == page:
        return
    try:
        ok = res.OpenPage(page)
    except Exception:
        ok = False
    if ok:
        log("  %s the %s page" % (why, page))
    else:
        log("  could not open the %s page, left on %s" % (page, now))


def finish_on_page(res, cfg, page):
    """Land on the Color page if asked, otherwise go back where we were."""
    if getattr(cfg, "jump_to_colour", False):
        open_page(res, "color", "opened")
        return
    restore_page(res, page)


def restore_page(res, page):
    """Put Resolve back on `page` if something moved it."""
    if not RESTORE_PAGE or not page:
        return
    now = current_page(res)
    if now == page:
        return
    try:
        ok = res.OpenPage(page)
    except Exception:
        ok = False
    if ok:
        log("  returned to the %s page" % page)
    else:
        log("  could not return to the %s page, left on %s" % (page, now))


def gather(cfg):
    """Returns (project, timeline, media_pool, fps, fps_raw, clips)."""
    res = get_resolve()
    if not res:
        raise RuntimeError("no connection to Resolve")
    project = res.GetProjectManager().GetCurrentProject()
    if not project:
        raise RuntimeError("no project open")
    timeline = project.GetCurrentTimeline()
    if not timeline:
        raise RuntimeError("no current timeline")
    media_pool = project.GetMediaPool()
    fps, fps_raw = timeline_fps(timeline)
    clips = usable_clips(media_pool)
    if clips:
        clips = sort_clips(clips, fps, cfg)
    return project, timeline, media_pool, fps, fps_raw, clips


def do_append(cfg):
    res = get_resolve()
    page = current_page(res)
    project, timeline, media_pool, fps, fps_raw, clips = gather(cfg)
    del project
    if not clips:
        raise RuntimeError("select at least one clip in the Media Pool")

    log("timeline: %s  fps: %s" % (timeline.GetName(), fps_raw))
    content_end = timeline_content_end(timeline, verbose=True)
    plan, groups = build_plan(clips, fps, cfg)
    if groups:
        log("reels: %s" % ", ".join("%s (%d)" % (k, len(v))
                                    for k, v in groups))

    if USE_RECORD_FRAME:
        appended = place_with_record_frame(
            media_pool, plan, content_end, int(FRAME_OFFSET))
        landings = []
    else:
        appended, landings = place_with_filler(
            media_pool, timeline, plan, clips)

    bad = 0
    for expected, item in landings:
        actual = int(item.GetStart())
        if actual != expected:
            bad += 1
            log("WARNING: %s landed at %d, expected %d"
                % (item.GetName(), actual, expected))
    for item in appended:
        log("  %s  %d -> %d" % (item.GetName(), int(item.GetStart()),
                                int(item.GetEnd())))
    if bad:
        # A bad landing is not a success: go back where we were rather
        # than jumping to Color, so the error stays in front of you.
        restore_page(res, page)
        return "%d block(s) landed wrong, undo with cmd+Z" % bad

    markers = ""
    if cfg.reel_markers and groups is not None:
        try:
            written = add_reel_markers(timeline, appended, cfg)
            markers = ", %d marker(s)" % written
        except RuntimeError as err:
            markers = ", markers failed: %s" % err
            log("  %s" % err)
    elif cfg.reel_markers:
        log("  reel markers need 'Clip name' order, skipped")

    if cfg.colour_clips and groups is not None:
        try:
            coloured = colour_appended_clips(timeline, appended, cfg)
            markers += ", %d clip(s) coloured" % coloured
        except RuntimeError as err:
            markers += ", clip colours failed: %s" % err
            log("  %s" % err)
    elif cfg.colour_clips:
        log("  clip colouring needs 'Clip name' order, skipped")

    finish_on_page(res, cfg, page)
    return "appended %d clip(s) from frame %d%s" % (
        len(appended), content_end + plan_head_gap(plan), markers)


# ------------------------------------------------------------- gui


def force_relayout(win):
    """
    Showing or hiding a widget does not always re-flow the parent layout,
    which leaves the new field painted over its neighbours until the window
    is resized by hand. Try the documented call, then fall back to nudging
    the geometry, which is what a manual resize does.
    """
    try:
        recalc = getattr(win, "RecalcLayout", None)
        if recalc is not None:
            recalc()
            return True
    except Exception:
        pass
    try:
        geo = list(win.Geometry)
        win.Geometry = [geo[0], geo[1], geo[2], geo[3] + 1]
        win.Geometry = geo
        return True
    except Exception:
        return False


def window_height(cfg, detail_row=False):
    """Height for what is actually on show."""
    height = BASE_HEIGHT
    if cfg.reel_markers or cfg.colour_clips:
        height += BLOCK_CHROME
        height += getattr(cfg, "visible_rows", 1) * CAMERA_ROW_HEIGHT
    if detail_row:
        height += DETAIL_ROW_HEIGHT
    if cfg.show_preview:
        height += PREVIEW_HEIGHT
    return height


def set_window_height(win, cfg, detail_row=False):
    """Resize only when the computed height actually changed."""
    height = window_height(cfg, detail_row)
    if getattr(cfg, "last_height", None) == height:
        return
    cfg.last_height = height
    try:
        geo = list(win.Geometry)
        geo[3] = height
        win.Geometry = geo
    except Exception:
        pass


RUNNING_KEY = "AppendIt.Running"


def already_open(ui, fusion_app):
    """
    Returns an existing window to raise, or None. Resolve runs every script
    inside its own process, so a pid based lock is useless here. The window
    registry is the real check; the Fusion data flag is a backstop for a
    build where FindWindow is missing, and is cleared if no window is found.
    """
    window = None
    try:
        window = ui.FindWindow("AppendItWin")
    except Exception:
        window = None
    if window:
        return window
    try:
        if fusion_app.GetData(RUNNING_KEY):
            fusion_app.SetData(RUNNING_KEY, None)
    except Exception:
        pass
    return None


def mark_running(fusion_app, state):
    try:
        fusion_app.SetData(RUNNING_KEY, True if state else None)
    except Exception:
        pass


def get_ui():
    g = globals()
    fusion_app = g.get("fusion") or g.get("fu")
    if fusion_app is None:
        res = get_resolve()
        fusion_app = res.Fusion() if res else None
    if fusion_app is None:
        raise RuntimeError("no Fusion app object, cannot build the UI")

    manager = fusion_app.UIManager
    if manager is None:
        raise RuntimeError("UIManager is unavailable. It is a Studio "
                           "feature as of Resolve 19.1.")

    bmd_mod = g.get("bmd")
    if bmd_mod is None:
        import DaVinciResolveScript as bmd_mod
    return manager, bmd_mod.UIDispatcher(manager), fusion_app


def vgap(ui, size):
    """Vertical padding, with a fallback if VGap is unavailable."""
    try:
        return ui.VGap(size)
    except Exception:
        return ui.Label({"Text": "", "Weight": 0,
                         "MaximumSize": [0, size]})


def fixed(width, height=None):
    return [width, height if height is not None else FIELD_HEIGHT]


def contrast_text(hex_colour):
    """Black or white, whichever stays readable on that background."""
    try:
        r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#ffffff"
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 \
        else "#ffffff"


def style_pick(itm, key, colour, table):
    """Put a colour on a picker button: its name as text, itself as fill."""
    hex_colour = table.get(colour, "#404040")
    try:
        itm[key].Text = colour
    except Exception:
        return
    try:
        itm[key].StyleSheet = (
            "QPushButton { background-color: %s; color: %s; "
            "border: 1px solid #00000060; border-radius: 3px; }"
            % (hex_colour, contrast_text(hex_colour)))
    except Exception:
        pass          # no stylesheet, the name on the button still reads


def pick_value(itm, key, valid, fallback):
    colour = ""
    try:
        colour = (itm[key].Text or "").strip().title()
    except Exception:
        colour = ""
    return colour if colour in valid else fallback


def camera_cell(ui, index):
    """One camera slot: letter, marker colour button, clip colour button."""
    return [
        ui.LineEdit({"ID": "MarkerLetter%d" % index, "Weight": 0,
                     "MinimumSize": fixed(COL_LETTER),
                     "MaximumSize": fixed(COL_LETTER)}),
        ui.Button({"ID": "MarkerPick%d" % index, "Text": "", "Weight": 0,
                   "MinimumSize": fixed(COL_COMBO),
                   "MaximumSize": fixed(COL_COMBO)}),
        ui.Button({"ID": "ClipPick%d" % index, "Text": "", "Weight": 0,
                   "MinimumSize": fixed(COL_COMBO),
                   "MaximumSize": fixed(COL_COMBO)}),
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(COL_PAD),
                  "MaximumSize": fixed(COL_PAD)}),
    ]


CENTRED = {"AlignHCenter": True, "AlignVCenter": True}


def header_label(ui, text, width):
    attrs = {"Text": text, "Weight": 0,
             "MinimumSize": fixed(width, 20),
             "MaximumSize": fixed(width, 20)}
    try:
        attrs["Alignment"] = dict(CENTRED)
    except Exception:
        pass
    return ui.Label(attrs)


def header_cell(ui):
    """Same four columns, same widths, so the titles sit over the fields."""
    return [
        header_label(ui, "Cam", COL_LETTER),
        header_label(ui, "Marker", COL_COMBO),
        header_label(ui, "Clip", COL_COMBO),
        header_label(ui, "", COL_PAD),
    ]


def colour_rows(ui):
    """Padding, the add and remove buttons, a header, the slots, fallback."""
    rows = [vgap(ui, 4)]
    rows.append(ui.HGroup({"Weight": 0}, [
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(MARKER_LABEL_WIDTH),
                  "MaximumSize": fixed(MARKER_LABEL_WIDTH)}),
        ui.Button({"ID": "AddCameraButton", "Text": "Add cameras",
                   "Weight": 0}),
        ui.Button({"ID": "RemoveCameraButton", "Text": "Remove cameras",
                   "Weight": 0}),
        ui.Label({"ID": "AddCameraNote", "Text": "", "Weight": 1}),
    ]))

    rows.append(ui.HGroup({"Weight": 0}, [
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(MARKER_LABEL_WIDTH, 20),
                  "MaximumSize": fixed(MARKER_LABEL_WIDTH, 20)}),
    ] + header_cell(ui) + header_cell(ui) + [ui.Label({"Weight": 1})]))

    for row in range(1, MARKER_PAIR_ROWS + 1):
        left, right = row * 2 - 1, row * 2
        rows.append(ui.HGroup({"ID": "MarkerRow%d" % row, "Weight": 0,
                               "Hidden": True}, [
            ui.Label({"Text": "", "Weight": 0,
                      "MinimumSize": fixed(MARKER_LABEL_WIDTH),
                      "MaximumSize": fixed(MARKER_LABEL_WIDTH)}),
        ] + camera_cell(ui, left) + camera_cell(ui, right) + [
            ui.Label({"Weight": 1}),
        ]))

    # The row must carry the same number of children as a camera row, not
    # just the same total width: the layout inserts a gap between every
    # child, so four children instead of nine shifts everything after them
    # left by five missing gaps. The checkbox and three spacers stand in for
    # the first camera cell, keeping the column widths identical.
    rows.append(ui.HGroup({"ID": "FallbackRow", "Weight": 0}, [
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(MARKER_LABEL_WIDTH),
                  "MaximumSize": fixed(MARKER_LABEL_WIDTH)}),
        ui.CheckBox({"ID": "UseFallback", "Text": "Any other camera",
                     "Weight": 0,
                     "MinimumSize": fixed(COL_LETTER + COL_COMBO),
                     "MaximumSize": fixed(COL_LETTER + COL_COMBO)}),
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(COL_COMBO // 2),
                  "MaximumSize": fixed(COL_COMBO // 2)}),
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(COL_COMBO - COL_COMBO // 2),
                  "MaximumSize": fixed(COL_COMBO - COL_COMBO // 2)}),
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(COL_PAD),
                  "MaximumSize": fixed(COL_PAD)}),
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(COL_LETTER),
                  "MaximumSize": fixed(COL_LETTER)}),
        ui.Button({"ID": "MarkerPick0", "Text": "", "Weight": 0,
                   "MinimumSize": fixed(COL_COMBO),
                   "MaximumSize": fixed(COL_COMBO)}),
        ui.Button({"ID": "ClipPick0", "Text": "", "Weight": 0,
                   "MinimumSize": fixed(COL_COMBO),
                   "MaximumSize": fixed(COL_COMBO)}),
        ui.Label({"Text": "", "Weight": 0,
                  "MinimumSize": fixed(COL_PAD),
                  "MaximumSize": fixed(COL_PAD)}),
        ui.Label({"Weight": 1}),
    ]))
    rows.append(vgap(ui, 4))
    return rows


def refresh_swatches(itm, index):
    """Re-apply the colour styling to one slot's two buttons."""
    style_pick(itm, "MarkerPick%d" % index,
               pick_value(itm, "MarkerPick%d" % index, MARKER_COLOURS,
                          "Cream"), COLOUR_HEX)
    style_pick(itm, "ClipPick%d" % index,
               pick_value(itm, "ClipPick%d" % index, CLIP_COLOURS,
                          "Beige"), CLIP_COLOUR_HEX)


def fill_colour_rows(itm, cfg):
    """Put the saved mapping into the slots."""
    try:
        pairs = parse_marker_pairs(cfg.marker_colors)
    except RuntimeError:
        pairs = parse_marker_pairs(DEFAULTS["marker_colors"])

    fallback, use_fallback, cameras = ("Cream", "Tan"), False, []
    for letter, marker, clip in pairs:
        if letter == "*":
            fallback, use_fallback = (marker, clip), True
        else:
            cameras.append((letter, marker, clip))

    used_rows = (len(cameras) + 1) // 2
    cfg.visible_rows = max(1, min(used_rows, MARKER_PAIR_ROWS))

    for index in range(1, MARKER_SLOTS + 1):
        if index <= len(cameras):
            letter, marker, clip = cameras[index - 1]
        else:
            letter, marker, clip = "", "Cream", "Tan"
        itm["MarkerLetter%d" % index].Text = letter
        style_pick(itm, "MarkerPick%d" % index, marker, COLOUR_HEX)
        style_pick(itm, "ClipPick%d" % index, clip, CLIP_COLOUR_HEX)

    style_pick(itm, "MarkerPick0", fallback[0], COLOUR_HEX)
    style_pick(itm, "ClipPick0", fallback[1], CLIP_COLOUR_HEX)
    itm["UseFallback"].Checked = use_fallback

    if len(cameras) > MARKER_SLOTS:
        log("only the first %d cameras fit, %s dropped"
            % (MARKER_SLOTS, ", ".join(l for l, _, _ in cameras[MARKER_SLOTS:])))


def fill_next_cameras(itm, row):
    """Prefill a newly revealed row with the next unused camera letters."""
    used = set()
    for index in range(1, MARKER_SLOTS + 1):
        letter = itm["MarkerLetter%d" % index].Text.strip().upper()[:2]
        if letter:
            used.add(letter)
    for slot in (row * 2 - 1, row * 2):
        if itm["MarkerLetter%d" % slot].Text.strip():
            continue
        for letter in CAMERA_LETTERS:
            if letter in used:
                continue
            marker, clip = DEFAULT_CAMERA_COLOURS.get(
                letter, ("Cream", "Tan"))
            itm["MarkerLetter%d" % slot].Text = letter
            style_pick(itm, "MarkerPick%d" % slot, marker, COLOUR_HEX)
            style_pick(itm, "ClipPick%d" % slot, clip, CLIP_COLOUR_HEX)
            used.add(letter)
            break


def read_colour_rows(itm, visible_rows=MARKER_PAIR_ROWS):
    """Visible slots back to the stored string. Empty letters are dropped."""
    slots = min(visible_rows, MARKER_PAIR_ROWS) * 2
    parts = []
    for index in range(1, slots + 1):
        letter = itm["MarkerLetter%d" % index].Text.strip().upper()[:2]
        if not letter:
            continue
        parts.append("%s:%s/%s" % (
            letter,
            pick_value(itm, "MarkerPick%d" % index, MARKER_COLOURS, "Cream"),
            pick_value(itm, "ClipPick%d" % index, CLIP_COLOURS, "Beige")))
    if itm["UseFallback"].Checked:
        parts.append("*:%s/%s" % (
            pick_value(itm, "MarkerPick0", MARKER_COLOURS, "Cream"),
            pick_value(itm, "ClipPick0", CLIP_COLOURS, "Beige")))
    if not parts:
        raise RuntimeError("set at least one camera colour, or switch on "
                           "'Any other camera'")
    text = ", ".join(parts)
    parse_marker_pairs(text)        # raises on a duplicate letter
    return text


def palette_position(win, itm, key, row_id):
    """
    Screen position for the popup: under the field that was clicked.
    A widget's geometry is relative to its parent, so the offsets are summed
    up the chain we have IDs for. Approximate, but consistent.
    """
    x, y = 340, 340
    try:
        geo = list(win.Geometry)
        x, y = int(geo[0]), int(geo[1])
    except Exception:
        return [x, y]
    for widget_id in ("MarkerColorBox", row_id, key):
        try:
            geo = list(itm[widget_id].Geometry)
            x += int(geo[0])
            y += int(geo[1])
        except Exception:
            pass
    return [x, y + FIELD_HEIGHT + 6]


def row_id_for(index):
    if index == 0:
        return "FallbackRow"
    return "MarkerRow%d" % ((index + 1) // 2)


def palette_grid(ui, kind, colours):
    cell = palette_cell()
    rows = []
    for first in range(0, len(colours), PALETTE_COLS):
        rows.append(ui.HGroup({"Weight": 0}, [
            ui.Button({"ID": "%s_%s" % (kind, name), "Text": name,
                       "Weight": 0,
                       "MinimumSize": list(cell),
                       "MaximumSize": list(cell)})
            for name in colours[first:first + PALETTE_COLS]
        ]))
    return rows


def picker_size():
    cell = palette_cell()
    width = PALETTE_COLS * (cell[0] + 6) + 16
    grid = (16 // PALETTE_COLS) * (cell[1] + 6)
    return [width, grid * 2 + 110]


def build_picker(ui, disp):
    """One window with the marker palette above the clip palette."""
    size = picker_size()
    win = disp.AddWindow({
        "ID": "ColourPicker",
        "WindowTitle": "Camera colours",
        "Geometry": [340, 340, size[0], size[1]],
    }, ui.VGroup({"Weight": 0}, [
        ui.Label({"ID": "PickerTitle", "Text": "", "Weight": 0,
                  "MinimumSize": [0, 22], "MaximumSize": [4000, 22]}),
        ui.Label({"Text": "Marker", "Weight": 0,
                  "MinimumSize": [0, 18], "MaximumSize": [4000, 18]}),
    ] + palette_grid(ui, "MK", MARKER_COLOURS) + [
        ui.Label({"Text": "Clip", "Weight": 0,
                  "MinimumSize": [0, 18], "MaximumSize": [4000, 18]}),
    ] + palette_grid(ui, "CL", CLIP_COLOURS) + [
        ui.HGroup({"Weight": 0}, [
            ui.Label({"Weight": 1}),
            ui.Button({"ID": "PickerDone", "Text": "Done", "Weight": 0}),
        ]),
    ]))
    itm = win.GetItems()
    for name in MARKER_COLOURS:
        style_pick(itm, "MK_%s" % name, name, COLOUR_HEX)
    for name in CLIP_COLOURS:
        style_pick(itm, "CL_%s" % name, name, CLIP_COLOUR_HEX)
    return win, itm, size


def build_window(cfg):
    ui, disp, fusion_app = get_ui()
    existing = already_open(ui, fusion_app)
    if existing is not None:
        return None, None, existing, None, None, fusion_app

    sort_values = [key for key, _ in SORT_LABELS]
    mode = resolve_sort_mode(cfg.clip_order)

    win = disp.AddWindow({
        "ID": "AppendItWin",
        "WindowTitle": "Append It",
        "Geometry": [200, 200, WINDOW_WIDTH, window_height(cfg)],
        "Events": {"KeyPress": True, "MousePress": True},
    }, ui.VGroup([
        ui.HGroup({"Weight": 0}, [
            ui.Label({"Text": "Gap before the clips (seconds)",
                      "Weight": 0, "MinimumSize": label_min()}),
            ui.LineEdit({"ID": "GapSeconds", "Text": "%g" % cfg.gap_seconds,
                         "MinimumSize": field_min(),
                         "MaximumSize": field_max()}),
            ui.Label({"ID": "GapReadout", "Text": "", "Weight": 1}),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.Label({"Text": "Sort clips by", "Weight": 0,
                      "MinimumSize": label_min()}),
            ui.ComboBox({"ID": "ClipOrder", "MaximumSize": [200, 30]}),
            ui.CheckBox({"ID": "ClipOrderReverse", "Text": "Reverse",
                         "Checked": bool(cfg.clip_order_reverse),
                         "Weight": 0}),
            ui.Label({"Weight": 1}),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.CheckBox({"ID": "ReelGaps", "Text": "Add gap between reels",
                         "Checked": bool(cfg.reel_gaps), "Weight": 0,
                         "MinimumSize": [180, FIELD_HEIGHT],
                         "MaximumSize": [180, FIELD_HEIGHT]}),
            ui.CheckBox({"ID": "ReelSeparate",
                         "Text": "Same gap as head gap",
                         "Checked": bool(cfg.reel_gap_same), "Weight": 0,
                         "MinimumSize": [180, FIELD_HEIGHT],
                         "MaximumSize": [180, FIELD_HEIGHT]}),
            ui.HGroup({"ID": "ReelGapBox", "Weight": 0, "Hidden": True}, [
                ui.LineEdit({"ID": "ReelGapSeconds",
                             "Text": "%g" % cfg.reel_gap_seconds,
                             "Weight": 0,
                             "MinimumSize": [70, FIELD_HEIGHT],
                             "MaximumSize": [70, FIELD_HEIGHT]}),
                ui.Label({"Text": "seconds", "Weight": 0,
                          "MinimumSize": [70, FIELD_HEIGHT]}),
            ]),
            ui.Label({"ID": "ReelGapsNote", "Text": "", "Weight": 1}),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.Label({"Text": "Reel naming detection by", "Weight": 0,
                      "MinimumSize": label_min()}),
            ui.ComboBox({"ID": "ReelPreset", "Weight": 0,
                         "MinimumSize": [300, FIELD_HEIGHT],
                         "MaximumSize": [300, FIELD_HEIGHT]}),
            ui.Label({"Weight": 1}),
        ]),
        ui.HGroup({"ID": "ReelDetailRow", "Weight": 0, "Hidden": True}, [
            ui.Label({"Text": "", "Weight": 0,
                      "MinimumSize": label_min()}),
            ui.HGroup({"ID": "ReelCustomBox", "Weight": 1,
                       "Hidden": True}, [
                ui.LineEdit({"ID": "ReelPattern", "Text": cfg.reel_pattern}),
            ]),
            ui.HGroup({"ID": "ReelCharsBox", "Weight": 1,
                       "Hidden": True}, [
                ui.LineEdit({"ID": "ReelChars", "Text": str(cfg.reel_chars),
                             "Weight": 1,
                             "MaximumSize": field_max()}),
                ui.Label({"Text": "characters", "Weight": 1}),
            ]),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.CheckBox({"ID": "ReelMarkers",
                         "Text": "Coloured marker per reel",
                         "Checked": bool(cfg.reel_markers), "Weight": 0}),
            ui.Label({"ID": "ReelMarkersNote", "Text": "", "Weight": 1}),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.CheckBox({"ID": "ColourClips",
                         "Text": "Colour the clips per camera",
                         "Checked": bool(cfg.colour_clips), "Weight": 0}),
            ui.Label({"ID": "ColourClipsNote", "Text": "", "Weight": 1}),
        ]),
        ui.VGroup({"ID": "MarkerColorBox", "Weight": 0, "Hidden": True},
                  colour_rows(ui)),
        ui.HGroup({"Weight": 0}, [
            ui.CheckBox({"ID": "JumpToColour",
                         "Text": "Jump to the Color page when finished",
                         "Checked": bool(cfg.jump_to_colour), "Weight": 0}),
            ui.Label({"Weight": 1}),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.CheckBox({"ID": "ShowPreview", "Text": "Show preview",
                         "Checked": bool(cfg.show_preview), "Weight": 0}),
            ui.Label({"Weight": 1}),
        ]),
        ui.VGroup({"ID": "PreviewBox", "Weight": 1, "Hidden": True}, [
            ui.Tree({"ID": "ClipTree", "ColumnCount": 4, "Weight": 1,
                     "SortingEnabled": False,
                     "AlternatingRowColors": True}),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.Label({"ID": "SelectionSummary", "Text": "", "Weight": 1}),
            ui.HGroup({"ID": "RefreshBox", "Weight": 0, "Hidden": True}, [
                ui.Button({"ID": "RefreshButton", "Text": "Refresh",
                           "Weight": 0}),
            ]),
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.Label({"Text": "v%s" % VERSION, "Weight": 0,
                      "MinimumSize": [56, FIELD_HEIGHT],
                      "MaximumSize": [56, FIELD_HEIGHT]}),
            ui.Label({"ID": "StatusLine", "Text": "", "Weight": 1}),
            ui.Button({"ID": "CloseButton", "Text": "Close", "Weight": 0}),
            ui.Button({"ID": "AppendButton", "Text": "Append", "Weight": 0,
                       "Default": True}),
        ]),
    ]))

    itm = win.GetItems()
    for _, label in SORT_LABELS:
        itm["ClipOrder"].AddItem(label)
    itm["ClipOrder"].CurrentIndex = sort_values.index(mode)
    for _, label, _ in REEL_PRESETS:
        itm["ReelPreset"].AddItem(label)
    itm["ReelPreset"].CurrentIndex = PRESET_KEYS.index(cfg.preset_key())
    fill_colour_rows(itm, cfg)
    itm["ClipTree"].SetHeaderLabels(["Name", "Reel", "Frames", "Duration"])
    for index, width in enumerate((280, 90, 80, 110)):
        itm["ClipTree"].ColumnWidth[index] = width
    return ui, disp, win, itm, sort_values, fusion_app


def read_gui(itm, cfg, sort_values):
    cfg.clip_order = sort_values[itm["ClipOrder"].CurrentIndex]
    cfg.clip_order_reverse = bool(itm["ClipOrderReverse"].Checked)
    cfg.reel_gaps = bool(itm["ReelGaps"].Checked)
    cfg.reel_gap_same = bool(itm["ReelSeparate"].Checked)
    cfg.reel_markers = bool(itm["ReelMarkers"].Checked)
    cfg.colour_clips = bool(itm["ColourClips"].Checked)
    cfg.show_preview = bool(itm["ShowPreview"].Checked)
    cfg.jump_to_colour = bool(itm["JumpToColour"].Checked)
    cfg.marker_colors = read_colour_rows(itm, getattr(cfg, "visible_rows", 1))
    cfg.reel_preset = PRESET_KEYS[itm["ReelPreset"].CurrentIndex]
    cfg.reel_pattern = itm["ReelPattern"].Text
    if cfg.preset_key() == "first_n":
        try:
            count = int(itm["ReelChars"].Text.strip())
        except ValueError:
            raise RuntimeError("character count is not a whole number")
        if count < 1:
            raise RuntimeError("character count must be at least 1")
        cfg.reel_chars = count
    for field, attr in (("GapSeconds", "gap_seconds"),
                        ("ReelGapSeconds", "reel_gap_seconds")):
        try:
            value = float(itm[field].Text.strip().replace(",", "."))
        except ValueError:
            raise RuntimeError("%s is not a number"
                               % ("Gap" if field == "GapSeconds"
                                  else "Reel gap"))
        if value < 0:
            raise RuntimeError("gap cannot be negative")
        setattr(cfg, attr, value)
    return cfg


def set_status(itm, text, error=False):
    """Bottom line of the window. Errors in red so they are not missed."""
    try:
        itm["StatusLine"].Text = text or ""
    except Exception:
        return
    try:
        itm["StatusLine"].StyleSheet = "color: #ff6161;" if error else ""
    except Exception:
        pass


def refresh(win, itm, cfg, sort_values, relayout=False):
    """Rebuild the tree from the current Media Pool selection."""
    tree = itm["ClipTree"]
    tree.Clear()
    set_status(itm, "")

    try:
        read_gui(itm, cfg, sort_values)
    except RuntimeError as err:
        set_status(itm, str(err), error=True)
        itm["SelectionSummary"].Text = ""
        return False

    mode = resolve_sort_mode(cfg.clip_order)
    reels_possible = mode == "name"
    itm["ReelGaps"].Enabled = reels_possible
    itm["ReelGapsNote"].Text = "" if reels_possible else \
        "needs Clip name order"
    if not reels_possible:
        itm["ReelMarkersNote"].Text = "needs Clip name order"
    elif cfg.reel_markers:
        try:
            marker_maps(cfg.marker_colors)
            itm["ReelMarkersNote"].Text = ""
        except RuntimeError as err:
            itm["ReelMarkersNote"].Text = str(err)
    else:
        itm["ReelMarkersNote"].Text = ""
    reels_on = reels_possible and cfg.reel_gaps
    itm["ReelSeparate"].Enabled = reels_on
    preset = cfg.preset_key()
    itm["ReelPreset"].Enabled = reels_on
    itm["ReelPattern"].Enabled = reels_on
    itm["ReelChars"].Enabled = reels_on

    itm["ReelMarkers"].Enabled = reels_possible
    itm["ColourClips"].Enabled = reels_possible
    itm["UseFallback"].Enabled = reels_possible
    colours_used = reels_possible and (cfg.reel_markers or cfg.colour_clips)
    visible_rows = getattr(cfg, "visible_rows", 1)
    fallback_on = colours_used and bool(itm["UseFallback"].Checked)
    for index in range(0, MARKER_SLOTS + 1):
        live = colours_used if index else fallback_on
        itm["MarkerPick%d" % index].Enabled = live
        itm["ClipPick%d" % index].Enabled = live
        if index:
            itm["MarkerLetter%d" % index].Enabled = colours_used
        refresh_swatches(itm, index)
    itm["AddCameraButton"].Enabled = \
        colours_used and visible_rows < MARKER_PAIR_ROWS
    itm["RemoveCameraButton"].Enabled = colours_used and visible_rows > 1
    itm["AddCameraNote"].Text = "" if visible_rows < MARKER_PAIR_ROWS else \
        "%d cameras is the limit" % MARKER_SLOTS
    wanted = {
        "ReelGapBox": not cfg.reel_gap_same,
        "ReelCustomBox": preset == "custom",
        "ReelCharsBox": preset == "first_n",
        "MarkerColorBox": cfg.reel_markers or cfg.colour_clips,
        "PreviewBox": cfg.show_preview,
        "RefreshBox": cfg.show_preview,
        "ReelDetailRow": preset in ("custom", "first_n"),
    }

    for row in range(1, MARKER_PAIR_ROWS + 1):
        wanted["MarkerRow%d" % row] = row <= visible_rows
    changed = relayout
    for name, visible in wanted.items():
        if bool(itm[name].Hidden) == bool(visible):
            itm[name].Hidden = not visible
            changed = True
    if relayout:
        # A box that was created hidden only takes up space after a real
        # hidden to visible transition, so drive one deliberately.
        for name, visible in wanted.items():
            if visible:
                itm[name].Hidden = True
                itm[name].Hidden = False
    if changed:
        force_relayout(win)
    set_window_height(win, cfg, preset in ("custom", "first_n"))
    itm["ReelGapSeconds"].Enabled = reels_on and not cfg.reel_gap_same

    try:
        _, timeline, _, fps, fps_raw, clips = gather(cfg)
    except RuntimeError as err:
        itm["GapReadout"].Text = ""
        itm["SelectionSummary"].Text = ""
        set_status(itm, str(err), error=True)
        return False

    head = gap_frames_from_seconds(fps, cfg.head_gap_seconds(), quiet=True)
    itm["GapReadout"].Text = "%d frames at %s fps, %.4f s" % (
        head, fps_raw, head / fps)

    if not clips:
        itm["SelectionSummary"].Text = "nothing selected in the Media Pool"
        return False

    try:
        plan, groups = build_plan(clips, fps, cfg, quiet=True)
    except RuntimeError as err:
        set_status(itm, str(err), error=True)
        return False

    mapping = None
    if cfg.reel_markers:
        try:
            mapping, _ = marker_maps(cfg.marker_colors)
        except RuntimeError:
            mapping = None

    total = 0
    seen = set()
    fill_tree = bool(cfg.show_preview)
    for kind, payload in plan:
        if kind == "pad":
            total += payload
            if not fill_tree:
                continue
            row = tree.NewItem()
            row.Text[0] = "gap"
            row.Text[2] = str(payload)
            row.Text[3] = frames_to_tc(payload, fps)
            tree.AddTopLevelItem(row)
            continue
        for mpi, s, e in payload:
            frames = e - s + 1
            total += frames
            if not fill_tree:
                continue
            row = tree.NewItem()
            row.Text[0] = mpi.GetName()
            key = reel_key(mpi.GetName(), cfg) or ""
            row.Text[1] = key
            if mapping is not None and key and key not in seen:
                seen.add(key)
                colour = colour_for(key, mapping)
                if colour:
                    row.Text[1] = "%s  %s" % (key, colour)
            row.Text[2] = str(frames)
            row.Text[3] = frames_to_tc(frames, fps)
            tree.AddTopLevelItem(row)

    reel_count = len(groups) if groups else 0
    unmatched = 0
    if groups and groups[-1][0] == "unmatched":
        unmatched = len(groups[-1][1])
    reels = ""
    if reel_count:
        reels = ", %d reel(s)" % reel_count
        if unmatched:
            reels += " incl. %d unmatched" % unmatched
    itm["SelectionSummary"].Text = "%d clip(s)%s, %s added to %s" % (
        len(clips), reels, frames_to_tc(total, fps), timeline.GetName())
    return True


def run_gui():
    cfg = load_settings()
    ui, disp, win, itm, sort_values, fusion_app = build_window(cfg)
    if disp is None:
        log("already open, raising the existing window")
        try:
            win.Show()
            win.Raise()
        except Exception:
            pass
        return
    mark_running(fusion_app, True)
    pick_win, pick_itm, pick_size = build_picker(ui, disp)
    del pick_itm
    target = {"slot": None}

    def on_change(ev):
        del ev
        hide_palettes()
        refresh(win, itm, cfg, sort_values)

    def on_dismiss(ev):
        del ev
        hide_palettes()
        refresh(win, itm, cfg, sort_values)

    def leave_field(ev):
        """Return commits the value and takes focus out of the field."""
        del ev
        hide_palettes()
        refresh(win, itm, cfg, sort_values)
        try:
            itm["AppendButton"].SetFocus("OtherFocusReason")
        except Exception:
            pass

    def hide_palettes():
        try:
            pick_win.Hide()
        except Exception:
            pass
        target["slot"] = None

    def slot_title(index):
        if index == 0:
            return "Any other camera"
        letter = itm["MarkerLetter%d" % index].Text.strip().upper()
        return "Camera %s" % letter if letter else "Camera slot %d" % index

    def make_opener(key, kind):
        del kind
        index = int("".join(c for c in key if c.isdigit()) or 0)

        def opener(ev):
            del ev
            target["slot"] = index
            try:
                pick_win.GetItems()["PickerTitle"].Text = slot_title(index)
            except Exception:
                pass
            where = palette_position(win, itm, key, row_id_for(index))
            try:
                # Size comes from what the layout was built with. Reading it
                # back before the window has been shown returns zeros.
                pick_win.Geometry = [where[0], where[1],
                                     pick_size[0], pick_size[1]]
            except Exception:
                pass
            pick_win.Show()
        return opener

    def make_chooser(colour, palette):
        marker = palette is MARKER_COLOURS
        table = COLOUR_HEX if marker else CLIP_COLOUR_HEX
        field = "MarkerPick%d" if marker else "ClipPick%d"

        def chooser(ev):
            del ev
            slot = target["slot"]
            if slot is None:
                return
            # The picker stays open so both colours can be set in one visit.
            style_pick(itm, field % slot, colour, table)
            refresh(win, itm, cfg, sort_values)
        return chooser

    def on_append(ev):
        del ev
        hide_palettes()
        if not refresh(win, itm, cfg, sort_values):
            if not (itm["StatusLine"].Text or "").strip():
                set_status(itm, "nothing to append", error=True)
            return
        itm["AppendButton"].Enabled = False
        set_status(itm, "working")
        failed = False
        page = current_page(get_resolve())
        try:
            message = do_append(cfg)
        except Exception as err:
            failed = True
            message = "failed: %s" % err
            log(message)
            try:
                restore_page(get_resolve(), page)
            except Exception:
                pass
        itm["AppendButton"].Enabled = True
        set_status(itm, message, error=failed)
        save_settings(cfg)
        if failed:
            refresh(win, itm, cfg, sort_values)
            return
        close_window()

    def close_window():
        hide_palettes()
        try:
            read_gui(itm, cfg, sort_values)
            save_settings(cfg)
        except RuntimeError:
            pass
        disp.ExitLoop()

    def on_add_camera(ev):
        del ev
        hide_palettes()
        current = getattr(cfg, "visible_rows", 1)
        if current >= MARKER_PAIR_ROWS:
            return
        cfg.visible_rows = current + 1
        fill_next_cameras(itm, current + 1)
        refresh(win, itm, cfg, sort_values, relayout=True)

    def on_remove_camera(ev):
        del ev
        hide_palettes()
        current = getattr(cfg, "visible_rows", 1)
        if current <= 1:
            return
        for slot in (current * 2 - 1, current * 2):
            itm["MarkerLetter%d" % slot].Text = ""
        cfg.visible_rows = current - 1
        refresh(win, itm, cfg, sort_values, relayout=True)

    def on_close(ev):
        del ev
        close_window()

    def on_key(ev):
        """Escape closes. Qt passes unhandled keys up from the line edits."""
        key = None
        if isinstance(ev, dict):
            key = ev.get("Key", ev.get("key"))
        else:
            key = getattr(ev, "Key", None)
        if key in (KEY_ESCAPE, "Escape"):
            if target["slot"] is not None:
                hide_palettes()     # first Escape only closes the palette
                return
            close_window()

    win.On.AppendItWin.Close = on_close
    win.On.AppendItWin.KeyPress = on_key
    try:
        win.On.AppendItWin.MousePress = on_dismiss
    except Exception:
        pass          # no such event on this build, the handlers above cover it
    win.On.CloseButton.Clicked = on_close
    win.On.AppendButton.Clicked = on_append
    win.On.RefreshButton.Clicked = on_change
    win.On.AddCameraButton.Clicked = on_add_camera
    win.On.RemoveCameraButton.Clicked = on_remove_camera
    win.On.ClipOrder.CurrentIndexChanged = on_change
    win.On.ClipOrderReverse.Clicked = on_change
    win.On.ReelGaps.Clicked = on_change
    win.On.ReelSeparate.Clicked = on_change
    win.On.GapSeconds.TextChanged = on_change
    win.On.ReelGapSeconds.TextChanged = on_change
    for field in ("GapSeconds", "ReelGapSeconds", "ReelPattern", "ReelChars"):
        for event in ("ReturnPressed", "EditingFinished"):
            try:
                setattr(getattr(win.On, field), event, leave_field)
            except Exception:
                pass          # not every build exposes both
    win.On.ReelPattern.TextChanged = on_change
    win.On.ReelChars.TextChanged = on_change
    win.On.ReelMarkers.Clicked = on_change
    win.On.ColourClips.Clicked = on_change
    win.On.UseFallback.Clicked = on_change
    win.On.ShowPreview.Clicked = on_change
    win.On.JumpToColour.Clicked = on_change
    # Dynamic event binding for the camera grid and the two palettes.
    try:
        for index in range(0, MARKER_SLOTS + 1):
            setattr(getattr(win.On, "MarkerPick%d" % index), "Clicked",
                    make_opener("MarkerPick%d" % index, "MK"))
            setattr(getattr(win.On, "ClipPick%d" % index), "Clicked",
                    make_opener("ClipPick%d" % index, "CL"))
            if index:
                setattr(getattr(win.On, "MarkerLetter%d" % index),
                        "TextChanged", on_change)
        for name in MARKER_COLOURS:
            setattr(getattr(pick_win.On, "MK_%s" % name), "Clicked",
                    make_chooser(name, MARKER_COLOURS))
        for name in CLIP_COLOURS:
            setattr(getattr(pick_win.On, "CL_%s" % name), "Clicked",
                    make_chooser(name, CLIP_COLOURS))
        pick_win.On.PickerDone.Clicked = on_dismiss
        pick_win.On.ColourPicker.Close = on_dismiss
    except Exception as err:
        log("could not bind the colour picker events: %s" % err)
    win.On.ReelPreset.CurrentIndexChanged = on_change

    refresh(win, itm, cfg, sort_values)
    win.Show()
    # The row layout is settled before the window exists, so a box created
    # visible beside a hidden sibling gets no space. Re-apply now that it is
    # realised, which is the same path a manual toggle takes.
    refresh(win, itm, cfg, sort_values, relayout=True)
    try:
        itm["AppendButton"].SetFocus("OtherFocusReason")
    except Exception:
        pass
    disp.RunLoop()
    win.Hide()
    mark_running(fusion_app, False)


def main():
    if SHOW_GUI:
        run_gui()
        return
    cfg = load_settings(verbose=True)
    log("running headless with:")
    for key in sorted(cfg.as_dict()):
        value = getattr(cfg, key)
        if key == "reel_pattern" and cfg.preset_key() != "custom":
            continue          # unused unless the custom preset is selected
        if key in ("reel_chars",) and cfg.preset_key() != "first_n":
            continue
        if key in ("reel_gap_seconds",) and cfg.reel_gap_same:
            continue
        log("  %s: %r" % (key, value))
    log(do_append(cfg))


if __name__ == "__main__":
    main()
