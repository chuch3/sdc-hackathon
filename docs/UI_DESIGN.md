# FreshStock UI design notes

FreshStock uses an **Autumn Bakehouse** theme: warm cream paper, rust and amber accents,
Fraunces display headings, Nunito Sans body text, and small handcrafted motion cues. Navigation
runs across the top of the workspace, and the **Autumn Forest** piece from ASCII Magic is
the page background behind the whole workspace. The look is deliberately
vintage: aged paper, letterpress buttons, small-caps labels, double rules, and rubber-stamp
status chips. It keeps the business-first layout of an operations dashboard but avoids the cold
sidebar-plus-charts template. The interaction personality is inspired by the handmade, playful
web (Neocities-style micro-interactions such as floating leaves, rising steam, a slow bench
ticker, and hover lift) without copying any site.

The Orbyte integration remains real: Orbyte supplies actor context and can host the dashboard.
The visual language is no longer Orbyte blue; the layout lineage is documented below.

## Design tokens

All tokens live at the top of `dashboard/static/theme.css` under `:root`.

| Token | Value | Use |
|---|---|---|
| Canvas | `#EFE4D0` | Warm oat page background |
| Paper | `#FDF8EC` | Cards, sidebar, tables |
| Paper 2 | `#F7EDDB` | Inputs, code blocks, secondary surfaces |
| Paper deep | `#F2E5CE` | Pressed and inset surfaces |
| Ink | `#3A2A1C` | Headings and primary text |
| Ink soft | `#57422F` | Secondary headings |
| Muted | `#7A6853` | Supporting text, labels |
| Faint | `#9D8A72` | Captions and metadata |
| Line | `#E2D2B6` | Card and divider borders |
| Line strong | `#CFB894` | Card edges, stamps, rules |
| Rule | `#B9A07A` | Double rules and page ornaments |
| Primary | `#A8431F` | Rust CTAs, links, active navigation |
| Primary strong | `#8C3517` | Primary hover |
| Primary soft | `#F6E3D4` | Active nav, selected chips |
| Amber | `#E39A2D` | Bake actions, highlights |
| Pumpkin | `#C9622A` | Markdown, secondary warning |
| Sage | `#6F7F4E` | Success, donations, healthy stock |
| Berry | `#9B2335` | Expired, write-off, errors |
| Eucalyptus | `#4F7C74` | Informational cool counterweight |
| Font display | Fraunces | Page titles, hero, product names |
| Font body | Nunito Sans | Body, tables, controls |
| Radius | `12px` | Cards and containers |
| Radius small | `8px` | Buttons and inputs |
| Shadow | `0 12px 26px rgba(90,60,30,.10)` | Hovered cards and hero |
| Press | `inset 0 1px 0 rgba(255,255,255,.65)` | Letterpress highlight on cards and chips |

Contrast notes: primary rust on cream and white-on-rust both clear WCAG AA for normal text;
amber is used with dark ink (`#8A5A00`), never white. Colour is always paired with a label.

## Layout

```text
┌──────────────────────────────────────────────────────────────────────┐
│ FreshStock                         [API] [date]  [Setup popover]    │
│ Autumn bakehouse                                                     │
├──────────────────────────────────────────────────────────────────────┤
│ [Today] [Inventory] [Expiry] [Actions] [Purchasing] [Bakery] ...     │
├──────────────────────────────────────────────────────────────────────┤
│ FreshStock Bakehouse              Page title          [date] [role]  │
│ Short page description                                               │
│                                                                      │
│  KPI card   KPI card   KPI card   KPI card                           │
│                                                                      │
│  Animated hero: greeting + basket art                                │
│  On-the-bench ticker                                                 │
│  Shelf-life runway                                                   │
│                                                                      │
│  Section title                              section note             │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Card / chart / recommendation                                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
    Page background: the Autumn Forest ASCII piece, seen through the 50% paper panel
```

## Light and night themes

The top navigation ends with a theme button ("Dark mode" / "Light mode") that flips the whole
workspace. The choice lives in `st.session_state.fs_dark` and `dashboard/app.py` mirrors it onto
`<html data-fs-theme="dark|light">`.

- The night palette is the same token set with dark values (ink becomes cream, paper becomes
  charcoal, the accent hues brighten). `theme.css` section 14 holds it, so no component needs a
  second implementation.
- The Autumn Forest piece stays the background in both themes; the night palette sets
  `--fs-ascii-ink` to warm cream and raises the backdrop opacity so the dots glow.
- Streamlit widgets that are not skinned by the app's own CSS (selects, popovers, toggles,
  dataframes) get explicit night overrides in the same section. Dataframes are inverted with a
  CSS filter because Streamlit paints them on canvas.

## Motion rules

- Motion is decorative and slow; it must never delay a decision.
- The Autumn Forest piece animates behind the workspace. It is decoration only; there is no
  pointer-reactive overlay.
- Steam rises, leaves float, the bench ticker scrolls, the status dot pulses, and cards lift
  slightly on hover. Buttons press down on click.
- `prefers-reduced-motion: reduce` disables all of it, including the ticker and shimmer. The
  ASCII piece is served by the ASCII Magic runtime, which honours the same preference.
- No cursor-following, confetti, sound, or animated gradients behind data tables.
- Everything except the hero piece is CSS-only. The piece is one inline loader in
  `dashboard/ascii_magic.py` plus the ASCII Magic module; no webfont download, no build step.

## Component rules

- **Navigation:** a sticky pill bar across the top, Material Symbols icons, active item in
  solid rust with cream text and a soft shadow. It wraps or tightens on narrow screens; no
  nested menus.
- **Header:** the Buns At Work! logo and wordmark sit on the right of the top bar, with
  the connection status and the setup popover next to it, then the navigation bar, then a
  wheat icon eyebrow, one Fraunces H1, one sentence, and date/role chips.
- **KPIs:** four compact cards with a soft icon tile, large value, and a one-line caveat.
- **Hero:** only on Today; greeting, real counts from the API, two chips, and the basket
  illustration. Never fabricate counts.
- **Recommendations:** category icon, action/risk chips, confidence meter, quantity, expandable
  "Baker's note", and explicit approve/reject/edit actions.
- **Tables:** white surface, compact rows, progress bars for days-left where useful.
- **Charts:** Altair (bundled with Streamlit), autumn palette, no gridlines, rounded bars.
  Impact is labelled as an estimate.
- **Empty states:** dashed card with an animated icon, a plain explanation, and the next step.
- **Copy:** short, warm, operational. Use "write off", "donate", "bake", "buy".

## Weekly quest board

The Week board (`dashboard/views/week.py`) is the seventh page of the same theme, not a
second visual language. It shows a seven-day projection from `GET /api/v1/planner/week`.

- **Header:** the same four KPI cards as every other page, then the weekly workload bar
  (`quest-workload`): the total task count, the completion percentage, a thin progress
  line, one horizontal bar split into seven day segments (width = task count, colour =
  risk level), and a legend with the task count per kind. The board starts right after
  the bar; there is no badge or gamification row above it.
- **Day column:** `quest-day` panel with the weekday, the date, a risk pill
  (calm/busy/risky), and three lines of projected stock, sales, arrivals, value at risk,
  and expected waste.
- **Overflow:** a day with more than three tasks shows the first three cards and a
  `+N more tasks · show all N` button. The button opens a modal (`fs-quest-modal`) listing
  every task for that day with its reasoning, impact, and calculation; the close (X)
  button, Escape, and a backdrop click all dismiss it. The hidden cards stay in the DOM
  (`quest-card-overflow`) so the popup only has to clone them.
- **Card:** always shows the kind pill, the quantity, the product name, and a two-line
  summary, so the whole week can be read without interaction. The reasoning, impact, and
  calculation stay behind one toggle ("Show every task's reasoning"), which opens all
  cards at once and works with touch and keyboard.
- **Board rules:** the board is read-only. It never implies that an action happened, and
  it never writes to the ledger. Approvals stay on the Actions page.
- **Activity calendar:** above the weekly workload bar, a contribution-style heatmap
  (`heat-grid`, `heat-cell`) with one column per week and one row per weekday. Darker
  squares are busier days; a red corner means waste was recorded and an amber corner
  means a stockout was recorded. Hovering a square shows the units sold, wasted,
  donated, and the decisions recorded that day.
- **Interaction:** the board does not depend on hover. The workload bar answers "what is
  left this week" at a glance, and the details toggle opens the reasoning for every card.
  Cards keep a focus ring and a border highlight on hover, but nothing is hidden behind the
  pointer.
- **Responsive:** seven columns on desktop; Streamlit stacks the columns on narrow screens,
  and the day panels become full-width cards.

## Decisions on the cards

A recorded decision has to be visible. `POST /recommendations/{id}/decision` writes to the
activity log, and the recommendation list returns the latest `decision`, `decided_at`, and
`decided_by` per product. The card then shows an Approved, Edited, or Rejected pill plus a
`decision-note` line with who decided and when, so the queue cannot silently re-ask for a
decision that was already made. The confirmation message is held in the session and shown
after the rerun, so the feedback is never wiped by the refresh.

## Where to customise

The theme is split so you can change one layer without touching the others.

| File | What it controls |
|---|---|
| `dashboard/static/theme.css` | **Main CSS scaffold.** Tokens at the top, then numbered sections: fonts, canvas, sidebar, header, hero/motion, cards, pills, buttons/inputs, tables/tabs/code, extras, quest board, responsive, reduced motion. |
| `.streamlit/config.toml` | Streamlit's own widget theme (primary colour, canvas, radius) so native widgets match the CSS. |
| `dashboard/art.py` | SVG icon paths (`ICONS`), Material icon names for nav (`NAV_ICONS`), the Buns At Work! badge (`BUN_MARK`, `brand_mark`), category mapping, and the inline hero illustration (`HERO_ART`). |
| `dashboard/components.py` | HTML builders: `pill`, `metric_row`, `page_header`, `section_header`, `hero`, `ticker`, `freshness_ladder`, `empty_state`, `note_card`, `confidence`, `status_row`. |
| `dashboard/app.py` | App shell, CSS/font links, top brand bar, sticky top navigation, setup popover, actor simulation, and page copy (`PAGE_COPY`). |
| `dashboard/ascii_magic.py` | Loads the ASCII Magic module once and creates the `autumn-forest` element in the fixed page-background layer. |
| `dashboard/quest_modal.py` | Delegated click handler that turns a day's hidden `quest-card-overflow` cards into a modal with a close (X) button. |
| `dashboard/views/*.py` | Page content and Altair charts. |
| `dashboard/static/*.woff2` | Bundled Fraunces and Nunito Sans files; no runtime Google Fonts dependency. |

### Common edits

- **Change the palette:** edit the `:root` block in `theme.css`. Most components inherit from
  the tokens.
- **Add an icon:** add an SVG path to `ICONS` in `art.py`, then call `icon("name")` or pass the
  name to `metric_row`/`section_header`.
- **Add a KPI:** append `(label, value, help, icon_name, tone)` to a `metric_row` call. Tones:
  `""`, `amber`, `sage`, `berry`, `eucalyptus`.
- **Change page titles:** edit `PAGE_COPY` in `app.py`; the third item is the header icon.
- **Add a nav item:** add it to `NAV_ITEMS` and `NAV_LABELS` in `app.py`, give it a Material
  icon in `NAV_ICONS`, and add a branch in the final page router. The top bar wraps
  automatically.
- **Tune motion:** change the keyframes or the `--speed`/`--ease` tokens in the `:root` block
  of `theme.css`; keep the reduced-motion block intact.

## Orbyte webview

When launched with `?from=orbyteApp&actor=...&role=...`, the sidebar shows an
**Orbyte webview** chip. The role is still a simulated demo role, not authentication.
Credentials remain server-side in environment variables.

## ASCII art notes

- The page background carries the **Autumn Forest** piece from ASCII Magic
  (`<ascii-art piece="autumn-forest" look="dots">`). The module script is loaded once per
  browser session from `https://www.ascii-magic.com/ascii/ascii.js` and the element is reused
  across Streamlit reruns, so the animation is not restarted on every interaction.
- The element is created with `document.createElement` in `dashboard/ascii_magic.py`, because
  Streamlit sanitises rendered HTML and DOMPurify drops unknown custom elements.
- The art is decoration only. It is a fixed layer at `z-index: -2`, so it never sits on top of
  a table, and it is scaled to cover the viewport from a 100 x 36 frame.
- The workspace panel sits on top of it at 50% paper opacity, so the art shows through
  the panel as a faint texture while every heading, table, and number stays readable.
- The paper grain lives in its own `body::before` layer at `z-index: -3`, below the art;
  a body background would paint over a negative z-index backdrop.
- If the CDN is unreachable the dashboard keeps working: the layer simply stays empty and the
  aged-paper background remains.

## What changed from the first UI

- Moved navigation from the left sidebar to a sticky top bar with a `Setup` popover for the
  API endpoint and actor simulation.
- Moved the Autumn Forest piece into the real page background and gave the workspace panel
  50% paper opacity, so the art reads through the surface without fighting the data.
- Replaced Orbyte blue with the Autumn Bakehouse cream/rust/amber/sage system.
- Added Fraunces and Nunito Sans, bundled locally for offline and Docker use.
- Added Material Symbols navigation icons and a custom bakery SVG icon set.
- Added an animated Today hero, bench ticker, freshness ladder, and reduced-motion support.
- Added Altair stock, daypart, and impact charts.
- Moved all styling out of `app.py` into the editable `theme.css` scaffold.
- Retouched the theme as vintage letterpress: aged paper, double rules, small-caps labels,
  squared stamp chips, letterpress buttons, and index-card KPI tiles with a folded corner.
