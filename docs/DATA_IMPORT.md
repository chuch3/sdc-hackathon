# Importing sales history

FreshStock learns from dated sales, not from a spreadsheet living beside the app. The CSV
importer turns a messy export into closed historical batches and immutable `SALE`
movements. It never changes today's saleable stock.

## Demo path

```bash
cd backend
uv run python -m scripts.seed --skip-history
uv run python -m scripts.start
```

Then open **Settings → Import sales**. Download the sample CSV, or use **Load the demo
CSV**, preview it, and import the valid rows. Today changes from a safe data warning to a
forecast-ready state without any manual stock edits.

Checked-in examples:

- `docs/samples/sales_template.csv` — the preferred clean shape.
- `docs/samples/messy_sales.csv` — six weeks of sales for every demo SKU, plus mixed date
  formats, an unknown SKU, a bad quantity, a duplicate row, and a stockout marker. The
  importer skips bad rows and reports them. Six weeks is deliberate: it leaves a 28-day
  training window before a 14-day holdout, so the impact proof is meaningful.

## Accepted columns

Required fields are date, SKU and quantity. Daypart and stockout are optional.

| Field | Header aliases |
|---|---|
| Date | `date`, `business_date`, `sale_date`, `sold_at`, `timestamp`, `day` |
| SKU | `sku`, `product_sku`, `product`, `item`, `item_code` |
| Quantity | `quantity`, `qty`, `units`, `sold`, `quantity_sold` |
| Daypart | `daypart`, `day_part`, `part_of_day`, `shift` |
| Stockout | `stockout`, `stock_out`, `out_of_stock`, `censored`, `stockout_flag` |

If auto-detection is ambiguous, choose the exact column for each field in the Settings
wizard. Explicit mapping values win over aliases.

Dates may mix ISO (`2026-10-21`), day-first (`21/10/2026`, `21-10-2026`), dotted, and
year-first slash formats. Ambiguous values are read day-first. Future dates, negative or
non-numeric quantities, blank fields, and SKUs that do not match an active product are
reported and skipped. Blank rows are ignored.

A stockout row records censored demand. It creates a `StockoutEvent` and is excluded from
training, so the model does not mistake an empty shelf for low demand.

## API

Both endpoints accept JSON. There is no multipart upload requirement.

```http
POST /api/v1/imports/sales/preview
{
  "csv_text": "date,sku,quantity,daypart,stockout\n2026-10-20,MILK-001,12,morning,false\n",
  "mapping": {"date": null, "sku": null, "quantity": null, "daypart": null, "stockout": null}
}
```

The preview returns resolved columns, valid/invalid/duplicate counts, usable days, unknown
SKUs, the first 50 row issues, and `can_commit`. It writes nothing.

```http
POST /api/v1/imports/sales/commit
{
  "csv_text": "...",
  "mapping": {},
  "request_id": "store-42-2026-10-21"
}
```

Reuse a `request_id` to replay the original result safely. The idempotency key is stored as
`Setting import_sales:{sha256(request_id)}`. Reusing the same id with different CSV content
returns `409`.

## What a commit writes

- One closed `Batch` per SKU, code `IMPORT-HIST-{request_id}-{sku}`
  (`quantity_remaining=0`, `status=CLOSED`, `unit_cost=0`).
- One `RECEIPT` movement for the total imported quantity and one dated `SALE` movement per
  valid sales row, all at 12:00 UTC to keep the business date stable.
- One `StockoutEvent` per `stockout=true` row.
- One `SALES_IMPORTED` activity event and the idempotency `Setting`.

The imported history is deliberately kept away from live stock. No active batch is
allocated, and `inventory/positions` reports zero new saleable units.

## Limits and assumptions

- Up to `import_max_rows` rows per upload (default 20,000) and 5 MB of CSV text.
- Unknown SKUs are not created automatically; add products first or correct the export.
- Exact duplicate rows inside one upload are imported once.
- The importer records sales demand only. It does not infer cost, margin, or waste.
