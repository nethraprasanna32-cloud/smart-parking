---
version: 1.0
name: Smart Parking
description: "A calm operations dashboard that reads like real parking equipment: guidance signs ('FREE 23'), painted stalls and number plates. Warm paper background (#f5f4f0) or near-black (#111317) in dark mode, flat cards with 1 px borders, IBM Plex Sans with IBM Plex Mono for plates and times. Colour is used only for meaning: green free, amber filling, red full or blocked, blue for the brand and the main action. No gradients, no shadows, no icons."

colors:
  light:
    paper: "#f5f4f0"        # page background
    card: "#ffffff"         # cards, top bar, tables
    sunken: "#efeee9"       # inputs, empty previews, meter track
    line: "#e2e0d9"         # borders, dividers
    line-strong: "#cfccc3"  # control borders, free-bay dashes
    ink: "#16181d"          # text
    muted: "#5f6470"        # secondary text, labels, hints
    blue: "#0b57d0"         # brand, primary button, links, focus, taken bays
    blue-soft: "#e7eefb"
    green: "#16794a"        # free, allowed, came in
    green-soft: "#e4f2ea"
    amber: "#a85d00"        # filling up, warnings, forecast
    amber-soft: "#fbf0df"
    red: "#c0292f"          # full, stolen, blocked, turned away
    red-soft: "#fbe7e7"
  dark:
    paper: "#111317"
    card: "#191c21"
    sunken: "#22252b"
    line: "#2c3037"
    line-strong: "#3b4048"
    ink: "#eceef2"
    muted: "#9aa0ab"
    blue: "#7fa8f5"
    blue-soft: "#1c2840"
    green: "#52c48a"
    green-soft: "#15291f"
    amber: "#e8a54b"
    amber-soft: "#2e2416"
    red: "#f07a7e"
    red-soft: "#33191b"

typography:
  sans: "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
  mono: "'IBM Plex Mono', ui-monospace, Consolas, monospace"
  weights: [400, 500, 600]
  numerals: tabular-nums
  scale:
    sign-number: { size: "clamp(88px, 14vw, 168px)", weight: 600, line-height: 0.95, tracking: "-0.03em" }
    figure: { size: 32px, weight: 600, line-height: 1.15 }
    page-title: { size: 24px, weight: 600, line-height: 1.25 }
    brand: { size: 17px, weight: 600, tracking: "-0.01em" }
    card-title: { size: 15px, weight: 600 }
    body: { size: 15px, weight: 400, line-height: 1.5 }
    button: { size: 14px, weight: 500 }
    small: { size: 13px, weight: 400, color: muted }
    plate: { family: mono, size: 14px, weight: 500, tracking: "0.06em" }
    clock: { family: mono, size: 14px, weight: 500 }

shape:
  radius-card: 6px
  radius-control: 4px
  radius-plate: 3px
  border: "1px solid line"
  shadows: none   # only the toast and the sign-in dialog

spacing:
  base: 4px
  steps: [4, 8, 12, 16, 20, 24, 32, 48]
  card-padding: 20px      # 16px on phones
  grid-gap: 16px
  control-height: 38px
  top-bar-height: 56px
  page-max-width: 1760px
---

# Smart Parking design

## 1. Feel

A piece of parking equipment, not a SaaS template. Someone who has never seen
it should understand it at a glance, and someone 3 m from a projector should
read the free-space number and the latest event. The references are parking
guidance signs, painted bay markings, real number plates and transit
wayfinding.

Five rules carry the whole look:

1. **The number first.** The most important number (free spaces) is the
   biggest thing on screen. Labels explain numbers; numbers never hide in
   sentences.
2. **Colour means something.** Green = free/allowed, amber = filling/needs a
   look, red = full/stolen/blocked, blue = brand and the main action. Anything
   without a meaning is grey. Status is always a word as well as a colour.
3. **Flat and quiet.** Flat surfaces, 1 px borders, no shadows, no gradients,
   no glow, no animation except a brief highlight on new activity rows.
4. **Words, not icons.** "Turned away" in red, not a red dot or an emoji.
5. **Plain language, sentence case.** "Came in", not "ENTRY_EVENT".

## 2. Colour

- The page is warm paper (`paper`), and content sits on white cards (`card`)
  with a 1 px `line` border. In dark mode the same roles map to near-black
  surfaces; nothing else changes.
- Each status colour has a `-soft` tint. Use the tint **only** behind text of
  the same colour: a taken bay (blue on blue-soft), a banner (amber on
  amber-soft).
- Buttons on blue use white text in light mode and `#0d1526` in dark mode.
- Number plates are always black on white with a dark border, even in dark
  mode, because that is what a plate looks like.
- Define colours as CSS variables on `:root`. Redefine them under
  `@media (prefers-color-scheme: dark)` guarded by
  `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`,
  so the user can force either theme.

## 3. Type

- One family, IBM Plex Sans, in three weights (400 body, 500 controls and
  labels, 600 titles and numbers). IBM Plex Mono 500 is only for plates,
  times and codes.
- All numbers use `font-variant-numeric: tabular-nums` so counts don't jitter.
- Hints and secondary lines are 13 px in `muted`. Never go below 13 px.
- Only the sign and the figures row are centred; everything else is
  left-aligned.

## 4. Layout

- Max content width 1760 px, with a shared gutter
  `max(24px, calc((100% - 1760px) / 2 + 24px))` so the top bar, banners and
  content all line up on the same left and right edges.
- The home page is two columns: the main overview on the left
  (`minmax(0, 1fr)`) and a 360–440 px column on the right with live gate
  cameras stacked on top of each other.
- Inside the overview:
  - Row 1: the availability sign (5 parts) beside the lot map (7 parts).
  - Row 2: a figures strip with 4 numbers.
  - Row 3: a chart (7 parts) beside the latest-activity list (5 parts).
- Breakpoints:
  - At 1280 px or less, the camera column moves under the overview with the two
    cameras side by side.
  - At 1000 px or less, everything is one column and the figures go 2 by 2.
  - At 720 px or less, the gutter is 16 px and inputs and buttons go full width.
- It must work at 360 px wide with no horizontal scroll.

## 5. Components

**Top bar**: 56 px, `card` background, bottom border. The name (text only,
17 px/600) on the left, then page tabs. The active tab is `ink` with a 2 px
blue underline; the others are `muted`. On the right: the connection status
(green "Online" / red), a mono clock and a secondary **Present** button. It
stays at the top when scrolling.

**Availability sign**: a centred card: the label "Free spaces", a huge
number, "of N spaces", an 8 px meter (track `sunken`, fill = status colour,
max 360 px wide), and a one-line status ("Plenty of space"). The number,
meter and status share the state colour: green, amber when filling, red when
full.

**Bays (lot map)**: a grid of stalls (`minmax(132px, 1fr)`, 104–124 px tall).
The bay ID is in mono in the top-left corner.
- A free bay is a 1.5 px dashed `line-strong` outline with "Free" in green.
- A taken bay is a solid 1.5 px blue border on `blue-soft`, with the plate
  centred and the time parked underneath.

**Figures strip**: one bordered strip (not separate cards), split by 1 px
vertical rules. Each cell has a 13 px muted label above a 32 px/600 number,
centred. A number goes red only when it's bad (e.g. "Turned away today").

**Cards**: `card` background, 1 px `line` border, 6 px radius, 20 px padding.
The header row has a 15 px/600 title on the left and a link or status word on
the right, baseline-aligned.

**Camera card**: a title and a status word ("Watching" in green, "Camera
off" in muted). Below that:
- a 16:9 preview on `sunken`
- a short muted detail line
- the source picker and buttons (primary **Start**, secondary **Stop** and
  **Try a reading**)
- a barrier row above a top divider: "Barrier" with the last-opened time and
  an **Open barrier** button

**Plate**: mono 14 px/500, letter-spacing 0.06em, `#111` on `#fff`, 1.5 px
`#111` border, 3 px radius, padding `4px 6px 3px`.

**Activity row**: plate | outcome word plus a muted detail line ("Entry gate ·
Parked in A03") | a relative time on the right. Rows are separated by 1 px
`line` dividers. The outcome word is coloured: "Came in" green, "Left" blue,
"Turned away" red, "Seen again" in plain text.

**Buttons**: 38 px tall, 7×14 px padding, 14 px/500, 4 px radius.
- **Primary**: solid blue, used once per area.
- **Secondary**: `card` background with a `line-strong` border, and a
  `sunken` background on hover.
- **Text button**: blue text with no border, for row actions; red text for
  destructive ones, which always ask to confirm.
- **Disabled**: 45% opacity.

**Inputs and selects**: 38 px, `line-strong` border, 4 px radius. On focus the
border turns blue and gets a 1 px blue ring. Plate inputs are mono and
uppercase.

**Segmented control**: joined buttons in one 1 px border. The selected button
is `ink` background with `card` text.

**Banners**: a full-width strip under the top bar, on the gutter.
- Red on `red-soft` when the server is offline.
- Amber on `amber-soft` for warnings, with a Dismiss text button.

**Toast**: a single message at the bottom centre that disappears after 5
seconds. It's one of only two things with a shadow; the other is the sign-in
dialog.

**Chart**: a thin line chart in SVG.
- The series is a 2 px blue line over a `blue-soft` area.
- Capacity is a dashed `muted` line, and grid lines are `line`.
- The forecast is a translucent amber band with an amber dot.
- Axis text is 12 px `muted`.

## 6. Present mode

A full-screen version for a projector or TV, toggled with **Present**, the
`P` key or `?present` in the URL.
- **Hidden:** tabs, banners and every control.
- **Still shown:** the overview and the gate cameras (live view, status and
  last barrier opening), but no source pickers, buttons or forms.
- **Bigger:** the base text goes to 18 px, the sign number to
  `clamp(120px, 16vh, 220px)` and the figures to 44 px. The latest list shows
  4 rows.
- **Corner bar:** a muted clock and an **Exit** button in the top-right,
  which only become fully visible on hover.

## 7. Writing

- Labels name things ("Number of parking spaces"); buttons say what happens
  ("Car came in", "Open barrier").
- Empty states say what to do next ("Nothing yet. Press Try a reading on a
  gate camera.").
- Errors say what went wrong and what to try, in one sentence.
- Times are relative when recent ("4 min ago"), with the exact time in the
  tooltip.

## 8. Accessibility

- Text contrast is at least 4.5:1 in both themes. Status is never shown by
  colour alone.
- Focus rings are a visible 2 px blue outline with a 2 px offset, and
  everything works by keyboard. Tabs use `aria-current="page"`.
- Data from outside (plates from OCR) is inserted with `textContent`, never
  `innerHTML`.

## 9. Do and don't

| Don't | Do |
|---|---|
| Gradients, glows, glass, blur | Flat surfaces, 1 px borders |
| Pastel backgrounds on every card | White cards on warm paper; tint only behind status |
| Icons, emoji, coloured dots | A coloured word |
| 16–24 px radius, pill shapes | 6 px cards, 4 px controls |
| Drop shadows on cards | No shadows (toast and dialog only) |
| Many fonts and weights | Plex Sans 400/500/600 + Plex Mono for plates |
| A dashboard of 12 equal tiles | One sign, one map, one list: a clear hierarchy |
| Status chips everywhere | One short status word per thing |

## 10. Prompt for an AI tool

"Build it in the Smart Parking style:
- **Colours:** a warm paper background (#f5f4f0; #111317 in dark mode) with
  white cards (#191c21 in dark mode), a 1 px #e2e0d9 border and a 6 px radius.
  No shadows or gradients.
- **Type:** IBM Plex Sans 15 px body, 600 for titles; IBM Plex Mono for codes
  and times. Tabular numbers.
- **Meaning:** green #16794a = good/free, amber #a85d00 = warning,
  red #c0292f = bad, blue #0b57d0 = brand and the single primary action per
  area. Status is a coloured word, never an icon.
- **Hierarchy:** put the single most important number very large and centred,
  like a parking guidance sign.
- **Writing:** sentence case and plain words."
