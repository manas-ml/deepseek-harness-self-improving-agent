# csv-anomaly-check (v1)

**Distilled from:** run-1 (cold-start session, see `runs/run-1.json`)

## What it does

Callable check for the vendor-export task family. Given a CSV path, returns
a report of anomalies found across five categories:

| type | how v1 detects it |
|---|---|
| `missing_value` | `sku`/`quantity`/`unit_price` cell is an empty string |
| `duplicate_row` | full row is byte-identical to an earlier row |
| `out_of_range` | quantity < 0 or > 1000; unit_price < 0 or > 100000 |
| `malformed_date` | `order_date` doesn't match `^\d{4}-\d{2}-\d{2}$` |
| `shifted_column` | `quantity` doesn't parse as an integer |

## Why this shape

During run-1 the agent worked through the file column by column, by hand,
in exactly this order. This skill is that manual process turned into a
reusable, callable module (`check(csv_path) -> {"anomalies_found": [...]}`)
so future sessions don't have to rediscover it.

## Known limitations (as of v1)

- Only recognizes truly empty cells as "missing" -- sentinel placeholders
  like `NULL`, `N/A`, `-` will slip through.
- Treats a price/quantity of exactly `0` as valid, not suspicious.

## Changelog

- **v1** -- initial version, distilled directly from run-1.
