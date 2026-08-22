"""
csv-anomaly-check skill
Version: v1
Distilled from: run-1 (cold-start reflection)

Checks a vendor-export CSV (see task-family/schema.py for the expected
columns) and flags:
  - missing values (empty cells in sku/quantity/unit_price)
  - duplicate rows (exact full-row duplicates)
  - out-of-range numeric values (negative quantity/price, absurd magnitudes)
  - malformed order dates (must match YYYY-MM-DD)
  - shifted columns (a numeric field that doesn't parse as a number --
    usually caused by an upstream column shift/swap)

Changelog:
  v3 - out-of-range check treated 0 as a valid quantity/price, but a $0.00 line item or 0-unit order is a data error in this vendor feed. Changed the negative-only bound (`< 0`) to `<= 0` for both fields.
  v2 - missing-value check only recognized truly empty cells; vendor files also use sentinel placeholders (NULL, N/A, -, --, NaN) which slipped through. Expanded MISSING_VALUE_TOKENS to cover them.
  v1 - initial version, distilled directly from the manual checks the
       agent performed by hand during run-1.
"""
import csv
import re

VERSION = "v3"
TRIGGER_KEYWORDS = [
    "csv", "vendor", "anomaly", "anomalies", "data issue", "data issues",
    "export", "data quality", "vendor export",
]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# --- MISSING_VALUE_TOKENS_ANCHOR ---
MISSING_VALUE_TOKENS = {"", "NULL", "N/A", "-", "--", "NaN", "null", "n/a"}
# --- END_MISSING_VALUE_TOKENS_ANCHOR ---


# --- OUT_OF_RANGE_ANCHOR ---
def _quantity_out_of_range(value):
    try:
        q = int(value)
    except (TypeError, ValueError):
        return False  # non-numeric is a shifted-column concern, not ours
    return q <= 0 or q > 1000


def _price_out_of_range(value):
    try:
        p = float(value)
    except (TypeError, ValueError):
        return False
    return p <= 0 or p > 100000
# --- END_OUT_OF_RANGE_ANCHOR ---


def check(csv_path):
    anomalies = []
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    seen_rows = set()
    for row in rows:
        row_id = row.get("row_id")

        for field in ("sku", "quantity", "unit_price"):
            if row.get(field, "") in MISSING_VALUE_TOKENS:
                anomalies.append({
                    "type": "missing_value", "row_id": row_id, "field": field,
                    "detail": f"value={row.get(field)!r}",
                })

        key = tuple(v for k, v in row.items() if k != "row_id")
        if key in seen_rows:
            anomalies.append({
                "type": "duplicate_row", "row_id": row_id, "field": None,
                "detail": "exact duplicate of an earlier row",
            })
        else:
            seen_rows.add(key)

        if _quantity_out_of_range(row.get("quantity")):
            anomalies.append({
                "type": "out_of_range", "row_id": row_id, "field": "quantity",
                "detail": f"quantity={row.get('quantity')}",
            })
        if _price_out_of_range(row.get("unit_price")):
            anomalies.append({
                "type": "out_of_range", "row_id": row_id, "field": "unit_price",
                "detail": f"unit_price={row.get('unit_price')}",
            })

        if not DATE_RE.match(row.get("order_date", "")):
            anomalies.append({
                "type": "malformed_date", "row_id": row_id, "field": "order_date",
                "detail": f"order_date={row.get('order_date')!r}",
            })

        try:
            int(row.get("quantity"))
        except (TypeError, ValueError):
            if row.get("quantity") not in MISSING_VALUE_TOKENS:
                anomalies.append({
                    "type": "shifted_column", "row_id": row_id, "field": "quantity",
                    "detail": f"non-numeric quantity={row.get('quantity')!r}",
                })
        # --- END_CHECK_LOOP_BODY_ANCHOR ---

    return {"anomalies_found": anomalies}
