#!/usr/bin/env python3
"""Generator for the vendor-export task family.

Produces a CSV file with a fixed schema (see schema.py) plus a `.meta.json`
sidecar recording the *exact* ground-truth anomalies that were injected, so
`checker.py` can grade a report automatically without needing an LLM judge.

Usage:
    python generate.py --out samples/sample_01.csv --seed 1 --rows 40 \
        --missing 2 --duplicate 1 --out-of-range 2 --malformed-date 2 \
        --shifted-column 1 [--missing-style empty|sentinel]
        [--zero-price] [--currency-symbol 0]
"""
import argparse
import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import COLUMNS, PRODUCTS, WAREHOUSES, QUANTITY_RANGE, UNIT_PRICE_RANGE

SENTINEL_TOKENS = ["NULL", "N/A", "-", "--", "NaN"]
MALFORMED_DATE_TEMPLATES = [
    lambda d: d.strftime("%d/%m/%Y"),
    lambda d: d.strftime("%m-%d-%Y"),
    lambda d: d.strftime("%d.%m.%Y"),
    lambda d: d.strftime("%B %-d, %Y") if hasattr(d, "strftime") else str(d),
    lambda d: d.strftime("%d/%m/%y"),
]
CURRENCY_SYMBOLS = ["$", "€", "£"]


def make_valid_rows(rng, n_rows, start_row_id=1):
    rows = []
    base_date = date(2024, 1, 1)
    for i in range(n_rows):
        row_id = start_row_id + i
        sku, name = rng.choice(PRODUCTS)
        order_date = base_date + timedelta(days=rng.randint(0, 500))
        rows.append({
            "row_id": str(row_id),
            "order_id": f"ORD-{10000 + row_id}",
            "sku": sku,
            "product_name": name,
            "quantity": str(rng.randint(*QUANTITY_RANGE)),
            "unit_price": f"{rng.uniform(*UNIT_PRICE_RANGE):.2f}",
            "order_date": order_date.strftime("%Y-%m-%d"),
            "warehouse": rng.choice(WAREHOUSES),
        })
    return rows


def inject_missing(rng, rows, count, style, anomalies, used_rows):
    tokens = SENTINEL_TOKENS if style == "sentinel" else [""]
    fields = ["sku", "quantity", "unit_price"]
    candidates = [r for r in rows if r["row_id"] not in used_rows]
    rng.shuffle(candidates)
    for row in candidates[:count]:
        field = rng.choice(fields)
        token = rng.choice(tokens)
        row[field] = token
        used_rows.add(row["row_id"])
        anomalies.append({
            "type": "missing_value", "row_id": row["row_id"], "field": field,
            "detail": f"value={token!r} (style={style})",
        })


def inject_duplicate(rng, rows, count, anomalies):
    for _ in range(count):
        source = rng.choice(rows)
        new_id = str(max(int(r["row_id"]) for r in rows) + 1)
        dup = dict(source)
        dup["row_id"] = new_id
        rows.append(dup)
        anomalies.append({
            "type": "duplicate_row", "row_id": new_id, "field": None,
            "detail": f"exact duplicate of row_id={source['row_id']}",
        })


def inject_out_of_range(rng, rows, count, anomalies, used_rows, allow_zero):
    candidates = [r for r in rows if r["row_id"] not in used_rows]
    rng.shuffle(candidates)
    modes = ["negative", "huge"]
    if allow_zero:
        modes.append("zero")
    for row in candidates[:count]:
        field = rng.choice(["quantity", "unit_price"])
        mode = rng.choice(modes)
        if mode == "negative":
            value = "-5" if field == "quantity" else "-12.50"
        elif mode == "huge":
            value = "99999" if field == "quantity" else "999999.99"
        else:
            value = "0" if field == "quantity" else "0.00"
        row[field] = value
        used_rows.add(row["row_id"])
        anomalies.append({
            "type": "out_of_range", "row_id": row["row_id"], "field": field,
            "detail": f"{field}={value} (mode={mode})",
        })


def inject_malformed_date(rng, rows, count, anomalies, used_rows):
    candidates = [r for r in rows if r["row_id"] not in used_rows]
    rng.shuffle(candidates)
    for row in candidates[:count]:
        d = date(2024, rng.randint(1, 12), rng.randint(1, 28))
        template = rng.choice(MALFORMED_DATE_TEMPLATES)
        value = template(d)
        row["order_date"] = value
        used_rows.add(row["row_id"])
        anomalies.append({
            "type": "malformed_date", "row_id": row["row_id"], "field": "order_date",
            "detail": f"order_date={value!r}",
        })


def inject_shifted_column(rng, rows, count, anomalies, used_rows):
    candidates = [r for r in rows if r["row_id"] not in used_rows]
    rng.shuffle(candidates)
    for row in candidates[:count]:
        # simulate a vendor export bug: quantity and unit_price swap places
        row["quantity"], row["unit_price"] = row["unit_price"], row["quantity"]
        used_rows.add(row["row_id"])
        anomalies.append({
            "type": "shifted_column", "row_id": row["row_id"], "field": "quantity",
            "detail": "quantity/unit_price values swapped",
        })


def inject_currency_symbol(rng, rows, count, anomalies, used_rows):
    """Novel anomaly type (used for the optional regression-guard demo)."""
    candidates = [r for r in rows if r["row_id"] not in used_rows]
    rng.shuffle(candidates)
    for row in candidates[:count]:
        symbol = rng.choice(CURRENCY_SYMBOLS)
        row["unit_price"] = f"{symbol}{row['unit_price']}"
        used_rows.add(row["row_id"])
        anomalies.append({
            "type": "currency_symbol", "row_id": row["row_id"], "field": "unit_price",
            "detail": f"unit_price={row['unit_price']!r}",
        })


def generate(seed, n_rows, missing, duplicate, out_of_range, malformed_date,
             shifted_column, missing_style, allow_zero, currency_symbol):
    rng = random.Random(seed)
    rows = make_valid_rows(rng, n_rows)
    rng.shuffle(rows)  # shuffle BEFORE duplicates are appended, so a
    # duplicate's row always lands after its source in the final file --
    # otherwise "second occurrence = the anomaly" wouldn't hold.
    anomalies = []
    used_rows = set()

    inject_missing(rng, rows, missing, missing_style, anomalies, used_rows)
    inject_out_of_range(rng, rows, out_of_range, anomalies, used_rows, allow_zero)
    inject_malformed_date(rng, rows, malformed_date, anomalies, used_rows)
    inject_shifted_column(rng, rows, shifted_column, anomalies, used_rows)
    inject_currency_symbol(rng, rows, currency_symbol, anomalies, used_rows)
    # duplicates are appended last, after the shuffle, so they always
    # appear after their source row in the written file.
    inject_duplicate(rng, rows, duplicate, anomalies)

    return rows, anomalies


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_meta(path, source_csv, anomalies, seed):
    meta = {
        "file": Path(source_csv).name,
        "seed": seed,
        "columns": COLUMNS,
        "anomalies": sorted(anomalies, key=lambda a: (a["type"], a["row_id"])),
    }
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--rows", type=int, default=40)
    p.add_argument("--missing", type=int, default=2)
    p.add_argument("--duplicate", type=int, default=1)
    p.add_argument("--out-of-range", type=int, default=2)
    p.add_argument("--malformed-date", type=int, default=2)
    p.add_argument("--shifted-column", type=int, default=1)
    p.add_argument("--missing-style", choices=["empty", "sentinel"], default="empty")
    p.add_argument("--zero-price", action="store_true")
    p.add_argument("--currency-symbol", type=int, default=0)
    args = p.parse_args()

    rows, anomalies = generate(
        seed=args.seed, n_rows=args.rows, missing=args.missing,
        duplicate=args.duplicate, out_of_range=args.out_of_range,
        malformed_date=args.malformed_date, shifted_column=args.shifted_column,
        missing_style=args.missing_style, allow_zero=args.zero_price,
        currency_symbol=args.currency_symbol,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(out_path, rows)
    meta_path = out_path.with_suffix(".meta.json")
    write_meta(meta_path, out_path, anomalies, args.seed)
    print(f"wrote {out_path} ({len(rows)} rows, {len(anomalies)} injected anomalies)")
    print(f"wrote {meta_path}")


if __name__ == "__main__":
    main()
