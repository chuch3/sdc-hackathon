# Buns At Work! UI customization manual

The dashboard deliberately keeps visual decisions in a few places so a team can tune the look
without changing inventory behavior.

## Palette, type, spacing, and motion

Edit `dashboard/static/theme.css`. The `:root` block contains the color, radius, shadow,
font, speed, and easing tokens. Prefer changing tokens rather than component-specific values.
Keep the `prefers-reduced-motion` rules intact: motion is optional and must never be required to
understand a task.

The same stylesheet now contains the focus-ring, market-day, daily-sheet, and `@media print`
rules. When changing print styles, preserve hiding of navigation and buttons and keep the sheet
black-on-white for paper/PDF readability.

## App structure and copy

`dashboard/app.py` owns the primary navigation, page labels, page headers, and setup popover.
Keep only the five primary work areas in the top navigation. Add specialist flows from Today or
an explicit detail link rather than making every feature a peer page.

`dashboard/components.py` contains shared cards, headings, pills, and empty states. Reuse those
builders before adding a new visual pattern. Text should be short, operational, and explicit
about estimates or human approval.

## Page-specific changes

- `dashboard/views/today.py`: daily command center and operational quick links.
- `dashboard/views/week.py`: market-day editor and forecast board.
- `dashboard/views/daily_sheet.py`: print-only handoff content.
- `dashboard/views/purchasing.py`: supplier email-draft UI.

Do not put data-access logic directly in a view; add an API-client method in
`dashboard/api_client.py` first.

## Accessibility and keyboard safety

Use native Streamlit controls for any action that changes data. They participate in normal Tab
order and work with Enter/Space. Never add a hover-only control. Any custom clickable HTML needs
a keyboard focus target, an accessible label, Enter/Space behavior, and the shared focus ring.

Test the changed workflow with mouse unplugged: Tab to it, read the focus state, activate it,
and leave it with Escape where relevant.
