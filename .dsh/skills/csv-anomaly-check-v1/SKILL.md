---
name: csv-anomaly-check-v1
description: Check a vendor-export CSV (task-family/schema.py's fixed columns) for missing values, duplicate rows, out-of-range numbers, malformed dates, and shifted columns. Use whenever asked to check a vendor CSV export for data issues and produce a report.
whenToUse: A user asks to check, audit, or validate a vendor/data export CSV for anomalies, data-quality issues, or produce a data-quality report on one.
---

# csv-anomaly-check (v1)

A callable check for the vendor-export task family (see `task-family/schema.py`
and `task-family/generate.py` in this repository). Don't re-derive these
checks by reading the CSV by hand -- run the script below and read its
report.

## How to use it

Run the resource script through the bash tool:

```
python3 .dsh/skills/csv-anomaly-check-v1/check.py <path-to-csv>
```

It prints a JSON report to stdout:

```json
{
  "file": "<path>",
  "anomalies_found": [
    {"type": "missing_value", "row_id": "12", "field": "quantity", "detail": "..."},
    ...
  ],
  "summary": {"missing_value": 2, "duplicate_row": 1, "out_of_range": 2, "malformed_date": 2, "shifted_column": 1}
}
```

Anomaly types and how v1 detects each:

| type | how v1 detects it |
|---|---|
| `missing_value` | `sku`/`quantity`/`unit_price` cell is an empty string |
| `duplicate_row` | a row's fields (excluding `row_id`) are byte-identical to an earlier row |
| `out_of_range` | quantity < 0 or > 1000; unit_price < 0 or > 100000 |
| `malformed_date` | `order_date` doesn't match `^\d{4}-\d{2}-\d{2}$` |
| `shifted_column` | `quantity` doesn't parse as an integer |

## After running it

1. Turn `anomalies_found` into the requested report for the user.
2. Before finishing, sanity-check the raw CSV by eye for value patterns the
   script's report doesn't explain (sentinel placeholders like `NULL`/`N/A`,
   a suspicious `0` price/quantity, an unfamiliar format). If you find one,
   don't hand-fix that one file -- edit `check.py` itself to handle the
   category, bump the skill to a new version directory (`csv-anomaly-check-v2/`,
   with an updated `SKILL.md` changelog explaining the gap and the fix), and
   call `record_skill_version` (from the `dsh-csv-anomaly-memory` bundle, if
   mounted) so the reason survives for future sessions. Re-run the new
   version before reporting.
3. Call `record_reflection` (same bundle) with what you observed and what you
   did, so a future session starting cold can `recall_task_memory` instead of
   re-deriving this from scratch.

## Known limitations (as of v1)

- Only recognizes truly empty cells as "missing" -- sentinel placeholders
  like `NULL`, `N/A`, `-` will slip through undetected.
- Treats a price/quantity of exactly `0` as valid, not suspicious.
- No check at all for values that look like currency (`$45.00`, `€12.50`)
  in `unit_price` -- that's a different category, not a variant of an
  existing one, so it needs a genuinely new check if it shows up.

## Changelog

- **v1** -- initial version, written directly from a first cold-start pass
  over the task family (same checks the standalone Python POC's run-1
  performed manually; see `../../../agent/agent.py`'s `cold_start_run` in
  this repository for that reference trajectory).
