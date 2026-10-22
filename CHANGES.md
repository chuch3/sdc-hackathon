# Buns At Work! — Operations-first changes

## What changed

- The primary navigation is now deliberately small: **Today**, **Week**, **Stock**,
  **Insights**, and **Settings**. Purchase and bake workflows remain available from Today.
- The new **Daily sheet** is a read-only, print-friendly floor/bakery handoff containing
  bake work, expiry priorities, actions to review, and deliveries.
- The Week planner now supports editable **market days**. Their demand multiplier is applied
  alongside holiday multipliers and shown in the affected day column.
- Purchase orders can produce an editable supplier email draft and optional `mailto:` handoff.
  The application never sends mail or marks an order emailed.
- `POST /api/v1/webhooks/pos` accepts signed, idempotent POS sale, stockout, and refund events.
  Sales use FEFO; a refund is deliberately rejected until a manager identifies a safe batch.

## POS webhook setup

Set `POS_WEBHOOK_SECRET` in `backend/.env`. Sign the exact request body with:

```text
hex(HMAC-SHA256(secret, X-Buns-Timestamp + "." + raw_body))
```

Send `X-Buns-Timestamp` as Unix seconds and `X-Buns-Signature: sha256=<signature>`.
The timestamp must be within five minutes. The JSON envelope has `event_id`, `event_type`
(`sale`, `stockout`, or `refund`), `occurred_at`, and `payload`. Reusing an `event_id` with
the same body safely replays the stored result; a changed body is rejected.

## Keyboard workflow

Native controls are keyboard reachable with Tab, Shift+Tab, Enter, and Escape. `Ctrl/Cmd+K`
returns focus to navigation; `?` opens the shortcut reminder. Focus rings are intentionally
high contrast. This is the supported keyboard workflow—no action is hidden behind hover.

## What was intentionally not added

- Geolocation, OCR scanning, and automatic timezone detection.
- Automated email delivery or a provider-specific POS connector.
- Cosmetic “phase 4” polish.

## UI audit

The old UI leaned into an AI-generated feel through too many KPI cards, repeated descriptions,
animated decoration, nested cards, and nine peer navigation choices. The new direction favors
one daily work queue, direct wording, compact secondary workflows, and print-safe operational
content. The bakery identity remains, but never competes with the next safe action.

## Forecast and impact caveats

Forecast quality needs usable sales history. Stockout-censored days are excluded from training,
recommendations always require human approval, and sustainability/impact values remain estimates.
