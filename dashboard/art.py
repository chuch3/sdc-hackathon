from __future__ import annotations

from html import escape

ICONS = {
    "loaf": (
        '<path d="M4.5 10.5c0-3 3.1-5 7.5-5s7.5 2 7.5 5v5.5a2 2 0 0 1-2 2H6.5a2 2 0 0 1-2-2z"/>'
        '<path d="M8.5 7.8 7.5 11"/><path d="M12 7v3.4"/><path d="M15.5 7.8l1 3.2"/>'
    ),
    "wheat": (
        '<path d="M12 21V9"/>'
        '<path d="M12 12c-2.5 0-3.5-1.5-3.5-3.5C11 8.5 12 10 12 12Z"/>'
        '<path d="M12 12c2.5 0 3.5-1.5 3.5-3.5C13 8.5 12 10 12 12Z"/>'
        '<path d="M12 16c-2.5 0-3.5-1.5-3.5-3.5C11 12.5 12 14 12 16Z"/>'
        '<path d="M12 16c2.5 0 3.5-1.5 3.5-3.5C13 12.5 12 14 12 16Z"/>'
        '<path d="M12 9c-1.8 0-3-1.2-3-3 1.8 0 3 1.2 3 3Z"/>'
        '<path d="M12 9c1.8 0 3-1.2 3-3-1.8 0-3 1.2-3 3Z"/>'
    ),
    "leaf": (
        '<path d="M5 19C5 10.5 11.5 4.5 20 4c.5 8.5-5.5 15-14 15Z"/>'
        '<path d="M5 19c2.5-4.5 6-8 10.5-10.5"/>'
    ),
    "basket": (
        '<path d="M4.5 10h15l-1.6 8.2a1.5 1.5 0 0 1-1.5 1.2H7.6a1.5 1.5 0 0 1-1.5-1.2Z"/>'
        '<path d="M8 10 9.5 4h5L16 10"/><path d="M9.5 13.5v3"/><path d="M14.5 13.5v3"/>'
    ),
    "croissant": (
        '<path d="M4 13.5c0-2.5 2-4.5 4.5-4.5 1 0 1.9.3 2.6.8.7-.5 1.6-.8 2.6-.8'
        'C16.2 9 18 11 18 13.5c0 .8-.2 1.5-.5 2.1-1 .4-2 .6-3.2.6-1.5 0-2.6-.4-3.3-1'
        '-.7.6-1.8 1-3.3 1-1.2 0-2.2-.2-3.2-.6A4.6 4.6 0 0 1 4 13.5Z"/>'
        '<path d="M9 12c.8.4 1.8.6 3 .6s2.2-.2 3-.6"/>'
    ),
    "oven": (
        '<rect x="4.5" y="5" width="15" height="14" rx="2.5"/><path d="M4.5 9.5h15"/>'
        '<circle cx="8" cy="7.3" r=".8"/><circle cx="11" cy="7.3" r=".8"/>'
        '<rect x="7.5" y="12" width="9" height="5" rx="1"/>'
    ),
    "pumpkin": (
        '<path d="M12 8c-3.5 0-6 2-6 5s2.5 5 6 5 6-2 6-5-2.5-5-6-5Z"/>'
        '<path d="M12 8v10"/><path d="M9.5 8.5C8 10 8 15 9.5 17"/>'
        '<path d="M14.5 8.5C16 10 16 15 14.5 17"/><path d="M12 8c0-1.5.7-2.5 2-3"/>'
    ),
    "sparkle": (
        '<path d="M12 3.5 13.6 9l5.4 1.6-5.4 1.6L12 17.6l-1.6-5.4L5 10.6 10.4 9Z"/>'
        '<path d="M18.5 16.5l.7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7Z"/>'
    ),
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4'
        'M18.4 5.6 17 7M7 17l-1.4 1.4"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="8"/><path d="M12 8v4.5l3 1.8"/>',
    "check": '<path d="M5 12.5 10 17l9-10"/>',
    "gear": (
        '<circle cx="12" cy="12" r="3.2"/>'
        '<path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M5.8 5.8l1.4 1.4'
        'M16.8 16.8l1.4 1.4M18.2 5.8l-1.4 1.4M7.2 16.8l-1.4 1.4"/>'
    ),
    "scale": (
        '<path d="M12 4v16"/><path d="M6 8h12"/><path d="M6 8 3.5 14h5Z"/>'
        '<path d="M18 8l-2.5 6h5Z"/><path d="M8 20h8"/>'
    ),
    "heart": (
        '<path d="M12 20s-7-4.5-7-9a4 4 0 0 1 7-2.5A4 4 0 0 1 19 11c0 4.5-7 9-7 9Z"/>'
    ),
    "chart": (
        '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M7 16v-4M11 16V8M15 16v-6M19 16v-2"/>'
    ),
    "receipt": (
        '<path d="M6 3.5h12v17l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5-2 1.5Z"/>'
        '<path d="M9 8h6M9 11.5h6M9 15h3"/>'
    ),
    "alert": (
        '<path d="M12 4 21 19H3Z"/><path d="M12 9v4.5"/>'
        '<circle cx="12" cy="16.5" r=".6" fill="currentColor" stroke="none"/>'
    ),
    "coffee": (
        '<path d="M5 8h11v5a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5Z"/>'
        '<path d="M16 9h2a2.5 2.5 0 0 1 0 5h-2"/>'
        '<path d="M8 4v1.5M11 4v1.5M14 4v1.5"/>'
    ),
    "flame": (
        '<path d="M12 21c-4 0-6.5-2.5-6.5-6 0-3 2-5 3.5-7 .4 2 1.5 3 2.5 3.5'
        '0-2.5 1-5 3.5-7.5.5 3 3.5 5.5 3.5 10.5 0 3.5-2.5 6.5-6.5 6.5Z"/>'
    ),
}

NAV_ICONS = {
    "Today": ":material/wb_sunny:",
    "Week": ":material/calendar_view_week:",
    "Inventory": ":material/inventory_2:",
    "Expiry": ":material/hourglass_bottom:",
    "Recommendations": ":material/tips_and_updates:",
    "Purchasing": ":material/shopping_basket:",
    "Bakery": ":material/bakery_dining:",
    "Impact": ":material/eco:",
    "Settings": ":material/settings:",
}

CATEGORY_ICONS = {
    "bakery": "croissant",
    "dairy": "coffee",
    "produce": "leaf",
    "pantry": "basket",
    "beverage": "coffee",
}


def icon(name: str, size: int = 18, cls: str = "") -> str:
    body = ICONS.get(name, ICONS["sparkle"])
    classes = f"ui-icon {cls}".strip()
    return (
        f'<svg class="{classes}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


def category_icon(category: str | None) -> str:
    return CATEGORY_ICONS.get(str(category or "").lower(), "loaf")


HERO_ART = """
<svg class="hero-svg" viewBox="0 0 340 230" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="loafGrad" x1="126" y1="80" x2="214" y2="146" gradientUnits="userSpaceOnUse">
      <stop stop-color="#D97B3F"/><stop offset="1" stop-color="#A8431F"/>
    </linearGradient>
    <linearGradient id="basketGrad" x1="170" y1="138" x2="170" y2="212" gradientUnits="userSpaceOnUse">
      <stop stop-color="#E8B26A"/><stop offset="1" stop-color="#C98A3F"/>
    </linearGradient>
  </defs>
  <circle cx="170" cy="116" r="94" fill="#F8ECD6"/>
  <circle cx="170" cy="116" r="94" stroke="#E3CDA9" stroke-width="2" stroke-dasharray="3 8"/>
  <g class="steam s1" stroke="#C9A97C" stroke-width="3" stroke-linecap="round">
    <path d="M150 62c-6-8 6-12 0-20"/>
  </g>
  <g class="steam s2" stroke="#C9A97C" stroke-width="3" stroke-linecap="round">
    <path d="M172 58c-6-8 6-12 0-20"/>
  </g>
  <g class="steam s3" stroke="#C9A97C" stroke-width="3" stroke-linecap="round">
    <path d="M194 62c-6-8 6-12 0-20"/>
  </g>
  <g class="leaf leaf-a">
    <path d="M62 78c-2-12 6-21 18-23 2 12-6 21-18 23Z" fill="#C9622A"/>
    <path d="M63 77c4-7 9-12 15-18" stroke="#F6E3D4" stroke-width="2" stroke-linecap="round"/>
  </g>
  <g class="leaf leaf-b">
    <path d="M276 96c12-4 22 2 26 13-12 4-22-2-26-13Z" fill="#6F7F4E"/>
    <path d="M278 97c7 2 13 6 20 10" stroke="#EAF0DC" stroke-width="2" stroke-linecap="round"/>
  </g>
  <g class="leaf leaf-c">
    <path d="M286 170c-10-6-12-17-5-26 10 6 12 17 5 26Z" fill="#E39A2D"/>
  </g>
  <path d="M94 140h152l-13 60c-1.4 6-5.8 10-11.9 10H119c-6.1 0-10.5-4-11.9-10Z" fill="url(#basketGrad)"/>
  <path d="M102 152h136" stroke="#A86F2F" stroke-width="3" stroke-linecap="round" opacity=".55"/>
  <path d="M111 163h118M115 179h110M119 195h102" stroke="#A86F2F" stroke-width="2.4" stroke-linecap="round" opacity=".35"/>
  <path d="M122 140c0-34 21-52 48-52s48 18 48 52" stroke="#B87C3C" stroke-width="8" stroke-linecap="round"/>
  <path d="M128 124c0-25 17-41 42-41s42 16 42 41v13c0 6-5 10-11 10H139c-6 0-11-4-11-10Z" fill="url(#loafGrad)"/>
  <path d="M150 98l-6 20M172 94v24M194 98l6 20" stroke="#F7D9B6" stroke-width="5" stroke-linecap="round" opacity=".85"/>
  <g stroke="#8A6A3F" stroke-width="2.4" stroke-linecap="round" fill="none">
    <path d="M78 178c-9-17-7-35 6-48"/>
    <path d="M84 160c-7-1-11-5-12-11 7 1 11 5 12 11Z"/>
    <path d="M82 170c6-4 12-4 17 0-6 4-12 4-17 0Z"/>
    <path d="M80 152c-6-3-9-8-8-14 6 3 9 8 8 14Z"/>
  </g>
  <g stroke="#8A6A3F" stroke-width="2.4" stroke-linecap="round" fill="none">
    <path d="M264 182c8-16 6-33-6-46"/>
    <path d="M258 164c6-1 10-5 11-11-6 1-10 5-11 11Z"/>
    <path d="M260 174c-6-4-11-4-16 0 6 4 11 4 16 0Z"/>
  </g>
  <g class="hero-pumpkin">
    <ellipse cx="252" cy="132" rx="15" ry="13" fill="#E39A2D"/>
    <path d="M252 119c0-4 2-7 6-8" stroke="#6F7F4E" stroke-width="3" stroke-linecap="round"/>
    <path d="M252 120v24M246 121c-4 5-4 16 0 22M258 121c4 5 4 16 0 22" stroke="#C47A1E" stroke-width="1.6" opacity=".7"/>
  </g>
</svg>
"""


def hero_art() -> str:
    return HERO_ART


BUN_MARK = """
<svg class="brand-logo" viewBox="0 0 48 48" width="42" height="42" aria-hidden="true">
  <defs>
    <linearGradient id="bunsCrust" x1="24" y1="2" x2="24" y2="46" gradientUnits="userSpaceOnUse">
      <stop stop-color="#D97B3F"/>
      <stop offset="1" stop-color="#8C3517"/>
    </linearGradient>
  </defs>
  <circle cx="24" cy="24" r="23" fill="url(#bunsCrust)"/>
  <circle cx="24" cy="24" r="21.4" fill="none" stroke="#FBEEDB" stroke-width="1.2" opacity=".65"/>
  <path d="M11.5 31.5c0-7 5.6-11.8 12.5-11.8s12.5 4.8 12.5 11.8a2.2 2.2 0 0 1-2.2 2.2H13.7a2.2 2.2 0 0 1-2.2-2.2Z" fill="#FFF3DC"/>
  <path d="M18.6 22.4 17 30.2M24 21.6v8.6M29.4 22.4 31 30.2" stroke="#C9622A" stroke-width="1.9" stroke-linecap="round"/>
  <path d="M14.4 35.4h19.2" stroke="#8A5A00" stroke-width="1.3" stroke-linecap="round" opacity=".45"/>
  <path d="M36.6 9.6l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9Z" fill="#F3C77B"/>
</svg>
"""


def brand_mark() -> str:
    return BUN_MARK


def escape_text(value: str) -> str:
    return escape(str(value))
