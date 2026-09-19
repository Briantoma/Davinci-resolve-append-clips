# Resolve colour reference

Reference table for Append It. The camera mapping below is the one the script ships as its defaults, in `DEFAULT_CAMERA_COLOURS`.

Measured from screenshots of the Resolve 21.1 colour menus on macOS, sampled at the centre of each swatch with a median over a 7 by 7 box. The screenshots are JPEG, so values are accurate to a few units, not exact.

Two things worth knowing before using this table. The marker colour named Yellow is orange, #fd9800; the actual yellow marker is Lemon. And the two palettes share five names, Blue, Green, Yellow, Purple and Pink, but none of those five is the same colour in both.

## Marker colours

| Name | Hex | RGB |
|---|---|---|
| Blue | `#0281ec` | 2, 129, 236 |
| Cyan | `#01d2d2` | 1, 210, 210 |
| Green | `#01af00` | 1, 175, 0 |
| Yellow | `#fd9800` | 253, 152, 0 |
| Red | `#f60100` | 246, 1, 0 |
| Pink | `#ff24ce` | 255, 36, 206 |
| Purple | `#9d00ff` | 157, 0, 255 |
| Fuchsia | `#cf136f` | 207, 19, 111 |
| Rose | `#ff9ab9` | 255, 154, 185 |
| Lavender | `#a493ca` | 164, 147, 202 |
| Sky | `#76e5fe` | 118, 229, 254 |
| Mint | `#3edc04` | 62, 220, 4 |
| Lemon | `#d7e938` | 215, 233, 56 |
| Sand | `#c68e54` | 198, 142, 84 |
| Cocoa | `#684e41` | 104, 78, 65 |
| Cream | `#f0e9df` | 240, 233, 223 |

## Clip colours

| Name | Hex | RGB |
|---|---|---|
| Orange | `#fb6400` | 251, 100, 0 |
| Apricot | `#ffa302` | 255, 163, 2 |
| Yellow | `#dbab02` | 219, 171, 2 |
| Lime | `#93c801` | 147, 200, 1 |
| Olive | `#499b00` | 73, 155, 0 |
| Green | `#18915f` | 24, 145, 95 |
| Teal | `#019b9c` | 1, 155, 156 |
| Navy | `#005379` | 0, 83, 121 |
| Blue | `#3077a4` | 48, 119, 164 |
| Purple | `#a16fa2` | 161, 111, 162 |
| Violet | `#e34a92` | 227, 74, 146 |
| Pink | `#f787b7` | 247, 135, 183 |
| Tan | `#bab093` | 186, 176, 147 |
| Beige | `#ca9f77` | 202, 159, 119 |
| Brown | `#a16303` | 161, 99, 3 |
| Chocolate | `#93583c` | 147, 88, 60 |

## Camera letter colours

Sampled from the supplied swatches, with the nearest Resolve equivalents computed as CIE76 distance in Lab, then adjusted by eye, and finally adjusted again in use. C takes Lemon rather than the marker called Yellow, because that one is orange.

| Cam | Colour | Hex | Marker | Clip |
|---|---|---|---|---|
| A | red | `#fb0006` | Red | Violet |
| B | blue | `#0a56b2` | Blue | Navy |
| C | yellow | `#fec30a` | Lemon | Yellow |
| D | fluo green | `#48ff46` | Green | Green |
| E | purple | `#68349a` | Purple | Purple |
| F | fluo orange | `#fd8508` | Yellow | Orange |
| G | fluo pink | `#fb0054` | Fuchsia | Violet |
| H | fluo yellow | `#c2ff27` | Lemon | Lime |
| I | fluo cyan | `#27ffc3` | Cyan | Teal |
| J | burgundy | `#800336` | Fuchsia | Chocolate |
| K | baby pink | `#febfc1` | Rose | Pink |
| L | olive drab | `#447128` | Cocoa | Olive |
| M | brown | `#6f2c0d` | Cocoa | Chocolate |
| N | light blue | `#1f9fd1` | Sky | Blue |
| O | light purple | `#ac6ed3` | Lavender | Purple |
| P | cyan | `#2bfafa` | Cyan | Teal |
| any other | | | Cream | Tan |

## Where the palette runs out

Sixteen cameras do not map onto sixteen markers without repeats. Forcing a unique assignment produces worse matches than allowing duplicates: the best unique solution sends purple to brown at a Lab distance of 105, which is not a colour match by any measure. These duplicates are therefore deliberate.

On the marker side, Cocoa covers L and M, Cyan covers I and P, Fuchsia covers G and J, Lemon covers C and H. On the clip side, Chocolate covers J and M, Purple covers E and O, Teal covers I and P, Violet covers A and G.

Three matches are poor and no better option exists. F fluo orange takes marker Yellow, which is the closest thing to orange in the palette at a distance of 11, and it is a good match despite the misleading name. L olive drab has nothing in the marker palette within 45; Cocoa is the least bad. J burgundy sits 30 from Fuchsia, which reads far pinker than burgundy does.

The clip palette handles the warm and earthy cameras much better than the marker palette: Orange, Olive, Brown and Chocolate all exist there, which is why F, L, M and J have good clip matches and poor marker ones.
