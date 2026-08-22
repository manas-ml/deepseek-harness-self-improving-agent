"""Shared schema for the "vendor export" task family.

Every generated sample file uses this exact column layout. The generator
injects the same *categories* of data-quality issues into every file, but
the specific rows/values/formats differ each time -- that's what makes this
a task *family* rather than a single fixed puzzle the agent can memorize.
"""

COLUMNS = [
    "row_id",
    "order_id",
    "sku",
    "product_name",
    "quantity",
    "unit_price",
    "order_date",
    "warehouse",
]

PRODUCTS = [
    ("SKU-1001", "Aluminum Bracket 10mm"),
    ("SKU-1002", "Steel Hinge Pair"),
    ("SKU-1003", "Nylon Washer Set"),
    ("SKU-1004", "Brass Fitting 1/2in"),
    ("SKU-1005", "Rubber Gasket Roll"),
    ("SKU-1006", "Copper Wire Spool"),
    ("SKU-1007", "PVC Pipe Coupling"),
    ("SKU-1008", "Stainless Bolt M6"),
]

WAREHOUSES = ["WH-A", "WH-B", "WH-C"]

QUANTITY_RANGE = (1, 200)
UNIT_PRICE_RANGE = (4.5, 850.0)
DATE_FORMAT = "%Y-%m-%d"

# Anomaly categories every sample draws from (specifics vary per file).
ANOMALY_TYPES = [
    "missing_value",
    "duplicate_row",
    "out_of_range",
    "malformed_date",
    "shifted_column",
]
