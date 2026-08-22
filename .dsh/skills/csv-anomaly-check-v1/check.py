#!/usr/bin/env python3
"""csv-anomaly-check v1 -- callable resource script for the SKILL.md alongside
this file. Standalone: no dependency on anything else in this repository, so
it works from any cwd once invoked with a CSV path.

Usage:
    python3 check.py <path-to-csv>

Prints a JSON report to stdout: {"file", "anomalies_found", "summary"}.
"""
import csv
import json
import re
import sys
from collections import Counter

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MISSING_VALUE_TOKENS = {""}


def _quantity_out_of_range(value):
    try:
        q = int(value)
    except (TypeError, ValueError):
        return False  # non-numeric is a shifted-column concern, not ours
    return q < 0 or q > 1000


def _price_out_of_range(value):
    try:
        p = float(value)
    except (TypeError, ValueError):
        return False
    return p < 0 or p > 100000


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

    return anomalies


def main():
    if len(sys.argv) != 2:
        print("usage: check.py <path-to-csv>", file=sys.stderr)
        raise SystemExit(2)

    csv_path = sys.argv[1]
    anomalies = check(csv_path)
    report = {
        "file": csv_path,
        "anomalies_found": anomalies,
        "summary": dict(Counter(a["type"] for a in anomalies)),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
