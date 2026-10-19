# Smart Parking: design rules

The dashboard should feel like a piece of parking equipment: calm, readable
from across a room, and obvious to someone who has never seen it. The
reference is real parking guidance signs ("FREE 23") and transit wayfinding,
not a SaaS template.

Read this before changing anything in `frontend/`.

## 1. Principles

1. **One job per page.** Each page answers one question. Anything that doesn't
   help answer it moves to another page.
   - **Overview**: "How full is the lot, and what just happened?" This is the
     page you put on a projector.
   - **Gates**: "Are the cameras and barriers working?" It also holds the
     camera controls and the form for recording a car by hand.
   - **Activity**: "What happened, and when?" Search, filter, export, weekly report.
   - **Vehicles**: "Who is allowed in?" The registry.
   - **Settings**: everything you set once and then leave alone.
2. **The number first.** Free spaces is the biggest thing on the screen. Labels
   explain numbers; numbers never hide inside sentences.
3. **Plain words.** Write "Came in", not "ENTRY_EVENT". Write "Turned away",
   not "Rejected". Use sentence case everywhere. No jargon unless it's on a
   setting that needs it, and then explain it in one line underneath.
4. **Colour means something.** Green means free or allowed, amber means
   filling up or needs a look, red means full, stolen or blocked, and blue is
   the brand and the main action. If a colour carries no meaning, the element
   is grey.
5. **Quiet until it matters.** No animation, no pulsing, no count-ups. Only new
   activity rows get a brief highlight.

## 2. What "AI-generated looking" means, and what we do instead

| Don't | Do |
|---|---|
| Gradients, glows, glass and blur | Flat surfaces, 1 px borders |
| A pastel background on every card | A white card on warm paper; colour only on status |
| Icons, emoji, logo marks or coloured dots | Words. Status is a coloured word ("Turned away" in red) |
| Radius 16–24 px, pill everything | Radius 6 px on cards, 4 px on controls |
| Big drop shadows on cards | No shadows, except the toast and the sign-in dialog |
| Many fonts and weights | One family (IBM Plex Sans), plus IBM Plex Mono for plates |
| Marketing copy, centred paragraphs | Short factual sentences; only the sign and figures are centred |
| Status chips everywhere | One small text status per thing |
| A dashboard of 12 equal tiles | A clear hierarchy: one sign, one map, one list |

## 3. Tokens

All colours are CSS variables on `:root`, redefined for dark mode.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#f5f4f0` | `#111317` | Page background |
| `--card` | `#ffffff` | `#191c21` | Cards, tables |
| `--sunken` | `#efeee9` | `#22252b` | Inputs, empty bays, previews |
| `--line` | `#e2e0d9` | `#2c3037` | Borders, dividers |
| `--ink` | `#16181d` | `#eceef2` | Text |
| `--muted` | `#5f6470` | `#9aa0ab` | Secondary text |
| `--blue` | `#0b57d0` | `#7fa8f5` | Brand, primary button, links, focus |
| `--green` | `#16794a` | `#52c48a` | Free, allowed, came in |
| `--amber` | `#a85d00` | `#e8a54b` | Filling up, warnings |
| `--red` | `#c0292f` | `#f07a7e` | Full, stolen, blocked, turned away |

Each status colour has a `-soft` tint used only behind its own text (tags, bays).

**Type.** IBM Plex Sans 400/500/600, plus IBM Plex Mono 500 for plates and times.

| Role | Size | Weight |
|---|---|---|
| Sign number (free spaces) | `clamp(88px, 14vw, 168px)` | 600 |
| Figure (key numbers) | 32 px | 600 |
| Page title | 24 px | 600 |
| Card title | 15 px | 600 |
| Body | 15 px | 400 |
| Small / hints | 13 px | 400, `--muted` |

All numbers use `font-variant-numeric: tabular-nums`.

**Spacing.** A 4 px base; use 8, 12, 16, 24, 32 or 48. Cards have 20 px
padding (16 px on phones), and grid gaps are 16 px.

**Shape.** Card radius 6 px, control radius 4 px. Borders are 1 px `--line`.

## 4. Components

- **Top bar.** The name (text only) on the left, page tabs in the middle, and the
  connection status, clock and **Present** on the right. The active tab gets a
  2 px blue underline. On phones the tabs scroll sideways inside the bar, never
  the page. The bar and banners share the page's left and right edges
  (`--gutter`), so the name lines up with the content below it.
- **Availability sign.** Centred, like a guidance sign: the label "Free
  spaces", a huge number, "of N spaces", a thin meter and one status line. The
  number and meter take the status colour.
- **Bays.** Drawn like painted stalls: a dashed outline when free, a solid card
  with the plate centred when taken. The stall number is in the corner.
- **Figures row.** 3–4 centred numbers in a row separated by vertical rules,
  each with a short label above. These are not cards.
- **Plate.** Mono, black on white with a 1.5 px dark border, like a real plate.
  It stays black on white in dark mode too.
- **Outcome.** A coloured word ("Came in", "Turned away"), no symbol.
  Colour follows principle 4.
- **Tables.** For lists people scan: activity, the weekly report, vehicles.
  Left-aligned text, right-aligned numbers, and row actions as text buttons.
- **Buttons.** Primary is solid blue and used once per area. Secondary has a
  white background and a border. Text buttons are for row actions. Destructive
  actions use red text and always ask to confirm.
- **Toast.** A single message at the bottom centre that disappears after 5 s.
  It's used for every action's result, so feedback is always in the same place.
- **Banners.** A full-width strip under the top bar for "server offline" (red)
  and "no password set" (amber, with a Dismiss button).

## 5. Presentation mode

**Present** (or the `P` key) opens the Overview full-screen and hides the tabs
and controls. Text gets 25% bigger, and clicking a bay doesn't change
anything. Esc or **Exit** leaves it. Design the Overview so that a stranger
3 m from a projector can read the free spaces and the latest event.

## 6. Writing

- Labels name things ("Number of parking spaces"), and buttons say what
  happens ("Car came in", "Open barrier").
- Empty states say what to do next: "Nothing yet. Press Try a reading on the
  Gates page."
- Errors say what went wrong and what to try next, in one sentence.
- Times are relative when recent ("4 min ago") and absolute otherwise. The
  exact time is in the tooltip.

## 7. Accessibility

- Text contrast is at least 4.5:1 in both themes, and status is never shown by
  colour alone (there's always a word).
- Everything works with the keyboard, focus rings are visible (2 px blue), and
  tabs use `aria-current`.
- Data is inserted with `textContent`, never `innerHTML`, because plates come
  from OCR.
- The layout works at 360 px wide without horizontal scrolling.
