# Append It

A DaVinci Resolve script that appends the clips selected in the Media Pool to
the end of the current timeline, leaving a timed gap before them, and
optionally a gap between reels, a coloured marker per reel, and a clip colour
per camera.

Built for dailies and assembly work, where new camera rolls get dropped onto
the end of a working timeline and need to stay visually separated from what
is already there.

Generated with Claude.

Don't hesitate to reach out for bugs and feature requests.

<img src="docs/Append It_1.jpg" alt="The Append It window" width="570">
<img src="docs/Append It_2.jpg" alt="The Append It window" width="570">

## Requirements

DaVinci Resolve **Studio** 21.1 or later. 

Tested on Studio 21.1, macOS. It should work on Windows and Linux but has not
been tested there.

## Install

Copy `append_it_V1.0.py` into your Resolve scripts folder:

- macOS: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/`
- Windows: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\`
- Linux: `~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/`

It then appears under Workflow > Scripts. Restart Resolve if it does not.

## Use

Select the clips you want in the Media Pool, open the script, set the gap and
press Append. Enter appends, Escape closes.

### Gap

The gap is given in seconds and converted using the timeline frame rate, so it
stays correct on 23.976 and 29.97 projects. The readout next to the field
shows the resulting frame count and the real duration, since 30 seconds at
23.976 is 719 frames, or 29.9883 s. A gap of zero is allowed and appends the
clips straight onto the end.

The gap is measured from the last frame of any clip on any track, not from the
end of the video track you are appending to.

### Sorting and reels

Clips can be appended in Media Pool order, by clip name, by source timecode or
by duration. Note that Media Pool order is not the order you clicked, as the
API does not expose selection order.

Reel detection only works in clip name order, because any other order can
scatter a reel through the sequence. Five naming schemes are offered, from
`A001` and `A_0001` style camera plus reel numbering through to a custom
regular expression. Clips that match nothing are grouped together at the end.

### Markers and colours

With reel detection active you can add one timeline marker spanning each reel,
named with the reel, and colour the appended clips per camera. Audio items are
coloured along with their video.

Marker colours and clip colours are two different palettes in Resolve and only
five names appear in both, so each camera carries a colour for each. Colours
are chosen from a popup grid showing the actual colours. Up to sixteen cameras
can be configured, with a fallback for anything unlisted that can be switched
off if you want unknown cameras left alone.

See `resolve_colour_reference.md` for the measured hex values of both palettes
and the standard camera letter colours they are matched against.

### Settings

Everything except the preview is remembered in `append_it_settings.json`,
written next to the script. The file is per user, not per project.

## How it places clips

Worth knowing if you read the code and wonder why it is not simpler.

`AppendToTimeline` accepts a `recordFrame` to place a clip at an exact frame,
which would make the gap trivial. On Studio 21.0.4.5 that path produced
timelines that read back correctly through the API but rendered as a near
empty stub, so it is not used. Instead the script appends a temporary filler
clip to push the append point out, appends the real clips, then deletes the
filler with ripple off, leaving a true gap.

The `endFrame` in a clipInfo dict is exclusive, so a clip's length is
`endFrame - startFrame`. The script compensates, and recalibrates itself
against the first filler segment if a future build changes that.

## Limitations

There is no undo in the Resolve API and no way to group operations into a
single undo step, so reversing an append takes a dozen presses of cmd+Z.

Media Pool selection order is not available, so the sort order has to be
chosen explicitly.

Full source length means the clip's Start and End properties, so for a subclip
that is the subclip range, not the whole file.

## Licence

MIT
